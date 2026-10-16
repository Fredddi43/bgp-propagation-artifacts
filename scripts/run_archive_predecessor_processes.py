"""Run isolated archive checks in processes so MRT header scans use allocated CPUs."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
import multiprocessing
from pathlib import Path
import time

from audit_archive_predecessors import atomic, load_plan, worker


def one(run, index, min_free_gib):
    while min_free_gib:
        available = next(int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()
                         if line.startswith('MemAvailable:'))
        if available >= min_free_gib * 1024 * 1024:
            break
        time.sleep(5)
    try:
        result = worker(run, index)
        return {'task': index, 'status': result['status'],
                'added_rows': sum(result.get('in_window_rows', {}).values())}
    except Exception as error:
        return {'task': index, 'status': 'failed', 'error': repr(error)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--indices', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=16)
    parser.add_argument('--min-free-gib', type=int, default=0)
    args = parser.parse_args()
    dispatch = json.loads((args.run / 'boundary-audit/dispatch.json').read_text())
    for path, expected in (
        (args.run / 'boundary-audit/plan.json', dispatch['plan_sha256']),
        (Path(__file__).with_name('audit_archive_predecessors.py'), dispatch['code_sha256']),
    ):
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f'Frozen boundary input changed: {path}')
    expected_chunk = next(record['sha256'] for record in dispatch['chunks']
                          if record['chunk'] == int(args.indices.stem))
    if hashlib.sha256(args.indices.read_bytes()).hexdigest() != expected_chunk:
        raise ValueError('Frozen task chunk changed')
    tasks = [int(value) for value in args.indices.read_text().split()]
    if len(tasks) != len(set(tasks)):
        raise ValueError('Duplicate task indices')
    load_plan(args.run / 'boundary-audit/plan.json')
    completed = {i for i in tasks if (args.run / 'boundary-audit/tasks' / f'{i}.json').exists()}
    results = [{'task': i, 'status': 'already_complete'} for i in sorted(completed)]
    print(json.dumps({'tasks': len(tasks), 'already_complete': len(completed), 'workers': args.workers}), flush=True)
    with ProcessPoolExecutor(max_workers=args.workers, mp_context=multiprocessing.get_context('spawn')) as pool:
        futures = [pool.submit(one, args.run, i, args.min_free_gib) for i in tasks if i not in completed]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(json.dumps(result), flush=True)
    atomic(args.indices.with_suffix('.complete.json'), {'tasks': len(results),
           'failed': [r for r in results if r['status'] == 'failed'], 'scheduler': 'spawn_process_pool'})


if __name__ == '__main__':
    main()
