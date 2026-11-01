"""Custodian-only exports and automated label-free loading; no summary of features."""
import io
import hashlib
import json
import math
from pathlib import Path

import torch

from .forecast_manifest import (file_sha, seal_manifest, utc, validate_prediction_manifest,
                                validate_custodian_manifest)
from .forecast_train import INPUT_KEYS, require_input_cutoff_rule

PROVENANCE_KEYS = {'history_provenance', 'forecast_contract', 'feature_contract', 'library_protocol'}


NESTED_KEYS = {
    'history_provenance': {'version', 'family', 'collectors', 'target_horizon_seconds',
        'signature_collectors', 'target_collectors', 'history_service', 'event_universe',
        'source_digest', 'issue_time', 'availability_cutoff', 'library_events',
        'library_event_ids_sha256', 'excluded_event_id', 'history_root', 'signature_source_digest'},
    'forecast_contract': {'history_mode', 'history_version', 'history_source_digest', 'history_frozen_at',
        'cohort_mode', 'manifest_sha256', 'delta_s', 'tag', 'max_nodes', 'topology_lag_months',
        'rov_lag_days', 'input_collectors', 'reference_collectors', 'history_target_scope', 'early_filter_inputs',
        'input_cutoff_rule', 'history_root', 'signature_source_digest'},
    'feature_contract': {'name', 'version', 'width', 'feature_names', 'history_feature_indices',
        'topology_lag_months', 'rov_lag_days', 'input_collectors', 'reference_collectors'},
    'library_protocol': {'mode', 'version', 'family', 'collectors', 'target_horizon_seconds',
        'signature_collectors', 'target_collectors', 'history_service', 'event_universe', 'availability_delay_s'},
}


def validate_nested(name, value):
    if not isinstance(value, dict) or set(value) - NESTED_KEYS[name]:
        raise ValueError('Non-allow-listed nested contract fields: ' + name)
    scalar = (str, int, float, bool, type(None))
    for item in value.values():
        if not isinstance(item, scalar) and not (isinstance(item, list) and all(isinstance(v, scalar) for v in item)):
            raise ValueError('Nested contract values must be scalar or flat scalar lists: ' + name)
    # JSON forbids nonfinite values and custom objects even inside allowed fields.
    json.dumps(value, allow_nan=False)


def panel(value):
    # Legacy pooled metadata is None; new manifests use the explicit word.
    if value is None or value == 'pooled':
        return 'pooled'
    if (not isinstance(value, list) or not value or any(not isinstance(v, str) or not v for v in value)
            or len(set(value)) != len(value)):
        raise ValueError('Invalid collector panel')
    return sorted(value)


def source_inventory(path, expected_sha256, reference_sha256, task_sha256, manifest):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('Audited parse-source inventory changed')
    inventory = json.loads(raw)
    if (inventory.get('passed') is not True or inventory.get('reference_population_sha256') != reference_sha256
            or inventory.get('task_protocol_sha256') != task_sha256):
        raise ValueError('Parse-source inventory does not anchor task/reference population')
    if (panel(inventory.get('input_collectors')) != panel(manifest['input_collectors'])
            or inventory.get('source_manifest_sha256') != manifest['source_manifest_sha256']):
        raise ValueError('Audited input panel or construction identity mismatch')
    expected = [{k: row[k] for k in ('event_id', 'onset', 'issue_time', 'incident_id')}
                for row in manifest['events'] + manifest.get('excluded_inputs', [])]
    actual = inventory['reference_rows']
    if sorted(actual, key=lambda r: r['event_id']) != sorted(expected, key=lambda r: r['event_id']):
        raise ValueError('Audited reference clocks or grouping identity changed')
    entries = inventory['parse_receipts']
    if len({r['event_id'] for r in entries}) != len(entries):
        raise ValueError('Duplicate parse receipt identities')
    return inventory


def allowed_keys(profile):
    if profile not in ('core', 'temporal'):
        raise ValueError('Unknown input profile')
    return set(INPUT_KEYS) | PROVENANCE_KEYS | ({'msgs'} if profile == 'temporal' else set())


def validate_tensor(payload, row, manifest):
    for name in PROVENANCE_KEYS:
        if name not in payload:
            raise ValueError('Missing provenance dictionary: ' + name)
        validate_nested(name, payload[name])
    if set(payload) - allowed_keys(manifest['input_profile']):
        raise ValueError('Input tensor contains non-allow-listed fields')
    if not isinstance(payload.get('event_id'), str) or payload['event_id'] != row['event_id']:
        raise ValueError('Tensor event identity mismatch')
    width = manifest['feature_contract'].get('width')
    x = payload['x']
    if (type(width) is not int or width < 1 or not isinstance(x, torch.Tensor)
            or x.dtype != torch.float32 or x.ndim != 2 or x.shape[1] != width):
        raise ValueError('Feature tensor must be float32 with contracted width')
    integer_types = (torch.uint8, torch.int8, torch.int16, torch.int32, torch.int64)
    for name in ('asn', 'seed_asns'):
        if not isinstance(payload[name], torch.Tensor) or payload[name].dtype != torch.int64:
            raise ValueError('AS identities must use int64: ' + name)
    for name in ('asn', 'seed_asns', 'edge_index', 'edge_type'):
        if not isinstance(payload[name], torch.Tensor) or payload[name].dtype not in integer_types:
            raise ValueError('Integer tensor required: ' + name)
    if any(payload[name].ndim != 1 for name in ('asn', 'seed_asns', 'edge_type')):
        raise ValueError('Identity and edge-type tensors must be one-dimensional')
    for name, expected in [('n_seed_all', len(payload['seed_asns'])), ('observation_cutoff_s', manifest['delta_s'])] + ([('delta_s', manifest['delta_s'])] if 'delta_s' in payload else []):
        value = payload.get(name)
        if type(value) not in (int, float) or not math.isfinite(value) or value != expected:
            raise ValueError('Invalid scalar input: ' + name)
    n = len(x)
    mask = payload['persistence_pred']
    if (not isinstance(mask, torch.Tensor) or mask.ndim != 1 or len(mask) != n
            or not torch.isfinite(mask).all() or not ((mask == 0) | (mask == 1)).all()):
        raise ValueError('Invalid persistence mask')
    if not 0 < n <= manifest['max_nodes'] or not torch.isfinite(payload['x']).all():
        raise ValueError('Invalid node capacity/features')
    asns = torch.as_tensor(payload['asn'])
    seeds = torch.as_tensor(payload['seed_asns'])
    if (len(asns) != n or len(set(asns.tolist())) != n
            or not torch.equal(torch.as_tensor(payload['persistence_pred']).bool(), torch.isin(asns, seeds))):
        raise ValueError('Candidate identities or seed mask mismatch')
    edges = torch.as_tensor(payload['edge_index'])
    types = torch.as_tensor(payload['edge_type'])
    if (edges.ndim != 2 or edges.shape[0] != 2 or edges.shape[1] != len(types)
            or (edges < 0).any() or (edges >= n).any() or (edges != edges.long()).any()
            or (types < 0).any() or (types >= manifest['n_edge_types']).any()):
        raise ValueError('Invalid candidate topology')
    if float(payload['observation_cutoff_s']) != manifest['delta_s']:
        raise ValueError('Input cutoff mismatch')
    contract, history = payload['forecast_contract'], payload['history_provenance']
    for name in ('input_collectors', 'reference_collectors'):
        if panel(contract.get(name)) != panel(manifest[name]):
            raise ValueError('Tensor collector panel differs from manifest: ' + name)
    if (contract.get('manifest_sha256') != manifest['source_manifest_sha256']
            or contract.get('history_mode') != 'shared_completed'):
        raise ValueError('Graph construction provenance mismatch')
    require_input_cutoff_rule(contract, row['event_id'])
    if (history.get('excluded_event_id') != row['event_id'] or utc(history['issue_time']) != utc(row['issue_time'])
            or utc(history['availability_cutoff']) > utc(row['issue_time'])):
        raise ValueError('History is not causal at this issue time')
    for key in ('feature_contract', 'library_protocol'):
        if payload[key] != manifest[key]:
            raise ValueError('Input scientific contract changed')
    # Split-root keys (opus-newperiod-dev-v1-review C6): absent from both dictionaries under a single-root manifest,
    # otherwise exactly the declared root and the row year's declared signature-library digest. Never free text.
    root = manifest.get('history_root')
    year = str(row.get('year', str(row['event_id'])[:4]))
    expected = ({} if root is None else
                {'history_root': root, 'signature_source_digest': (manifest.get('signature_source_digests') or {}).get(year)})
    for name in ('forecast_contract', 'history_provenance'):
        actual = {key: payload[name][key] for key in ('history_root', 'signature_source_digest') if key in payload[name]}
        if actual != expected:
            raise ValueError('Split-root history fields differ from the declared history root: ' + name)
    if manifest['input_profile'] == 'temporal':
        msgs = payload['msgs']
        if (not isinstance(msgs, torch.Tensor) or msgs.dtype not in (torch.float32, torch.float64) or msgs.ndim != 2 or msgs.shape[1] != 3 or not torch.isfinite(msgs).all()
                or (msgs[:, 0] < 0).any() or (msgs[:, 0] > manifest['delta_s']).any()
                or (msgs[:, 1:] < 0).any() or (msgs[:, 1:] >= n).any()
                or (msgs[:, 1:] != msgs[:, 1:].long()).any()):
            raise ValueError('Temporal export has invalid/future messages')


def validate_status_receipt(receipt, row, inventory):
    evidence_fields = {'event_id', 'scope', 'issue_time', 'complete', 'parse_ok', 'observed_input_count', 'failure_kind', 'input_collectors', 'source_manifest_sha256'}
    allowed = evidence_fields | {'input_status', 'source_receipt_path', 'source_receipt_sha256'}
    if (set(receipt) - allowed or receipt.get('event_id') != row['event_id']
            or receipt.get('input_status') != row['input_status'] or receipt.get('scope') != 'issue_window'
            or utc(receipt['issue_time']) != utc(row['issue_time'])):
        raise ValueError('Invalid issue-window status evidence')
    matches = [entry for entry in inventory['parse_receipts'] if entry['event_id'] == row['event_id']]
    if (len(matches) != 1 or matches[0]['path'] != receipt.get('source_receipt_path')
            or matches[0]['sha256'] != receipt.get('source_receipt_sha256')):
        raise ValueError('Status parse receipt is absent from audited source inventory')
    raw = Path(matches[0]['path']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != matches[0]['sha256']:
        raise ValueError('Audited parse receipt changed')
    parsed = json.loads(raw)
    if set(parsed) - evidence_fields or parsed != {k: receipt[k] for k in evidence_fields if k in receipt}:
        raise ValueError('Status contradicts audited parse evidence')
    if (panel(receipt.get('input_collectors')) != panel(inventory['input_collectors'])
            or receipt.get('source_manifest_sha256') != inventory['source_manifest_sha256']):
        raise ValueError('Parse record panel or construction identity mismatch')
    count = receipt.get('observed_input_count')
    if count is not None and (type(count) is not int or count < 0):
        raise ValueError('Invalid observed input count')
    status = row['input_status']
    if status == 'unavailable_no_input':
        if (receipt.get('complete') is not True or receipt.get('parse_ok') is not True
                or count != 0 or receipt.get('failure_kind') is not None):
            raise ValueError('No-input requires complete successful parsing with zero observations')
    elif status == 'technical_failure':
        if (receipt.get('failure_kind') != 'construction_failure' or receipt.get('complete') is not True
                or receipt.get('parse_ok') is not True or type(count) is not int or count <= 0):
            raise ValueError('Technical failure requires complete successful parsing, observed input and a construction failure')
    elif (status not in ('source_failure', 'parser_failure') or receipt.get('failure_kind') != status
            or (receipt.get('complete') is True and receipt.get('parse_ok') is True)
            or (status == 'source_failure' and receipt.get('complete') is not False)
            or (status == 'parser_failure' and receipt.get('parse_ok') is not False)):
        raise ValueError('Technical status contradicts source/parser failure evidence')


def export_inputs(master_path, out, *, expected_master_sha256, expected_reference_population_sha256,
                  source_inventory_path, expected_source_inventory_sha256, input_profile, max_nodes):
    """Run only in custody after review; no model development or outcome summaries."""
    master_path, out = Path(master_path), Path(out)
    raw_master = master_path.read_bytes()
    if hashlib.sha256(raw_master).hexdigest() != expected_master_sha256:
        raise ValueError('Custodian master changed')
    master = json.loads(raw_master)
    validate_custodian_manifest(master)
    if master['reference_population_sha256'] != expected_reference_population_sha256:
        raise ValueError('Independent reference population mismatch')
    inventory = source_inventory(source_inventory_path, expected_source_inventory_sha256,
                                 expected_reference_population_sha256, master['task_protocol_sha256'], master)
    for name in ('feature_contract', 'library_protocol'):
        validate_nested(name, master[name])
    out.mkdir(parents=True, exist_ok=False)
    names = ('protocol', 'task_protocol_sha256', 'reference_population_sha256', 'source_manifest_sha256',
             'delta_s', 'history_feature_indices', 'feature_contract', 'library_protocol', 'input_collectors', 'reference_collectors', 'n_edge_types')
    exported = {key: master[key] for key in names}
    exported.update({key: master[key] for key in ('history_root', 'signature_source_digests') if key in master})
    exported.update(schema_version=2, manifest_kind='prediction_inputs', protected_test=True,
                    parent_master_sha256=expected_master_sha256, source_inventory_sha256=expected_source_inventory_sha256, input_profile=input_profile, max_nodes=max_nodes,
                    history_visibility='custodian_derived_frozen_inference_only', events=[])
    for original in master['events']:
        row = {key: original[key] for key in ('event_id', 'split', 'onset', 'issue_time', 'incident_id', 'input_status')}
        if row['input_status'] == 'available':
            path = Path(original['graph_path'])
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != original['graph_sha256']:
                raise ValueError('Custodian source tensor changed')
            source = torch.load(io.BytesIO(raw), map_location='cpu', weights_only=False)
            payload = {key: value for key, value in source.items() if key in allowed_keys(input_profile)}
            validate_tensor(payload, row, exported)
            target = out / f'{row["event_id"]}.pt'
            torch.save(payload, target)
            row['input_kind'] = 'tensor'
        else:
            path = Path(original['status_receipt_path'])
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != original['status_receipt_sha256']:
                raise ValueError('Input-status evidence changed')
            status = json.loads(raw)
            validate_status_receipt(status, row, inventory)
            target = out / f'{row["event_id"]}.status.json'
            target.write_text(json.dumps(status, sort_keys=True) + '\n')
            row['input_kind'] = 'status'
        row.update(input_path=str(target.resolve()), input_sha256=file_sha(target))
        exported['events'].append(row)
    exported = seal_manifest(exported)
    validate_prediction_manifest(exported)
    destination = out / 'input_manifest.json'
    destination.write_text(json.dumps(exported, indent=2, allow_nan=False) + '\n')
    return {'input_manifest_path': str(destination), 'input_manifest_sha256': file_sha(destination),
            'history_visibility': exported['history_visibility']}


def load_inputs(manifest_path, *, expected_manifest_sha256, expected_task_protocol_sha256, consumer,
                input_gate, expected_gate_sha256, expected_reference_population_sha256,
                source_inventory_path, expected_source_inventory_sha256):
    if consumer != 'frozen_inference':
        raise ValueError('Custodian-derived evaluation history permits frozen automated inference only')
    manifest_path = Path(manifest_path)
    if file_sha(manifest_path) != expected_manifest_sha256:
        raise ValueError('Frozen input manifest changed')
    manifest = json.loads(manifest_path.read_text())
    rows = validate_prediction_manifest(manifest)
    if (manifest['reference_population_sha256'] != expected_reference_population_sha256
            or manifest.get('source_inventory_sha256') != expected_source_inventory_sha256):
        raise ValueError('Independent reference population or source inventory mismatch')
    inventory = source_inventory(source_inventory_path, expected_source_inventory_sha256,
                                 expected_reference_population_sha256, expected_task_protocol_sha256, manifest)
    for name in ('feature_contract', 'library_protocol'):
        validate_nested(name, manifest[name])
    if manifest['task_protocol_sha256'] != expected_task_protocol_sha256:
        raise ValueError('Frozen task protocol changed')
    if file_sha(input_gate) != expected_gate_sha256:
        raise ValueError('Frozen prediction input gate changed')
    gate = json.loads(Path(input_gate).read_text())
    members = [entry for entry in gate.get('manifests', []) if entry['sha256'] == expected_manifest_sha256]
    expected_inputs = {row['event_id']: row['input_sha256'] for row in rows}
    if (gate.get('passed') is not True or gate.get('task_protocol_sha256') != expected_task_protocol_sha256
            or len(members) != 1 or len(members[0]['inputs']) != len(rows)
            or {row['event_id']: row['sha256'] for row in members[0]['inputs']} != expected_inputs):
        raise ValueError('Prediction input gate does not bind the full reference population')
    inputs, abstentions = [], []
    for row in rows:
        path = Path(row['input_path'])
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != row['input_sha256']:
            raise ValueError('Exported input changed')
        if row['input_kind'] == 'status':
            validate_status_receipt(json.loads(raw), row, inventory)
            # Cause flags remain bound in the manifest; forecast rows use the
            # existing custody prediction allow-list without free-text payloads.
            abstentions.append({'event_id': row['event_id'], 'seed_asns': [],
                                'observation_cutoff_s': manifest['delta_s'], 'predicted_asns': [], 'curve_log_quantiles': [[0., 0., 0.] for _ in range(4)]})
        else:
            payload = torch.load(io.BytesIO(raw), map_location='cpu', weights_only=True)
            validate_tensor(payload, row, manifest)
            inputs.append(payload)
    return inputs, abstentions
