"""Prove full eligible non-graph input equality across an isolated boundary correction.

Equality includes all training/test rows before sampling, so sampled cohorts,
co-affection histories, embargoes and prefix feature shards are covered.
Raw replay inputs must be the same physical files or byte-identical copies.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import polars as pl


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()


def content(table):
    return hashlib.sha256(table.select(sorted(table.columns)).write_json().encode()).hexdigest()


def eligible(table,task,floor):
    kind=task['kind'];args=task.get('args',{})
    out=table.filter(pl.col('error').is_null())
    leak=kind!='cascade' or args.get('set_tag','').startswith('leak')
    if leak and kind!='radar_prefix_agreement':out=out.filter(pl.col('observation_lag_s').is_null()|(pl.col('observation_lag_s')>=-60))
    minimum=args.get('min_asns',0) if kind=='cascade' else 200 if kind in ('curve_naive','tsfm','chronos_lora') else 0
    if minimum:out=out.filter(pl.col('asns_final_2h')>=minimum)
    if kind in ('prefix_model','prefix_features'):
        ids=floor.filter(pl.col('prefixes_2h')>=10)['event_id']
        out=out.filter(pl.col('event_id').is_in(ids.implode()))
    return out


def consumed_columns(task):
    kind=task['kind'];args=task.get('args',{})
    if kind=='radar_prefix_agreement':return ['event_id','error']
    cols=['event_id','split','error','observation_lag_s','asns_final_2h','t0_obs']
    if kind=='cascade':cols+=['set_'+args['delta'],'set_'+args['target'],'vis_bucket','labelled']
    elif kind in ('curve_naive','tsfm'):cols+=['asns_T5m']
    return cols


def verify(run):
    candidate_manifest=run/'boundary-audit/candidate-manifest.json'
    manifest=json.loads(candidate_manifest.read_text());assert manifest['status']=='ready'
    before=run/'data';after=Path(manifest['candidate_data_root'])
    plan_path=run/'nongraph-plan.json';tasks=json.loads(plan_path.read_text());assert len(tasks)==98
    for relative,digest in manifest['source_sha256'].items():assert sha(run/relative)==digest,(relative,'changed since candidate build')
    sources={'nongraph-plan.json':sha(plan_path),'boundary-audit/candidate-manifest.json':sha(candidate_manifest)}
    shared={}
    for name in ('graphs','ribs','inventory','labels'):
        assert (before/name).resolve()==(after/name).resolve(),('external input tree changed',name)
        shared[name]=str((before/name).resolve())
    cache={};result=[];raw_cache={};changed_rows={};prefix_checked=set()
    for task in tasks:
        kind=task['kind'];year=task['year'];tag=task.get('args',{}).get('set_tag','') if kind=='cascade' else 'leak'
        folder=str(year)+('_'+tag if tag else '');relative=f'eventset/{folder}/events.parquet'
        if relative not in cache:
            old=pl.read_parquet(before/relative);new=pl.read_parquet(after/relative)
            assert old['event_id'].to_list()==new['event_id'].to_list(),('event order/population changed',relative)
            cache[relative]=(old,new)
            for base in (before,after):sources[str((base/relative).relative_to(run))]=sha(base/relative)
            oldrows={r['event_id']:r for r in old.to_dicts()};newrows={r['event_id']:r for r in new.to_dicts()}
            changes=[{'event_id':eid,'before':row,'after':newrows[eid]} for eid,row in oldrows.items() if row!={c:newrows[eid][c] for c in old.columns}]
            if changes:changed_rows[relative]=changes
        old,new=cache[relative]
        floor=None
        if kind in ('prefix_model','prefix_features'):
            path=before/f'eventset/{year}_leak/prefix_floor.parquet';floor=pl.read_parquet(path)
            sources[str(path.relative_to(run))]=sha(path)
            # Candidate keeps the old floor until the explicitly changed floor
            # task is rerun. Prove its >=10 eligibility on every raw-changed row.
            new_base=new.filter(pl.col('error').is_null()&(pl.col('observation_lag_s').is_null()|(pl.col('observation_lag_s')>=-60)))
            if year not in prefix_checked:
                for eid in new_base['event_id']:
                    a=before/'events_replay_leak'/eid/'anomalous.parquet';b=after/'events_replay_leak'/eid/'anomalous.parquet'
                    assert a.resolve()==b.resolve() or sha(a)==sha(b),('prefix eligibility needs recomputation',eid)
                prefix_checked.add(year)
        a=eligible(old,task,floor);b=eligible(new,task,floor)
        columns=[c for c in consumed_columns(task) if c in old.columns]
        a=a.select(columns);b=b.select(columns)
        equal=a.equals(b,null_equal=True)
        raw_names=[]
        if kind in ('curve_naive','tsfm','chronos_lora'):raw_names=['membership.parquet']
        elif kind in ('prefix_floor','radar_prefix_agreement'):raw_names=['anomalous.parquet']
        elif kind in ('prefix_features','prefix_model'):raw_names=['anomalous.parquet','summary.json']
        closure=[];raw_changes=[]
        for eid in sorted(set(a['event_id'])&set(b['event_id'])):
            for name in raw_names:
                rel=f'events_replay_leak/{eid}/{name}'
                if rel not in raw_cache:
                    left,right=before/rel,after/rel
                    if left.resolve()==right.resolve():
                        stat=left.stat();raw_cache[rel]={'same_physical_file':True,'path':str(left.resolve()),'bytes':stat.st_size,'mtime_ns':stat.st_mtime_ns}
                    else:
                        x,y=sha(left),sha(right);raw_cache[rel]={'same_physical_file':False,'before_sha256':x,'after_sha256':y,'equal':x==y}
                proof=raw_cache[rel]
                closure.append(rel)
                if not proof['same_physical_file'] and not proof['equal']:raw_changes.append(rel)
        marker=run/f'nongraph-final/{year}/{task["index"]:03d}_{kind}/complete.json'
        completion=json.loads(marker.read_text());assert completion['task']==task
        sources[str(marker.relative_to(run))]=sha(marker)
        result.append({'task_index':task['index'],'kind':kind,'year':year,'status':'equivalent' if equal and not raw_changes else 'rerun_required',
            'consumed_columns':columns,'event_table':relative,'before_rows':a.height,'after_rows':b.height,'before_input_sha256':content(a),'after_input_sha256':content(b),
            'removed_event_ids':sorted(set(a['event_id'])-set(b['event_id'])),'added_event_ids':sorted(set(b['event_id'])-set(a['event_id'])),
            'raw_input_files':closure,'raw_changed':raw_changes,'historical_completion':str(marker.relative_to(run)),
            'historical_input_content_sha256':completion['correction_run']['input_content_sha256']})
    for rel,proof in raw_cache.items():
        if proof['same_physical_file']:
            p=before/rel;stat=p.stat()
            assert str(p.resolve())==proof['path'] and stat.st_size==proof['bytes'] and stat.st_mtime_ns==proof['mtime_ns'],(rel,'changed during audit')
    for rel,digest in sources.items():assert sha(run/rel)==digest,(rel,'changed during audit')
    return {'status':'passed','mode':'private_consumed_input_equivalence','tasks':result,'task_count':len(result),
            'equivalent_tasks':[r['task_index'] for r in result if r['status']=='equivalent'],
            'rerun_tasks':[r['task_index'] for r in result if r['status']=='rerun_required'],
            'source_sha256':sources,'shared_external_inputs':shared,'raw_input_equivalence':raw_cache,'changed_event_rows':changed_rows,
            'scope':'Full ordered producer-consumed source columns across all eligible train and test rows before sampling, with identical raw count/prefix inputs and shared CAIDA/RIB/label trees. Prefix features use unchanged >=10-prefix eligibility; no test-ID-only exemption.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=verify(a.run);a.output.write_text(json.dumps(result,indent=2,default=str)+'\n');print(json.dumps({'equivalent':len(result['equivalent_tasks']),'rerun_tasks':result['rerun_tasks']}))
