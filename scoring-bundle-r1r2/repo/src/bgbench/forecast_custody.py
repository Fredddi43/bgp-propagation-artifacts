"""One-batch prediction commitments for a protected forecasting evaluation.

This is an auditable workflow barrier, not an OS access-control boundary. The
custodian owns the outcome files and must keep them outside developer workflows.
No function here reads outcome labels or computes performance.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path


def hashed_json(path):
    raw = Path(path).read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_once(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def freeze(path, *, protocol, arms, scientific_protocol, exposure_ledger):
    """Freeze the complete retention list before any retained prediction exists.

    Each arm names an immutable model/configuration artifact, input manifest,
    input gate, expected event IDs, and future prediction+commitment paths.
    Deterministic baselines use a frozen configuration artifact in model_path.
    This gate cannot itself establish that a period was historically unexposed.
    """
    if not protocol or not arms:
        raise ValueError('A named protocol and nonempty complete retention list are required')
    names, outputs, records = set(), set(), []
    for arm in arms:
        name = arm['arm_id']
        ids = arm['event_ids']
        if not name or name in names or not ids or len(set(ids)) != len(ids):
            raise ValueError('Duplicate/empty arms or event IDs')
        names.add(name)
        record = dict(arm)
        for key in ('predictions_path', 'commitment_path'):
            output = Path(arm[key]).resolve()
            if output.exists() or str(output) in outputs:
                raise ValueError('Retained prediction outputs must be unique and absent at freeze')
            outputs.add(str(output))
            record[key] = str(output)
        for key in ('model_path', 'manifest_path', 'input_gate_path'):
            source = Path(arm[key]).resolve()
            record[key] = str(source)
            record[key.replace('_path', '_sha256')] = sha(source)
        manifest, _ = hashed_json(record['manifest_path'])
        if not (manifest.get('protected_test') or manifest.get('locked_test')):
            raise ValueError('Protected custody requires a protected manifest')
        expected = {r['event_id'] for r in manifest['events'] if r['split'] == 'test'}
        if expected != set(ids):
            raise ValueError('Retention population differs from protected manifest')
        if any(not r.get('input_path') or not r.get('input_sha256')
               for r in manifest['events'] if r['split'] == 'test'):
            raise ValueError('Protected test must have custodian-exported input paths/hashes')
        gate, _ = hashed_json(record['input_gate_path'])
        if gate.get('passed') is not True:
            raise ValueError('Input gate has not passed')
        if not any(r['sha256'] == record['manifest_sha256'] for r in gate.get('manifests', [])):
            raise ValueError('Protected manifest is not bound to its input gate')
        record['event_ids'] = sorted(ids)
        records.append(record)
    receipt = {'protocol': protocol, 'frozen_at': datetime.now(timezone.utc).isoformat(),
               'scientific_protocol_path': str(Path(scientific_protocol).resolve()),
               'scientific_protocol_sha256': sha(scientific_protocol),
               'exposure_ledger_path': str(Path(exposure_ledger).resolve()),
               'exposure_ledger_sha256': sha(exposure_ledger),
               'arms': sorted(records, key=lambda r: r['arm_id']),
               'all_retained_outputs_absent_at_freeze': True,
               'historical_exposure_claim': 'Determined by exposure ledger, not by this software gate'}
    write_once(path, receipt)
    return receipt | {'freeze_sha256': sha(path)}


def verify_arm(arm):
    for key in ('model', 'manifest', 'input_gate'):
        if sha(arm[key + '_path']) != arm[key + '_sha256']:
            raise ValueError(f'Frozen {key} changed for {arm["arm_id"]}')
    manifest, _ = hashed_json(arm['manifest_path'])
    for row in manifest['events']:
        if row['split'] == 'test' and sha(row['input_path']) != row['input_sha256']:
            raise ValueError('Custodian-exported input changed after retention freeze')
    commitment, digest = hashed_json(arm['commitment_path'])
    predictions, prediction_digest = hashed_json(arm['predictions_path'])
    if commitment.get('predictions_sha256') != prediction_digest:
        raise ValueError('Prediction commitment mismatch')
    if commitment.get('manifest_sha256') != arm['manifest_sha256']:
        raise ValueError('Committed manifest differs from frozen arm')
    if commitment.get('input_gate_sha256') != arm['input_gate_sha256']:
        raise ValueError('Committed input gate differs from frozen arm')
    if commitment.get('checkpoint_sha256') != arm['model_sha256']:
        raise ValueError('Committed model differs from frozen arm')
    if commitment.get('label_free_input_files') is not True:
        raise ValueError('Protected predictions require label-free inputs')
    ids = [row['event_id'] for row in predictions]
    if len(set(ids)) != len(ids) or sorted(ids) != arm['event_ids']:
        raise ValueError('Committed prediction population differs or duplicates')
    allowed = {'event_id', 'candidate_asns', 'probabilities', 'seed_asns', 'predicted_asns',
               'curve_log_quantiles', 'threshold', 'observation_cutoff_s', 'forward_seconds',
               # ranking-v1: committed baseline ranking scores and slice/remainder decisions
               'ranking_scores', 'slice_predicted_asns'}
    def numeric(value):
        if isinstance(value, list):
            return all(numeric(item) for item in value)
        return type(value) in (int, float) and math.isfinite(value)
    for row in predictions:
        if set(row) - allowed or not isinstance(row['event_id'], str):
            raise ValueError('Prediction payload has fields outside the explicit forecast schema')
        if not ('predicted_asns' in row or 'curve_log_quantiles' in row):
            raise ValueError('Prediction payload lacks a forecast')
        if any(not numeric(value) for key, value in row.items() if key != 'event_id'):
            raise ValueError('Prediction values must be finite numeric scalars/arrays; no nested objects')
    return {'arm_id': arm['arm_id'], 'commitment_sha256': digest,
            'predictions_sha256': prediction_digest, 'events': len(ids)}


def seal(spec_path, seal_path, *, expected_spec_sha256):
    """Validate every retained arm before allowing any outcome join."""
    spec, spec_digest = hashed_json(spec_path)
    # Anchor supplied from the independently retained review/custodian ledger,
    # not recomputed from a possibly edited spec at the point of sealing.
    if spec_digest != expected_spec_sha256:
        raise ValueError('Retention spec changed from its independently anchored freeze digest')
    for name in ('scientific_protocol', 'exposure_ledger'):
        if sha(spec[name + '_path']) != spec[name + '_sha256']:
            raise ValueError('Frozen protocol/exposure ledger changed; explicit revision required')
    commitments = [verify_arm(arm) for arm in spec['arms']]
    receipt = {'spec_path': str(Path(spec_path).resolve()), 'spec_sha256': spec_digest,
               'sealed_at': datetime.now(timezone.utc).isoformat(), 'arms': commitments,
               'all_retained_predictions_verified': True, 'outcome_files_opened': False}
    write_once(seal_path, receipt)
    return receipt


def authorize_outcome_join(seal_path):
    """Custodian must call this immediately before its first label-file read.

    All prediction/model/input artifacts are rechecked together. There is no
    single-arm escape hatch or flag to ignore an incomplete retained arm.
    """
    receipt, digest = hashed_json(seal_path)
    spec, spec_digest = hashed_json(receipt['spec_path'])
    if receipt.get('all_retained_predictions_verified') is not True or spec_digest != receipt['spec_sha256']:
        raise ValueError('Missing or changed one-batch seal')
    for name in ('scientific_protocol', 'exposure_ledger'):
        if sha(spec[name + '_path']) != spec[name + '_sha256']:
            raise ValueError('Frozen protocol/exposure ledger changed after sealing')
    current = [verify_arm(arm) for arm in spec['arms']]
    if current != receipt['arms']:
        raise ValueError('Prediction batch changed after sealing')
    return {'seal_sha256': digest, 'spec_sha256': spec_digest,
            'authorized_arm_ids': [r['arm_id'] for r in current]}
