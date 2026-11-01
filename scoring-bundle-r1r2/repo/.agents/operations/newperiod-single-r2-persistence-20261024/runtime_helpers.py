"""One baseline arm of an externally frozen complete N batch; custody-owned execution.

No launcher, authority issuer, freeze generator, scoring, automatic retry or seal.
Whole exported tensors may remain resident under actual resource admission; graph
projection and mature-history views are processed one query at a time.
"""
import ast
import hashlib
import importlib.abc
import importlib.metadata
import importlib.util
import io
import json
import os
import stat
import sys
import types
import signal
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PINS_SHA = 'c9af56901795d93e3becea3b7d2d595247003682b8a9686d0ff0da2c2509139b'
AUTHORS = {'/root/metadata_check_review', '/metadata_check_review'}


def need(ok, why):
    if not ok:
        raise ValueError(why)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def raw(ref, limit=64 << 20):
    need(isinstance(ref, dict) and set(ref) == {'path', 'sha256'}, 'Exact reference required')
    path = Path(ref['path'])
    need(path.is_absolute() and path.resolve() == path, 'Canonical regular input required')
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
        before = os.fstat(stream.fileno())
        need(stat.S_ISREG(before.st_mode) and before.st_size <= limit, 'Input byte bound exceeded')
        value = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    need(len(value) == before.st_size and before.st_size == after.st_size
         and before.st_mtime_ns == after.st_mtime_ns and digest(value) == ref['sha256'], 'Input bytes changed')
    return value


def document(ref, limit=64 << 20):
    value = json.loads(raw(ref, limit))
    need(isinstance(value, dict), 'Expected document')
    return value


def reference(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': digest(path.read_bytes())}


def exclusive(path, value):
    data = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    with Path(path).open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return {'path': str(path), 'sha256': digest(data)}


def extract(source, name, names, namespace):
    """Compile exact verified function/class/constants, never a cached module."""
    tree = ast.parse(source)
    chosen = []
    for node in tree.body:
        key = node.name if isinstance(node, (ast.FunctionDef, ast.ClassDef)) else None
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            key = node.targets[0].id
        if key in names:
            chosen.append(node)
    need(len(chosen) == len(names), 'Original helper extraction is incomplete')
    exec(compile(ast.Module(body=chosen, type_ignores=[]), name, 'exec'), namespace)
    return namespace


def install_source_imports(repo, closure_ref, pins):
    """A fresh interpreter executes only externally bound bgbench source bytes."""
    need(not any(n == 'bgbench' or n.startswith('bgbench.') for n in sys.modules),
         'Baseline runner requires a fresh interpreter before scientific imports')
    closure = document(closure_ref, 4 << 20)
    need(set(closure) == {'source_root', 'files'} and closure['source_root'] == str(repo)
         and 0 < len(closure['files']) <= 1024, 'Finite exact scientific source closure required')
    captured = {}
    prefix = repo / 'src' / 'bgbench'
    for item in closure['files']:
        p = Path(item['path'])
        need(p.is_relative_to(prefix) and p.suffix == '.py', 'Unscoped scientific source closure')
        rel = p.relative_to(repo / 'src').with_suffix('')
        name = '.'.join(rel.parts[:-1] if rel.name == '__init__' else rel.parts)
        need(name not in captured, 'Duplicate scientific module')
        captured[name] = (str(p), raw(item, 4 << 20), rel.name == '__init__')
    for item in pins.values():
        if item['path'].startswith('src/bgbench/'):
            filename = str(repo / item['path'])
            matches = [source for path, source, _ in captured.values() if path == filename]
            need(len(matches) == 1 and digest(matches[0]) == item['sha256'], 'Pinned scientific closure differs')
    class SourceOnly(importlib.abc.MetaPathFinder, importlib.abc.Loader):
        def find_spec(self, fullname, path=None, target=None):
            if fullname == 'bgbench' or fullname.startswith('bgbench.'):
                need(fullname in captured, 'Scientific import outside approved source closure')
                filename, _, package = captured[fullname]
                return importlib.util.spec_from_file_location(fullname, filename, loader=self,
                    submodule_search_locations=[str(Path(filename).parent)] if package else None)
        def create_module(self, spec):
            return None
        def exec_module(self, module):
            filename, source, _ = captured[module.__name__]
            exec(compile(source, filename, 'exec'), module.__dict__)
    sys.meta_path.insert(0, SourceOnly())


def modules(repo, access_log, closure_ref):
    """Source-only helper reuse; imported scientific modules must match the same pins."""
    repo = Path(repo)
    pins_raw = (HERE / 'pins.json').read_bytes()
    need(digest(pins_raw) == PINS_SHA, 'Source pin document changed')
    pins = json.loads(pins_raw)
    sources = {k: raw({'path': str(repo / v['path']), 'sha256': v['sha256']}, 4 << 20)
               for k, v in pins.items()}
    install_source_imports(repo, closure_ref, pins)
    from bgbench import forecast_custody as custody, forecast_custodian_eval as evaluation
    from bgbench import forecast_history as history, forecast_inputs as inputs
    for key in ('history', 'inputs', 'custody', 'evaluation', 'manifest', 'ranking', 'train', 'precision'):
        module = __import__('bgbench.forecast_' + {'inputs': 'inputs', 'evaluation': 'custodian_eval'}.get(key, key), fromlist=['x'])
        need(Path(module.__file__).resolve() == repo / pins[key]['path'], 'Scientific module came from another source')
    import numpy as np
    import torch
    import copy
    from collections import Counter
    from datetime import timedelta
    log = types.ModuleType('bound_baseline_access')
    exec(compile(sources['access'], str(repo / pins['access']['path']), 'exec'), log.__dict__)
    log.LOG = Path(access_log)
    campaign = types.SimpleNamespace()
    cn = extract(sources['campaign'], 'original_campaign', {'BASELINE_ARMS', 'TOPOLOGY_RULE',
        'expected_graph_history_provenance', 'history_ranking_rows', 'topology_ranking_rows', 'participation_check'}, {})
    campaign.__dict__.update(cn)
    baseline = types.SimpleNamespace()
    tree = ast.parse(sources['baseline'])
    names = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    names |= {'FROZEN_AT', 'PROJECTION_KEYS', 'PREDICTION_KEYS'}
    bn = {'np': np, 'torch': torch, 'copy': copy, 'hashlib': hashlib, 'io': io, 'json': json,
          'Counter': Counter, 'timedelta': timedelta, 'SimpleNamespace': types.SimpleNamespace,
          'forecast_inputs': inputs, 'utc': history.utc, 'campaign': campaign}
    baseline.__dict__.update(extract(sources['baseline'], 'reviewed_baseline', names, bn))
    fn = {'Path': Path, 'os': os, 'stat': stat, 'access': log, 'hashlib': hashlib, 'json': json,
          'math': __import__('math')}
    frozen = types.SimpleNamespace(**extract(sources['frozen'], 'reviewed_frozen_helpers',
        {'need', 'sha_bytes', 'canonical', 'configured_log', 'durable_log', 'numeric',
         'validated_rows', 'ALLOWED_ROW_KEYS'}, fn))
    loader_ns = {'log_read': log.log_read}
    extract(sources['custodian'], 'original_custody_loader', {'require', 'custody_load'}, loader_ns)
    return types.SimpleNamespace(baseline=baseline, frozen=frozen, loader=loader_ns['custody_load'],
        custody=custody, evaluation=evaluation, history=history, inputs=inputs, pins=pins, torch=torch)


def identity(value):
    return (os.path.normpath('/' + value.casefold().lstrip('/'))
            if isinstance(value, str) and value and not any(c.isspace() for c in value) else '')


def authority(plan_ref, approval_ref):
    plan, approval = document(plan_ref), document(approval_ref)
    need(plan.get('kind') == 'newperiod_baseline_custodian_run_v1'
         and approval.get('passed') is True and approval.get('plan') == plan_ref
         and approval.get('runner_sha256') == digest(Path(__file__).read_bytes())
         and all(identity(approval.get(k)) not in AUTHORS | {'', '/', '/.'}
                 for k in ('reviewer_worker', 'reviewer_session'))
         and approval.get('reviewer_model') and approval.get('execution_authorized') is True
         and approval.get('resources') == plan['resources']
         and all(approval.get(k) is False for k in ('retry_authorized', 'fit_authorized',
                  'score_authorized', 'seal_authorized', 'outcome_release_authorized')),
         'Independent exact baseline execution authority required')
    raw(approval['review'], 2 << 20)
    return plan


def runtime(plan):
    """Exact allocation/runtime evidence is supplied by the independently reviewed execution plan."""
    r = plan['resources']
    need(type(r['memory_mib']) is int and r['memory_mib'] > 0
         and type(r['cpus']) is int and r['cpus'] > 0
         and type(r['wall_seconds']) is int and 0 < r['wall_seconds'] <= 86400,
         'Finite actual resources required')
    need(set(plan['bounds']) == {'runtime_file_bytes', 'history_total_bytes', 'history_file_bytes',
        'history_events', 'graph_file_bytes', 'export_total_bytes', 'prediction_bytes', 'projection_bytes'}
        and all(type(n) is int and n > 0 for n in plan['bounds'].values()), 'Finite positive bounds required')
    need(os.environ.get('SLURM_JOB_ID') == str(r['job_id'])
         and os.environ.get('SLURM_JOB_PARTITION') == 'cpu'
         and os.environ.get('SLURM_CPUS_PER_TASK') == str(r['cpus'])
         and os.environ.get('SLURM_MEM_PER_NODE') == str(r['memory_mib'])
         and os.environ.get('SLURM_RESTART_COUNT', '0') == '0', 'Actual non-requeued CPU allocation differs')
    admission = document(plan['resource_readiness'])
    need(admission.get('passed') is True and admission.get('resources') == r
         and admission.get('freeze') == plan['freeze'] and admission.get('arm_id') == plan['arm_id']
         and admission.get('bounds') == plan['bounds'] and admission.get('resident_inputs_and_two_libraries_fit') is True,
         'Actual full-input/library memory admission required')
    rt = document(plan['runtime'])
    need(rt.get('passed') is True and rt['python'] == reference(sys.executable)
         and rt['versions'] == {n: importlib.metadata.version(n) for n in ('numpy', 'polars', 'torch')}
         and rt.get('files'), 'Bound numerical runtime required')
    for item in rt['files']:
        raw(item, plan['bounds']['runtime_file_bytes'])
    for k in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'POLARS_MAX_THREADS'):
        need(os.environ.get(k) == str(r['cpus']), 'Bound thread environment differs')


def batch(plan, m):
    receipt = document(plan['freeze'])
    need(receipt.get('all_retained_outputs_absent_at_freeze') is True and receipt.get('arms')
         and all(isinstance(a.get('role'), dict) for a in receipt['arms']), 'Complete externally frozen batch required')
    m.evaluation.derive_new_period_arms(receipt)
    for name in ('scientific_protocol', 'exposure_ledger'):
        raw({'path': receipt[name + '_path'], 'sha256': receipt[name + '_sha256']})
    arms = [a for a in receipt['arms'] if a['arm_id'] == plan['arm_id']]
    need(len(arms) == 1, 'Arm must occur exactly once in complete freeze')
    arm = arms[0]
    config = document({'path': arm['model_path'], 'sha256': arm['model_sha256']})
    m.baseline.checked_config(config)
    role = arm['role']
    need(role.get('family') == 'baseline' and role.get('panel') == 'reference'
         and role.get('baseline') == config['baseline'] and role.get('candidates') == config['candidates']
         and role.get('horizon_seconds') == config['horizon_seconds']
         and role.get('library') == ('online' if config['frozen_at'] is None else 'frozen_2026_09_01'),
         'Frozen role/configuration differs')
    need(arm.get('baseline_sources') == plan['sources'] and arm.get('custody_inputs') == plan['custody_inputs'],
         'Freeze must anchor source-service and custody inputs before predictions')
    for key in ('predictions_path', 'commitment_path'):
        p = Path(arm[key])
        need(p.is_absolute() and p.resolve() == p and p.parent.is_dir() and not p.exists(), 'Exclusive frozen output required')
    return receipt, arm, config


class SourceReader:
    """Finite receipt-bound logical paths, explicit resolved targets, and durable log-before-open."""
    def __init__(self, files, bounds, log, helpers):
        self.files = {x['path']: x for x in files}
        need(len(self.files) == len(files) and files, 'Nonempty unique source closure required')
        self.bounds, self.log, self.helpers = bounds, log, helpers
        need(sum(x['size_bytes'] for x in files) <= bounds['history_total_bytes'], 'History source closure budget exceeded')
        self.seen = set()

    def read(self, path):
        item = self.files.get(str(path))
        need(item is not None and set(item) == {'path', 'resolved', 'sha256', 'size_bytes'}, 'Unapproved library input')
        need(str(Path(path).resolve()) == item['resolved'], 'Receipt-bound logical source target changed')
        self.helpers.durable_log(self.log, [(path, 'baseline custody library source', 1)])
        data = raw({'path': item['resolved'], 'sha256': item['sha256']}, self.bounds['history_file_bytes'])
        need(len(data) == item['size_bytes'], 'Library source size changed')
        self.seen.add(str(path))
        return data


def library(spec, reader, history, *, role):
    """Original classmethod and scientific arithmetic, with only bound logged byte readers substituted."""
    import polars as pl
    need(set(spec) == {'root', 'years', 'family', 'collectors', 'availability_delay_s', 'digest', 'files'},
         'Exact causal library declaration required')
    need(spec['family'] == 'leak' and spec['availability_delay_s'] == 0
         and spec['collectors'] is None
         and spec['years'] == ([2023, 2024, 2025, 2026] if role == 'history' else [2026]),
         'Primary pooled library contract required')
    class BoundPath(type(Path())):
        def read_bytes(self):
            return reader.read(str(self))
    proxy = types.SimpleNamespace(**{k: getattr(pl, k) for k in dir(pl) if not k.startswith('__')})
    proxy.read_parquet = lambda p, *a, **kw: pl.read_parquet(io.BytesIO(reader.read(str(p))), *a, **kw)
    original = history.CompletedEventLibrary.from_eventsets.__func__
    function = types.FunctionType(original.__code__, dict(original.__globals__, pl=proxy),
                                  original.__name__, original.__defaults__, original.__closure__)
    function.__kwdefaults__ = original.__kwdefaults__
    result = function(history.CompletedEventLibrary, BoundPath(spec['root']), spec['years'], spec['family'],
                      collectors=spec['collectors'], availability_delay_s=spec['availability_delay_s'])
    need(result.digest == spec['digest'] and reader.seen == set(reader.files), 'Exact original library source/digest differs')
    need(len(result.events) <= reader.bounds['history_events'], 'History memory admission exceeded')
    return result


def _run(plan_ref, approval_ref, stage, *, validated_plan=None):
    stage[0] = 'authority'
    plan = validated_plan
    if plan is None:
        plan = authority(plan_ref, approval_ref)
        runtime(plan)
    m = modules(plan['source_root'], plan['access_log'], plan['scientific_source_closure'])
    _, arm, config = batch(plan, m)
    log = m.frozen.configured_log(plan['access_log'])
    records = Path(plan['records'])
    need(records.is_absolute() and records.resolve() == records and not records.exists(), 'Fresh attempt records required')
    records.mkdir()
    exclusive(records / 'intent.json', {'plan': plan_ref, 'approval': approval_ref, 'retry_authorized': False})
    (records / 'available-projections').mkdir()
    stage[0] = 'input metadata'
    a = arm['custody_inputs']
    m.frozen.durable_log(log, [(arm['manifest_path'], 'baseline frozen input manifest', 1),
        (arm['input_gate_path'], 'baseline frozen input gate', 1),
        (a['source_inventory']['path'], 'baseline source inventory', 1),
        (plan['sources']['master']['path'], 'baseline custody master graph bindings', 1)])
    manifest = document({'path': arm['manifest_path'], 'sha256': arm['manifest_sha256']})
    master = document(plan['sources']['master'])
    inventory = document(a['source_inventory'])
    m.frozen.durable_log(log, [(x['path'], 'baseline input status parse evidence', 1)
                              for x in inventory['parse_receipts']])
    from bgbench.forecast_manifest import validate_custodian_manifest
    validate_custodian_manifest(master)
    need(manifest['input_profile'] == 'core' and manifest['delta_s'] == config['horizon_seconds']
         and manifest['parent_master_sha256'] == plan['sources']['master']['sha256'], 'Actual original-core export/master required')
    by_id = {r['event_id']: r for r in master['events']}
    need(len(by_id) == len(master['events']) and set(by_id) == set(arm['event_ids']), 'Master reference population differs')
    for row in manifest['events']:
        need(all(row[k] == by_id[row['event_id']][k] for k in ('event_id', 'onset', 'issue_time', 'incident_id', 'input_status')),
             'Master/export clocks or statuses differ')
    need(all(Path(r['input_path']).resolve() == Path(r['input_path']) and Path(r['input_path']).is_file()
             for r in manifest['events']), 'Canonical exported inputs required')
    need(sum(Path(r['input_path']).stat().st_size for r in manifest['events']) <= plan['bounds']['export_total_bytes'],
         'Resident exported input bound exceeded')
    for row in manifest['events']:
        need(Path(row['input_path']).stat().st_size <= plan['bounds']['graph_file_bytes'], 'Export file exceeds admitted bound')
    stage[0] = 'custody inputs'
    m.frozen.durable_log(log, [(r['input_path'], 'baseline validated exported input', 1) for r in manifest['events']])
    payloads, abstentions = m.loader(arm['manifest_path'], purpose='baseline ' + arm['arm_id'], consumer='frozen_inference',
        expected_manifest_sha256=arm['manifest_sha256'], expected_task_protocol_sha256=a['task_protocol_sha256'],
        input_gate=arm['input_gate_path'], expected_gate_sha256=arm['input_gate_sha256'],
        expected_reference_population_sha256=a['reference_population_sha256'], source_inventory_path=a['source_inventory']['path'],
        expected_source_inventory_sha256=a['source_inventory']['sha256'])
    stage[0] = 'custody libraries'
    libraries, specs = {}, {}
    for name in ('history', 'signature'):
        m.frozen.durable_log(log, [(plan['sources'][name]['path'], 'baseline bound ' + name + ' source inventory', 1)])
        spec = specs[name] = document(plan['sources'][name])
        reader = SourceReader(spec['files'], plan['bounds'], log, m.frozen)
        libraries[name] = library(spec, reader, m.history, role=name)
    need(libraries['history'].digest == master['history_source_digest']
         and specs['history']['root'] == manifest['history_root']
         and manifest['signature_source_digests'] == {'2026': libraries['signature'].digest},
         'Manifest causal history/signature source differs')
    stage[0] = 'query inference'
    predictions, evidence = [], []
    projection_bytes = 0
    rows = {r['event_id']: r for r in manifest['events']}
    for payload in sorted(payloads, key=lambda p: (rows[p['event_id']]['issue_time'], p['event_id'])):
        row = rows[payload['event_id']]
        original = by_id[row['event_id']]
        graph_ref = {'path': original['graph_path'], 'sha256': original['graph_sha256']}
        m.frozen.durable_log(log, [(graph_ref['path'], 'baseline query signature custody projection', 1),
                                  (row['input_path'], 'baseline exact exported projection comparison', 1)])
        projection = m.baseline.project_signature(raw(graph_ref, plan['bounds']['graph_file_bytes']),
            raw({'path': row['input_path'], 'sha256': row['input_sha256']}, plan['bounds']['graph_file_bytes']),
            row, manifest, graph_sha256=graph_ref['sha256'], signature_event=libraries['signature'].by_id[row['event_id']],
            signature_source_digest=libraries['signature'].digest)
        # This is an available-only input projection, not a complete issue-time slice table.
        encoded_projection = (json.dumps(projection['projection'], sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
        projection_bytes += len(encoded_projection)
        need(projection_bytes <= plan['bounds']['projection_bytes'], 'Available projection byte bound exceeded')
        projected_ref = exclusive(records / 'available-projections' / (row['event_id'] + '.json'), projection['projection'])
        online = m.baseline.mature_view(libraries['history'], row)
        frozen = (m.baseline.mature_view(libraries['history'], row, frozen_at=config['frozen_at'])
                  if config['frozen_at'] is not None else None)
        prediction, _, check = m.baseline.inference_event(payload, projection, row, manifest, config,
                                                       online_view=online, frozen_view=frozen)
        predictions.append(prediction)
        evidence.append({'event_id': row['event_id'], 'projection_sha256': digest(json.dumps(projection, sort_keys=True).encode()),
                         'available_input_projection': projected_ref,
                         'input_sha256': row['input_sha256'], 'graph_sha256': graph_ref['sha256'],
                         'history_event_ids_sha256': online['provenance']['library_event_ids_sha256'],
                         'participation_mismatches': check['mismatched_events']})
        del online, frozen, projection
    predictions = m.baseline.assemble_rows(manifest, predictions, abstentions)
    encoded = m.frozen.validated_rows(predictions, arm)
    need(len(encoded) <= plan['bounds']['prediction_bytes'], 'Prediction output bound exceeded')
    stage[0] = 'commit'
    need(projection_bytes + len(json.dumps(evidence, sort_keys=True, indent=2).encode()) + 1
         <= plan['bounds']['projection_bytes'], 'Projection and evidence byte bound exceeded')
    projection_ref = exclusive(records / 'projection-evidence.json', evidence)
    with Path(arm['predictions_path']).open('xb') as stream:
        stream.write(encoded); stream.flush(); os.fsync(stream.fileno())
    exclusive(arm['commitment_path'], {'kind': 'newperiod_baseline_commitment_v1', 'arm_id': arm['arm_id'],
        'freeze_sha256': plan['freeze']['sha256'], 'manifest_sha256': arm['manifest_sha256'],
        'input_gate_sha256': arm['input_gate_sha256'], 'checkpoint_sha256': arm['model_sha256'],
        'predictions_sha256': digest(encoded), 'label_free_input_files': True,
        'predictor_received_source_graphs': False, 'predictor_received_full_history_library': False,
        'custodian_query_projection': projection_ref, 'sources': plan['sources'], 'plan': plan_ref,
        'approval': approval_ref, 'runner_sha256': digest(Path(__file__).read_bytes())})
    stage[0] = 'verification'
    m.frozen.durable_log(log, [(arm['manifest_path'], 'baseline original verify_arm recheck', len(rows) + 1)])
    result = m.custody.verify_arm(arm)
    exclusive(records / 'complete.json', result)
    return result


class BaselineRunFailure(ValueError):
    pass


def run(plan_ref, approval_ref):
    stage = ['start']
    old_handler = signal.getsignal(signal.SIGALRM)
    try:
        plan = authority(plan_ref, approval_ref)
        runtime(plan)
        def timeout(signum, frame):
            raise TimeoutError('Baseline wall bound reached')
        signal.signal(signal.SIGALRM, timeout)
        signal.alarm(plan['resources']['wall_seconds'])
        return _run(plan_ref, approval_ref, stage, validated_plan=plan)
    except BaseException:
        pass
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)
    raise BaselineRunFailure('Baseline custody run refused at ' + stage[0])
