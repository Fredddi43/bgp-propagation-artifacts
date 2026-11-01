"""Pure N custody preparation functions. No input-file reader, CLI, seal, or evaluator.

Production callers must own separately authorized protected reads and access logging.
The functions accept already-read bytes with externally retained hash references.
Only write_candidate writes anything, exclusively; it grants no execution authority.
"""
import copy
import hashlib
import importlib.util
import io
import json
import math
import types
from datetime import timedelta
from pathlib import Path, PurePosixPath

import polars as pl

from bgbench import forecast_custodian_eval as evaluation
from bgbench.forecast_custody import write_once
from bgbench.forecast_inputs import panel as normalize_panel
from bgbench.forecast_history import in_issue_time_slice, issue_time_slice_variables
from bgbench.forecast_manifest import utc, validate_custodian_manifest, validate_prediction_manifest

REPO = Path(__file__).resolve().parents[3]
# Reuse the existing canonical membership->target-set acceptance helper, unchanged.
_loader = importlib.util.spec_from_file_location('canonical_membership_targets',
    REPO/'scripts/custodian_multipart_acceptance_2026.py')
_targets = importlib.util.module_from_spec(_loader)
_loader.loader.exec_module(_targets)
COUNT_TARGET_SECONDS = (300, 900, 3600, 7200)
# Private globals preserve the original set helper and its default horizons.
_count_targets = types.FunctionType(_targets.sets_from_membership.__code__,
    dict(_targets.sets_from_membership.__globals__, HORIZONS=COUNT_TARGET_SECONDS),
    _targets.sets_from_membership.__name__, _targets.sets_from_membership.__defaults__,
    _targets.sets_from_membership.__closure__)
CONSTANTS = {'repetitions': 10000, 'alpha': 0.05, 'bootstrap_seed': 1701}


def need(condition, reason):
    if not condition:
        raise ValueError(reason)


def checked_bytes(item):
    """Hash supplied bytes without opening the provenance path."""
    need(isinstance(item, dict) and set(item) == {'ref', 'raw'}, 'Bound bytes required')
    ref, raw = item['ref'], item['raw']
    need(isinstance(ref, dict) and set(ref) == {'path', 'sha256'} and isinstance(raw, bytes), 'Invalid bound bytes')
    p = PurePosixPath(ref['path'])
    need(p.is_absolute() and '..' not in p.parts and str(p) == ref['path'], 'Canonical provenance path required')
    need(hashlib.sha256(raw).hexdigest() == ref['sha256'], 'Source bytes differ from retained hash')
    return raw


def document(item):
    value = json.loads(checked_bytes(item))
    need(isinstance(value, dict), 'JSON object required')
    return value


def reference(item):
    checked_bytes(item)
    return copy.deepcopy(item['ref'])


def reference_rows(manifest, decision, *, custodian):
    rows = (validate_custodian_manifest(manifest) if custodian else validate_prediction_manifest(manifest))
    start, end = evaluation.evaluation_window(decision)
    for row in rows:
        onset = utc(row['onset'])
        need(start <= onset < end and utc(row['issue_time']) == onset+timedelta(seconds=manifest['delta_s']),
             'Reference onset/issue time is outside its bound protocol window')
    return rows


def target_status(row, panel, source_inputs, *, declared_censor=None, coverage_collectors=None):
    """Write-ready target status from existing source-coverage semantics, never input status.

    An existing bound censor/missing-source declaration is retained verbatim. Missing
    evidence without such a declaration refuses; it never creates a zero target.
    """
    onset = utc(row['onset'])
    pooled = panel == 'pooled'
    covered = coverage_collectors if pooled else panel
    need((pooled or isinstance(panel, list)) and isinstance(covered, list) and covered
         and len(covered) == len(set(covered)) and all(isinstance(c, str) and c for c in covered)
         and (pooled or coverage_collectors is None), 'Explicit source coverage obligations required')
    selector = 'pooled' if pooled else list(panel)
    base = {'event_id': row['event_id'], 'onset': onset.isoformat(),
            'target_end_inclusive': (onset+timedelta(hours=2)).isoformat(),
            'reference_collectors': selector}
    if declared_censor is not None:
        declared = document(declared_censor)
        need(declared.get('event_id') == row['event_id'] and declared.get('target_status') == 'censored'
             and declared.get('reference_collectors') == selector
             and utc(declared['onset']) == onset
             and utc(declared['target_end_inclusive']) == onset+timedelta(hours=2)
             and isinstance(declared.get('reason'), str) and declared['reason'].strip(),
             'Declared censor must bind the exact target and reason')
        return copy.deepcopy(declared)
    need({'summary', 'coverage'} <= set(source_inputs),
         'Complete coverage evidence or explicit censor declaration required')
    summary, coverage = document(source_inputs['summary']), document(source_inputs['coverage'])
    need(not summary.get('error') and utc(summary['first_observation']) == onset
         and coverage['event_id'] == row['event_id'] and utc(coverage['onset']) == onset
         and utc(coverage['context_start']) <= onset, 'Coverage source identity differs')
    complete = True
    boundary = False
    for collector in covered:
        c = coverage['collectors'].get(collector)
        need(isinstance(c, dict) and type(c.get('target_window_complete')) is bool
             and type(c.get('boundary_censored')) is bool and isinstance(c.get('gaps'), list)
             and c['target_window_complete'] == (not c['gaps'])
             and not (c['boundary_censored'] and c['target_window_complete']),
             'Missing or contradictory target-coverage evidence')
        complete = complete and c['target_window_complete']
        boundary = boundary or c['boundary_censored']
    if not complete:
        return {**base, 'target_status': 'censored',
                'reason': 'boundary_censored' if boundary else 'incomplete_target_coverage',
                'source_refs': {k: reference(v) for k, v in source_inputs.items()}}
    need(set(source_inputs) == {'summary', 'coverage', 'membership'}, 'Complete target needs canonical membership bytes')
    return {**base, 'target_status': 'scorable', 'source_refs': {k: reference(v) for k, v in source_inputs.items()}}


COLLECTOR_RECIPE_SHA256 = '6d851282e4036a6323a24ef41740207c75b839a72a960604cb1404d593ae0917'


def reference_panel(masters, docs, collector_inventory_input, source_inventories, recipe_input):
    """Coverage obligations are explicit; the pooled scientific selector stays pooled."""
    selector = docs['30']['reference_collectors']
    need(docs['60']['reference_collectors'] == selector, 'Horizon reference selectors differ')
    if isinstance(selector, list):
        need(selector and len(selector) == len(set(selector)) and all(isinstance(c, str) and c for c in selector),
             'Explicit fixed reference collector panel required')
        need(collector_inventory_input is None and source_inventories is None and recipe_input is None,
             'Explicit-panel sources must not carry an unrelated pooled inventory')
        return list(selector), None
    need(selector == 'pooled' and isinstance(source_inventories, dict) and set(source_inventories) == {'30', '60'}
         and collector_inventory_input is not None and recipe_input is not None, 'Bound pooled source inventory required')
    inventory, recipe = document(collector_inventory_input), document(recipe_input)
    need(reference(recipe_input)['sha256'] == COLLECTOR_RECIPE_SHA256, 'Frozen collector recipe differs')
    need(inventory.get('kind') == 'newperiod_protected_source_collectors_v1'
         and inventory.get('selector') == 'pooled' and inventory.get('recipe_arm') == 'N-counts'
         and inventory.get('masters') == {h: reference(v) for h, v in masters.items()}
         and inventory.get('inventories') == {h: reference(v) for h, v in source_inventories.items()}
         and inventory.get('recipe') == reference(recipe_input), 'Protected collector inventory lineage differs')
    panel = recipe['recipes']['N-counts']['target_panel']
    need(isinstance(panel, list) and panel and len(panel) == len(set(panel))
         and all(isinstance(c, str) and c for c in panel) and inventory.get('collectors') == panel,
         'Protected collector universe differs')
    for h, item in source_inventories.items():
        source = document(item)
        expected = [{k: r[k] for k in ('event_id', 'onset', 'issue_time', 'incident_id')}
                    for r in docs[h]['events'] + docs[h].get('excluded_inputs', [])]
        need(source.get('passed') is True and source.get('reference_population_sha256') == docs[h]['reference_population_sha256']
             and source.get('task_protocol_sha256') == docs[h]['task_protocol_sha256']
             and normalize_panel(source.get('input_collectors')) == normalize_panel(docs[h]['input_collectors'])
             and source.get('source_manifest_sha256') == docs[h]['source_manifest_sha256']
             and sorted(source['reference_rows'], key=lambda r: r['event_id']) == sorted(expected, key=lambda r: r['event_id']),
             'Source inventory does not bind the complete reference population')
        entries = source['parse_receipts']
        need(len({r['event_id'] for r in entries}) == len(entries), 'Duplicate parse receipt identities')
    return list(panel), {'selector': 'pooled', 'collector_inventory': reference(collector_inventory_input),
                        'recipe': reference(recipe_input),
                        'source_inventories': {h: reference(v) for h, v in source_inventories.items()}}


def label_table(masters, decision_input, sources, *, collector_inventory_input=None, source_inventories=None,
                recipe_input=None):
    """Produce the consumer label schema from both complete master populations.

    sources[eid] has a bound status JSON with event_id, target_status, reason,
    and source_refs. A declared censored/missing target is preserved without any
    empty target array. Scorable targets require the exact bound master membership
    and summary plus separately bound complete coverage for every reference collector.
    """
    need(set(masters) == {'30', '60'}, 'Both master horizons required')
    decision = document(decision_input)
    docs = {h: document(item) for h, item in masters.items()}
    rows = {h: reference_rows(d, decision, custodian=True) for h, d in docs.items()}
    need(all(docs[h]['delta_s'] == int(h) for h in docs), 'Master horizon mismatch')
    identities = lambda rs: sorted((r['event_id'], r['incident_id'], utc(r['onset'])) for r in rs)
    need(identities(rows['30']) == identities(rows['60']), 'Horizon reference cohorts differ')
    panel, pooled = reference_panel(masters, docs, collector_inventory_input, source_inventories, recipe_input)
    need(set(sources) == {r['event_id'] for r in rows['30']}, 'Source statuses must cover the complete cohort')
    other = {r['event_id']: r for r in rows['60']}
    labels, provenance = {}, {}
    for row in rows['30']:
        eid = row['event_id']
        src = sources[eid]
        status = document(src['status'])
        need(status.get('event_id') == eid and status.get('target_status') in ('scorable', 'censored'),
             'Explicit event target status required')
        onset = utc(row['onset'])
        need(status.get('reference_collectors') == docs['30']['reference_collectors'] and utc(status['onset']) == onset
             and utc(status['target_end_inclusive']) == onset+timedelta(hours=2),
             'Target status must bind the exact onset, target boundary and reference panel')
        provenance[eid] = {'status': reference(src['status'])}
        if status['target_status'] == 'censored':
            need(isinstance(status.get('reason'), str) and status['reason'].strip(), 'Censoring reason required')
            labels[eid] = {'target_status': 'censored', 'reason': status['reason']}
            continue
        need(set(src) == {'status', 'summary', 'coverage', 'membership'}, 'Scorable source set incomplete')
        expected = {k: reference(src[k]) for k in ('summary', 'coverage', 'membership')}
        need(status.get('source_refs') == expected, 'Target status must bind exact source evidence')
        for master_row in (row, other[eid]):
            need(all(master_row['custodian_label_files'][name] == expected[key]
                     for name, key in [('summary.json', 'summary'), ('membership.parquet', 'membership')]),
                 'Master target sources differ')
        summary, coverage = document(src['summary']), document(src['coverage'])
        onset = utc(row['onset'])
        need(not summary.get('error') and utc(summary['first_observation']) == onset,
             'Canonical source onset/error differs')
        need(coverage['event_id'] == eid and utc(coverage['onset']) == onset
             and utc(coverage['context_start']) <= onset, 'Coverage clock/identity differs')
        for collector in panel:
            c = coverage['collectors'].get(collector)
            need(isinstance(c, dict) and c.get('target_window_complete') is True
                 and c.get('boundary_censored') is False and c.get('gaps') == [],
                 'Scorable target lacks complete reference coverage; no zero-fill')
        members = pl.read_parquet(io.BytesIO(checked_bytes(src['membership'])))
        need({'asn', 'collector', 'first_seen'} <= set(members.columns), 'Canonical membership columns missing')
        canonical = []
        for m in members.iter_rows(named=True):
            need(type(m['asn']) is int and 0 <= m['asn'] <= 4294967295
                 and isinstance(m['collector'], str) and m['collector'], 'Invalid canonical member')
            first = utc(m['first_seen'])
            if pooled is not None:
                need(m['collector'] in panel, 'Pooled membership contains a collector without frozen coverage evidence')
            if m['collector'] in panel:
                canonical.append({'asn': m['asn'], 'first_seen': first})
        frame = pl.DataFrame(canonical, schema={'asn': pl.Int64, 'first_seen': pl.Datetime('us', 'UTC')})
        # Inclusive +7200 s and raw first_seen, exactly the pre-existing helper semantics.
        target = _targets.sets_from_membership(frame, onset)[7200]
        count_sets = _count_targets(frame, onset)
        need(count_sets[7200] == target, 'Two-hour target identity differs')
        labels[eid] = {'target_status': 'scorable', 'target_asns': target,
                       'target_counts': {str(h): len(count_sets[h]) for h in COUNT_TARGET_SECONDS}}
        provenance[eid].update(expected)
    return {'kind': 'custodian_label_table', 'horizons': {h: copy.deepcopy(labels) for h in ('30', '60')},
            'provenance': {'masters': {h: reference(x) for h, x in masters.items()},
                           'extension_decision': reference(decision_input), 'events': provenance,
                           **({} if pooled is None else {'reference_scope': pooled})}}


def attach_roles(retention_input, role_plan_input):
    """Attach a separately reviewed explicit role declaration to every retained arm.

    Role identity is never inferred from a filename. This does not freeze custody;
    the complete result still belongs to the existing forecast_custody.freeze route.
    """
    retention, plan = document(retention_input), document(role_plan_input)
    arms = retention['arms']
    ids = [a['arm_id'] for a in arms]
    need(ids and len(ids) == len(set(ids)) and plan.get('kind') == 'newperiod_retained_role_plan_v1'
         and plan.get('retention_sha256') == retention_input['ref']['sha256']
         and set(plan['roles']) == set(ids), 'Role plan must bind every retained arm exactly')
    result = copy.deepcopy(retention)
    for arm in result['arms']:
        role = plan['roles'][arm['arm_id']]
        need(isinstance(role, dict) and isinstance(role.get('family'), str) and role['family']
             and type(role.get('horizon_seconds')) is int and role['horizon_seconds'] in (30, 60), 'Typed role required')
        if 'role' in arm:
            need(arm['role'] == role, 'An existing retained role cannot change')
        evaluation.role_arm(role)
        arm['role'] = copy.deepcopy(role)
        arm['role_plan'] = reference(role_plan_input)
    evaluation.derive_new_period_arms(result)
    return result


def issue_time_table(manifest_input, decision_input, projected_inputs, frozen_rule_input):
    """All rows require explicit input-only projections; missing inputs are never imputed."""
    manifest, decision = document(manifest_input), document(decision_input)
    rows = reference_rows(manifest, decision, custodian=False)
    need(set(projected_inputs) == {r['event_id'] for r in rows}, 'Issue-time table must cover every retained event')
    rules = document(frozen_rule_input)
    rule = rules['horizons'][str(manifest['delta_s'])]
    events = {}
    for row in rows:
        eid = row['event_id']
        projected = document(projected_inputs[eid])
        need(set(projected) == {'event_id', 'input_only', 'input_sha256', 'history_signature', 'seed_asns'}
             and projected['event_id'] == eid and projected['input_only'] is True
             and projected['input_sha256'] == row['input_sha256'], 'Exact input-only projection required')
        signature, seeds = projected['history_signature'], projected['seed_asns']
        need(isinstance(signature, list) and len(signature) == 3
             and all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= math.log1p(4294967296) for v in signature)
             and signature == sorted(signature), 'Finite monotone causal signature required')
        need(isinstance(seeds, list) and all(type(a) is int and 0 <= a <= 4294967295 for a in seeds), 'Valid seed ASNs required')
        variables = issue_time_slice_variables(signature, seeds)
        in_issue_time_slice(rule, variables)
        events[eid] = variables
    return {'kind': 'newperiod_issue_time_table_v1', 'input_only': True,
            'horizon_seconds': manifest['delta_s'], 'events': events,
            'manifest': reference(manifest_input), 'slice_rules': reference(frozen_rule_input),
            'projections': {k: reference(v) for k, v in projected_inputs.items()}}


def arm_spec(custody_input, decision_input, *, slice_rules_input=None, issue_tables=None):
    custody, decision = document(custody_input), document(decision_input)
    evaluation.evaluation_window(decision)
    derived = evaluation.derive_new_period_arms(custody)
    need((slice_rules_input is None) == (issue_tables is None), 'Slice rule and both tables are supplied together')
    if issue_tables is not None:
        need(set(issue_tables) == {'30', '60'}, 'Both issue-time table horizons required')
        document(slice_rules_input)
        by_id = {a['arm_id']: a for a in custody['arms']}
        for h, item in issue_tables.items():
            table = document(item)
            need(table.get('input_only') is True and table.get('horizon_seconds') == int(h)
                 and table.get('slice_rules') == reference(slice_rules_input), 'Issue-time table binding differs')
            used = [by_id[i] for horizons in derived.values() for i in horizons[h]]
            need(all(set(a['event_ids']) == set(table['events']) for a in used),
                 'Slice table must cover each derived arm reference cohort exactly')
    spec = {'kind': 'frozen_evaluation_arm_spec', 'population': 'new_period',
            'seed_pairing': 'training_seed', 'online_history': 'history-knn-mean/matched/online',
            'arms': derived, 'custody_spec_sha256': custody_input['ref']['sha256'],
            'slice_rules_sha256': None if slice_rules_input is None else reference(slice_rules_input)['sha256'],
            'issue_time_tables': None if issue_tables is None else {h: reference(i)['sha256'] for h, i in issue_tables.items()},
            'extension_decision_sha256': reference(decision_input)['sha256'],
            'evaluation_end_exclusive': decision['evaluation_end_exclusive'], **CONSTANTS}
    return evaluation.check_arm_spec(spec, derived, 'new_period')


def write_candidate(output, value):
    """Exclusive caller-chosen local output. A data artifact is not a custody approval."""
    need(isinstance(value, dict), 'JSON document required')
    json.dumps(value, allow_nan=False)
    write_once(output, value)
