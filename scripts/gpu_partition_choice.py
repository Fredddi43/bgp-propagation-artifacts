"""Read-only Slurm start estimates for selecting an available GPU partition."""
from concurrent.futures import ThreadPoolExecutor
import datetime
import json
import re
import shlex
import subprocess


def choose_gpu_partition(script, arguments, *, cpus=2, memory='48G', walltime='04:00:00',
                         prefer_fast=False, chdir=None):
    def probe(kind):
        command = ['sbatch', '--test-only', '-p', 'gpu-' + kind, '--gres=gpu:' + kind + ':1',
                   '-c', str(cpus), '--mem=' + memory, '-t', walltime, '--export=ALL']
        if chdir is not None:
            command += ['--chdir', str(chdir)]
        command += [str(script), *map(str, arguments)]
        result = subprocess.run(['ssh', 'slurm-submit', shlex.join(command)], capture_output=True, text=True)
        match = re.search(r'to start at ([0-9T:-]+)', result.stdout + result.stderr)
        return {'kind': kind, 'estimated_start': match.group(1) if match else None}
    with ThreadPoolExecutor(max_workers=5) as pool:
        predictions = list(pool.map(probe, ('a40', 'a100', 'h100', 'l40', 'rtx8000')))
    usable = [row for row in predictions if row['estimated_start']]
    if not usable:
        return {'estimates': predictions, 'selected': None, 'options': [
            '-p', 'gpu-all', '--gres=gpu:1', '--constraint=gpu-a40|gpu-a100|gpu-h100|gpu-l40|gpu-rtx8000']}
    earliest = min(usable, key=lambda row: row['estimated_start'])
    choice = earliest
    if prefer_fast:
        deadline = datetime.datetime.fromisoformat(earliest['estimated_start']) + datetime.timedelta(minutes=30)
        fast = [row for row in usable if row['kind'] in ('h100', 'a100', 'l40')
                and datetime.datetime.fromisoformat(row['estimated_start']) <= deadline]
        if fast:
            choice = min(fast, key=lambda row: row['estimated_start'])
    return {'estimates': predictions, 'selected': choice,
            'options': ['-p', 'gpu-' + choice['kind'], '--gres=gpu:' + choice['kind'] + ':1']}
