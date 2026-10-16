"""Inspect predecessor archive spillover in an isolated tree; never mutate replay inputs."""
from __future__ import annotations
import argparse
import bz2
import gzip
import struct
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import hashlib
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import subprocess
import time
import polars as pl
from bgbench.broker import BrokerItem
from bgbench.fetch import fetch_all
from bgbench.replay_day import ROW_COLS, _leak_regex


def atomic(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,indent=1,default=str));temp.replace(path)


def predecessor_url(template, timestamp):
    t=dt.datetime.fromtimestamp(timestamp,dt.UTC)
    url=re.sub(r'updates\.\d{8}\.\d{4}',t.strftime('updates.%Y%m%d.%H%M'),template)
    url=re.sub(r'/\d{4}\.\d{2}/',t.strftime('/%Y.%m/'),url)
    url=re.sub(r'/\d{6}/',t.strftime('/%Y%m/'),url)
    return url


def prepare(run):
    original=run/'crossday-repair-plan.json';plan=json.loads(original.read_text())
    def read(i):
        payload=(run/'crossday-repair/tasks'/f'{i}.json').read_bytes()
        return i,(json.loads(payload),hashlib.sha256(payload).hexdigest())
    with ThreadPoolExecutor(max_workers=16) as pool:reports=dict(pool.map(read,range(len(plan['tasks']))))
    fetched=defaultdict(list);templates={}
    for i,(report,report_hash) in reports.items():
        collector=plan['tasks'][i]['collector']
        for a in report.get('archives',[]):
            templates.setdefault(collector,a['url'])
            if not a.get('error'):
                timestamp=a.get('ts_start')
                if timestamp is None:
                    match=re.search(r'updates\.(\d{8})\.(\d{4})',a['url'])
                    timestamp=int(dt.datetime.strptime(''.join(match.groups()),'%Y%m%d%H%M').replace(tzinfo=dt.UTC).timestamp())
                fetched[(collector,timestamp)].append({'source_task':i,'url':a['url'],'report_sha256':report_hash})
    requests=defaultdict(set);steps={};existing=0;eligible=0;reuse={};unscoped=0
    for key,event in plan['events'].items():
        start=dt.datetime.fromisoformat(event['w_start']).timestamp()
        collectors={plan['tasks'][i]['collector']:plan['tasks'][i]['step'] for i in event['tasks']}
        for collector,step in collectors.items():
            eligible+=1;previous=int(start)//step*step-step
            covered=None
            for proof in fetched.get((collector,previous),[]):
                source_task=proof['source_task']
                part=run/'crossday-repair/parts'/(event['tag'] or 'origin')/event['event_id']/f'{collector}__{source_task}.parquet'
                if key in plan['tasks'][source_task]['events'] and part.exists():
                    covered={**proof,'part':str(part.relative_to(run))};break
            if covered:
                existing+=1
                reuse_key=f'{collector}:{previous}:{covered["source_task"]}'
                entry=reuse.setdefault(reuse_key,{'collector':collector,'ts_start':previous,'source_task':covered['source_task'],'archive_url':covered['url'],'source_report':f"crossday-repair/tasks/{covered['source_task']}.json",'source_report_sha256':covered['report_sha256'],'event_parts':{}})
                entry['event_parts'][key]=covered['part']
                continue
            if (collector,previous) in fetched:unscoped+=1
            requests[(collector,previous)].add(key);steps[collector]=step
    tasks=[{'collector':c,'ts_start':t,'step':steps[c],'url':predecessor_url(templates[c],t),'events':sorted(keys)} for (c,t),keys in sorted(requests.items(),key=lambda x:(x[0][1],x[0][0]))]
    for i,task in enumerate(tasks):task['index']=i
    output=run/'boundary-audit';output.mkdir(exist_ok=True)
    atomic(output/'already-fetched-predecessors.json',list(reuse.values()))
    result={'reuse_proof_sha256':hashlib.sha256((output/'already-fetched-predecessors.json').read_bytes()).hexdigest(),'fetched_but_unscoped_event_collector_pairs':unscoped,'source_plan_sha256':hashlib.sha256(original.read_bytes()).hexdigest(),'events':plan['events'],'tasks':tasks,'already_fetched_predecessor_event_collector_pairs':existing,'event_collector_pairs':eligible}
    atomic(output/'plan.json',result)
    print(json.dumps({'tasks':len(tasks),'events_needing_guard':len({k for t in tasks for k in t['events']}),'existing_pairs':existing,'fetched_but_unscoped_pairs':unscoped,'event_collector_pairs':eligible,'collectors':{c:sum(t['collector']==c for t in tasks) for c in steps}}),flush=True)


@lru_cache(maxsize=4)
def load_plan(path):
    return json.loads(path.read_text())


def retain_mrt_since(source, destination, since):
    """Retain complete MRT records by their common-header timestamp.

    Replay window starts are integral seconds. Extended microseconds cannot move
    a record across that cutoff, and retained header/payload bytes are unchanged.
    The production Rust parser still interprets every retained BGP record.
    """
    assert float(since).is_integer()
    opener = bz2.open if source.suffix == '.bz2' else gzip.open if source.suffix == '.gz' else open
    total = retained = 0
    earliest = latest = None
    with opener(source, 'rb') as incoming, destination.open('wb') as outgoing:
        while True:
            header = incoming.read(12)
            if not header:break
            if len(header) != 12:raise ValueError('truncated MRT header')
            seconds, kind, subtype, length = struct.unpack('!IHHI', header)
            payload = incoming.read(length)
            if len(payload) != length:raise ValueError('truncated MRT payload')
            micros = struct.unpack('!I',payload[:4])[0] if kind == 17 else 0
            if micros >= 1000000:raise ValueError('invalid MRT extended microseconds')
            stamp = (seconds,micros)
            earliest = stamp if earliest is None else min(earliest,stamp)
            latest = stamp if latest is None else max(latest,stamp)
            total += 1
            if seconds >= since:
                outgoing.write(header);outgoing.write(payload);retained += 1
    def iso(value):
        return (dt.datetime.fromtimestamp(value[0],dt.UTC)+dt.timedelta(microseconds=value[1])).isoformat() if value else None
    return {'mrt_records':total,'retained_mrt_records':retained,'archive_timestamp_min':iso(earliest),'archive_timestamp_max':iso(latest)}


@lru_cache(maxsize=4)
def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def worker(run,index):
    output=run/'boundary-audit';plan=load_plan(output/'plan.json');task=plan['tasks'][index]
    plan_hash=file_hash(output/'plan.json');code_hash=file_hash(Path(__file__))
    marker=output/'tasks'/f'{index}.json'
    if marker.exists():
        existing=json.loads(marker.read_text())
        if existing.get('boundary_plan_sha256')!=plan_hash or existing.get('code_sha256')!=code_hash:
            raise ValueError('existing boundary task has different plan/code provenance')
        return existing
    work=output/'work'/str(index);work.mkdir(parents=True,exist_ok=True)
    start=dt.datetime.fromtimestamp(task['ts_start'],dt.UTC)
    item=BrokerItem(task['collector'],'updates',start,start+dt.timedelta(seconds=task['step']),task['url'],0,0)
    result=fetch_all([item],work/'raw',workers=1)[0]
    base={'boundary_plan_sha256':plan_hash,'code_sha256':code_hash,'task':index,'collector':task['collector'],'url':task['url'],'transport_url':result.transport_url,'bytes':result.size,'events':task['events']}
    if not result.path:
        if result.error!='404':raise RuntimeError(f'archive retrieval failed: {result.error}')
        report={**base,'status':'archive_gap','error':'404'};atomic(marker,report);return report
    raw_sha=hashlib.sha256(result.path.read_bytes()).hexdigest()
    filtered=work/'in-window.mrt'
    earliest=min(dt.datetime.fromisoformat(plan['events'][key]['w_start']).timestamp() for key in task['events'])
    record_scope=retain_mrt_since(result.path,filtered,earliest)
    if not record_scope['retained_mrt_records']:
        report={**base,'status':'complete','archive_sha256':raw_sha,**record_scope,'rows':0,'in_window_rows':{key:0 for key in task['events']},'parts':{}}
        atomic(marker,report);result.path.unlink();filtered.unlink();return report
    parsed=work/'parsed.parquet'
    parse_bin=os.environ.get('BGBENCH_PARSE_BIN',str(run/'code/rust/bgbench-parse/target/release/bgbench-parse'))
    proc=subprocess.run([parse_bin,'--collector',task['collector'],'--out',str(parsed),str(filtered)],capture_output=True,text=True)
    if proc.returncode:raise RuntimeError(f'parser failed: {proc.stderr[-1000:]}')
    table=pl.read_parquet(parsed)
    counts={};parts={}
    for key in task['events']:
        e=plan['events'][key];lo=dt.datetime.fromisoformat(e['w_start']);hi=dt.datetime.fromisoformat(e['w_end'])
        rows=table.filter((pl.col('ts')>=lo)&(pl.col('ts')<=hi))
        if e['tag']=='withdrawal':
            # All rows retained for isolated downstream merge; prefix eligibility
            # is recomputed against the complete existing plus predecessor input.
            rows=rows.select('elem_type',*ROW_COLS)
        else:
            rows=rows.filter((pl.col('elem_type')=='A')&pl.col('as_path').is_not_null())
            rows=(rows.filter(pl.col('prefix')==e['prefix']) if e['tag']=='' else rows.filter(pl.col('as_path').str.contains(_leak_regex(int(e['a']),e['sources']))))
            rows=rows.select(ROW_COLS)
        counts[key]=rows.height
        if rows.height:
            dest=output/'parts'/(e['tag'] or 'origin')/e['event_id']/f"{task['collector']}__predecessor_{index}.parquet"
            dest.parent.mkdir(parents=True,exist_ok=True);rows.write_parquet(dest,compression='zstd');parts[key]=str(dest.relative_to(output))
    report={**base,'status':'complete','archive_sha256':raw_sha,**record_scope,'rows':table.height,'timestamp_min':table['ts'].min(),'timestamp_max':table['ts'].max(),'nominal_end':item.ts_end,'in_window_rows':counts,'parts':parts,'parse_summary':proc.stderr.strip()}
    atomic(marker,report)
    result.path.unlink();filtered.unlink();parsed.unlink()
    return report


def batch(run,indices,workers,min_free_gib=200):
    tasks=[int(x) for x in indices.read_text().split()]
    load_plan(run/'boundary-audit/plan.json')
    def one(i):
        while True:
            available=next(int(x.split()[1]) for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:'))
            if available>min_free_gib*1024*1024:break
            time.sleep(5)
        try:
            r=worker(run,i);print(json.dumps({'task':i,'status':r['status'],'added_rows':sum(r.get('in_window_rows',{}).values())}),flush=True);return {'task':i,'status':r['status']}
        except Exception as e:
            print(json.dumps({'task':i,'error':repr(e)}),flush=True);return {'task':i,'status':'failed','error':repr(e)}
    with ThreadPoolExecutor(max_workers=workers) as pool:results=list(pool.map(one,tasks))
    atomic(indices.with_suffix('.complete.json'),{'tasks':len(results),'failed':[x for x in results if x['status']=='failed']})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['prepare','worker','batch']);p.add_argument('run',type=Path);p.add_argument('--index',type=int);p.add_argument('--indices',type=Path);p.add_argument('--workers',type=int,default=32);p.add_argument('--min-free-gib',type=int,default=200)
    a=p.parse_args()
    if a.mode=='prepare':prepare(a.run)
    elif a.mode=='worker':print(json.dumps(worker(a.run,a.index),default=str))
    else:batch(a.run,a.indices,a.workers,a.min_free_gib)
