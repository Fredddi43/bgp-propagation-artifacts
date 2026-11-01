"""Purpose-specific forecasting manifests; no fake test partition or outcome I/O."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utc(value):
    result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Manifest clocks require explicit timezones')
    return result.astimezone(timezone.utc)


def seal_manifest(document):
    result = {key: value for key, value in document.items() if key != 'manifest_sha256'}
    return result | {'manifest_sha256': digest(result)}


def _base(document, kind):
    if document.get('schema_version') != 2 or document.get('manifest_kind') != kind:
        raise ValueError('Wrong manifest purpose/version')
    if document.get('manifest_sha256') != seal_manifest(document)['manifest_sha256']:
        raise ValueError('Manifest self-digest mismatch')
    for name in ('task_protocol_sha256', 'reference_population_sha256'):
        if not isinstance(document.get(name), str) or len(document[name]) != 64:
            raise ValueError('Manifest needs a bound task and reference population')
    rows = document['events']
    if any(Path(row['event_id']).name != row['event_id'] or row['event_id'] in ('.', '..') for row in rows):
        raise ValueError('Unsafe event identity')
    withheld = document.get('excluded_inputs', [])
    ids = [row['event_id'] for row in rows + withheld]
    if not rows or len(ids) != len(set(ids)) or any(not isinstance(eid, str) or not eid for eid in ids):
        raise ValueError('Empty or duplicate real event identities')
    if digest(sorted(ids)) != document['reference_population_sha256']:
        raise ValueError('Reference population changed')
    indices = document.get('history_feature_indices')
    if (not isinstance(indices, list) or not indices or any(type(i) is not int or i < 0 for i in indices)
            or len(indices) != len(set(indices)) or not document.get('feature_contract') or not document.get('library_protocol')):
        raise ValueError('Explicit feature/history contracts required')
    if document.get('delta_s') not in (30, 60):
        raise ValueError('Undeclared forecast cutoff')
    return rows


# technical_failure: unbuildable although the issue window parsed completely with observed input (construction
# failure). A flagged technical abstention kept in the reference denominator, never relabelled as no-input
# (opus-newperiod-inputs-v1-review Q3; DECISION-LOG 2026-10-18 new-period inputs).
STATUSES = {'available', 'unavailable_no_input', 'source_failure', 'parser_failure', 'technical_failure'}


def validate_status(row):
    status = row.get('input_status', 'available')
    if status not in STATUSES:
        raise ValueError('Unknown input status')
    if status != 'available' and (not row.get('status_receipt_path') or not row.get('status_receipt_sha256')):
        raise ValueError('Abstention requires a bound issue-window status receipt')
    return status


def validate_development_manifest(document):
    return _validate_supervised(document, 'development', require_graphs=True)


def validate_construction_manifest(document, *, require_release=True):
    """``require_release=False`` only for the unguarded source-only shard build, whose graphs are not yet fitting
    inputs: every other rule holds, and the development manifest sealed from it after R1 must bind the release."""
    return _validate_supervised(document, 'development_construction', require_graphs=False,
                                require_release=require_release)


def _split_root(document, kind, rows):
    """A separate history root (TARGET-CONSISTENCY-POLICY v6) must be declared with its absolute path; a fitting
    manifest also declares the per-year signature-library digest its split-root tensors carry."""
    root = document.get('history_root')
    digests = document.get('signature_source_digests')
    if root is None:
        if digests is not None:
            raise ValueError('Signature digests need a declared history root')
        return
    if not isinstance(root, str) or not root.startswith('/') or os.path.normpath(root) != root:
        raise ValueError('Declared history root must be an absolute normalized path')
    if kind == 'development_construction' and digests is None:
        return
    years = {str(row.get('year', str(row['event_id'])[:4])) for row in rows + document.get('excluded_inputs', [])}
    if (not isinstance(digests, dict) or set(digests) != years
            or any(not isinstance(v, str) or len(v) != 64 or set(v) - set('0123456789abcdef') for v in digests.values())):
        raise ValueError('Split-root manifest needs one signature-library digest per row year')


def _validate_supervised(document, kind, *, require_graphs, require_release=True):
    rows = _base(document, kind)
    if document.get('protected_test') or document.get('locked_test'):
        raise ValueError('Protected manifests cannot be fitted')
    settings = document.get('construction')
    if (not isinstance(settings, dict)
            or set(settings) != {'tag', 'max_nodes', 'history_years', 'topology_lag_months', 'rov_lag_days'}
            or not isinstance(settings['tag'], str) or not settings['tag']
            or type(settings['max_nodes']) is not int or settings['max_nodes'] < 1
            or any(type(settings[k]) is not int or settings[k] < 0 for k in ('topology_lag_months', 'rov_lag_days'))
            or not isinstance(settings['history_years'], list) or not settings['history_years']
            or any(type(year) is not int for year in settings['history_years'])
            or len(set(settings['history_years'])) != len(settings['history_years'])):
        raise ValueError('Explicit construction settings required')
    history_digest = document.get('history_source_digest')
    if not isinstance(history_digest, str) or len(history_digest) != 64 or any(c not in '0123456789abcdef' for c in history_digest):
        raise ValueError('Audited history source digest required')
    windows = document['windows']
    start, boundary, end = map(utc, (windows['train_start'], windows['validation_start'], windows['test_start']))
    if not start < boundary < end:
        raise ValueError('Nonchronological calendar windows')
    incidents, parts = {}, {'train': [], 'validation': []}
    excluded_ids = {row['event_id'] for row in document.get('excluded_inputs', [])}
    for row in rows + document.get('excluded_inputs', []):
        allowed = {'event_id', 'split', 'onset', 'issue_time', 'incident_id', 'label_available_at',
                   'input_status', 'status_receipt_path', 'status_receipt_sha256', 'year', 'family',
                   'actor', 'observation_lag_s', 'source_record_sha256'}
        if require_graphs:
            allowed |= {'graph_path', 'graph_sha256'}
        if set(row) - allowed:
            raise ValueError('Supervised manifest contains non-allow-listed row fields')
        split = row['split']
        if split not in parts:
            raise ValueError('Development permits only train and validation rows')
        onset = utc(row['onset'])
        lower, upper = (start, boundary) if split == 'train' else (boundary, end)
        if not lower <= onset < upper:
            raise ValueError('Row outside its fixed calendar partition')
        incident = row.get('incident_id')
        if not incident or (incident in incidents and incidents[incident] != split):
            raise ValueError('Incident crosses development boundary')
        incidents[incident] = split
        if utc(row['issue_time']) != onset + timedelta(seconds=document['delta_s']):
            raise ValueError('Issue-time mismatch')
        status = validate_status(row)
        if row['event_id'] in excluded_ids:
            if status == 'available':
                raise ValueError('Available rows cannot disappear from fitting/calibration')
            continue
        if status != 'available':
            raise ValueError('Abstentions belong in the retained excluded-input ledger')
        maturity = utc(row['label_available_at'])
        if maturity < onset + timedelta(hours=2) or maturity > upper:
            raise ValueError('Supervised labels not mature at the fixed calendar boundary')
        if utc(row['issue_time']) != onset + timedelta(seconds=document['delta_s']):
            raise ValueError('Issue-time mismatch')
        if require_graphs and (not row.get('graph_path') or not row.get('graph_sha256')):
            raise ValueError('Supervised graph path/hash required')
        parts[split].append((onset, maturity, row['event_id']))
    if any(not values for values in parts.values()):
        raise ValueError('Development needs nonempty train and validation partitions')
    if not document.get('incident_boundary_audit_sha256'):
        raise ValueError('Source-only incident boundary audit required')
    _split_root(document, kind, rows)
    if require_release and not document.get('retrospective_release_sha256'):
        raise ValueError('Retrospective release must precede new-period fitting')
    return parts


PREDICTION_ROW_KEYS = {'event_id', 'split', 'onset', 'issue_time', 'incident_id', 'input_status',
                       'input_kind', 'input_path', 'input_sha256'}
PREDICTION_KEYS = {'schema_version', 'manifest_kind', 'manifest_sha256', 'protocol', 'protected_test',
                   'history_root', 'signature_source_digests',
                   'task_protocol_sha256', 'reference_population_sha256', 'source_manifest_sha256',
                   'parent_master_sha256', 'source_inventory_sha256', 'events', 'delta_s', 'history_feature_indices', 'feature_contract',
                   'library_protocol', 'input_collectors', 'reference_collectors', 'n_edge_types', 'input_profile', 'max_nodes', 'history_visibility'}


def validate_prediction_manifest(document):
    rows = _base(document, 'prediction_inputs')
    if set(document) - PREDICTION_KEYS or not document.get('protected_test'):
        raise ValueError('Prediction manifest contains non-allow-listed/protected fields')
    if document.get('history_visibility') != 'custodian_derived_frozen_inference_only':
        raise ValueError('Evaluation history features require protected automated consumption')
    if document.get('input_profile') not in ('core', 'temporal') or document.get('max_nodes', 0) < 1:
        raise ValueError('Explicit input profile and candidate capacity required')
    for row in rows:
        if set(row) - PREDICTION_ROW_KEYS or row.get('split') != 'test':
            raise ValueError('Prediction rows must contain test identities and inputs only')
        status = row.get('input_status')
        if status not in STATUSES or row.get('input_kind') != ('tensor' if status == 'available' else 'status'):
            raise ValueError('Input status/type mismatch')
        if not row.get('input_path') or not row.get('input_sha256') or not row.get('incident_id'):
            raise ValueError('Prediction rows require bound inputs and incident identity')
        if utc(row['issue_time']) != utc(row['onset']) + timedelta(seconds=document['delta_s']):
            raise ValueError('Prediction issue-time mismatch')
    _split_root(document, 'prediction_inputs', rows)
    return rows


def verify_release(path, expected_sha256, gate):
    """Read an already reviewed release; never synthesize or approve one."""
    if file_sha(path) != expected_sha256 or gate.get('retrospective_release_sha256') != expected_sha256:
        raise ValueError('Retrospective release is not externally anchored')
    receipt = json.loads(Path(path).read_text())
    if not all(receipt.get(key) is True for key in ('passed', 'development_frozen', 'evaluation_release_complete')):
        raise ValueError('Retrospective evaluation release is incomplete')
    if (receipt.get('released_window') != {'start': '2025-09-01T00:00:00+00:00', 'end': '2026-01-01T00:00:00+00:00'}
            or utc(receipt['completed_utc']) > datetime.now(timezone.utc)):
        raise ValueError('Retrospective release window/time is not valid')
    for key in ('evaluation_manifest', 'source_audit', 'retained_arm_ledger', 'prediction_ledger', 'score_artifacts'):
        evidence = receipt[key]
        if file_sha(evidence['path']) != evidence['sha256']:
            raise ValueError('Retrospective release evidence changed: ' + key)
    return file_sha(path)


def validate_custodian_manifest(document):
    rows = _base(document, 'custodian_master')
    if document.get('excluded_inputs') or any(row['split'] != 'test' for row in rows):
        raise ValueError('Custodian master must retain the full evaluation cohort')
    for row in rows:
        validate_status(row)
    _split_root(document, 'custodian_master', rows)
    return rows
