"""Run independent final CPU tensor builds on an explicitly authorized batch host."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
import fcntl
import time
import json
import os
from pathlib import Path
import socket
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('manifest', type=Path)
parser.add_argument('run_root', type=Path)
parser.add_argument('data_root', type=Path)
parser.add_argument('--workers', type=int, default=14)
args = parser.parse_args()
phase = args.manifest.stem
lines = [row for row in args.manifest.read_text().splitlines() if row.strip()]
record = args.run_root / 'graph-final-build' / f'submitted-{phase}.json'
status = {'phase': phase, 'host': socket.gethostname(), 'pid': os.getpid(), 'cohorts': len(lines),
          'data_root': str(args.data_root), 'workers': args.workers, 'completed': [], 'status': 'running'}
record.write_text(json.dumps(status, indent=2))


def acquire_slot():
    directory = args.run_root / 'graph-final-build'
    limit_file = directory / 'worker-limit.txt'
    while True:
        limit = int(limit_file.read_text()) if limit_file.exists() else args.workers
        for slot in range(min(limit, args.workers)):
            handle = (directory / f'worker-slot-{slot}.lock').open('a')
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return handle
            except BlockingIOError:
                handle.close()
        time.sleep(5)


def run(index):
    slot = acquire_slot()
    env = dict(os.environ, SLURM_ARRAY_TASK_ID=str(index))
    log = args.run_root / 'logs' / f'graph_final_build_{phase}_{index}.log'
    with slot, log.open('w') as output:
        result = subprocess.run(['bash', str(args.run_root / 'code/jobs/graph_final_build.sh'), str(args.manifest),
                                 str(args.run_root), str(args.data_root)], env=env, stdout=output, stderr=subprocess.STDOUT)
    return {'index': index, 'cohort': lines[index], 'returncode': result.returncode, 'log': str(log)}


with ThreadPoolExecutor(max_workers=args.workers) as pool:
    for future in as_completed([pool.submit(run, i) for i in range(len(lines))]):
        result = future.result()
        status['completed'].append(result)
        record.write_text(json.dumps(status, indent=2))
        print(json.dumps(result), flush=True)
status['status'] = 'failed' if any(r['returncode'] for r in status['completed']) else 'complete'
record.write_text(json.dumps(status, indent=2))
if status['status'] != 'complete':
    raise SystemExit(1)
