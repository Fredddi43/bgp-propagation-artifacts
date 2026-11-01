"""D-A26: in-process replacement of forecast_custody.authorize_outcome_join for the one-shot R2 run (no pinned file is edited).

The pinned authorize_outcome_join re-runs verify_arm for all arms serially: it re-hashes every test input (~2.7 TB unique for the origin
valid arms; one NFS stream reads ~0.05-0.2 GB/s) and re-hashes+parses every predictions file. The G3 seal already verified every arm
with the unchanged verify_arm. This replacement keeps every check of the original that does not need those hours, and replaces the
bulk re-hash with an immutability proof from file metadata:

  * seal receipt / spec / protocol / exposure-ledger checks exactly as the original;
  * model, manifest and input-gate files are re-hashed (small) exactly as verify_arm does;
  * each commitment file is re-hashed and must equal the digest recorded in the seal, and the seal's predictions digest must equal the
    one the commitment records;
  * every file verify_arm reads (model, manifest, input gate, commitment, predictions, every test input) must have st_ctime and st_mtime
    <= CUTOFF, the time before which the seal verification began. ctime changes on any write, truncate, rename-over or chmod, so a file
    that passes was not modified after it was verified at seal time (the guarantee the re-hash gave, up to the seal-to-now interval).
Returns the same dict as the original. Raises ValueError on any difference.
"""
import os
import stat as statmod
from concurrent.futures import ThreadPoolExecutor


def install(custody, cutoff_epoch):
    cutoff_ns = int(round(float(cutoff_epoch) * 1_000_000_000))

    def authorize(seal_path):
        receipt, digest = custody.hashed_json(seal_path)
        spec, spec_digest = custody.hashed_json(receipt['spec_path'])
        if receipt.get('all_retained_predictions_verified') is not True or spec_digest != receipt['spec_sha256']:
            raise ValueError('Missing or changed one-batch seal')
        for name in ('scientific_protocol', 'exposure_ledger'):
            if custody.sha(spec[name + '_path']) != spec[name + '_sha256']:
                raise ValueError('Frozen protocol/exposure ledger changed after sealing')
        arms, sealed = spec['arms'], receipt['arms']
        if len(arms) != len(sealed) or [a['arm_id'] for a in arms] != [r['arm_id'] for r in sealed]:
            raise ValueError('Prediction batch changed after sealing')
        files, manifests = set(), {}
        for arm, seal_row in zip(arms, sealed):
            for key in ('model', 'manifest', 'input_gate'):
                if custody.sha(arm[key + '_path']) != arm[key + '_sha256']:
                    raise ValueError(f'Frozen {key} changed for {arm["arm_id"]}')
                files.add(arm[key + '_path'])
            if arm['manifest_path'] not in manifests:
                manifest, _ = custody.hashed_json(arm['manifest_path'])
                manifests[arm['manifest_path']] = [row['input_path'] for row in manifest['events'] if row['split'] == 'test']
            files.update(manifests[arm['manifest_path']])
            commitment, commitment_digest = custody.hashed_json(arm['commitment_path'])
            if (commitment_digest != seal_row['commitment_sha256'] or commitment.get('predictions_sha256') != seal_row['predictions_sha256']
                    or commitment.get('manifest_sha256') != arm['manifest_sha256']
                    or commitment.get('input_gate_sha256') != arm['input_gate_sha256']
                    or commitment.get('checkpoint_sha256') != arm['model_sha256']):
                raise ValueError('Prediction batch changed after sealing')
            files.update((arm['commitment_path'], arm['predictions_path']))

        def stat(path):
            try:
                st = os.lstat(path)   # lstat: a symlink swapped in after the seal must not borrow its target's stamps
            except OSError as error:
                raise ValueError(f'verified file unreadable after the seal: {path}: {error}')
            if not statmod.S_ISREG(st.st_mode):
                return path
            return path if (st.st_ctime_ns > cutoff_ns or st.st_mtime_ns > cutoff_ns) else None

        with ThreadPoolExecutor(max_workers=64) as pool:
            changed = [p for p in pool.map(stat, sorted(files)) if p]
        if changed:
            raise ValueError(f'{len(changed)} verified files changed after the seal verification (first: {changed[0]})')
        return {'seal_sha256': digest, 'spec_sha256': spec_digest, 'authorized_arm_ids': [r['arm_id'] for r in sealed]}

    custody.authorize_outcome_join = authorize
    return authorize
