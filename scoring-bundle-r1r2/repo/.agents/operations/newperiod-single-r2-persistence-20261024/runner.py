"""One admitted R2 CPU execution, all retained components before one label opening.

No freeze, source selection, prediction, fit, retry or public-result release.
"""
import contextlib,hashlib,importlib.metadata,json,os,posixpath,resource,signal,stat,sys,types
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT='<FORECAST_ROOT>/data-custodian/single-R2-v1'
HELPER_SHA='9c41f26746205037f3561f836fa51e91c1ab609a18368caf1fcf57b57a3db307'
COMPONENTS={'baseline':('components/baseline/consumer.py','cd2a20467fbc8c77f981a6c3e0b4c5f5cd77b6b5cf38fa315d9ccabb2898aa71'),'composition':('components/composition/compose.py','b4952f08025194700f8612771561aada3c37fe25feefa18e534154e8e59bebfe'),
 'origin':('components/origin/consumer.py','43585d446b35f2c9c6cf15029117ac72eba91b51dffcad25b53f0cf440f5482f')}
PINS_SHA='2e438517d9d0ed58ab7c626f3624bd48ea1bddacf8ac38b5ec30a1d6b87d3ca9'
AUTHORS={'/root/metadata_check_review','/metadata_check_review','/root/deadline_audit','/deadline_audit'}
BOOTSTRAP={'repetitions':10000,'bootstrap_seed':1701,'alpha':0.05}

def need(ok,why):
 if not ok:raise ValueError(why)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def source(path,digest,name):
 p=Path(path);need(p.resolve()==p and p.is_file() and p.stat().st_size<=4<<20,'Finite canonical operational source required')
 raw=p.read_bytes();need(len(raw)<=4<<20 and sha(raw)==digest,'Reviewed operational source differs')
 m=types.ModuleType(name);m.__file__=str(path);exec(compile(raw,str(path),'exec'),m.__dict__);return m
helper=source(HERE/'runtime_helpers.py',HELPER_SHA,'R2_original_helpers')
raw,document,exclusive=helper.raw,helper.document,helper.exclusive

def independent(value):
 return isinstance(value,str) and value and not any(c.isspace() for c in value) and posixpath.normpath('/'+value.casefold().lstrip('/')) not in AUTHORS|{'/','/.'}

def authority(pref,aref):
 plan= document(pref);a=document(aref)
 need(plan['kind']=='newperiod_single_R2_execution_v1' and plan['arm_id']=='R2'
  and a.get('passed') is True and a.get('plan')==pref and a.get('runner_sha256')==sha(Path(__file__).read_bytes())
  and a.get('resources')==plan['resources'] and a.get('read_inventory')==plan['read_inventory']
  and a.get('seal')==plan['seal'] and a.get('labels')==plan['labels'] and a.get('full_retention_review')==plan['full_retention_review']
  and independent(a.get('reviewer_worker')) and independent(a.get('reviewer_session')) and a.get('reviewer_model')
  and all(a.get(k) is True for k in ('execution_authorized','single_label_join_authorized','score_authorized'))
  and all(a.get(k) is False for k in ('retry_authorized','fit_authorized','prediction_authorized','seal_authorized','outcome_release_authorized')),
  'Exact independent single-R2 authority required')
 raw(a['review'],2<<20)
 return plan

def runtime(plan):
 r=plan['resources'];b=plan['bounds']
 need(set(r)=={'cpus','memory_mib','wall_seconds','job_id'} and all(type(r[k]) is int and r[k]>0 for k in ('cpus','memory_mib','wall_seconds'))
  and r['memory_mib']>=1024 and r['cpus']<=128 and r['memory_mib']<=2097152 and r['wall_seconds']<=86400,'Finite actual CPU allocation required')
 need(set(b)=={'metadata_bytes','input_bytes','checkpoint_bytes','label_bytes','runtime_file_bytes','total_read_bytes','total_unique_bytes','output_file_bytes','output_total_bytes','access_log_bytes','input_view_cache_bytes'}
  and all(type(v) is int and v>0 for v in b.values()) and b['output_total_bytes']>=6*b['output_file_bytes']+b['access_log_bytes'],'Finite complete read/output bounds including primary-score sidecar required')
 e=os.environ
 need(e.get('SLURM_JOB_ID')==str(r['job_id']) and e.get('SLURM_JOB_PARTITION')=='cpu'
  and e.get('SLURM_CPUS_PER_TASK')==str(r['cpus']) and e.get('SLURM_MEM_PER_NODE')==str(r['memory_mib'])
  and e.get('SLURM_RESTART_COUNT','0')=='0' and 'SLURM_ARRAY_TASK_ID' not in e,'Exact non-requeued singleton allocation required')
 for name in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','POLARS_MAX_THREADS'):need(e.get(name)==str(r['cpus']),'Exact thread allocation required')
 admission=document(plan['resource_readiness'])
 need(admission.get('passed') is True and admission.get('resources')==r and admission.get('freeze')==plan['freeze']
  and admission.get('arm_id')=='R2' and admission.get('bounds')==b and admission.get('read_inventory')==plan['read_inventory']
  and admission.get('all_prepared_predictions_and_bootstrap_memory_fit') is True and admission.get('shared_storage_reservation_bytes',0)>=b['output_total_bytes']
  and admission.get('free_floor_bytes',0)>=64<<30 and independent(admission.get('reviewer_worker')) and independent(admission.get('reviewer_session')),
  'Actual whole-batch memory/storage admission required')
 rt=document(plan['runtime'])
 need(rt.get('passed') is True and rt['python']==helper.reference(sys.executable)
  and rt['versions']=={n:importlib.metadata.version(n) for n in ('numpy','polars','torch')} and rt['files'],'Exact numerical runtime required')
 for ref in rt['files']:raw(ref,b['runtime_file_bytes'])
 return admission


class Reader:
 """Finite exact byte objects; hash-only reuse never caches mutable payloads."""
 def __init__(self,inventory,bounds,log,labels):
  need(isinstance(inventory,list) and inventory and len(inventory)<=1000000,'Finite source inventory required')
  self.items={x['path']:x for x in inventory};need(len(self.items)==len(inventory),'Duplicate source path')
  self.bounds,self.log,self.labels=bounds,log,labels;self.verified={};self.read_bytes=0;self.label_reads=0;self.input_views={};self.input_view_bytes=0;self.input_loads=0;self.input_reuses=0
  for item in inventory:
   need(set(item)=={'path','sha256','size_bytes','kind'} and item['kind'] in ('metadata','input','checkpoint','label')
    and type(item['size_bytes']) is int and 0<item['size_bytes']<=bounds[item['kind']+'_bytes']
    and isinstance(item['sha256'],str) and len(item['sha256'])==64 and set(item['sha256'])<=set('0123456789abcdef'),'Finite typed input reference required')
   p=Path(item['path']);need(p.is_absolute() and p.resolve()==p,'Canonical explicit input path required')
  need(sum(x['size_bytes'] for x in inventory)<=bounds['total_unique_bytes'],'Unique source byte budget exceeded')
  need([{'path':x['path'],'sha256':x['sha256']} for x in inventory if x['kind']=='label']==[labels],'Exactly one explicit label artifact required')
 def item(self,path,expected=None):
  p=str(Path(path));item=self.items.get(p);need(item is not None and (expected is None or expected==item['sha256']),'Read outside exact source inventory')
  return item
 def identity(self,path):
  p=Path(path);need(p.resolve()==p,'Source path changed');s=p.lstat();need(stat.S_ISREG(s.st_mode),'Source is not regular')
  return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
 def consume(self,item,purpose,*,hash_only=False):
  path=item['path'];need(item['kind']!='label' or not hash_only,'Label cannot be preflight hashed')
  identity=self.identity(path);need(identity[2]==item['size_bytes'],'Source size differs')
  prior=self.verified.get(path)
  if prior is not None:need(prior==(item['sha256'],identity),'Previously verified source identity changed')
  if hash_only and prior is not None:return item['sha256']
  if item['kind']=='label':
   need(purpose=='Custodian label table' and self.label_reads==0,'Only original once-only label opening allowed');self.label_reads+=1
  need(self.read_bytes+item['size_bytes']<=self.bounds['total_read_bytes'],'Aggregate read byte budget exceeded')
  self.log(path,purpose)
  h=hashlib.sha256();chunks=[]
  fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
  with os.fdopen(fd,'rb') as stream:
   s=os.fstat(stream.fileno());opened=(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
   need(opened==identity and stat.S_ISREG(s.st_mode),'Source changed at open')
   remaining=item['size_bytes'];seen=0
   while remaining:
    block=stream.read(min(1<<20,remaining));need(bool(block),'Truncated exact input');remaining-=len(block);seen+=len(block);h.update(block)
    if not hash_only:chunks.append(block)
   need(stream.read(1)==b'' and self.identity(path)==identity,'Source changed during read')
  need(h.hexdigest()==item['sha256'],'Source hash differs');self.read_bytes+=seen;self.verified[path]=(item['sha256'],identity)
  return item['sha256'] if hash_only else b''.join(chunks)
 def bytes(self,ref,purpose):return self.consume(self.item(ref['path'],ref['sha256']),purpose)
 def json(self,ref,purpose):return json.loads(self.bytes(ref,purpose))
 def verify(self,path):return self.consume(self.item(path),'original whole-batch hash verification',hash_only=True)
 def input(self,ref,purpose,loader):
  """Cache only immutable event/candidate/seed projections, never graph payloads."""
  item=self.item(ref['path'],ref['sha256']);need(item['kind']=='input','Only explicitly admitted label-free inputs can be cached')
  path=item['path'];identity=self.identity(path);prior=self.input_views.get(path)
  if prior is not None:
   digest,previous,value,cost=prior
   need(digest==item['sha256'] and previous==identity,'Cached input identity changed')
   self.log(path,purpose+' (verified immutable input-view reuse)');self.input_reuses+=1
  else:
   event=loader(self.bytes(ref,purpose));self.input_loads+=1
   need(set(event)=={'event_id','asn','seed_asns'} and isinstance(event['event_id'],str),'Original minimal input projection required')
   value=(event['event_id'],tuple(event['asn']),tuple(event['seed_asns']))
   need(all(type(v) is int for rows in value[1:] for v in rows),'Original integer candidate/seed projection required')
   # Include conservative dictionary/key/identity overhead; no unbounded tensors
   # are retained. Fail on an oversized single projection; evict oldest otherwise.
   cost=2048+sys.getsizeof(path)+sum(sys.getsizeof(x) for x in value)+sum(sys.getsizeof(v) for rows in value[1:] for v in rows)
   limit=self.bounds['input_view_cache_bytes'];need(cost<=limit,'Single immutable view exceeds admitted cache budget')
   while self.input_view_bytes+cost>limit:
    oldest=next(iter(self.input_views));self.input_view_bytes-=self.input_views.pop(oldest)[3]
   need(self.identity(path)==identity,'Input changed during projection')
   self.input_views[path]=(item['sha256'],identity,value,cost);self.input_view_bytes+=cost
  # Consumers get independent mutable lists; cached values remain immutable.
  return dict(event_id=value[0],asn=list(value[1]),seed_asns=list(value[2]))



def log_function(path,limit):
 """Reuse original custody logger and require durable completion before reads."""
 from custodian_access_log import log_read
 start=Path(path).stat().st_size if Path(path).exists() else 0
 def log(source_path,purpose):
  size=Path(path).stat().st_size if Path(path).exists() else 0
  need(size>=start and size-start+len(str(source_path))+len(purpose)+2048<=limit,'Aggregate access-log budget exceeded')
  log_read(source_path,purpose,files=1)
  with Path(path).open('rb') as f:os.fsync(f.fileno())
  fd=os.open(Path(path).parent,os.O_RDONLY|os.O_DIRECTORY)
  try:os.fsync(fd)
  finally:os.close(fd)
 return log


def components():return {name:source(HERE/relative,digest,'R2_'+name) for name,(relative,digest) in COMPONENTS.items()}

def pooled_evidence(value,reader):
 """Materialize explicit metadata refs at the original pure-function boundary."""
 if 'pooled_target_lineage' not in value:return value
 line=value['pooled_target_lineage']
 need(set(line)=={'masters','collector_inventory','source_inventories','recipe'} and set(line['masters'])==set(line['source_inventories'])=={'30','60'},'Exact pooled metadata reference envelope required')
 def bound(ref):
  need(isinstance(ref,dict) and set(ref)=={'path','sha256'} and reader.item(ref['path'],ref['sha256'])['kind']=='metadata','Pooled scope requires explicit metadata refs')
  return dict(ref=ref,raw=reader.bytes(ref,'pooled source/target lineage metadata'))
 value=dict(value);value['pooled_target_lineage']=dict(masters={h:bound(x) for h,x in line['masters'].items()},
  source_inventories={h:bound(x) for h,x in line['source_inventories'].items()},collector_inventory=bound(line['collector_inventory']),recipe=bound(line['recipe']))
 return value


def persist_primary_scores(plan,arms,rows,identities):
 """Write already computed scores, streaming under the admitted extra file cap.

 No labels are opened, metrics computed, cohorts filtered or RNG calls made.
 References to original score objects are streamed directly without a second
 decoded population copy. A failed partial file is preserved, never retried.
 """
 path=Path(plan['primary_scores_output']);records=Path(plan['records'])
 need(path==records/'primary-scores.json' and path.resolve()==path and records.is_dir(),'Exact primary-score sidecar path required')
 bound=plan['bounds']['output_file_bytes']
 need(type(bound) is int and bound>0 and plan['bounds']['output_total_bytes']>=6*bound+plan['bounds']['access_log_bytes'],'Extra score-file reservation absent')
 need(set(arms)==set(identities),'Primary score identity map differs')
 for model,by_horizon in arms.items():
  need(set(map(str,by_horizon))==set(identities[model]),'Primary score horizon map differs')
  for horizon,seeds in by_horizon.items():
   need(len(seeds)==len(identities[model][str(horizon)]) and all([r['event_id'] for r in one]==[r['event_id'] for r in rows[horizon]] for one in seeds),'Primary score rows or retained seed identities differ')
 document=dict(kind='newperiod_primary_computed_scores_v1',seal=plan['seal'],freeze=plan['freeze'],
  arm_spec=plan['arm_spec'],labels=plan['labels'],source_closure=plan['source_closure'],
  primary_report_path=plan['primary_output'],identities=identities,arms=arms,rows=rows,
  metrics_recomputed=False,additional_label_reads=0,outcome_release_authorized=False)
 digest=hashlib.sha256();size=0
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb') as stream:
  encoder=json.JSONEncoder(sort_keys=True,separators=(',',':'),allow_nan=False)
  for token in encoder.iterencode(document):
   raw=token.encode('utf-8');need(size+len(raw)<=bound,'Primary score sidecar exceeds admitted file bound')
   stream.write(raw);digest.update(raw);size+=len(raw)
  need(size+1<=bound,'Primary score sidecar exceeds admitted file bound')
  stream.write(b'\n');digest.update(b'\n');size+=1;stream.flush();os.fsync(stream.fileno())
 parent=os.open(records,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(parent)
 finally:os.close(parent)
 return dict(path=str(path),sha256=digest.hexdigest(),size_bytes=size,bound_bytes=bound)


def evaluate(plan,reader,original,custody,components,*,score_receipts=None):
 """Original per-arm checks/numerics, scoped byte readers and fixed whole grid."""
 need({k:plan[k] for k in BOOTSTRAP}==BOOTSTRAP,'Original production bootstrap parameters required')
 comp,origin=components['composition'],components['origin']
 frozen=reader.json(plan['freeze'],'complete retention freeze');seal=reader.json(plan['seal'],'complete prediction seal')
 need(seal['spec_path']==plan['freeze']['path'] and seal['spec_sha256']==plan['freeze']['sha256'],'Actual freeze/seal differs')
 count_freeze=reader.json(plan['count_freeze'],'count retention')
 member_freezes={k:reader.json(v,'membership retention '+k) for k,v in plan['membership_freezes'].items()}
 evidence={k:pooled_evidence(reader.json(v,'membership evidence '+k),reader) for k,v in plan['evidence'].items()}
 stable_freeze=reader.json(plan['stable_freeze'],'stable retention');stable_evidence=reader.json(plan['stable_evidence'],'stable evidence')
 origin_freeze=reader.json(plan['origin_freeze'],'origin retention');origin_evidence=reader.json(plan['origin_evidence'],'origin evidence')
 baseline_freeze=reader.json(plan['baseline_freeze'],'additional baseline retention');baseline_evidence=pooled_evidence(reader.json(plan['baseline_evidence'],'additional baseline evidence'),reader)
 primary=comp.components()['count'].private_primary(original)
 derived=primary.derive_new_period_arms(frozen)
 # The original evaluator computes these objects once, immediately before its
 # existing contrast report. Capture only at that boundary, in its private copy.
 old_contrasts=primary._contrast_families;score_calls=[]
 def capture_scores(arms,rows,*args,**kwargs):
  need(not score_calls,'Primary contrast boundary invoked more than once')
  score_calls.append(None)
  result=old_contrasts(arms,rows,*args,**kwargs)
  receipt=persist_primary_scores(plan,arms,rows,derived)
  score_calls[0]=receipt
  return result
 expected={x for by_horizon in derived.values() for ids in by_horizon.values() for x in ids}
 families=[count_freeze,stable_freeze,origin_freeze,baseline_freeze,*member_freezes.values()]
 for family in families:
  ids=[a['arm_id'] for a in family['arms']];need(not expected.intersection(ids),'Arm assigned to multiple evaluation components');expected.update(ids)
 retained=[a['arm_id'] for a in frozen['arms']+frozen.get('retained_failures',[])]
 need(len(retained)==len(set(retained)) and expected==set(retained),'Complete retained batch has unhandled or duplicated cells')
 review=reader.json(plan['full_retention_review'],'full retained-science review')
 need(review.get('passed') is True and review.get('freeze')==plan['freeze'] and review.get('seal')==plan['seal']
  and review.get('all_retained_arms')==sorted(expected) and review.get('pre_R2_implementation_binding')==plan['pre_R2_implementation_binding']
  and independent(review.get('reviewer_worker')) and independent(review.get('reviewer_session')) and review.get('reviewer_model'),
  'Independent exact full retained-batch review required')
 reader.json(plan['pre_R2_implementation_binding'],'required pre-R2 implementation freeze')
 prepared_origin=origin.prepare_sealed(frozen,seal,origin_freeze,origin_evidence,reader.json,
  lambda ref,purpose:reader.input(ref,purpose,original.default_input_loader))
 prepared_baseline=components['baseline'].prepare_sealed(frozen,seal,baseline_freeze,baseline_evidence,reader.json,lambda ref,purpose:reader.input(ref,purpose,original.default_input_loader))
 captured=[]
 def bound_json(path,digest,purpose):
  value=reader.json(dict(path=str(path),sha256=digest),purpose)
  if purpose=='Custodian label table':captured.append(value)
  return value
 class BoundPath(type(Path())):
  def read_bytes(self):return reader.consume(reader.item(str(self)),'original one-opening marker metadata')
 primary.Path=BoundPath
 primary.bound_json=bound_json
 primary.hashed_bytes=lambda path:(reader.consume(reader.item(path),'original bound metadata'),reader.item(path)['sha256'])
 primary._bound_bytes=lambda path,digest,purpose:reader.input(dict(path=str(path),sha256=digest),purpose,original.default_input_loader) if purpose=='Custodian input' else reader.bytes(dict(path=str(path),sha256=digest),purpose)
 primary.sha=lambda path:reader.verify(path)
 # Original authorize_outcome_join imports this exact admitted module. Only its
 # I/O primitives are substituted in the isolated worker; its checks are intact.
 old_sha,old_hashed=custody.sha,custody.hashed_json
 custody.sha=reader.verify
 custody.hashed_json=lambda path:(reader.json(dict(path=str(path),sha256=reader.item(path)['sha256']),'original custody metadata'),reader.item(path)['sha256'])
 primary._contrast_families=capture_scores
 try:
  result=comp.evaluate(primary,(plan['seal']['path'],plan['seal']['sha256'],plan['arm_spec']['path'],plan['arm_spec']['sha256'],plan['labels']['path'],plan['labels']['sha256'],plan['primary_output']),
   dict(extension_decision_path=plan['extension_decision']['path'],expected_extension_decision_sha256=plan['extension_decision']['sha256'],
    slice_rules_path=plan['slice_rules']['path'],expected_slice_rules_sha256=plan['slice_rules']['sha256'],issue_time_tables=plan['issue_time_tables'],
    repetitions=plan['repetitions'],seed=plan['bootstrap_seed'],alpha=plan['alpha'],access_log=reader.log,input_loader=lambda view:view),
   custody=frozen,seal=seal,count_freeze=count_freeze,membership_freezes=member_freezes,evidence=evidence,
   stable_freeze=stable_freeze,stable_evidence=stable_evidence,read_json=reader.json,
   read_input=lambda ref,purpose:reader.input(ref,purpose,original.default_input_loader),original_score_curves=__import__('bgbench.forecast_retrospective_scoring',fromlist=['score_curves']).score_curves)
 finally:
  custody.sha,custody.hashed_json=old_sha,old_hashed
  primary._contrast_families=old_contrasts
 need(len(captured)==1 and reader.label_reads==1,'Original one label opening missing')
 need(len(score_calls)==1 and score_calls[0] is not None,'Exactly one complete primary score sidecar required')
 if score_receipts is not None:score_receipts.append(score_calls[0])
 result['origin']=origin.evaluate(prepared_origin,{family:captured[0][family] for family in origin.FAMILIES})
 result['additional_baselines']=components['baseline'].evaluate(prepared_baseline,captured[0])
 result['covered_secondary_families']+=['additional_baselines',*origin.FAMILIES]
 result['kind']='newperiod_all_retained_R2_evaluation_v1';result['full_newperiod_coverage']=True
 result['actual_execution_authorized']=False # Custodian result is not public release authority.
 return result


def scientific_modules(plan):
 need(sys.flags.isolated and sys.dont_write_bytecode and not sys.flags.optimize,'Fresh isolated nonoptimized source runtime required')
 pins_raw=(HERE/'pins.json').read_bytes();need(sha(pins_raw)==PINS_SHA,'Fixed scientific source pins changed')
 pins=json.loads(pins_raw);repo=Path(plan['source_root'])
 helper.install_source_imports(repo,plan['source_closure'],pins)
 access=pins['custodian_access_log'];access_path=repo/access['path']
 module=source(access_path,access['sha256'],'custodian_access_log');module.LOG=Path(plan['access_log']);sys.modules['custodian_access_log']=module
 from bgbench import forecast_custodian_eval,forecast_custody
 return forecast_custodian_eval,forecast_custody


def execute(plan,reader,original,custody):
 import shutil
 records=Path(plan['records']);need(str(records)==ROOT+'/arms/000/attempt' and records.resolve()==records,'Fixed exclusive R2 attempt required')
 need(plan['primary_output']==str(records/'primary.json') and plan['result_output']==str(records/'complete-result.json') and plan['primary_scores_output']==str(records/'primary-scores.json'),'Fixed output artifacts required')
 b=plan['bounds'];need(type(b['output_file_bytes']) is int and b['output_file_bytes']>0 and b['output_total_bytes']>=6*b['output_file_bytes']+b['access_log_bytes'],'Extra score-file reservation absent')
 # Metadata-only output/space preconditions; no labels opened here.
 need(not records.exists() and records.parent.is_dir(),'Existing R2 attempt forbids repetition')
 need(Path(plan['freeze']['path']).parent.stat().st_dev==records.parent.stat().st_dev and Path(plan['access_log']).parent.stat().st_dev==records.parent.stat().st_dev,'Marker/log/results must share admitted filesystem')
 need(shutil.disk_usage(records.parent).free>=plan['bounds']['output_total_bytes']+(64<<30),'Actual storage reservation unavailable')
 records.mkdir();exclusive(records/'intent.json',dict(seal=plan['seal'],labels=plan['labels'],resources=plan['resources'],automatic_retry_authorized=False))
 score_receipts=[]
 result=evaluate(plan,reader,original,custody,components(),score_receipts=score_receipts)
 encoded=(json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
 need(len(encoded)<=plan['bounds']['output_file_bytes'],'Complete result exceeds admitted output bound')
 with Path(plan['result_output']).open('xb') as stream:stream.write(encoded);stream.flush();os.fsync(stream.fileno())
 output=dict(path=plan['result_output'],sha256=sha(encoded))
 need(len(score_receipts)==1,'Primary score completion identity absent')
 return dict(passed=True,result=output,primary_scores=score_receipts[0],seal=plan['seal'],labels=plan['labels'],label_reads=reader.label_reads,
  bytes_read=reader.read_bytes,unique_verified_objects=len(reader.verified),input_loads=reader.input_loads,input_view_reuses=reader.input_reuses,input_view_retained_bytes=reader.input_view_bytes,outcome_release_authorized=False)


class R2Failure(ValueError):pass

def run(pref,aref):
 stage='authority';old_alarm=signal.getsignal(signal.SIGALRM);old_term=signal.getsignal(signal.SIGTERM)
 try:
  plan=authority(pref,aref)
  need(type(plan['resources']['wall_seconds']) is int and 0<plan['resources']['wall_seconds']<=86400,'Finite whole execution wall bound required')
  def interrupted(*_):raise TimeoutError('Single R2 wall bound reached')
  signal.signal(signal.SIGALRM,interrupted);signal.signal(signal.SIGTERM,interrupted);signal.alarm(plan['resources']['wall_seconds'])
  stage='runtime';runtime(plan)
  stage='scientific_source';original,custody=scientific_modules(plan)
  need(os.environ.get('CUSTODIAN_ACCESS_LOG')==plan['access_log'],'Original custody log differs')
  logpath=Path(plan['access_log']);need(logpath.is_absolute() and logpath.resolve()==logpath and not logpath.is_symlink(),'Canonical original access log required')
  need((logpath.stat().st_size if logpath.exists() else 0)+plan['bounds']['access_log_bytes']<=plan['bounds']['output_file_bytes'],'Complete access-log growth exceeds hard file limit')
  log=log_function(plan['access_log'],plan['bounds']['access_log_bytes']);log(plan['read_inventory']['path'],'exact R2 input inventory')
  inventory=document(plan['read_inventory'],plan['bounds']['metadata_bytes'])
  need(set(inventory)=={'files'} and plan['labels']['path']!=plan['access_log'],'Exact input inventory required')
  reader=Reader(inventory['files'],plan['bounds'],log,plan['labels'])
  # Per-file writes are hard bounded, including the unchanged original marker
  # and primary JSON writer. Exactly named results are separately aggregate bound.
  resource.setrlimit(resource.RLIMIT_AS,((plan['resources']['memory_mib']-512)<<20,)*2)
  resource.setrlimit(resource.RLIMIT_FSIZE,(plan['bounds']['output_file_bytes'],)*2)
  stage='single_evaluation';result=execute(plan,reader,original,custody)
  exclusive(Path(plan['records'])/'done.json',result);return result
 except BaseException:pass
 finally:
  signal.alarm(0);signal.signal(signal.SIGALRM,old_alarm);signal.signal(signal.SIGTERM,old_term)
 raise R2Failure('Single R2 execution refused at '+stage)


if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser()
 for key in ('plan','plan-sha256','approval','approval-sha256'):p.add_argument('--'+key,required=True)
 a=p.parse_args()
 print(json.dumps(run(dict(path=a.plan,sha256=a.plan_sha256),dict(path=a.approval,sha256=a.approval_sha256)),sort_keys=True))
