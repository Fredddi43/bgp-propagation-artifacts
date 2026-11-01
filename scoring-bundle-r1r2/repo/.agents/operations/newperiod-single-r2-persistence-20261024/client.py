"""Prospective fixed baseline stage -> held jobs -> admission -> independently bound release.

Reuse the reviewed GBDT transport's byte readers, durable records and SSH adapter.
No freeze/config generation, scientific retry, arbitrary shell payload or job selection.
"""
import base64
import hashlib
import json
import os
import re
import shlex
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = '<FORECAST_ROOT>/data-custodian/single-R2-v1'
HELPER_SHA = 'cdc41765f19cb045ad09345b30cd7f9da0a28a6d1f895ce4023aa5ce763a172e'
RUNNER_SHA = 'cf90e07d314c481849f22297d3a6815de5b6fa7aded60cd5797810c654f913df'
BOOT = '<RESULTS_ROOT>/work/vllm/miniforge/bin/python3.12'
helper_raw = globals().get('_HELPER_SOURCE') or (HERE/'reviewed_transport.py').read_bytes()
if hashlib.sha256(helper_raw).hexdigest() != HELPER_SHA:
    raise ValueError('Reviewed transport helper changed')
h = types.ModuleType('unchanged_transport_helpers'); h.__file__ = str(HERE/'reviewed_transport.py')
exec(compile(helper_raw, h.__file__, 'exec'), h.__dict__)
need, read, write, sha, encode = h.need, h.read_file, h.write_new, h.sha, h.raw_json


def independent(value):
    return (isinstance(value, str) and bool(value) and not any(c.isspace() for c in value)
        and os.path.normpath('/'+value.casefold().lstrip('/')) not in (
            '/root/metadata_check_review', '/metadata_check_review', '/root/deadline_audit', '/deadline_audit', '/', '/.'))


def doc(ref):
    data = read(ref['path']); need(sha(data) == ref['sha256'], 'Bound metadata changed')
    return json.loads(data)


def check_batch(batch,files):
    need(batch.get('kind')=='newperiod_single_R2_transport_v1' and batch.get('root')==ROOT,'Exact singleton R2 namespace required')
    need(Path(batch['python']).is_absolute(),'Exact runtime Python required')
    for n in files:
        p=Path(n);need(not p.is_absolute() and '..' not in p.parts and str(p)==n and p.suffix!='.pyc','Canonical cache-free member required')
    need(sha(files['runner.py'])==RUNNER_SHA and sha(files['reviewed_transport.py'])==HELPER_SHA,'Reviewed execution sources changed')
    frozen=json.loads(files['freeze-capture.json'])
    need(sha(files['freeze-capture.json'])==batch['freeze']['sha256'] and frozen.get('all_retained_outputs_absent_at_freeze') is True,'Exact complete freeze capture required')
    need(len(batch['jobs'])==1 and batch['max_concurrent_arms']==1,'One R2 job only')
    j=batch['jobs'][0];need(set(j)=={'arm_id','template','cpus','memory_mib','wall_seconds'} and j['arm_id']=='R2' and j['template']=='templates/000.json','Fixed R2 slot required')
    need(all(type(j[k]) is int and j[k]>0 for k in ('cpus','memory_mib','wall_seconds')) and j['cpus']<=128 and 1024<=j['memory_mib']<=2097152 and j['wall_seconds']<=86400,'Finite CPU allocation required')
    p=json.loads(files[j['template']])
    need(p['arm_id']=='R2' and p['kind']=='newperiod_single_R2_execution_v1' and p['freeze']==batch['freeze']
        and p['seal']==batch['seal'] and p['source_root']==ROOT+'/source' and p['records']==ROOT+'/arms/000/attempt'
        and p['primary_output']==p['records']+'/primary.json' and p['result_output']==p['records']+'/complete-result.json'
        and p['primary_scores_output']==p['records']+'/primary-scores.json'
        and p['resources']=={k:j[k] for k in ('cpus','memory_mib','wall_seconds')}|{'job_id':None}
        and p['resource_readiness'] is None and p['access_log']==batch['access_log'],'Only actual job/resource admission may remain unresolved')
    a=batch['admission'];bounds=p['bounds']
    need(type(bounds['output_file_bytes']) is int and bounds['output_file_bytes']>0
        and bounds['output_total_bytes']>=6*bounds['output_file_bytes']+bounds['access_log_bytes'],
        'Extra primary-score file must be included in storage admission')
    need(a.get('passed') is True and a.get('freeze')==batch['freeze'] and a.get('jobs')==batch['jobs']
        and a.get('max_concurrent_arms')==1 and a.get('aggregate_memory_mib')==j['memory_mib']
        and a.get('all_prepared_predictions_and_bootstrap_memory_fit') is True
        and a.get('read_inventory')==p['read_inventory'] and a.get('bounds')==bounds
        and a.get('storage_reservation_bytes',0)>=bounds['output_total_bytes']+(64<<20)
        and a.get('free_floor_bytes')==64<<30,'Whole single-evaluation resource admission required')
    for n,digest in batch['source_files'].items():need(sha(files[n])==digest,'Exact complete source/control closure differs')
    need(set(files)==set(batch['source_files'])|{'runner.py','pins.json','bootstrap.py','client.py','reviewed_transport.py','freeze-capture.json','batch.json','templates/000.json','job-000.sbatch'},'Unexpected or missing staged file')
    need(sha(files['batch.json'])==sha(encode(batch)) and files['job-000.sbatch']==job_script(batch,0,sha(files['batch.json'])),'Canonical batch/bootstrap differs')
    need(sum(map(len,files.values()))<=48<<20,'Finite staged package required')
    return [p]


def readiness(batch,*,all_outputs=False,slot=None):
    import shutil
    need(slot in (None,0),'Only R2 slot exists')
    frozen=doc(batch['freeze'])
    # No label or prediction content read here. The complete seal/read inventory
    # is admitted in the independently approved plan and consumed by the worker.
    root=Path(ROOT);parent=root.parent;need(parent.resolve()==parent,'Canonical stage parent required')
    attempt=root/'arms/000/attempt';need(not attempt.exists() and not attempt.is_symlink(),'Existing R2 attempt cannot repeat')
    from pathlib import Path as LocalPath
    freeze_parent=LocalPath(batch['freeze']['path']).parent
    need(freeze_parent.stat().st_dev==parent.stat().st_dev,'Original one-opening marker outside storage admission')
    marker=freeze_parent/('unblinded-'+batch['seal']['sha256']+'.json')
    need(not marker.exists() and not marker.is_symlink(),'Existing original R2 opening marker')
    if all_outputs:need(shutil.disk_usage(parent).free>=batch['admission']['storage_reservation_bytes']+(64<<30),'Shared storage reservation unavailable')


def job_script(batch,slot,batch_sha):
    need(slot==0,'Singleton slot required');j=batch['jobs'][slot]
    env=['PATH=/usr/bin:/bin','LANG=C.UTF-8','CUSTODIAN_ACCESS_LOG='+batch['access_log'],*[k+'='+str(j['cpus']) for k in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','POLARS_MAX_THREADS')]]
    inherited=' '.join(k+'="${'+k+':?}"' for k in ('SLURM_JOB_ID','SLURM_JOB_PARTITION','SLURM_CPUS_PER_TASK','SLURM_MEM_PER_NODE'))
    return ('#!/bin/bash\nset -eu\nexec env -i '+shlex.join(env)+' '+inherited+' SLURM_RESTART_COUNT="${SLURM_RESTART_COUNT:-0}" '+shlex.join([batch['python'],'-I','-B',ROOT+'/bootstrap.py','--batch-sha256',batch_sha,'--slot','0'])+'\n').encode()


def binding(files):
    return {'root':ROOT,'files':{n:sha(v) for n,v in sorted(files.items())},'batch_sha256':sha(files['batch.json'])}


def authority(a, review, bound, *, release=False):
    need(a.get('passed') is True and a.get('binding') == bound and a.get('review_sha256') == sha(review)
         and independent(a.get('reviewer_worker')) and independent(a.get('reviewer_session'))
         and bool(a.get('reviewer_model')) and a.get('retry_authorized') is False
         and a.get('stage_authorized') is (not release) and a.get('submit_held_authorized') is (not release)
         and a.get('release_authorized') is release, 'Exact separate independent transport authority required')


def time_limit(seconds):
    # Slurm allocates whole minutes; exact requests use a whole-minute admission.
    need(seconds % 60 == 0, 'Whole-minute Slurm wall bound required')
    days,rem=divmod(seconds,86400);hours,rem=divmod(rem,3600);minutes=rem//60
    return (str(days)+'-' if days else '')+f'{hours:02}:{minutes:02}:00'


def submit_argv(batch, i, dependency):
    j=batch['jobs'][i]
    return ['sbatch','--parsable','--hold','--nodes=1','--ntasks=1','--partition=cpu',
        '--cpus-per-task='+str(j['cpus']),'--mem='+str(j['memory_mib'])+'M','--time='+time_limit(j['wall_seconds']),
        '--no-requeue','--export=ALL','--job-name=bg-n-R2-'+f'{i:03}','--chdir='+ROOT,
        '--output='+ROOT+f'/arms/{i:03}/job-%j.stdout','--error='+ROOT+f'/arms/{i:03}/job-%j.stderr',
        *(['--dependency=afterok:'+dependency,'--kill-on-invalid-dep=yes'] if dependency else []),ROOT+f'/job-{i:03}.sbatch']


def held(text,batch,i,job,dependency):
    need('\n' not in text.strip(),'One scheduler job record required')
    f={}
    for word in shlex.split(text):
        if '=' in word:
            k,v=word.split('=',1);need(k not in f,'Duplicate scheduler field');f[k]=v
    j=batch['jobs'][i]
    expected={'JobId':job,'JobName':f'bg-n-R2-{i:03}','JobState':'PENDING','Reason':'JobHeldUser','Priority':'0',
        'Partition':'cpu','NumCPUs':str(j['cpus']),'CPUs/Task':str(j['cpus']),'NumTasks':'1','Requeue':'0','Restarts':'0',
        'TimeLimit':time_limit(j['wall_seconds']),'WorkDir':ROOT,'Command':ROOT+f'/job-{i:03}.sbatch',
        'ReqNodeList':'(null)','ExcNodeList':'(null)','StdOut':ROOT+f'/arms/{i:03}/job-{job}.stdout',
        'StdErr':ROOT+f'/arms/{i:03}/job-{job}.stderr'}
    need(all(f.get(k)==v for k,v in expected.items()) and f.get('NumNodes') in ('1','1-1')
         and re.fullmatch(r'<USER>\([0-9]+\)',f.get('UserId','')) and not any(k.startswith('Array') for k in f),
         'Exact held baseline job admission differs')
    need(f.get('Dependency') in (['(null)'] if dependency is None else ['afterok:'+dependency,'afterok:'+dependency+'(unfulfilled)']),
         'Concurrency dependency differs')
    mem={str(j['memory_mib'])+'M'}
    if j['memory_mib']%1024==0:mem.add(str(j['memory_mib']//1024)+'G')
    tres=dict(part.split('=',1) for part in f.get('ReqTRES','').split(',') if '=' in part)
    need(set(tres)<={'cpu','mem','node','billing'} and tres.get('cpu')==str(j['cpus']) and tres.get('node')=='1'
         and tres.get('mem') in mem and f.get('MinMemoryNode') in mem,'Held memory/TRES differs')
    return f


def remote(payload):
    """Fixed stage/records/bind actions; no scheduler or scientific execution here."""
    import pwd
    need(pwd.getpwuid(os.getuid()).pw_name=='<USER>','Wrong cluster owner')
    b=payload['binding'];need(b['root']==ROOT,'Wrong stage')
    approval=json.loads(payload['approval']);authority(approval,payload['review'].encode(),b)
    root=Path(ROOT);need(root.parent.resolve()==root.parent,'Canonical stage parent required')
    action=payload['action']
    if action=='stage':
        files={n:base64.b64decode(v,validate=True) for n,v in payload['files'].items()}
        need(binding(files)==b,'Stage binding differs');batch=json.loads(files['batch.json']);check_batch(batch,files)
        need(sha(read(batch['freeze']['path']))==batch['freeze']['sha256'],'Actual complete freeze changed')
        readiness(batch,all_outputs=True)
        root.mkdir()
        for name,data in files.items():
            rel=Path(name);need(not rel.is_absolute() and '..' not in rel.parts and str(rel)==name,'Unsafe package member')
            p=root/rel;p.parent.mkdir(parents=True,exist_ok=True)
            with p.open('xb') as out:out.write(data);out.flush();os.fsync(out.fileno())
            p.chmod(0o444);need(sha(read(p))==b['files'][name],'Staged file differs')
        for i in range(len(batch['jobs'])):(root/f'arms/{i:03}').mkdir(parents=True)
        (root/'records').mkdir();write(root/'records/stage-complete.json',{'binding':b})
        return {'passed':True,'binding':b}
    files={n:read(root/n) for n in b['files']};need(binding(files)==b,'Staged closure changed')
    batch=json.loads(files['batch.json']);check_batch(batch,files)
    need(json.loads(read(root/'records/stage-complete.json'))=={'binding':b},'Stage receipt differs')
    need(sha(read(batch['freeze']['path']))==batch['freeze']['sha256'],'Frozen retention changed')
    if action=='preflight':
        readiness(batch,all_outputs=payload.get('initial',False),slot=payload.get('slot'))
        return {'passed':True}
    if action in ('record','get','record_batch','get_batch'):
        items=payload.get('items') if action.endswith('_batch') else [payload]
        need(isinstance(items,list) and 1<=len(items)<=len(batch['jobs']),'Finite record batch required')
        names=[x['name'] for x in items];need(len(set(names))==len(names),'Duplicate batch record')
        return_values=[]
        for item in items:
            name=item['name'];need(re.fullmatch(r'(submission-intent|submitted|admission-intent|admitted|release-intent|released)-[0-9]{3}',name),
                                     'Unexpected record name')
            phase,index=name.rsplit('-',1);i=int(index);need(i<len(batch['jobs']),'Unknown slot')
            path=root/'records'/f'{name}.json'
            if action.startswith('get'):
                return_values.append(json.loads(read(path)));continue
            phases=['submission-intent','submitted','admission-intent','admitted','release-intent','released']
            if phase!='submission-intent':
                previous=json.loads(read(root/'records'/(phases[phases.index(phase)-1]+'-'+index+'.json')))
                if 'job_id' in previous:need(item['document']['job_id']==previous['job_id'],'Job identity changed')
            if phase=='release-intent':need((root/'controls-bound.json').is_file(),'Execution controls not independently bound')
            need(item['document']['binding']==b,'Record binding differs')
            write(path,item['document']);return_values.append(item['document'])
        return return_values if action.endswith('_batch') else return_values[0]
    if action=='bind':
        release=json.loads(payload['release']);authority(release,payload['release_review'].encode(),b,release=True)
        controls={n:base64.b64decode(v,validate=True) for n,v in payload['controls'].items()}
        admitted=[json.loads(read(root/f'records/admitted-{i:03}.json')) for i in range(len(batch['jobs']))]
        validate_controls(batch,files,controls,admitted,release)
        readiness(batch,all_outputs=True)
        for n,data in controls.items():
            p=root/n
            with p.open('xb') as out:out.write(data);out.flush();os.fsync(out.fileno())
            p.chmod(0o444)
        write(root/'controls-bound.json',{'binding':b,'release_sha256':sha(payload['release'].encode()),
             'control_files':{n:sha(v) for n,v in controls.items()}})
        return {'passed':True}
    raise ValueError('Unknown host operation')


def validate_controls(batch,files,controls,admitted,release):
    need(len(admitted)==1 and release.get('admitted')==admitted and release.get('control_files')=={n:sha(v) for n,v in controls.items()},'Exact actual admission release required')
    pre='arms/000/';need(set(controls)=={pre+n for n in ('plan.json','approval.json','review.txt','resources.json')} and sum(map(len,controls.values()))<=16<<20,'Finite exact controls required')
    p=json.loads(controls[pre+'plan.json']);expected=json.loads(files['templates/000.json'])
    expected['resources']['job_id']=admitted[0]['job_id'];expected['resource_readiness']={'path':ROOT+'/'+pre+'resources.json','sha256':sha(controls[pre+'resources.json'])}
    need(p==expected,'Only actual held job/resource bindings may change')
    a=json.loads(controls[pre+'approval.json']);pref={'path':ROOT+'/'+pre+'plan.json','sha256':sha(controls[pre+'plan.json'])}
    need(a.get('passed') is True and a.get('plan')==pref and a.get('runner_sha256')==RUNNER_SHA
        and a.get('resources')==p['resources'] and a.get('read_inventory')==p['read_inventory'] and a.get('seal')==p['seal'] and a.get('labels')==p['labels']
        and a.get('full_retention_review')==p['full_retention_review'] and independent(a.get('reviewer_worker')) and independent(a.get('reviewer_session')) and a.get('reviewer_model')
        and a.get('review')=={'path':ROOT+'/'+pre+'review.txt','sha256':sha(controls[pre+'review.txt'])}
        and all(a.get(k) is True for k in ('execution_authorized','single_label_join_authorized','score_authorized'))
        and all(a.get(k) is False for k in ('retry_authorized','fit_authorized','prediction_authorized','seal_authorized','outcome_release_authorized')),'Exact independent single opening approval required')
    a=json.loads(controls[pre+'resources.json'])
    need(a.get('passed') is True and a.get('resources')==p['resources'] and a.get('freeze')==p['freeze'] and a.get('arm_id')=='R2'
        and a.get('bounds')==p['bounds'] and a.get('read_inventory')==p['read_inventory']
        and a.get('all_prepared_predictions_and_bootstrap_memory_fit') is True
        and a.get('shared_storage_reservation_bytes',0)>=p['bounds']['output_total_bytes'] and a.get('free_floor_bytes',0)>=64<<30
        and independent(a.get('reviewer_worker')) and independent(a.get('reviewer_session')),'Exact one-job resource review required')


def scheduler_script(batch,mode,jobs=None):
    """Only Slurm external commands and shell builtins run on the dispatch host."""
    need(mode in ('submit','readback') and 1<=len(batch['jobs'])<=128,'Finite scheduler operation required')
    if mode=='readback':
        need(isinstance(jobs,list) and len(jobs)==len(batch['jobs']) and len(set(jobs))==len(jobs)
             and all(re.fullmatch('[1-9][0-9]*',j) for j in jobs),'Exact actual job identities required')
    lines=['set -u']
    for i in range(len(batch['jobs'])):
        if mode=='submit':
            argv=submit_argv(batch,i,None)
            command=shlex.join(argv[:-1])
            if i>=batch['max_concurrent_arms']:
                prior=i-batch['max_concurrent_arms']
                command+=' --dependency=afterok:"$job_'+f'{prior:03}'+'" --kill-on-invalid-dep=yes'
            command+=' '+shlex.quote(argv[-1])
        else:command=shlex.join(['scontrol','-o','show','job',jobs[i]])
        lines.extend(['if result=$('+command+'); then status=0; else status=$?; fi',
            "printf '%s\\t%s\\t%s\\n' '"+str(i)+"' \"$status\" \"$result\"",
            '[ "$status" -eq 0 ] || exit "$status"'])
        if mode=='submit':
            lines.extend(['case "$result" in ""|*[!0-9]*|0*) exit 65;; esac',f'job_{i:03}=$result'])
    return '\n'.join(lines)+'\n'


class Client:
    def __init__(self,files,approval,review,records,transport=h.command):
        self.files=files;self.batch=json.loads(files['batch.json']);check_batch(self.batch,files)
        self.binding=binding(files);self.approval=approval;self.review=review
        authority(json.loads(approval),review,self.binding)
        self.records=Path(records);self.records.mkdir(parents=True,exist_ok=True)
        self.transport=transport
    def save(self,name,data):write(self.records/(name+'.json'),data)
    def host(self,action,**extra):
        payload={'binding':self.binding,'approval':self.approval.decode(),'review':self.review.decode(),'action':action,
                 'source':self.files['client.py'].decode(),'helper':self.files['reviewed_transport.py'].decode(),**extra}
        code="import json,sys; p=json.load(sys.stdin); ns={'__name__':'baseline_remote','__file__':'<stdin>','_HELPER_SOURCE':p['helper'].encode()}; exec(compile(p['source'],'<reviewed-client>','exec'),ns); print(json.dumps(ns['remote'](p),sort_keys=True))"
        result=self.transport([BOOT,'-I','-S','-B','-c',code],host='<BATCH_HOST>',data=json.dumps(payload))
        self.save('host-'+str(len(list(self.records.glob('host-*.json')))),{'action':action,**result})
        need(result['returncode']==0,'Host action failed/uncertain; never retry');return json.loads(result['stdout'])
    def record(self,phase,i,document):
        name=f'{phase}-{i:03}';self.save(name,document);return self.host('record',name=name,document=document)
    def scheduler(self,name,args):
        result=self.transport(['env','-i','PATH=/usr/local/bin:/usr/bin:/bin','LANG=C.UTF-8',*args],host='<SUBMIT_HOST>')
        self.save(name,result);need(result['returncode']==0,'Scheduler action failed/uncertain; never retry');return result['stdout']
    def stage(self):
        self.save('stage-intent',{'binding':self.binding})
        return self.host('stage',files={n:base64.b64encode(v).decode() for n,v in self.files.items()})
    def record_batch(self,phase,documents):
        items=[]
        for i,d in enumerate(documents):
            name=f'{phase}-{i:03}';self.save(name,d);items.append({'name':name,'document':d})
        return self.host('record_batch',items=items)
    def get_batch(self,phase):
        return self.host('get_batch',items=[{'name':f'{phase}-{i:03}'} for i in range(len(self.batch['jobs']))])
    def scheduler_batch(self,mode,jobs=None):
        script=scheduler_script(self.batch,mode,jobs)
        result=self.transport(['env','-i','PATH=/usr/local/bin:/usr/bin:/bin','LANG=C.UTF-8',
            'bash','-p','-c',script],host='<SUBMIT_HOST>')
        self.save(mode+'-batch-response-'+str(len(list(self.records.glob(mode+'-batch-response-*.json')))),result)
        need(result['returncode']==0,'Scheduler batch failed/uncertain; never retry')
        rows=[]
        for line in result['stdout'].splitlines():
            fields=line.split('\t',2)
            need(len(fields)==3 and fields[0].isdigit() and fields[1]=='0','Malformed scheduler batch frame')
            rows.append({'slot':int(fields[0]),'returncode':0,'stdout':fields[2]+'\n'})
        need(len(rows)==len(self.batch['jobs']) and [x['slot'] for x in rows]==list(range(len(rows))),
             'Incomplete scheduler batch; never retry')
        return rows
    def submit_held(self):
        self.host('preflight',initial=True)
        self.record_batch('submission-intent',[{'binding':self.binding} for _ in self.batch['jobs']])
        rows=self.scheduler_batch('submit');jobs=[];submitted=[]
        for i,row in enumerate(rows):
            need(re.fullmatch('[1-9][0-9]*\n?',row['stdout']),'Uncertain submission; never resubmit')
            dep=jobs[i-self.batch['max_concurrent_arms']] if i>=self.batch['max_concurrent_arms'] else None
            argv=submit_argv(self.batch,i,dep)
            job=row['stdout'].strip();need(job not in jobs,'Duplicate job identity');jobs.append(job)
            submitted.append({'binding':self.binding,'job_id':job,'dependency':dep,'argv':argv})
        self.record_batch('submitted',submitted);return jobs
    def admit(self):
        previous=self.get_batch('submitted')
        documents=[{'binding':self.binding,'job_id':d['job_id'],'dependency':d['dependency']} for d in previous]
        self.record_batch('admission-intent',documents)
        rows=self.scheduler_batch('readback',[d['job_id'] for d in documents]);admitted=[]
        for i,(d,row) in enumerate(zip(documents,rows)):
            fields=held(row['stdout'],self.batch,i,d['job_id'],d['dependency'])
            admitted.append({**d,'scheduler':fields,'scheduler_text_sha256':sha(row['stdout'].encode())})
        return self.record_batch('admitted',admitted)
    def release(self,controls,approval,review):
        admitted=self.get_batch('admitted')
        authority(json.loads(approval),review,self.binding,release=True)
        validate_controls(self.batch,self.files,controls,admitted,json.loads(approval))
        self.save('bind-intent',{'binding':self.binding,'release_sha256':sha(approval)})
        self.host('bind',controls={n:base64.b64encode(v).decode() for n,v in controls.items()},
                  release=approval.decode(),release_review=review.decode())
        documents=[{'binding':self.binding,'job_id':d['job_id']} for d in admitted]
        self.record_batch('release-intent',documents)
        rows=self.scheduler_batch('readback',[d['job_id'] for d in admitted])
        for i,(d,row) in enumerate(zip(admitted,rows)):
            held(row['stdout'],self.batch,i,d['job_id'],d['dependency'])
        self.host('preflight',initial=True)
        self.scheduler('release-response',['scontrol','release',','.join(d['job_id'] for d in admitted)])
        self.record_batch('released',documents)


def package(directory):
    directory=Path(directory).resolve();batch=json.loads(read(directory/'batch.json'))
    names=set(batch['source_files']) | {'runner.py','pins.json','bootstrap.py','client.py','reviewed_transport.py',
        'freeze-capture.json','batch.json'} | {j['template'] for j in batch['jobs']} | {
        f'job-{i:03}.sbatch' for i in range(len(batch['jobs']))}
    need(len(names)<=4096,'Finite package closure required')
    for n in names:
        p=Path(n);need(not p.is_absolute() and '..' not in p.parts and str(p)==n,'Unsafe package path')
    files={n:read(directory/n) for n in names}
    check_batch(batch,files)
    need(sha(files['client.py'])==sha(Path(__file__).read_bytes()),'Executing client differs from bound package')
    return files


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('stage','submit-held','admit','release'))
    for n in ('package','records','approval','approval-sha256','review'):p.add_argument('--'+n,required=True)
    for n in ('controls','release-approval','release-sha256','release-review'):p.add_argument('--'+n)
    a=p.parse_args();approval=read(a.approval)
    need(sha(approval)==a.approval_sha256,'External transport authority hash differs')
    client=Client(package(a.package),approval,read(a.review),a.records)
    if a.action=='release':
        need(all((a.controls,a.release_approval,a.release_sha256,a.release_review)),'Actual independently bound release required')
        release=read(a.release_approval);need(sha(release)==a.release_sha256,'Release authority hash differs')
        controls={f'arms/{i:03}/{n}':read(Path(a.controls)/f'arms/{i:03}'/n)
            for i in range(len(client.batch['jobs'])) for n in ('plan.json','approval.json','review.txt','resources.json')}
        result=client.release(controls,release,read(a.release_review))
    else:result=getattr(client,a.action.replace('-','_'))()
    print(json.dumps(result,sort_keys=True))
