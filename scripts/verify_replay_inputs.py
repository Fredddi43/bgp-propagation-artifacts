"""Audit merged replay membership, comparison sets, clocks and archive coverage.

Use --scopes all for the final complete repair; named scopes audit early subsets.
This script imports no replay/measurement producer code and changes no inputs.
"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import argparse
import io
import time
import datetime as dt, hashlib, json, math, re
import polars as pl
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("run",type=Path)
parser.add_argument("--repair-root",type=Path,help="explicit final composite replay root")
parser.add_argument("--scopes",nargs="+",default=["all"])
parser.add_argument("--output",type=Path,required=True)
parser.add_argument("--wait-for-marker",type=Path,action="append",default=[])
args=parser.parse_args()
while not all(p.is_file() for p in args.wait_for_marker):
 time.sleep(10)
r=args.run
repair=args.repair_root or r/'crossday-repair'
plan_path=r/'crossday-repair-plan.json'
plan_bytes=plan_path.read_bytes()
source_hashes={'crossday-repair-plan.json':hashlib.sha256(plan_bytes).hexdigest()}
plan=json.loads(plan_bytes)
rows=[];changes={};digests={}
for scope in args.scopes:
 suffix='' if scope=='all' else '-'+scope
 for name in ['merge','input-changes']:
  p=repair/f'{name}{suffix}.json';digests[str(p.relative_to(r))]=hashlib.sha256(p.read_bytes()).hexdigest()
  values=json.loads(p.read_text())
  if name=='merge':rows.extend(values)
  else:changes.update({(v['tag'],v['event_id']):v for v in values})
assert len({(row['tag'],row['event_id']) for row in rows})==len(rows),'duplicate manifest event'
taskids={i for row in rows for i in plan['events'][(row['tag'] or 'origin')+':'+row['event_id']]['tasks']}
def task_read(i):
 relative=f'crossday-repair/tasks/{i}.json'
 payload=(r/relative).read_bytes()
 return i,json.loads(payload),relative,hashlib.sha256(payload).hexdigest()
with ThreadPoolExecutor(max_workers=24) as pool: task_rows=list(pool.map(task_read,taskids))
reports={i:report for i,report,_,_ in task_rows}
source_hashes.update({relative:digest for _,_,relative,digest in task_rows})
old={}
for year,tag in sorted({(row['year'],row['tag']) for row in rows}):
 p=r/'data/eventset'/f'{year}{"_"+tag if tag else ""}'/'events.before-crossday-repair.parquet'
 if not p.exists():p=p.with_name('events.parquet')
 source_hashes[str(p.relative_to(r))]=hashlib.sha256(p.read_bytes()).hexdigest()
 ids=[row['event_id'] for row in rows if row['year']==year and row['tag']==tag]
 table=pl.scan_parquet(p).filter(pl.col('event_id').is_in(ids)).select(pl.col('event_id'),pl.col('^set_.*$')).collect()
 old.update({(tag,v['event_id']):v for v in table.to_dicts()})
H={'d30s':30,'d1m':60,'d5m':300,'T5m':300,'d15m':900,'T15m':900,'T60m':3600,'final_2h':7200}
def stamp(s):return dt.datetime.fromisoformat(s)
def archive_start(a):
 if 'ts_start' in a:return a['ts_start']
 match=re.search(r'(?:updates|bview)\.(\d{8})\.(\d{4})',a['url'])
 return int(dt.datetime.strptime(''.join(match.groups()),'%Y%m%d%H%M').replace(tzinfo=dt.UTC).timestamp()) if match else None
def audit(row):
 eid=row['event_id'];tag=row['tag'];key=(tag,eid);change=changes[key]
 e=plan['events'][(tag or 'origin')+':'+eid]
 directory=repair/'events'/(tag or 'origin')/eid
 summary_path=directory/'summary.json'
 summary_bytes=summary_path.read_bytes()
 hashes={str(summary_path.relative_to(r)):hashlib.sha256(summary_bytes).hexdigest()}
 s=json.loads(summary_bytes)
 if row['status']=='excluded':
  assert s.get('error') and change['new_error'],(key,'missing exclusion')
  return {'merged':False,'membership_rows':0,'source_hashes':hashes}
 assert not s.get('error') and s['crossday_repair_complete'],(key,'summary status')
 assert s['measurement_repair_source_tasks']==e['tasks'],(key,'source task identity')
 lo,hi=stamp(e['w_start']).timestamp(),stamp(e['w_end']).timestamp()
 for i in e['tasks']:
  task=plan['tasks'][i];report=reports[i]
  required={t for a,b in task['intervals'] for t in range(a,b,task['step']) if t<=hi and t+task['step']>lo}
  good={archive_start(a) for a in report.get('archives',[]) if not a.get('error')}
  assert required<=good,(key,'missing event archive block',i,sorted(required-good))
  assert report['status'] in ['complete','archive_gaps'],(key,'bad task status',i)
 membership_path=directory/'membership.parquet'
 membership_bytes=membership_path.read_bytes()
 hashes[str(membership_path.relative_to(r))]=hashlib.sha256(membership_bytes).hexdigest()
 mem=pl.read_parquet(io.BytesIO(membership_bytes),columns=['asn','first_seen'])
 first={int(a):t for a,t in mem.group_by('asn').agg(pl.col('first_seen').min()).iter_rows()}
 t0=stamp(s.get('first_observation') or s['t0'])
 assert stamp(change['new_t0_obs'])==t0,(key,'clock mismatch')
 sets={h:{a for a,t in first.items() if t<=t0+dt.timedelta(seconds=seconds)} for h,seconds in H.items()}
 prior=set()
 for h in sorted(H,key=H.get):
  assert prior<=sets[h],(key,'non-nested sets',h)
  prior=sets[h]
  c=change['sets']['set_'+h]
  assert c['new_n']==len(sets[h]),(key,'set count',h,c['new_n'],len(sets[h]))
  before=set(old[key].get('set_'+h) or [])
  assert (before-set(c['removed']))|set(c['added'])==sets[h],(key,'set membership diff',h)
  if h in s['extent']:assert s['extent'][h]['asns_pooled']==len(sets[h]),(key,'summary extent',h,s['extent'][h]['asns_pooled'],len(sets[h]))
 times=sorted((t-t0).total_seconds() for a,t in first.items() if a in sets['final_2h'])
 t90=max(0.,times[math.ceil(.9*len(times))-1]) if times else None
 assert t90 is None or math.isfinite(t90) and 0<=t90<=7200,(key,'t90 bounds',t90)
 assert t90==change['new_t90_s'],(key,'t90 mismatch',t90,change['new_t90_s'])
 return {'merged':True,'membership_rows':mem.height,'source_hashes':hashes}
results=[];failures=[]
with ThreadPoolExecutor(max_workers=16) as pool:
 futures=[(row,pool.submit(audit,row)) for row in rows]
 for row,f in futures:
  try:results.append(f.result())
  except Exception as exc:failures.append({'event_id':row['event_id'],'tag':row['tag'],'error':str(exc)})
for result in results:source_hashes.update(result['source_hashes'])
def unchanged(item):
 name,digest=item
 return name if hashlib.sha256((r/name).read_bytes()).hexdigest()!=digest else None
with ThreadPoolExecutor(max_workers=24) as pool:
 for name in pool.map(unchanged,{**source_hashes,**digests}.items()):
  if name:failures.append({'file':name,'error':'source changed during verification'})
result={'events':len(rows),'merged':sum(x['merged'] for x in results),'excluded':sum(not x['merged'] for x in results),'source_tasks':len(reports),'membership_rows':sum(x['membership_rows'] for x in results),'failures':failures,'inputs_sha256':digests,'source_sha256':source_hashes}
result["status"]="passed" if not failures else "failed"
result["scopes"]=args.scopes
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v if k not in ('failures','source_sha256') else (v[:15] if k=='failures' else len(v)) for k,v in result.items()}),flush=True)

raise SystemExit(bool(failures))
