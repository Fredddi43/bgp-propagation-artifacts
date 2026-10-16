"""Merge predecessor additions in an isolated candidate tree and report exact impact."""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import time
import polars as pl
from bgbench.replay_day import merge_event,merge_withdrawal
from bgbench.eventset import DELTAS_S
from bgbench.extent import TARGETS_S


def atomic(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);t=path.with_suffix('.tmp');t.write_text(json.dumps(value,indent=1,default=str));t.replace(path)


def metrics(folder):
    summary=json.loads((folder/'summary.json').read_text())
    if summary.get('error'):return {'error':summary['error'],'sets':{},'t0_obs':None,'t90_s':None,'anomalous_msgs':summary.get('anomalous_msgs')}
    onset=dt.datetime.fromisoformat(summary.get('first_observation') or summary['t0'])
    mem=pl.read_parquet(folder/'membership.parquet');first=mem.group_by('asn').agg(pl.col('first_seen').min())
    sets={k:sorted(first.filter(pl.col('first_seen')<=onset+dt.timedelta(seconds=n))['asn'].to_list()) for k,n in {**DELTAS_S,**TARGETS_S}.items()}
    final=first.filter(pl.col('first_seen')<=onset+dt.timedelta(hours=2)).sort('first_seen')
    t90=max(0.,(final['first_seen'][math.ceil(.9*final.height)-1]-onset).total_seconds()) if final.height else None
    return {'error':None,'t0_obs':onset.isoformat(),'t90_s':t90,'sets':sets,**{k:summary.get(k) for k in ['observation_lag_s','anomalous_msgs','sessions_carrying_prefix','sessions_switched_to_new_origin','leaked_prefixes','wave_prefixes']}}


def assess_event(run,plan,key,reports):
    root=run/'boundary-audit';e=plan['events'][key];family=e['tag'] or 'origin';eid=e['event_id']
    relevant=[r for r in reports if key in r['events']]
    gap=[r['task'] for r in relevant if r['status']!='complete']
    added=[root/r['parts'][key] for r in relevant if key in r.get('parts',{})]
    source=run/'crossday-repair/events'/family/eid
    original=json.loads((source/'summary.json').read_text())
    result={'event_id':eid,'year':e['year'],'tag':e['tag'],'source_tasks':[r['task'] for r in relevant],
            'predecessor_rows':sum(r.get('in_window_rows',{}).get(key,0) for r in relevant),'archive_gap_tasks':gap,
            'original_error':original.get('error'),'added_parts_sha256':{str(p.relative_to(run)):hashlib.sha256(p.read_bytes()).hexdigest() for p in added}}
    if gap:
        return {**result,'status':'coverage_gap','measurement_changed':False}
    if not added or original.get('error'):
        return {**result,'status':'existing_exclusion' if original.get('error') else 'no_in_window_rows','measurement_changed':False}
    combined=root/'combined-parts'/family/eid;combined.mkdir(parents=True,exist_ok=True)
    for p in (run/'crossday-repair/parts'/family/eid).glob('*.parquet'):
        link=combined/p.name
        if not link.exists():link.symlink_to(p.resolve())
    for p in added:
        link=combined/p.name
        if not link.exists():link.symlink_to(p.resolve())
    if e['tag']=='withdrawal':
        new=merge_withdrawal(eid,dt.datetime.fromisoformat(e['t0']),dt.datetime.fromisoformat(e['burst_end']) if e.get('burst_end') else None,
                            parts_root_override=root/'combined-parts'/family,merged_root_override=root/'events'/family)
    else:
        leak=(int(e['a']),e['sources'],e.get('upstreams') or '') if e['tag']=='leak' else None
        new=merge_event(eid,e.get('prefix'),e.get('new_origin'),dt.datetime.fromisoformat(e['t0']),tag=e['tag'],leak=leak,
                        parts_root_override=root/'combined-parts'/family,merged_root_override=root/'events'/family)
    new.update(crossday_repair_complete=True,measurement_repair_source_tasks=original.get('measurement_repair_source_tasks',[]),
               measurement_predecessor_task_ids=[r['task'] for r in relevant])
    candidate=root/'events'/family/eid;atomic(candidate/'summary.json',new)
    before,after=metrics(source),metrics(candidate)
    deltas={k:{'old_n':len(before['sets'].get(k,[])),'new_n':len(after['sets'].get(k,[])),
               'added':sorted(set(after['sets'].get(k,[]))-set(before['sets'].get(k,[]))),
               'removed':sorted(set(before['sets'].get(k,[]))-set(after['sets'].get(k,[])))} for k in {**DELTAS_S,**TARGETS_S}}
    scalar_changes={k:{'before':v,'after':after.get(k)} for k,v in before.items() if k!='sets' and v!=after.get(k)}
    original_rows=pl.read_parquet(source/'anomalous.parquet');new_rows=pl.read_parquet(candidate/'anomalous.parquet')
    cols=original_rows.columns
    lost=original_rows.join(new_rows.select(cols),on=cols,how='anti',nulls_equal=True).height
    if lost:raise ValueError(f'candidate lost {lost} original anomalous rows: {key}')
    return {**result,'status':'candidate','measurement_changed':before!=after,'scalar_changes':scalar_changes,'sets':deltas,
            'old':before,'new':after,'original_anomalous_rows':original_rows.height,'candidate_anomalous_rows':new_rows.height,'lost_anomalous_rows':lost,
            'candidate_replay':str(candidate.relative_to(run)),
            'original_files_sha256':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in source.iterdir() if f.is_file()},
            'candidate_files_sha256':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in candidate.iterdir() if f.is_file()}}


def main(run,workers,wait):
    root=run/'boundary-audit';plan=json.loads((root/'plan.json').read_text());by_event=defaultdict(set)
    for t in plan['tasks']:
        for key in t['events']:by_event[key].add(t['index'])
    reports={};done={};output=root/'event-impact';output.mkdir(exist_ok=True)
    def load(p):return int(p.stem),json.loads(p.read_text())
    while True:
        new=[p for p in (root/'tasks').glob('*.json') if int(p.stem) not in reports]
        with ThreadPoolExecutor(max_workers=workers) as pool:reports.update(pool.map(load,new))
        ready=[k for k,ids in by_event.items() if k not in done and ids<=reports.keys()]
        def one(key):
            file=output/(key.replace(':','_',1)+'.json')
            result=json.loads(file.read_text()) if file.exists() else assess_event(run,plan,key,[reports[i] for i in by_event[key]])
            atomic(file,result);return key,result
        with ThreadPoolExecutor(max_workers=workers) as pool:done.update(pool.map(one,ready))
        print(json.dumps({'task_reports':len(reports),'expected_tasks':len(plan['tasks']),'events_assessed':len(done),'changed_events':sum(x.get('measurement_changed',False) for x in done.values()),'gap_events':sum(x['status']=='coverage_gap' for x in done.values())}),flush=True)
        if len(reports)==len(plan['tasks']):break
        if not wait:return
        time.sleep(15)
    overhang=[]
    for i,r in reports.items():
        if r.get('archive_timestamp_max'):
            seconds=dt.datetime.fromisoformat(r['archive_timestamp_max']).timestamp()-plan['tasks'][i]['ts_start']-plan['tasks'][i]['step']
            overhang.append({'task':i,'overhang_s':seconds,'period_s':plan['tasks'][i]['step']})
    result={'plan_sha256':hashlib.sha256((root/'plan.json').read_bytes()).hexdigest(),'expected_tasks':len(plan['tasks']),'completed_tasks':len(reports),
            'task_statuses':dict(Counter(r['status'] for r in reports.values())),'events':list(done.values()),'event_statuses':dict(Counter(x['status'] for x in done.values())),
            'changed_events':[key for key,x in done.items() if x.get('measurement_changed')],
            'max_archive_overhang_s':max((x['overhang_s'] for x in overhang),default=None),'overhang_exceeding_one_period':[x for x in overhang if x['overhang_s']>x['period_s']]}
    atomic(root/'impact.json',result)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--workers',type=int,default=8);p.add_argument('--wait',action='store_true');a=p.parse_args();main(a.run,a.workers,a.wait)
