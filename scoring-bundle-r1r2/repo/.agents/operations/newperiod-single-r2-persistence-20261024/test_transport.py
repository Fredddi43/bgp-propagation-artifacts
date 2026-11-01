"""Real exclusive stage/state functions, fake Slurm executable boundary only."""
import ast,copy,json,sys,types
from pathlib import Path
import pytest
D=Path(__file__).resolve().parent

def load(p,name):
 m=types.ModuleType(name);m.__file__=str(p);exec(compile(p.read_bytes(),str(p),'exec'),m.__dict__);return m
b=load(D/'build.py','R2builder');c=b.c
old=load(D.parent/'newperiod-baseline-transport-20261023/test_transport.py','reviewed_transport_fixture')

def fixture(tmp_path,monkeypatch):
 stage=tmp_path/'stage';monkeypatch.setattr(c,'ROOT',str(stage));monkeypatch.setattr(old,'c',c)
 raw=c.encode(dict(all_retained_outputs_absent_at_freeze=True,arms=[]));freeze=tmp_path/'freeze.json';freeze.write_bytes(raw)
 fr=dict(path=str(freeze),sha256=c.sha(raw));dummy=dict(path=str(tmp_path/'metadata'),sha256='a'*64)
 bounds={k:1<<20 for k in ('metadata_bytes','input_bytes','checkpoint_bytes','label_bytes','runtime_file_bytes','total_read_bytes','total_unique_bytes','output_file_bytes','access_log_bytes')};bounds['output_total_bytes']=16<<20
 p=dict(kind='newperiod_single_R2_execution_v1',arm_id='R2',freeze=fr,seal=dummy,labels=dummy,full_retention_review=dummy,read_inventory=dummy,
    source_root=str(stage/'source'),records=str(stage/'arms/000/attempt'),primary_output=str(stage/'arms/000/attempt/primary.json'),result_output=str(stage/'arms/000/attempt/complete-result.json'),primary_scores_output=str(stage/'arms/000/attempt/primary-scores.json'),
    resources=dict(cpus=1,memory_mib=16384,wall_seconds=600,job_id=None),resource_readiness=None,bounds=bounds,access_log=str(tmp_path/'access.jsonl'))
 jobs=[dict(arm_id='R2',template='templates/000.json',cpus=1,memory_mib=16384,wall_seconds=600)]
 sources={'runtime_helpers.py':(D/'runtime_helpers.py').read_bytes()}
 admission=dict(passed=True,freeze=fr,jobs=jobs,max_concurrent_arms=1,aggregate_memory_mib=16384,all_prepared_predictions_and_bootstrap_memory_fit=True,
  read_inventory=dummy,bounds=bounds,storage_reservation_bytes=128<<20,free_floor_bytes=64<<30)
 batch=dict(kind='newperiod_single_R2_transport_v1',root=str(stage),python=sys.executable,freeze=fr,seal=dummy,access_log=p['access_log'],jobs=jobs,max_concurrent_arms=1,admission=admission,source_files={n:c.sha(x) for n,x in sources.items()})
 files=b.assemble(batch,{'templates/000.json':p},sources,raw);review=b'synthetic distinct independent review'
 approval=dict(passed=True,binding=c.binding(files),review_sha256=c.sha(review),reviewer_worker='/root',reviewer_session='/root',reviewer_model='fixture',retry_authorized=False,stage_authorized=True,submit_held_authorized=True,release_authorized=False)
 monkeypatch.setattr(c.h.pwd,'getpwuid',lambda _:types.SimpleNamespace(pw_name='<USER>'))
 w=types.SimpleNamespace(stage=stage,batch=batch,files=files,approval=c.encode(approval),review=review,templates={'templates/000.json':p})
 oldheld=old.held_text
 monkeypatch.setattr(old,'held_text',lambda w,i,j,d:oldheld(w,0,j,None).replace('bg-n-base-','bg-n-R2-'))
 return w

def controls(w,admitted):
 prefix='arms/000/';p=copy.deepcopy(w.templates['templates/000.json']);p['resources']['job_id']=admitted[0]['job_id']
 resource=dict(passed=True,resources=p['resources'],freeze=p['freeze'],arm_id='R2',bounds=p['bounds'],read_inventory=p['read_inventory'],all_prepared_predictions_and_bootstrap_memory_fit=True,shared_storage_reservation_bytes=p['bounds']['output_total_bytes'],free_floor_bytes=64<<30,reviewer_worker='/root',reviewer_session='/root')
 files={prefix+'resources.json':c.encode(resource)};p['resource_readiness']=dict(path=str(w.stage/prefix/'resources.json'),sha256=c.sha(files[prefix+'resources.json']))
 files[prefix+'plan.json']=c.encode(p);files[prefix+'review.txt']=b'synthetic operation review'
 a=dict(passed=True,plan=dict(path=str(w.stage/prefix/'plan.json'),sha256=c.sha(files[prefix+'plan.json'])),runner_sha256=c.RUNNER_SHA,resources=p['resources'],read_inventory=p['read_inventory'],seal=p['seal'],labels=p['labels'],full_retention_review=p['full_retention_review'],reviewer_worker='/root',reviewer_session='/root',reviewer_model='fixture',review=dict(path=str(w.stage/prefix/'review.txt'),sha256=c.sha(files[prefix+'review.txt'])))
 a.update({k:True for k in ('execution_authorized','single_label_join_authorized','score_authorized')});a.update({k:False for k in ('retry_authorized','fit_authorized','prediction_authorized','seal_authorized','outcome_release_authorized')});files[prefix+'approval.json']=c.encode(a)
 rel=json.loads(w.approval);rel.update(stage_authorized=False,submit_held_authorized=False,release_authorized=True,admitted=admitted,control_files={n:c.sha(v) for n,v in files.items()})
 return files,c.encode(rel)

def test_real_stage_single_held_admission_release_no_resubmit(tmp_path,monkeypatch):
 w=fixture(tmp_path,monkeypatch);fake=old.FakeCluster(w);client=c.Client(w.files,w.approval,w.review,tmp_path/'local',transport=fake)
 client.stage();assert client.submit_held()==['1000'];assert not fake.released
 admitted=client.admit();fs,rel=controls(w,admitted);client.release(fs,rel,w.review)
 assert fake.released==['1000'] and len(fake.jobs)==1
 other=c.Client(w.files,w.approval,w.review,tmp_path/'other',transport=fake)
 with pytest.raises(ValueError):other.submit_held()
 assert len(fake.jobs)==1
 assert 'CUSTODIAN_ACCESS_LOG='+w.batch['access_log'] in w.files['job-000.sbatch'].decode()

@pytest.mark.parametrize('damage',['secondjob','array','memory','retention','prediction','authority','source','path'])
def test_exact_singleton_control_refusals(tmp_path,monkeypatch,damage):
 w=fixture(tmp_path,monkeypatch);batch=copy.deepcopy(w.batch);files=dict(w.files)
 if damage=='secondjob':batch['jobs']*=2
 elif damage=='array':batch['max_concurrent_arms']=2
 elif damage=='memory':batch['admission']['aggregate_memory_mib']=1
 elif damage=='retention':batch['freeze']['sha256']='f'*64
 elif damage=='source':files['runtime_helpers.py']+=b'bad'
 elif damage=='path':files['../x']=b'bad'
 else:
  admitted=[dict(job_id='1000')];fs,rel=controls(w,admitted);a=json.loads(fs['arms/000/approval.json'])
  if damage=='prediction':a['prediction_authorized']=True
  else:a['reviewer_worker']='/root/x/../metadata_check_review'
  fs['arms/000/approval.json']=c.encode(a);release=json.loads(rel);release['control_files']={n:c.sha(v) for n,v in fs.items()}
  with pytest.raises(ValueError):c.validate_controls(batch,files,fs,admitted,release)
  return
 files['batch.json']=c.encode(batch)
 with pytest.raises(ValueError):c.check_batch(batch,files)

def test_original_scheduler_and_state_machine_ast_preserved():
 oldtree=ast.parse((D.parent/'newperiod-baseline-transport-20261023/client.py').read_text().replace('baseline-transport-v1','single-R2-v1').replace('bg-n-base-','bg-n-R2-'))
 newtree=ast.parse((D/'client.py').read_text());before={n.name:ast.dump(n,include_attributes=False) for n in oldtree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
 after={n.name:ast.dump(n,include_attributes=False) for n in newtree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
 changes={'check_batch','readiness','job_script','validate_controls','independent'}
 assert all(after[k]==v for k,v in before.items() if k not in changes)
 assert 'python' not in c.scheduler_script(dict(jobs=[dict(cpus=1,memory_mib=1024,wall_seconds=600)],max_concurrent_arms=1),'submit')

@pytest.mark.parametrize('damage',['omitted_score_path','old_five_file_budget'])
def test_new_sidecar_contract_required_before_stage(tmp_path,monkeypatch,damage):
 w=fixture(tmp_path,monkeypatch);p=copy.deepcopy(w.templates['templates/000.json']);batch=copy.deepcopy(w.batch)
 if damage=='omitted_score_path':p.pop('primary_scores_output')
 else:
  p['bounds']['output_total_bytes']=5*p['bounds']['output_file_bytes']+p['bounds']['access_log_bytes']
  batch['admission']['bounds']=p['bounds']
 with pytest.raises((ValueError,KeyError)):b.assemble(batch,{'templates/000.json':p},{'runtime_helpers.py':(D/'runtime_helpers.py').read_bytes()},w.files['freeze-capture.json'])
