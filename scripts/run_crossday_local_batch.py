"""Run exclusively reassigned repair tasks on an authorized batch host.

The assignment JSON must record CANCELLED Slurm tasks verified by the caller;
this runner never cancels jobs or accepts merely pending tasks.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def atomic_json(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=1))
    temp.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--assignment', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=24)
    parser.add_argument('--parse-bin', type=Path)
    parser.add_argument('--procs', type=int, default=4)
    parser.add_argument('--downloads', type=int, default=2)
    args = parser.parse_args()
    parse_bin = args.parse_bin or args.run/'code/rust/bgbench-parse/target/release/bgbench-parse'
    subprocess.run([str(parse_bin), '--help'], check=True, stdout=subprocess.DEVNULL)
    assignment = json.loads(args.assignment.read_text())
    tasks = assignment['tasks']
    assert tasks and all(row['verified_state'].startswith('CANCELLED') for row in tasks)
    assert len({row['plan_index'] for row in tasks}) == len(tasks)
    batch = args.assignment.parent
    logs = batch / 'logs'
    logs.mkdir(exist_ok=True)
    (batch / 'runner.pid').write_text(str(os.getpid()))
    scratch = args.run / 'work' / 'local-crossday' / batch.name
    scratch.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    for key in list(env):
        if key.startswith('SLURM_'):
            env.pop(key)
    env.update(BGBENCH_DATA_ROOT=str(args.run/'data'), BGBENCH_WORK_ROOT=str(args.run/'work'),
               BGBENCH_SHM=str(scratch), BGBENCH_MEM_MB='131072',
               PYTHONPATH=str(args.run/'code/src'), BGBENCH_PARSE_ENGINE='rust', BGBENCH_PARSE_BIN=str(parse_bin),
               OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', POLARS_MAX_THREADS='2')

    def run(row):
        index = row['plan_index']
        status = batch / f'{index}.json'
        marker = args.run / 'crossday-repair/tasks' / f'{index}.json'
        record = dict(row, started=dt.datetime.now(dt.UTC).isoformat())
        atomic_json(status, record)
        command = [sys.executable, '-u', str(args.run/'code/scripts/repair_crossday_replays.py'),
                   'worker', '--plan', str(args.run/'crossday-repair-plan.json'),
                   '--task-index', str(index), '--output', str(args.run/'crossday-repair'),
                   '--procs', str(args.procs), '--downloads', str(args.downloads)]
        # Keep headroom for other authorized jobs and rare large parser storms.
        while True:
            available = next(int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))
            if available >= 200*1024*1024:
                break
            time.sleep(10)
        with (logs/f'{index}.log').open('a') as log:
            result = subprocess.run(command, env=env, cwd=args.run/'code', stdout=log, stderr=subprocess.STDOUT)
        record.update(returncode=result.returncode, finished=dt.datetime.now(dt.UTC).isoformat(),
                      marker=json.loads(marker.read_text())['status'] if marker.exists() else None)
        atomic_json(status, record)
        print(json.dumps(record), flush=True)
        return record

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        result = list(pool.map(run, tasks))
    atomic_json(batch/'complete.json', {'tasks':len(result), 'failed':[r for r in result if r['returncode'] or not r['marker']]})

if __name__ == '__main__':
    main()
