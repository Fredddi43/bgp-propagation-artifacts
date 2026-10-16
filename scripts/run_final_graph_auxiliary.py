"""Run final CPU evaluations as their immutable model/input dependencies finish."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

parser = argparse.ArgumentParser()
parser.add_argument('run_root', type=Path)
args = parser.parse_args()
root = args.run_root
data = root / 'graph-final-data'
manifest = root / 'graph-final-build/auxiliary.txt'
rows = manifest.read_text().splitlines()


def task_files(index):
    kind, year, delta = rows[index].split()
    base = Path(f'tgn/{year}_leak200/d{delta}s')
    models = ('sage', 'gat', 'tgn', 'dyrep') if kind == 'per-vp' else ('sage',)
    inputs = [base / '_results' / (model + suffix) for model in models for suffix in
              ('_model.pt', '_summary.json', '_test_per_event.csv', '_test_probs.pt', '_correction_run.json')]
    folders = [base]
    if kind == 'transfer':
        folders.append(Path(f'tgn/{year}_withdrawal/d{delta}s'))
    if kind == 'trigger':
        folders.extend(Path(f'tgn/{year}_leak200@t0={shift}/d{delta}s') for shift in (-30, 60, 300, 900))
    inputs.extend(folder / name for folder in folders for name in ('index.csv', 'correction-impact.json', 'history-correction.json'))
    result = base / '_results'
    if kind == 'robustness':
        outputs = [result / ('sage_robustness' + suffix) for suffix in ('.json', '.csv', '_per_event.csv')]
    elif kind == 'prf1':
        outputs = [result / ('sage_prf1' + suffix) for suffix in ('.json', '_per_event.csv')]
    elif kind == 'per-vp':
        outputs = [result / (model + '_per_vp' + suffix) for model in models for suffix in ('.csv', '_per_event.csv')]
    else:
        targets = folders[1:] if kind == 'transfer' else folders
        outputs = [folder / '_results' / (f'cross_sage_leak200{year}' + suffix)
                   for folder in targets for suffix in ('.json', '_per_event.csv')]
        if kind == 'trigger':
            outputs.append(result / 'trigger_error_common_cohort.json')
    return inputs, outputs


def digests(paths):
    return {str(path): hashlib.sha256((data / path).read_bytes()).hexdigest() for path in paths}


def run_task(index):
    inputs, outputs = task_files(index)
    before = digests(inputs)
    with (root / f'logs/graph_final_auxiliary_{index}.log').open('w') as log:
        result = subprocess.run(['bash', str(root / 'code/jobs/graph_auxiliary.sh'), str(manifest), str(root)],
            env=dict(os.environ, SLURM_ARRAY_TASK_ID=str(index)), stdout=log, stderr=subprocess.STDOUT)
    if before != digests(inputs):
        raise RuntimeError(f'Auxiliary task {index} inputs changed while running')
    record = {'task': index, 'configuration': rows[index], 'returncode': result.returncode,
              'input_sha256': before, 'output_sha256': digests(outputs) if result.returncode == 0 else {}}
    (root / f'graph-final-build/auxiliary-task-{index}.json').write_text(json.dumps(record, indent=2))
    return record


results, pending, active = [], set(range(len(rows))), {}
for index in sorted(pending.copy()):
    saved = root / f'graph-final-build/auxiliary-task-{index}.json'
    if saved.exists():
        record = json.loads(saved.read_text())
        inputs, outputs = task_files(index)
        if record['returncode'] or record['input_sha256'] != digests(inputs) or record['output_sha256'] != digests(outputs):
            raise RuntimeError(f'Invalid existing auxiliary completion record: {saved}')
        results.append(record)
        pending.remove(index)
with ThreadPoolExecutor(max_workers=4) as pool:
    while pending or active:
        for index in sorted(pending.copy()):
            if len(active) >= 4:
                break
            inputs, _outputs = task_files(index)
            if all((data / path).is_file() for path in inputs):
                active[index] = pool.submit(run_task, index)
                pending.remove(index)
                print(json.dumps({'auxiliary_started': index, 'configuration': rows[index]}), flush=True)
        for index, future in list(active.items()):
            if future.done():
                record = future.result()
                results.append(record)
                del active[index]
                print(json.dumps({'auxiliary_finished': index, 'returncode': record['returncode']}), flush=True)
                if record['returncode']:
                    raise RuntimeError(f'Auxiliary task failed: {record}')
        if pending or active:
            time.sleep(10)
(root / 'graph-final-build/auxiliary-status.json').write_text(json.dumps(results, indent=2))
if any(row['returncode'] for row in results):
    raise RuntimeError(f'Auxiliary tasks failed: {results}')
while not (root / 'graph-final-models-complete.json').exists():
    time.sleep(30)
subprocess.run([sys.executable, str(root / 'code/scripts/compare_graph_models.py'), str(root / 'graph-final-data'),
    str(root / 'graph-final-build/expected-verification.json'), str(root / 'graph-final-data/analysis/graph_paired_comparisons.json')], check=True)
subprocess.run([sys.executable, str(root / 'code/scripts/verify_graph_auxiliary.py'), str(root / 'graph-final-data'),
    str(root / 'graph-final-build/expected-auxiliary.json')], check=True)
expected = json.loads((root / 'graph-final-build/expected-auxiliary.json').read_text())['auxiliary_files']
missing = [name for name in expected if not (root / 'graph-final-data' / name).exists()]
if missing:
    raise FileNotFoundError(missing)
(root / 'graph-final-auxiliary-complete.json').write_text(json.dumps({'files': len(expected),
    'sha256': {name: hashlib.sha256((root / 'graph-final-data' / name).read_bytes()).hexdigest() for name in expected}}, indent=2))
print(json.dumps({'auxiliary_complete': True, 'files': len(expected)}), flush=True)
