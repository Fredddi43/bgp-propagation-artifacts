"""One release boundary for new-period supervised construction and every fit family.

Custodian source-integrity/occurrence repair is deliberately outside this module:
that separate source-only workflow may reconstruct labels without disclosing them
as development data or producing model outcomes. It cannot issue this authority.
Legacy retrospective executables are not new-period entry points.
"""
import json
from pathlib import Path

from .forecast_manifest import (
    file_sha,
    seal_manifest,
    validate_construction_manifest,
    validate_development_manifest,
    verify_release,
)

OPERATIONS = frozenset({'supervised_graph_build', 'supervised_input_build', 'core_fit',
                        'temporal_fit', 'chronos_adaptation_fit', 'candidate_refit',
                        'count_fit', 'tsfm_fit', 'gbdt_fit'})


def authorize(manifest_path, *, operation, input_gate, expected_gate_sha256, retrospective_release):
    """Check externally anchored evidence before any supervised input/label read."""
    if operation not in OPERATIONS:
        raise ValueError('Undeclared new-period supervised operation')
    if file_sha(input_gate) != expected_gate_sha256:
        raise ValueError('Externally anchored development operation gate changed')
    gate = json.loads(Path(input_gate).read_text())
    manifest = json.loads(Path(manifest_path).read_text())
    if (manifest.get('manifest_kind') not in ('development', 'development_construction')
            or manifest.get('schema_version') != 2
            or manifest.get('manifest_sha256') != seal_manifest(manifest)['manifest_sha256']):
        raise ValueError('Supervised operation needs a valid development/construction manifest')
    if operation.endswith('_build'):
        validate_construction_manifest(manifest)
    else:
        validate_development_manifest(manifest)
    members = [m for m in gate.get('manifests', []) if m['sha256'] == file_sha(manifest_path)]
    if (gate.get('passed') is not True or len(members) != 1
            or operation not in gate.get('approved_operations', [])
            or gate.get('task_protocol_sha256') != manifest['task_protocol_sha256']
            or gate.get('reference_population_sha256') != manifest['reference_population_sha256']):
        raise ValueError('Gate does not authorize this operation/task/reference population')
    source_raw = Path(gate['source_audit_path']).read_bytes()
    import hashlib
    if hashlib.sha256(source_raw).hexdigest() != gate['source_audit_sha256']:
        raise ValueError('New-period source audit changed')
    source = json.loads(source_raw)
    if source.get('passed') is not True:
        raise ValueError('New-period source audit has not passed')
    if (source.get('history_source_digest') != manifest['history_source_digest']
            or source.get('construction') != manifest['construction']
            or source.get('history_root') != manifest.get('history_root')
            or (manifest.get('history_root') is not None and not operation.endswith('_build')
                and source.get('signature_source_digests') != manifest['signature_source_digests'])):
        raise ValueError('Source audit does not bind construction settings and history')
    boundary_raw = Path(gate['incident_boundary_audit_path']).read_bytes()
    boundary_sha = hashlib.sha256(boundary_raw).hexdigest()
    if (boundary_sha != gate['incident_boundary_audit_sha256']
            or boundary_sha != manifest['incident_boundary_audit_sha256']):
        raise ValueError('Incident boundary audit changed')
    boundary = json.loads(boundary_raw)
    expected_rows = [{key: row[key] for key in ('event_id', 'split', 'onset', 'issue_time', 'incident_id')}
                     for row in manifest['events'] + manifest.get('excluded_inputs', [])]
    if (boundary.get('passed') is not True or boundary.get('windows') != manifest['windows']
            or boundary.get('reference_population_sha256') != manifest['reference_population_sha256']
            or boundary.get('task_protocol_sha256') != manifest['task_protocol_sha256']
            or sorted(boundary['reference_rows'], key=lambda row: row['event_id']) != sorted(expected_rows, key=lambda row: row['event_id'])
            or set(boundary['crossing_incident_ids']) & {row['incident_id'] for row in manifest['events']}):
        raise ValueError('Source-only boundary audit does not certify exact supervised identities')
    release = verify_release(retrospective_release, manifest['retrospective_release_sha256'], gate)
    return {'operation': operation, 'release_sha256': release, 'operation_gate_sha256': expected_gate_sha256,
            'manifest_sha256': file_sha(manifest_path), 'release_guard_sha256': file_sha(__file__),
            'source_audit_sha256': gate['source_audit_sha256'], 'incident_boundary_audit_sha256': boundary_sha}


def run(operation, callback, *, manifest_path, input_gate, expected_gate_sha256,
        retrospective_release, args=(), kwargs=None):
    """Only new-period dispatcher: every registered family uses the same preflight.

    A callback is a separately reviewed implementation, not a bypass token. The
    gate must explicitly list its operation; callers retain the returned receipt.
    """
    receipt = authorize(manifest_path, operation=operation, input_gate=input_gate,
                        expected_gate_sha256=expected_gate_sha256, retrospective_release=retrospective_release)
    result = callback(*args, **(kwargs or {}))
    return result, receipt
