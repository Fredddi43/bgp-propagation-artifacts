"""Assemble immutable graph outputs with explicitly replaced origin experiments.

The old final tree stays intact. Completeness markers bind exact bytes; independent
raw-source verification remains a separate release gate.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    args = parser.parse_args()
    root = args.run
    old = root / 'graph-final-data'
    revised = root / 'origin-membership-revision/data'
    data = root / 'graph-release-data'
    contract = root / 'graph-final-build/expected-verification.json'
    expected = json.loads(contract.read_text())
    origins = {f'tgn/2024_{tag}/d{delta}s' for tag in ('rpkivalid', 'rpkiinvalid') for delta in (30, 60)}
    replaced = [p for p in expected['model_tables'] if str(Path(p).parents[1]) in origins]
    assert len(replaced) == 30, len(replaced)
    required = []
    for csv in expected['model_tables']:
        required.extend([csv, csv.replace('_test_per_event.csv', '_summary.json'),
                         csv.replace('_test_per_event.csv', '_correction_run.json')])
    required += expected['model_checkpoints']
    required += [v['probability_evidence'] for v in expected['model_targets'].values() if 'probability_evidence' in v]
    while True:
        missing = [p for p in required if not ((revised if str(Path(p).parents[1]) in origins else old) / p).is_file()]
        if not missing:
            break
        print(json.dumps({'waiting_origin_outputs': len(missing)}), flush=True)
        time.sleep(30)
    data.mkdir(exist_ok=False)
    for name in ('graphs', 'rpki', 'eventset', 'events_replay', 'events_replay_leak', 'events_replay_withdrawal'):
        (data / name).symlink_to((old / name).resolve(), target_is_directory=True)
    (data / '_publications').symlink_to((old / '_publications').resolve(), target_is_directory=True)
    cohorts = json.loads((root / 'graph-final-build/manifest.json').read_text())['cohorts']
    for year, tag, delta in cohorts:
        relative = Path('tgn') / f'{year}_{tag}' / f'd{delta}s'
        target = (revised if str(relative) in origins else old) / relative
        (data / relative).parent.mkdir(parents=True, exist_ok=True)
        (data / relative).symlink_to(target.resolve(), target_is_directory=True)
    (data / 'analysis').mkdir()
    auxiliary = root / 'graph-final-build/expected-auxiliary.json'
    files = json.loads(auxiliary.read_text())['auxiliary_files']
    for name in files:
        if name.startswith('analysis/') and not name.endswith(('graph_paired_comparisons.json', 'graph_auxiliary_verification.json')):
            shutil.copy2(old / name, data / name)
    revision = {'reason': 'Canonical origin membership replaces anomalous-path all-hop membership',
                'previous_completion': 'before-origin-revision-graph-final-models-complete.json',
                'replaced_model_tables': replaced,
                'equivalence_proofs_sha256': {p.name: digest(p) for p in (root / 'origin-membership-revision').glob('equivalence-*.json')},
                'data_root': 'graph-release-data'}
    (root / 'origin-membership-revision/composite.json').write_text(json.dumps(revision, indent=2))
    marker = {'data_root': 'graph-release-data', 'model_tables': len(expected['model_tables']),
              'checkpoints': len(expected['model_checkpoints']), 'revision': 'origin-membership-revision/composite.json',
              'revision_sha256': digest(root / 'origin-membership-revision/composite.json'),
              'scope': 'output completeness; numerical verification is separate',
              'sha256': {p: digest(data / p) for p in required}}
    pending = root / 'graph-final-models-complete.pending.json'
    pending.write_text(json.dumps(marker, indent=2)); pending.replace(root / 'graph-final-models-complete.json')
    subprocess.run([sys.executable, str(root / 'code/scripts/compare_graph_models.py'), str(data), str(contract),
                    str(data / 'analysis/graph_paired_comparisons.json')], check=True)
    subprocess.run([sys.executable, str(root / 'code/scripts/verify_graph_auxiliary.py'), str(data), str(auxiliary)], check=True)
    marker = {'data_root': 'graph-release-data', 'files': len(files), 'sha256': {p: digest(data / p) for p in files}}
    pending = root / 'graph-final-auxiliary-complete.pending.json'
    pending.write_text(json.dumps(marker, indent=2)); pending.replace(root / 'graph-final-auxiliary-complete.json')
    print(json.dumps({'origin_revision_complete': True, 'replaced_models': len(replaced)}), flush=True)


if __name__ == '__main__':
    main()
