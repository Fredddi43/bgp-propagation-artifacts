"""Refresh per-collector floors and duration summaries after replay publication."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys

from bgbench import config


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--workers',type=int,default=10)
    ap.add_argument('--retry-failed',action='store_true')
    ap.add_argument('--year',type=int)
    ap.add_argument('--tag',default='')
    args=ap.parse_args()
    if not os.environ.get('BGBENCH_DATA_ROOT'):
        raise SystemExit('Set an isolated BGBENCH_DATA_ROOT')
    if args.year is not None:
        from bgbench.eventset import per_vp_and_duration
        print(json.dumps(per_vp_and_duration(args.year,args.tag),indent=2))
        return
    logs=config.WORK_ROOT/'logs'/'per-vp-duration-final'
    logs.mkdir(parents=True,exist_ok=True)
    def run(task):
        year,tag=task
        command=[sys.executable,str(Path(__file__).resolve()),'--year',str(year),'--tag',tag]
        logfile=logs/f'{year}-{tag or "origin"}.log'
        with logfile.open('w') as stream:
            result=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,
                                  env={**os.environ,'POLARS_MAX_THREADS':'2','OPENBLAS_NUM_THREADS':'1'})
        result={'year':year,'tag':tag,'returncode':result.returncode,'log':str(logfile)}
        print(json.dumps(result),flush=True)
        return result
    tasks=[(year,tag) for year in range(2022,2027) for tag in ('','leak','withdrawal')]
    previous=[]
    if args.retry_failed:
        previous=json.loads((logs/'runs.json').read_text())
        assert {(r['year'],r['tag']) for r in previous}==set(tasks)
        tasks=[(r['year'],r['tag']) for r in previous if r['returncode']]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        retried=list(pool.map(run,tasks))
    results=[r for r in previous if not r['returncode']]+retried
    if previous:
        (logs/'runs-before-retry.json').write_text(json.dumps(previous,indent=2)+'\n')
    (logs/'runs.json').write_text(json.dumps(results,indent=2)+'\n')
    if any(r['returncode'] for r in results): raise SystemExit(1)

if __name__=='__main__': main()
