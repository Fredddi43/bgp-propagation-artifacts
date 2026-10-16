import importlib.util
import json
from pathlib import Path

import polars as pl
import pytest

spec = importlib.util.spec_from_file_location('boundary_audit', Path(__file__).resolve().parents[1] / 'scripts/audit_graph_boundary_inputs.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_dependency_closure_requires_crossyear_training_and_transfer_source(tmp_path):
    relative = 'tgn/2025_leak200/d30s/_results/sage_test_per_event.csv'
    summary = tmp_path / relative.replace('_test_per_event.csv', '_summary.json')
    summary.parent.mkdir(parents=True)
    summary.write_text(json.dumps({'years': '2023,2024>2025', 'tag': 'leak200', 'delta_s': 30}))
    models = {'model_tables': [relative], 'model_cohorts': {relative: {'index_tables': ['tgn/2025_leak200/d30s/index.csv']}}}
    auxiliary = {'auxiliary_files': ['tgn/2024_withdrawal/d30s/_results/cross_sage_leak2002024.json']}
    cohorts = [(2023, 'leak200', 30), (2024, 'leak200', 30), (2025, 'leak200', 30), (2024, 'withdrawal', 30)]
    assert len(audit.dependency_closure(tmp_path, cohorts, models, auxiliary)[relative]) == 3
    with pytest.raises(ValueError, match='Unaudited model'):
        audit.dependency_closure(tmp_path, cohorts[1:], models, auxiliary)
    with pytest.raises(ValueError, match='Unaudited auxiliary'):
        audit.dependency_closure(tmp_path, cohorts[:-1], models, auxiliary)


def test_evaluation_projection_includes_clock_and_full_horizon_sets():
    frame = pl.DataFrame({'event_id': ['e'], 't0_obs': ['2024-01-01T00:00:00Z'],
                          'set_d30s': [[1, 2]], 'set_final_2h': [[1, 2, 3]], 'asns_d30s': [None]})
    before = audit.source_evaluation_projection(frame, ['e'])
    assert before == audit.source_evaluation_projection(frame.with_columns(pl.lit(2).alias('asns_d30s')), ['e'])
    assert before != audit.source_evaluation_projection(frame.with_columns(pl.lit('2024-01-01T00:00:01Z').alias('t0_obs')), ['e'])
    assert before != audit.source_evaluation_projection(frame.with_columns(pl.lit([[1, 2, 4]]).alias('set_final_2h')), ['e'])


def test_table_binding_requires_original_audited_bytes(tmp_path):
    import hashlib
    spec = importlib.util.spec_from_file_location('boundary_binding', Path(__file__).resolve().parents[1] / 'scripts/bind_graph_boundary_tables.py')
    binding = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(binding)
    roots = [tmp_path / name for name in ('frozen', 'candidate')]
    relative = 'eventset/2024_leak/events.parquet'
    hashes = {}
    for root in roots:
        path = root / relative
        path.parent.mkdir(parents=True)
        path.write_bytes(b'unchanged source identity')
        hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    report = tmp_path / 'report.json'
    report.write_text(json.dumps({'status': 'passed', 'frozen_root': str(roots[0]), 'candidate_root': str(roots[1]),
        'source_sha256': hashes, 'cohorts': [{'cohort': [2024, 'leak200', 30],
            'source_before_sha256': hashes[str(roots[0] / relative)],
            'source_after_sha256': hashes[str(roots[1] / relative)], 'tensors': {'event': {}}, 'collector_membership': {'event': {}}}]}))
    index = roots[0] / 'tgn/2024_leak200/d30s/index.csv'
    index.parent.mkdir(parents=True)
    pl.DataFrame({'event_id': ['event'], 'split': ['test']}).write_csv(index)
    assert binding.bind(report)[relative]['after']['path'] == str(roots[1] / relative)
    (roots[1] / relative).write_bytes(b'changed since audit')
    with pytest.raises(ValueError, match='not bound'):
        binding.bind(report)


def test_population_binding_rejects_missing_tensor_evidence(tmp_path):
    import hashlib
    spec = importlib.util.spec_from_file_location('boundary_binding', Path(__file__).resolve().parents[1] / 'scripts/bind_graph_boundary_tables.py')
    binding = importlib.util.module_from_spec(spec); spec.loader.exec_module(binding)
    source = tmp_path / 'eventset/2024_leak/events.parquet'; source.parent.mkdir(parents=True)
    source.write_bytes(b'audited source')
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    index = tmp_path / 'tgn/2024_leak200/d30s/index.csv'; index.parent.mkdir(parents=True)
    pl.DataFrame({'event_id': ['event'], 'split': ['test']}).write_csv(index)
    report = tmp_path / 'report.json'
    report.write_text(json.dumps({'status': 'passed', 'frozen_root': str(tmp_path), 'candidate_root': str(tmp_path),
        'source_sha256': {str(source): digest}, 'cohorts': [{'cohort': [2024, 'leak200', 30],
        'source_before_sha256': digest, 'source_after_sha256': digest, 'tensors': {}, 'collector_membership': {}}]}))
    with pytest.raises(ValueError, match='Incomplete tensor evidence'):
        binding.bind(report)
