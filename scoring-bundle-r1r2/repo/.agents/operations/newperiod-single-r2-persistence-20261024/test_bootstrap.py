"""Fresh -I/-B source-only caller through genuine single-label science boundary."""
import importlib.metadata,json,os,shutil,subprocess,sys
from pathlib import Path
import pytest
from test_persistence import D,f,r
fixture,ref,save=f.fixture,f.ref,f.save

def test_fresh_isolated_full_runner_original_oneopening(tmp_path,monkeypatch):
 plan,reader,_,expected=fixture(tmp_path,monkeypatch)
 stage=tmp_path/'execution';stage.mkdir();(stage/'arms/000').mkdir(parents=True)
 for p in D.rglob('*'):
  if p.is_file() and '__pycache__' not in p.parts and p.suffix in ('.py','.json'):
   target=stage/p.relative_to(D);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
 repo=D.parents[2];pins=json.loads((D/'pins.json').read_bytes());closure=[]
 for value in pins.values():
  p=stage/'source'/value['path'];p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(repo/value['path'],p)
  if value['path'].startswith('src/bgbench/'):closure.append(ref(p))
 plan['source_root']=str(stage/'source');plan['source_closure']=save(stage/'closure.json',dict(source_root=plan['source_root'],files=closure))
 plan.update(kind='newperiod_single_R2_execution_v1',arm_id='R2',records=str(stage/'arms/000/attempt'),primary_output=str(stage/'arms/000/attempt/primary.json'),result_output=str(stage/'arms/000/attempt/complete-result.json'),primary_scores_output=str(stage/'arms/000/attempt/primary-scores.json'),access_log=str(tmp_path/'access-log.jsonl'),resources=dict(cpus=1,memory_mib=16384,wall_seconds=300,job_id='12345'))
 plan['bounds']=dict(reader.bounds,runtime_file_bytes=256<<20,output_file_bytes=256<<20,output_total_bytes=2<<30,access_log_bytes=32<<20)
 native=Path(sys.executable).resolve();plan['runtime']=save(stage/'runtime.json',dict(passed=True,python=ref(native),versions={n:importlib.metadata.version(n) for n in ('numpy','polars','torch')},files=[ref(native)]))
 inventory=list(reader.items.values())
 for n in ('forecast_custodian_eval.py','forecast_retrospective_scoring.py'):
  p=stage/'source/src/bgbench'/n;inventory.append(dict(**ref(p),size_bytes=p.stat().st_size,kind='metadata'))
 plan['read_inventory']=save(stage/'inventory.json',dict(files=inventory))
 plan['resource_readiness']=save(stage/'resources.json',dict(passed=True,resources=plan['resources'],freeze=plan['freeze'],arm_id='R2',bounds=plan['bounds'],read_inventory=plan['read_inventory'],all_prepared_predictions_and_bootstrap_memory_fit=True,shared_storage_reservation_bytes=plan['bounds']['output_total_bytes'],free_floor_bytes=64<<30,reviewer_worker='/root',reviewer_session='/root'))
 pref=save(stage/'plan.json',plan);review=stage/'review.txt';review.write_text('Synthetic fixture only: no actual execution authority.')
 auth=dict(passed=True,plan=pref,runner_sha256=ref(stage/'runner.py')['sha256'],resources=plan['resources'],read_inventory=plan['read_inventory'],seal=plan['seal'],labels=plan['labels'],full_retention_review=plan['full_retention_review'],reviewer_worker='/root',reviewer_session='/root',reviewer_model='synthetic',review=ref(review))
 auth.update({k:True for k in ('execution_authorized','single_label_join_authorized','score_authorized')});auth.update({k:False for k in ('retry_authorized','fit_authorized','prediction_authorized','seal_authorized','outcome_release_authorized')});aref=save(stage/'approval.json',auth)
 program="""import json,sys,types
from pathlib import Path
p=Path(sys.argv[1]);m=types.ModuleType('actual_R2_runner');m.__file__=str(p)
exec(compile(p.read_bytes(),str(p),'exec'),m.__dict__)
m.ROOT=str(p.parent) # exclusive local namespace; fixture stable selection below
m.BOOTSTRAP=dict(repetitions=200,bootstrap_seed=1701,alpha=.05) # synthetic CI work bound only
original_modules=m.scientific_modules
def fixture_modules(plan):
 result=original_modules(plan)
 import bgbench.forecast_stable_peer as stable
 selected=json.loads(sys.argv[4])
 stable.STABLE_SELECTION_SHA256=selected['selection_sha256'];stable.STABLE_SELECTION_FILE_SHA256=sys.argv[5];stable.STABLE_PEER_COUNT=1
 return result
m.scientific_modules=fixture_modules # synthetic one-peer selection, scientific source unchanged
original_execute=m.execute
def diagnose(*a,**k):
 try:return original_execute(*a,**k)
 except BaseException:
  import traceback;traceback.print_exc();raise
m.execute=diagnose # synthetic fixture diagnostics only, production stays sanitized
print(json.dumps(m.run(json.loads(sys.argv[2]),json.loads(sys.argv[3]))))
"""
 env=dict(os.environ,SLURM_JOB_ID='12345',SLURM_JOB_PARTITION='cpu',SLURM_CPUS_PER_TASK='1',SLURM_MEM_PER_NODE='16384',SLURM_RESTART_COUNT='0',CUSTODIAN_ACCESS_LOG=plan['access_log'],OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',POLARS_MAX_THREADS='1');env.pop('SLURM_ARRAY_TASK_ID',None)
 stable_stage=json.loads(Path(json.loads(Path(plan['stable_evidence']['path']).read_bytes())['stable_source']['path']).read_bytes())
 result=subprocess.run([sys.executable,'-I','-B','-c',program,str(stage/'runner.py'),json.dumps(pref),json.dumps(aref),json.dumps(stable_stage['sensitivity']),stable_stage['selection']['sha256']],env=env,capture_output=True,text=True,timeout=350)
 assert result.returncode==0,result.stderr
 done=json.loads(result.stdout);assert done['passed'] and done['label_reads']==1
 assert done['primary_scores']['path']==plan['primary_scores_output']
 assert ref(plan['primary_scores_output'])['sha256']==done['primary_scores']['sha256']
 assert Path(plan['primary_scores_output']).stat().st_size==done['primary_scores']['size_bytes']
 assert done['primary_scores']['size_bytes']<=done['primary_scores']['bound_bytes']==plan['bounds']['output_file_bytes']
 report=json.loads(Path(plan['result_output']).read_bytes())
 print('R2_FIXTURE_METRICS',json.dumps(dict(done,result_bytes=Path(plan['result_output']).stat().st_size),sort_keys=True))
 assert len(report['additional_baselines']['cells'])==6 and sum(len(x['cells']) for x in report['origin']['families'].values())==40
 for key in ('families','eligibility','history_median_vs_mean_jaccard'):assert report['primary'][key]==expected[key]
 logs=[json.loads(x) for x in Path(plan['access_log']).read_text().splitlines()]
 assert sum(x['path']==plan['labels']['path'] and x['purpose']=='Custodian label table' for x in logs)==1
 assert (Path(plan['records'])/'done.json').is_file()
 again=subprocess.run([sys.executable,'-I','-B','-c',program,str(stage/'runner.py'),json.dumps(pref),json.dumps(aref),json.dumps(stable_stage['sensitivity']),stable_stage['selection']['sha256']],env=env,capture_output=True,text=True,timeout=30)
 assert again.returncode!=0 and 'Single R2 execution refused' in again.stderr
