"""Recompute the changed prefix floor while retaining every historical completion."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import polars as pl
from rerun_nongraph import input_contract, table_content_fingerprint


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def atomic(path,value):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=1,default=str));tmp.replace(path)


def revise(run,wait):
    proof_path=run/'boundary-audit/nongraph-input-equivalence.json';source=run/'crossday-source-complete.json'
    if wait:
        while not proof_path.exists() or not source.exists():time.sleep(10)
    proof=json.loads(proof_path.read_text())
    if proof['status']!='passed' or proof['rerun_tasks']!=[62] or len(proof['equivalent_tasks'])!=97:
        raise ValueError('unexpected changed non-graph producer scope')
    tasks=json.loads((run/'nongraph-plan.json').read_text());task=tasks[62]
    assert task['kind']=='prefix_floor' and task['year']==2025
    old_folder='2025/062_prefix_floor';new_folder='2025/062_prefix_floor_boundary_v2'
    original=run/'nongraph-final'/old_folder;destination=run/'nongraph-final'/new_folder;destination.mkdir(exist_ok=True)
    marker=destination/'complete.json'
    before=input_contract(run,task);gate_sha=sha(source);started=dt.datetime.now(dt.UTC).isoformat()
    if not marker.exists():
        work=run/'work/prefixfloor-boundary/data';event=work/'eventset/2025_leak';event.mkdir(parents=True,exist_ok=True)
        for link,target in [(event/'events.parquet',run/'data/eventset/2025_leak/events.parquet'),(work/'events_replay_leak',run/'data/events_replay_leak')]:
            if not link.exists():link.symlink_to(target,target_is_directory=target.is_dir())
        env={**os.environ,'BGBENCH_DATA_ROOT':str(work),'PYTHONPATH':str(run/'code/src')}
        subprocess.run([sys.executable,str(run/'code/scripts/prefix_floor.py'),'2025'],env=env,check=True)
        for name in ('prefix_floor.parquet','prefix_floor_summary.json'):shutil.copy2(event/name,destination/name)
        old=pl.read_parquet(original/'prefix_floor.parquet');new=pl.read_parquet(destination/'prefix_floor.parquet')
        removed=old.filter(~pl.col('event_id').is_in(new['event_id'].implode()))
        retained=old.filter(pl.col('event_id').is_in(new['event_id'].implode()))
        if removed['event_id'].to_list()!=['20251010T213946_leak_266545'] or not retained.sort('event_id').equals(new.sort('event_id'),null_equal=True):
            raise ValueError('prefix revision changed more than the audited ineligible event')
        after=input_contract(run,task)
        if before!=after or sha(source)!=gate_sha:raise ValueError('prefix inputs changed during revision')
        provenance={**before,'inputs_after':after['inputs'],'input_files_byte_identical':True,'source_gate':'crossday-source-complete.json','source_gate_sha256':gate_sha,
                    'started_utc':started,'finished_utc':dt.datetime.now(dt.UTC).isoformat(),'inputs_unchanged':True,'code_unchanged':True}
        atomic(marker,{'task':task,'result':{},'correction_run':provenance,'replacement_for':{'path':str((original/'complete.json').relative_to(run)),'sha256':sha(original/'complete.json')},
            'boundary_input_equivalence_sha256':sha(proof_path),'revision_script_sha256':sha(Path(__file__)),
            'prefix_floor_revision':{'before_sha256':sha(original/'prefix_floor.parquet'),'after_sha256':sha(destination/'prefix_floor.parquet'),
             'before_content_sha256':table_content_fingerprint(original/'prefix_floor.parquet'),'after_content_sha256':table_content_fingerprint(destination/'prefix_floor.parquet'),
             'before_columns':old.columns,'removed_rows':removed.to_dicts(),'retained_rows_equal':True}})
    composite=run/'nongraph-release';composite.mkdir(exist_ok=True)
    for year in (2024,2025):
        (composite/str(year)).mkdir(exist_ok=True)
        for folder in (run/'nongraph-final'/str(year)).iterdir():
            if folder.is_dir():
                link=composite/str(year)/folder.name
                if not link.exists():link.symlink_to(folder,target_is_directory=True)
    original_manifest=run/'expected-nongraph.json';historical=run/'expected-nongraph.before-boundary.json'
    if not historical.exists():shutil.copy2(original_manifest,historical)
    expected=json.loads(historical.read_text());old_prefix='analysis/nongraph/'+old_folder;new_prefix='analysis/nongraph/'+new_folder
    for spec in expected['nongraph_tables']:
        for key,value in list(spec.items()):
            if isinstance(value,str) and value.startswith(old_prefix+'/'):spec[key]=new_prefix+value[len(old_prefix):]
    expected['required_files']=[new_prefix+v[len(old_prefix):] if v.startswith(old_prefix+'/') and not v.endswith('/complete.json') else v for v in expected['required_files']]
    expected['required_files'].append(new_prefix+'/complete.json')
    expected['nongraph_release']='analysis/nongraph-release-complete.json'
    expected['boundary_input_bridge']={'manifest':'analysis/boundary-input-bridge.json','verification':'analysis/boundary-input-verification.json','equivalence':'analysis/nongraph-boundary-input-equivalence.json'}
    expected['required_files']=list(dict.fromkeys([*expected['required_files'],expected['nongraph_release'],*expected['boundary_input_bridge'].values()]))
    atomic(original_manifest,expected)
    selected={}
    for year in (2024,2025):
        for folder in (composite/str(year)).iterdir():
            for file in folder.rglob('*'):
                if not file.is_file() or file.suffix not in ('.json','.csv','.parquet','.joblib','.safetensors'):continue
                if file.name.endswith('.verification.json'):continue
                relative=file.relative_to(composite)
                if str(relative).startswith(old_folder+'/') and file.name!='complete.json':continue
                if any('checkpoint' in component for component in relative.parts):continue
                selected[str(relative)]=sha(file)
    result={'status':'complete','data_root':'nongraph-release','original_completion_sha256':sha(run/'nongraph-final-complete.json'),
            'revisions':[{'index':62,'year':2025,'original_folder':old_folder,'replacement_folder':new_folder,'completion_sha256':sha(marker)}],
            'selected_artifact_sha256':selected,'boundary_input_equivalence_sha256':sha(proof_path),'expected_manifest_sha256':sha(original_manifest)}
    atomic(run/'nongraph-release-complete.json',result)
    print(json.dumps({'status':'complete','selected_artifacts':len(selected),'revision':new_folder}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--wait',action='store_true');a=p.parse_args();revise(a.run,a.wait)
