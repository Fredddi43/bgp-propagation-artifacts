"""Original full400 evaluation parity plus bounded, one-opening persistence."""
import ast
import copy
import hashlib
import json
import types
from datetime import datetime, timezone
from pathlib import Path

import pytest
from bgbench import forecast_custodian_eval as original, forecast_custody as custody

D = Path(__file__).resolve().parent
OLD = D.parent / 'newperiod-single-r2-execution-20261023'


def load(path, name):
    module = types.ModuleType(name); module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module


r = load(D / 'runner.py', 'R2_primary_persistence')
f = load(OLD / 'test_integration.py', 'original_full400_fixture')


def configure(plan, root):
    records = root / 'persistence-records'; records.mkdir()
    plan['primary_output'] = str(plan['primary_output'])  # Production plans are JSON, never Path objects.
    plan.update(records=str(records), primary_scores_output=str(records / 'primary-scores.json'),
                source_closure=f.save(root / 'synthetic-source-closure.json', {'scientific_pins_sha256': r.PINS_SHA}))
    plan['bounds'] = dict(output_file_bytes=256 << 20, access_log_bytes=1 << 20, output_total_bytes=(6 * 256 + 1) << 20)


@pytest.fixture(scope='module')
def paired_execution(tmp_path_factory):
    root = tmp_path_factory.mktemp('original-science-parity'); mp = pytest.MonkeyPatch()
    try:
        class FixedTime(datetime):
            @classmethod
            def now(cls, tz=None):
                value = datetime(2026, 10, 24, 4, 0, tzinfo=timezone.utc)
                return value if tz is not None else value.replace(tzinfo=None)
        mp.setattr(original, 'datetime', FixedTime)
        plan, reader, reads, _ = f.fixture(root, mp)
        configure(plan, root)
        mp.setattr(r, 'BOOTSTRAP', f.r.BOOTSTRAP)
        source_function = original._contrast_families
        before = {p for p in root.rglob('*') if p.is_file()}
        previous = f.r.evaluate(plan, reader, original, custody, f.r.components())
        original_report_bytes = Path(plan['primary_output']).read_bytes()
        original_outputs = {str(p): p.read_bytes() for p in root.rglob('*') if p.is_file() and p not in before}
        assert reader.label_reads == 1
        # Restore ONLY this synthetic world's new output files. The successor
        # starts from the identical pristine fixture, never production data.
        for path in original_outputs:
            Path(path).unlink()
        new_reads = []
        new_reader = r.Reader(list(reader.items.values()), reader.bounds, lambda p, w: new_reads.append((p, w)), plan['labels'])
        observed = []; real_writer = r.persist_primary_scores
        def observe(plan, arms, rows, identities):
            observed.append(json.loads(json.dumps(dict(arms=arms, rows=rows, identities=identities))))
            return real_writer(plan, arms, rows, identities)
        mp.setattr(r, 'persist_primary_scores', observe)
        receipts = []
        successor = r.evaluate(plan, new_reader, original, custody, r.components(), score_receipts=receipts)
        assert original._contrast_families is source_function
        yield dict(plan=plan, previous=previous, successor=successor, reader=new_reader,
                   reads=new_reads, receipt=receipts[0], observed=observed[0],
                   original_report_bytes=original_report_bytes, original_outputs=original_outputs)
    finally:
        mp.undo()


def test_original_complete_report_and_runtime_records_exact(paired_execution):
    p = paired_execution
    assert p['previous'] == p['successor']
    assert Path(p['plan']['primary_output']).read_bytes() == p['original_report_bytes']
    assert all(Path(name).read_bytes() == raw for name, raw in p['original_outputs'].items())
    assert p['reader'].label_reads == 1
    assert sum(path == p['plan']['labels']['path'] and purpose == 'Custodian label table' for path, purpose in p['reads']) == 1


def test_sidecar_is_exact_already_computed_objects_and_all56(paired_execution):
    p = paired_execution; raw = Path(p['receipt']['path']).read_bytes(); side = json.loads(raw)
    assert hashlib.sha256(raw).hexdigest() == p['receipt']['sha256'] and len(raw) == p['receipt']['size_bytes']
    assert len(raw) <= p['receipt']['bound_bytes']
    assert {key: side[key] for key in ('arms', 'rows', 'identities')} == p['observed']
    assert sum(len(ids) for horizons in side['identities'].values() for ids in horizons.values()) == 56
    assert side['identities'] == p['successor']['primary']['arms']
    for name, horizons in side['arms'].items():
        for horizon, seeds in horizons.items():
            assert len(seeds) == len(side['identities'][name][horizon])
            assert all([row['event_id'] for row in seed] == [row['event_id'] for row in side['rows'][horizon]] for seed in seeds)
    assert side['labels'] == p['plan']['labels'] and side['seal'] == p['plan']['seal']
    assert not side['metrics_recomputed'] and side['additional_label_reads'] == 0


def tiny_plan(root, *, bound=4096):
    plan = dict(records=str(root), primary_scores_output=str(root / 'primary-scores.json'), primary_output=str(root / 'primary.json'),
                bounds=dict(output_file_bytes=bound, access_log_bytes=100, output_total_bytes=6 * bound + 100))
    for key in ('seal', 'freeze', 'arm_spec', 'labels', 'source_closure'):
        plan[key] = dict(path=str(root / key), sha256='a' * 64)
    arms = {'model': {30: [[dict(event_id='e', eligible=False, average_precision=None, ranking_status='no_new_members')]]}}
    rows = {30: [dict(event_id='e', incident_id='i', onset='2026-09-03T00:00:00+00:00')]}
    ids = {'model': {'30': ['arm-seed0']}}
    return plan, arms, rows, ids


def test_streamed_byte_cap_partial_preserved_and_no_overwrite(tmp_path):
    plan, arms, rows, ids = tiny_plan(tmp_path, bound=128)
    with pytest.raises(ValueError, match='exceeds admitted file'):
        r.persist_primary_scores(plan, arms, rows, ids)
    path = Path(plan['primary_scores_output']); previous = path.read_bytes()
    assert len(previous) <= 128
    with pytest.raises(FileExistsError):
        r.persist_primary_scores(plan, arms, rows, ids)
    assert path.read_bytes() == previous


@pytest.mark.parametrize('damage', ['old_total', 'outside_path', 'seed_identity', 'event_order'])
def test_reservation_path_and_identity_fail_before_write(tmp_path, damage):
    plan, arms, rows, ids = tiny_plan(tmp_path)
    if damage == 'old_total': plan['bounds']['output_total_bytes'] = 5 * plan['bounds']['output_file_bytes'] + 100
    elif damage == 'outside_path': plan['primary_scores_output'] = str(tmp_path.parent / 'outside.json')
    elif damage == 'seed_identity': ids['model']['30'].append('extra-seed')
    else: rows[30][0]['event_id'] = 'other'
    with pytest.raises(ValueError): r.persist_primary_scores(plan, arms, rows, ids)
    assert not (tmp_path / 'primary-scores.json').exists()


def test_boundary_exception_restores_private_function_without_global_patch(tmp_path, monkeypatch):
    plan, reader, _, _ = f.fixture(tmp_path, monkeypatch); configure(plan, tmp_path)
    monkeypatch.setattr(r, 'BOOTSTRAP', f.r.BOOTSTRAP)
    modules = r.components(); composition = modules['composition']; loader = composition.components; seen = []
    def tracked_components():
        result = loader(); count = result['count']; private = count.private_primary
        def tracked(original_module):
            module = private(original_module); seen.append((module, module._contrast_families)); return module
        count.private_primary = tracked
        return result
    monkeypatch.setattr(composition, 'components', tracked_components)
    source_function = original._contrast_families
    def fail(*a, **k): raise ValueError('Synthetic persistence failure')
    monkeypatch.setattr(r, 'persist_primary_scores', fail)
    with pytest.raises(ValueError, match='Synthetic persistence failure'):
        r.evaluate(plan, reader, original, custody, modules)
    assert reader.label_reads == 1 and original._contrast_families is source_function
    assert seen and seen[0][0]._contrast_families is seen[0][1]
    assert not Path(plan['primary_scores_output']).exists()


def test_numerical_component_bytes_unchanged_and_only_known_runner_deltas():
    for path in (OLD / 'components').rglob('*.py'):
        assert (D / path.relative_to(OLD)).read_bytes() == path.read_bytes()
    assert (D / 'pins.json').read_bytes() == (OLD / 'pins.json').read_bytes()
    tree = lambda p: {x.name: ast.dump(x, include_attributes=False) for x in ast.parse(p.read_text()).body if isinstance(x, (ast.FunctionDef, ast.ClassDef))}
    a, b = tree(OLD / 'runner.py'), tree(D / 'runner.py')
    assert all(b[k] == v for k, v in a.items() if k not in ('runtime', 'evaluate', 'execute'))
    for name in ('client.py', 'bootstrap.py'):
        module = load(D / name, name.replace('.', '_'))
        assert module.RUNNER_SHA == hashlib.sha256((D / 'runner.py').read_bytes()).hexdigest()


@pytest.mark.parametrize('identity', ['/root/deadline_audit', 'deadline_audit', '/root/x/../deadline_audit'])
def test_new_author_is_not_own_reviewer(identity):
    assert not r.independent(identity)
