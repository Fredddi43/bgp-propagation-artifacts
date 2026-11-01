"""One exact admitted baseline arm, in a fresh isolated source-compiled process."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import types

ROOT=Path('<FORECAST_ROOT>/data-custodian/single-R2-v1')
RUNNER_SHA = 'cf90e07d314c481849f22297d3a6815de5b6fa7aded60cd5797810c654f913df'


def need(ok,message):
    if not ok:raise ValueError(message)


def source(path,expected,limit=64<<20):
    need(path.resolve()==path and path.is_file(),'Canonical fixed bootstrap input required')
    need(path.stat().st_size<=limit,'Bootstrap input bound exceeded')
    raw=path.read_bytes();need(len(raw)<=limit and hashlib.sha256(raw).hexdigest()==expected,'Bootstrap input changed')
    return raw


def execute(batch_sha,slot):
    need(type(slot) is int and slot>=0,'Exact nonnegative baseline slot required')
    batch=json.loads(source(ROOT/'batch.json',batch_sha))
    need(batch['root']==str(ROOT) and slot<len(batch['jobs']),'Actual batch slot differs')
    control_path=ROOT/'controls-bound.json'
    need(control_path.resolve()==control_path and control_path.is_file() and control_path.stat().st_size<=4<<20,
         'Finite canonical control receipt required')
    control_raw=control_path.read_bytes();need(len(control_raw)<=4<<20,'Control receipt grew past bound')
    controls=json.loads(control_raw)
    need(controls['binding']['batch_sha256']==batch_sha,'Independently bound controls required')
    prefix=f'arms/{slot:03}/'
    need(controls['binding']['files']['bootstrap.py']==hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
         'Bootstrap source changed')
    for name in ('plan.json','approval.json','review.txt','resources.json'):
        source(ROOT/prefix/name,controls['control_files'][prefix+name])
    plan_ref={'path':str(ROOT/prefix/'plan.json'),'sha256':controls['control_files'][prefix+'plan.json']}
    approval_ref={'path':str(ROOT/prefix/'approval.json'),'sha256':controls['control_files'][prefix+'approval.json']}
    plan=json.loads(source(Path(plan_ref['path']),plan_ref['sha256']))
    need(plan['arm_id']==batch['jobs'][slot]['arm_id'] and plan['freeze']==batch['freeze']
         and str(plan['resources']['job_id'])==os.environ.get('SLURM_JOB_ID'),'Exact arm/job/freeze differs')
    raw=source(ROOT/'runner.py',RUNNER_SHA)
    runner=types.ModuleType('source_compiled_baseline_runner');runner.__file__=str(ROOT/'runner.py')
    exec(compile(raw,runner.__file__,'exec'),runner.__dict__)
    return runner.run(plan_ref,approval_ref)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--batch-sha256',required=True);p.add_argument('--slot',required=True,type=int)
    a=p.parse_args()
    # The runner itself sanitizes protected exceptions. Bootstrap errors carry only control metadata.
    print(json.dumps(execute(a.batch_sha256,a.slot),sort_keys=True))
