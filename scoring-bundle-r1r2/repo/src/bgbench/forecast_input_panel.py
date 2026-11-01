"""H3 input-panel restriction: fewer input collectors against a fixed reference target.

Restricting the input panel removes the dropped collectors' messages and memberships
before any derived input is computed. Seeds, node features, the message stream and the
history signature are therefore rebuilt from the remaining collectors by the unchanged
``tgn_data.build_event`` code path (``input_collectors``). Targets, curve labels and
historical participation stay on the fixed reference panel
(``reference_collectors``, ``CompletedEventLibrary`` target panel).

This module adds three things around that path, without changing the default builder:

* a label-free input-status ledger per event and reference collector
  (``observed`` / ``empty`` / ``missing`` / ``not_in_panel``), derived from the staged
  replay sources plus the custodian's event-window coverage receipt;
* an abstention rule: an event whose input panel has no input seeds by issue time gets
  no forecast. It stays in the reference population and is scored as an empty set with
  zero count (``forecast_panel.align_panel_predictions``);
* a separate, label-bearing membership report with reference-new and input-new sets.

A panel equal to the reference panel delegates to the pooled builder call with exactly
the arguments of ``scripts/build_compressed_forecast_graphs.py``, so its tensors and
receipts are byte-identical to the existing build.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

import polars as pl

from .forecast_protocol import admit_available

PANEL_PROTOCOL_VERSION = 1
REFERENCE_PANEL = ('route-views.linx', 'route-views2', 'route-views3', 'rrc00', 'rrc01',
                   'rrc03', 'rrc12', 'rrc15', 'rrc20', 'rrc25')
# docs/forecasting-data-custodian.md; metadata proposal ab2cf633...
H3_PANELS = {
    'ris7': ('rrc00', 'rrc01', 'rrc03', 'rrc12', 'rrc15', 'rrc20', 'rrc25'),
    'mixed7': ('route-views.linx', 'route-views2', 'route-views3', 'rrc00', 'rrc03', 'rrc12', 'rrc25'),
    'reference10': REFERENCE_PANEL,
}
COLLECTOR_STATUSES = ('observed', 'empty', 'missing', 'not_in_panel')
# Event statuses use the forecast_inputs vocabulary; only 'available' gets a forecast.
EVENT_STATUSES = ('available', 'unavailable_no_input', 'source_failure')
# Receipt day evidence that certifies a collector's current input window.
CERTIFYING_DAY_STATUSES = frozenset({'reported_complete_day',
                                     'identified_day_gaps_outside_current_and_predecessor_window'})


def sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def resolve_panel(panel, reference=REFERENCE_PANEL) -> tuple[str, ...]:
    """Named or explicit panel, sorted; must be a nonempty subset of the reference."""
    members = H3_PANELS[panel] if isinstance(panel, str) else panel
    members = tuple(sorted(set(members)))
    reference = tuple(sorted(set(reference)))
    if not members or not reference:
        raise ValueError('Collector panels must not be empty')
    if len(members) != len(H3_PANELS[panel] if isinstance(panel, str) else panel):
        raise ValueError('Duplicate collectors in panel')
    outside = set(members) - set(reference)
    if outside:
        # Extra collectors would silently enlarge the input beyond the truth panel;
        # they belong to a separate frozen secondary arm (PLAN §2C).
        raise ValueError(f'Input panel exceeds the reference panel: {sorted(outside)}')
    return members


def restrict_messages(frame: pl.DataFrame, input_panel) -> pl.DataFrame:
    """Drop every message of a collector outside the panel (no reweighting)."""
    return frame.filter(pl.col('collector').is_in(list(input_panel)))


def _utc(value) -> dt.datetime:
    value = dt.datetime.fromisoformat(value.replace('Z', '+00:00')) if isinstance(value, str) else value
    return value.replace(tzinfo=dt.timezone.utc) if value.tzinfo is None else value.astimezone(dt.timezone.utc)


def coverage_extract(receipt_path, expected_sha256, event_ids, delta_s, panel_name):
    """Compact, hash-bound slice of the custodian event-window coverage receipt.

    Keeps per event: onset, retained part collectors, and for each panel collector the
    current-window day evidence. ``observed_anomaly_collectors`` is kept only as a
    diagnostic: the builder recomputes observation from the staged (possibly repaired)
    sources and never trusts the receipt for it.
    """
    raw = Path(receipt_path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('Coverage receipt changed')
    receipt = json.loads(raw)
    panel = resolve_panel(panel_name)
    if panel_name not in receipt['panels'] or tuple(sorted(receipt['panels'][panel_name])) != panel:
        raise ValueError('Coverage receipt panel differs from the fixed panel')
    wanted = set(event_ids)
    events = {}
    for row in receipt['events']:
        if row['event_id'] not in wanted:
            continue
        if row['event_id'] in events:
            raise ValueError(f"Duplicate coverage receipt event: {row['event_id']}")
        window = row['current_windows'][str(delta_s)][panel_name]
        events[row['event_id']] = {
            'observed_onset': row['observed_onset'],
            'retained_part_collectors': sorted(row['retained_part_collectors']),
            'missing_retained_part_collectors': sorted(window['missing_retained_part_collectors']),
            'receipt_observed_collectors': sorted(window['observed_anomaly_collectors']),
            'day_evidence': {c: sorted({e['status'] for e in window['current_window_ingestion_evidence'].get(c, [])})
                             for c in panel},
            'evidence_class_v2': window['evidence_class_v2'],
        }
    absent = wanted - set(events)
    if absent:
        raise ValueError(f'Coverage receipt lacks events: {sorted(absent)[:5]}')
    return {'kind': 'h3_panel_coverage_extract', 'version': PANEL_PROTOCOL_VERSION,
            'receipt_path': str(Path(receipt_path).resolve()), 'receipt_sha256': expected_sha256,
            'panel_name': panel_name, 'panel': list(panel), 'delta_s': delta_s,
            'certifying_day_statuses': sorted(CERTIFYING_DAY_STATUSES),
            'events': dict(sorted(events.items()))}


def load_coverage(path, expected_sha256, *, panel, delta_s):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('Coverage extract changed')
    coverage = json.loads(raw)
    if (coverage.get('kind') != 'h3_panel_coverage_extract' or coverage.get('delta_s') != delta_s
            or tuple(coverage.get('panel', ())) != tuple(panel)):
        raise ValueError('Coverage extract does not match panel/horizon')
    return coverage


def event_input_status(replay_dir, delta_s, input_panel, reference_panel, coverage_event=None,
                       *, require_coverage=True):
    """Label-free input status at issue time for one event.

    Per reference collector: ``not_in_panel`` if dropped; ``observed`` if it delivered
    an anomalous message available by issue time (``forecast_protocol.available_at``:
    whole-second sources at ts + 1 s); otherwise ``missing`` when its part is
    absent or its current-window source evidence is unresolved, else ``empty``.
    """
    replay_dir = Path(replay_dir)
    input_panel, reference_panel = tuple(sorted(input_panel)), tuple(sorted(reference_panel))
    summary = json.loads((replay_dir / 'summary.json').read_text())
    if summary.get('error') or not summary.get('first_observation'):
        raise ValueError(f'Reference event has no valid onset: {replay_dir.name}')
    onset = _utc(summary['first_observation'])
    issue = onset + dt.timedelta(seconds=delta_s)
    if coverage_event is None and require_coverage:
        raise ValueError(f'No coverage evidence for {replay_dir.name}')
    if coverage_event is not None and _utc(coverage_event['observed_onset']) != onset:
        # The receipt window is anchored at its own onset; a shifted onset is not covered.
        raise ValueError(f'Coverage receipt onset differs from staged onset: {replay_dir.name}')
    anomalous = pl.read_parquet(replay_dir / 'anomalous.parquet', columns=['ts', 'collector'])
    unexpected = set(anomalous['collector'].unique().to_list()) - set(reference_panel)
    if unexpected:
        raise ValueError(f'Messages from collectors outside the reference panel: {sorted(unexpected)}')
    by_issue = admit_available(anomalous.filter(pl.col('ts') <= pl.lit(issue)), issue)
    counts = dict(by_issue.group_by('collector').len().iter_rows())
    # Staged summaries record a part count (older ones a list). A count below the
    # reference size cannot say which collector lacks a part, so no unobserved
    # collector of that event can be certified empty from the staged side.
    parts = summary.get('collectors_with_parts', len(reference_panel))
    with_parts = set(parts) if isinstance(parts, list) else (
        set(reference_panel) if parts >= len(reference_panel) else set())
    part_reason = 'staged_part_absent' if isinstance(parts, list) else 'staged_part_count_incomplete'
    members = pl.read_parquet(replay_dir / 'membership.parquet', columns=['collector', 'asn', 'first_seen'])
    # Seeds: per-collector rows available by issue time, then pooled (labels keep raw first_seen).
    input_seeds = sorted(set(map(int, admit_available(members.filter(pl.col('collector').is_in(list(input_panel))),
                                                      issue, ts_column='first_seen')['asn'])))
    collectors = {}
    for collector in reference_panel:
        row = {'messages_by_issue': int(counts.get(collector, 0))}
        if collector not in input_panel:
            row['status'] = 'not_in_panel'
        elif row['messages_by_issue']:
            row['status'] = 'observed'
        else:
            reasons = []
            if collector not in with_parts:
                reasons.append(part_reason)
            if coverage_event is not None:
                if collector in coverage_event['missing_retained_part_collectors']:
                    reasons.append('missing_retained_part')
                evidence = set(coverage_event['day_evidence'].get(collector, []))
                if not evidence or not evidence <= CERTIFYING_DAY_STATUSES:
                    reasons.append('source_completeness_unresolved')
            row['status'] = 'missing' if reasons else 'empty'
            if reasons:
                row['missing_reasons'] = reasons
        collectors[collector] = row
    panel_states = [collectors[c]['status'] for c in input_panel]
    if input_seeds:
        status = 'available'
    elif 'missing' in panel_states:
        status = 'source_failure'
    else:
        status = 'unavailable_no_input'
    diagnostics = {}
    if coverage_event is not None:
        observed = sorted(c for c in input_panel if collectors[c]['status'] == 'observed')
        if observed != coverage_event['receipt_observed_collectors']:
            # Expected where occurrence repair changed staged messages; recorded, not fatal.
            diagnostics['receipt_observed_collectors'] = coverage_event['receipt_observed_collectors']
    return {'event_id': replay_dir.name, 'onset': onset.isoformat(), 'issue_time': issue.isoformat(),
            'status': status, 'forecast_available': status == 'available',
            'abstention_policy': None if status == 'available' else 'empty_set_zero_count',
            'partial_panel_input': status == 'available' and 'missing' in panel_states,
            'input_seed_asns': input_seeds, 'collectors': collectors,
            'input_collectors': list(input_panel), 'reference_collectors': list(reference_panel),
            **({'coverage_diagnostics': diagnostics} if diagnostics else {})}


def membership_sets(replay_dir, delta_s, input_panel, reference_panel, horizon_s=7200):
    """Label-bearing sets: reference target, reference-new and input-new members."""
    replay_dir = Path(replay_dir)
    onset = _utc(json.loads((replay_dir / 'summary.json').read_text())['first_observation'])
    issue = onset + dt.timedelta(seconds=delta_s)
    members = pl.read_parquet(replay_dir / 'membership.parquet', columns=['collector', 'asn', 'first_seen'])

    def rows(panel):
        return members.filter(pl.col('collector').is_in(list(panel)))

    def seeds(panel):
        # Inputs: per-collector availability before pooling (forecast_protocol.available_at).
        return set(map(int, admit_available(rows(panel), issue, ts_column='first_seen')['asn']))

    # Label: raw first_seen against the target horizon.
    target = set(map(int, rows(reference_panel).filter(
        pl.col('first_seen') <= pl.lit(onset + dt.timedelta(seconds=horizon_s)))['asn']))
    reference_seeds, input_seeds = seeds(reference_panel), seeds(input_panel)
    return {'target': target, 'reference_seeds': reference_seeds, 'input_seeds': input_seeds,
            'reference_new': target - reference_seeds, 'input_new': target - input_seeds,
            # Visible at a dropped collector by issue time: a cross-collector visibility
            # forecast if predicted, not a discovery of unseen propagation.
            'seen_only_outside_input': reference_seeds - input_seeds}


def membership_report_row(event_id, sets):
    return {'event_id': event_id,
            **{f'{k}_count': len(v) for k, v in sets.items()},
            'reference_new_asns': sorted(sets['reference_new']), 'input_new_asns': sorted(sets['input_new']),
            'seen_only_outside_input_asns': sorted(sets['seen_only_outside_input'])}


def _write_new(path, value):
    """Exclusive write; a resumed shard may only find byte-identical content."""
    text = json.dumps(value, indent=2, sort_keys=True)
    path = Path(path)
    if path.exists():
        if path.read_text() != text:
            raise ValueError(f'Existing {path.name} differs; use a fresh output directory')
        return
    with path.open('x') as handle:
        handle.write(text)


def build_panel_split(year, delta_s, *, input_panel, manifest_path, output_dir, history_years,
                      reference_panel=REFERENCE_PANEL, coverage=None, execution_shard=None,
                      tensor_writer=None, tag='leak', topology_lag_months=1, rov_lag_days=1,
                      max_nodes=3000, report_dir=None):
    """Retrospective panel build around the unchanged ``tgn_data.build_split``.

    Writes ``input-status-ledger.json`` (label-free) into ``output_dir`` and
    ``membership-report.json`` (label-bearing) into ``report_dir`` (default
    ``output_dir``). Every input-available event must be built and every abstained one
    must not be; any disagreement fails closed.
    """
    from . import config, tgn_data
    from .replay_day import roots

    reference = resolve_panel(reference_panel, reference_panel)
    panel = resolve_panel(input_panel, reference)
    full = panel == reference
    if coverage is not None and (tuple(coverage['panel']) != panel or coverage['delta_s'] != delta_s):
        raise ValueError('Coverage extract does not match panel/horizon')
    manifest_path, output_dir = Path(manifest_path), Path(output_dir)
    manifest = json.loads(manifest_path.read_text())
    ids = sorted(r['event_id'] for r in manifest['events'] if r.get('year', int(r['event_id'][:4])) == year)
    if execution_shard is not None:
        ids = ids[execution_shard[0]::execution_shard[1]]
    replay_root = roots(tgn_data.replay_tag(tag))[1]
    ledger, report = [], []
    for eid in ids:
        status = event_input_status(replay_root / eid, delta_s, panel, reference,
                                    None if coverage is None else coverage['events'].get(eid),
                                    require_coverage=coverage is not None or not full)
        ledger.append(status)
        report.append(membership_report_row(eid, membership_sets(replay_root / eid, delta_s, panel, reference)))
    if full:
        # Exactly the existing production call (scripts/build_compressed_forecast_graphs.py).
        result = tgn_data.build_split(year, delta_s, tag=tag, history_mode='shared_completed',
            history_years=history_years, cohort_mode='broad', manifest_path=manifest_path,
            output_dir=output_dir, topology_lag_months=topology_lag_months, rov_lag_days=rov_lag_days,
            execution_shard=execution_shard, tensor_writer=tensor_writer, max_nodes=max_nodes)
    else:
        result = tgn_data.build_split(year, delta_s, tag=tag, history_mode='shared_completed',
            history_years=history_years, cohort_mode='broad', manifest_path=manifest_path,
            output_dir=output_dir, topology_lag_months=topology_lag_months, rov_lag_days=rov_lag_days,
            execution_shard=execution_shard, tensor_writer=tensor_writer, max_nodes=max_nodes,
            input_collectors=panel, reference_collectors=reference)
    built = {r['event_id'] for r in json.loads((output_dir / 'cohort_ledger.json').read_text())
             if r['status'] == 'built'}
    available = {r['event_id'] for r in ledger if r['forecast_available']}
    if built != available:
        raise ValueError(f'Built tensors differ from input-available events: '
                         f'{sorted(built ^ available)[:5]}')
    counts = {s: sum(r['status'] == s for r in ledger) for s in EVENT_STATUSES}
    collector_counts = {c: {s: sum(r['collectors'][c]['status'] == s for r in ledger) for s in COLLECTOR_STATUSES}
                        for c in reference}
    header = {'kind': 'h3_input_status_ledger', 'version': PANEL_PROTOCOL_VERSION, 'year': year,
              'delta_s': delta_s, 'input_collectors': list(panel), 'reference_collectors': list(reference),
              'manifest_sha256': sha256(manifest_path), 'execution_shard': list(execution_shard) if execution_shard else None,
              'data_root': str(config.DATA_ROOT.resolve()),
              'coverage_extract_receipt_sha256': None if coverage is None else coverage['receipt_sha256'],
              'abstention_rule': 'No input seeds from the input panel by issue time: no forecast; scored as empty set and zero count; excluded from calibration.',
              'event_status_counts': counts, 'partial_panel_input': sum(r['partial_panel_input'] for r in ledger),
              'collector_status_counts': collector_counts, 'contains_labels': False}
    _write_new(output_dir / 'input-status-ledger.json', header | {'events': ledger})
    report_dir = Path(report_dir) if report_dir is not None else output_dir
    report_dir.mkdir(parents=True, exist_ok=True)
    _write_new(report_dir / 'membership-report.json',
               {k: header[k] for k in ('kind', 'version', 'year', 'delta_s', 'input_collectors',
                                       'reference_collectors', 'manifest_sha256', 'execution_shard')}
               | {'kind': 'h3_membership_report', 'contains_labels': True,
                  'definitions': {'reference_new': 'reference target minus reference-panel members at issue time',
                                  'input_new': 'reference target minus input-panel members at issue time',
                                  'seen_only_outside_input': 'reference-panel members at issue time absent from the input panel'},
                  'events': report})
    return result | {'input_status_counts': counts, 'input_available': len(available),
                     'abstained': len(ledger) - len(available), 'full_reference_delegation': full}
