"""Independently check cited Radar agreements and their saved raw-source matches."""
from __future__ import annotations
import argparse
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
import datetime as dt
import hashlib
import json
import multiprocessing
from pathlib import Path
import re
import time
import polars as pl
from verify_propagation_controls import equal, quantile, median, sha

PREFIX_FOLDER='analysis/nongraph/2024/097_radar_prefix_agreement'
PREFIX_STEM=PREFIX_FOLDER+'/cloudflare_leaks_prefixes_reconstructed'


def timestamp(value):
    if value is None: return None
    value=dt.datetime.fromisoformat(value.replace('Z','+00:00')) if isinstance(value,str) else value
    return value.astimezone(dt.timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def tag(value):
    if value is None: return None
    try:
        return next((r['name'][16:] for r in json.loads(value) if r['name'].startswith('rpki_new_origin_')),'none')
    except (ValueError,KeyError,TypeError): return 'none'


def check_prefix_summary(rows,saved):
    assert rows and len({r['radar_id'] for r in rows})==len(rows)
    for row in rows:
        prefixes=json.loads(row['prefixes'])
        assert len(set(prefixes))==len(prefixes)==row['our_prefix_count']
    ratios=[r['our_prefix_count']/max(1,r['radar_prefix_count']) for r in rows]
    expected={'matched_to_our_events':len(rows),
              'exact_count_match':sum(r['our_prefix_count']==r['radar_prefix_count'] for r in rows),
              'our_ge_radar':sum(r['our_prefix_count']>=r['radar_prefix_count'] for r in rows),
              'ratio_p10_p50_p90':[round(quantile(ratios,q),3) for q in (.1,.5,.9)],
              'radar_prefix_count_p50':median([r['radar_prefix_count'] for r in rows]),
              'our_prefix_count_p50':median([r['our_prefix_count'] for r in rows])}
    for key,value in expected.items(): equal(saved[key],value,'prefix/'+key)
    assert saved['measurement_definition']=='nearest_identifier_match_complete_radar_window_observed_prefixes_v1'


def check_rpki_summary(rows,saved,labels):
    assert rows and len({r['event_id'] for r in rows})==len(rows)
    counts=Counter((r['ours'],r['radar']) for r in rows)
    equal(saved['matched_events'],len(rows),'rpki/matched')
    equal(saved['agreement'],round(sum(r['ours']==r['radar'] for r in rows)/len(rows),4),'rpki/agreement')
    equal(saved['confusion_ours_vs_radar'],{f'{a}|{b}':n for (a,b),n in counts.items()},'rpki/confusion')
    for row in rows: equal(row['ours'],labels[row['event_id']],'rpki/source validity')
    equal(saved['match_policy'],'exclude conflicting RPKI tags; nearest timestamp then Radar ID among same-tag matches','rpki policy')
    excluded=saved['conflicting_tag_event_ids']
    assert excluded==sorted(set(excluded)) and not set(excluded)&{r['event_id'] for r in rows}
    equal(saved['conflicting_tag_events_excluded'],len(excluded),'rpki excluded count')
    equal(saved['matched_events_before_ambiguity_filter'],len(rows)+len(excluded),'rpki denominator')
    assert len(excluded)<=saved['multiple_match_events']<=saved['matched_events_before_ambiguity_filter']



def raw_prefix_group(payload):
    data,eid,windows=payload
    relative=f'events_replay_leak/{eid}/anomalous.parquet'
    path=data/relative
    digest=sha(path)
    frame=pl.read_parquet(path,columns=['prefix','ts'])
    if frame['ts'].dtype.time_zone:
        frame=frame.with_columns(pl.col('ts').dt.convert_time_zone('UTC').dt.replace_time_zone(None))
    output={}
    for rid,start,end in windows:
        output[rid]=sorted(frame.filter((pl.col('ts')>=start)&(pl.col('ts')<=end))['prefix'].unique().to_list())
    assert sha(path)==digest,(relative,'changed during audit')
    return relative,digest,output


def audit(data,raw=False,run_layout=False):
    sources,evidence,raw_hashes={},{},{}
    def path(relative):
        if run_layout and relative.startswith('analysis/nongraph/'):
            return data.parent/'nongraph-final'/relative.removeprefix('analysis/nongraph/')
        return data/relative
    def read(relative,category=sources):
        p=path(relative);category[relative]=sha(p)
        if p.suffix=='.parquet':return pl.read_parquet(p)
        if p.suffix=='.tsv':return pl.read_csv(p,separator='\t')
        return json.loads(p.read_text())
    rows=read(PREFIX_STEM+'.parquet',evidence).to_dicts()
    saved=read(PREFIX_STEM+'.json',evidence)
    check_prefix_summary(rows,saved)
    events=read('eventset/2024_leak/events.parquet')
    usable=set(events.filter(pl.col('error').is_null())['event_id'])
    selection=read('inventory/2024/leak_replay_selection.parquet')
    assert set(r['event_id'] for r in rows)<=usable
    ambiguous=[];censored=[]
    if raw:
        radar=read('labels/2024-01-01_2025-01-01/cloudflare_leaks.parquet',raw_hashes)
        equal(saved['radar_leaks'],radar.height,'prefix/radar population')
        # The retained API export can repeat an identical Radar observation.
        # Count raw rows in the inventory, but reconstruct each event ID once.
        multiplicity=Counter(radar['id'].to_list())
        radar=radar.unique()
        assert radar['id'].n_unique()==radar.height,'conflicting duplicate Radar IDs'
        origins=defaultdict(list)
        for r in selection.to_dicts():
            if r['event_id'] in usable:origins[int(r['a'])].append((timestamp(r['t0']),r['event_id']))
        for records in origins.values():records.sort()
        wanted={};windows=defaultdict(list)
        for label in radar.to_dicts():
            numbers=re.findall(r'\d+',label['leak_seg'] or '')
            leaker=int(numbers[1]) if len(numbers)>1 else 0
            start,end=timestamp(label['min_ts']),timestamp(label['max_ts'])
            records=origins.get(leaker,[])
            times=[t for t,_ in records]
            matches=records[bisect_left(times,start-dt.timedelta(minutes=10)):bisect_right(times,start+dt.timedelta(minutes=10))]
            if not matches:continue
            if len(matches)*multiplicity[label['id']]>1:ambiguous.append(label['id'])
            onset,eid=min(matches,key=lambda item:(abs((item[0]-start).total_seconds()),item[1]))
            low,high=start-dt.timedelta(minutes=10),(end or start)+dt.timedelta(minutes=10)
            if low<onset-dt.timedelta(hours=1) or high>onset+dt.timedelta(hours=3):
                censored.append({'radar_id':label['id'],'event_id':eid,'reason':'radar_window_outside_retained_replay'});continue
            wanted[label['id']]={'event_id':eid,'leaker':leaker,'radar_prefix_count':int(label['prefix_count']),
                'radar_peer_count':int(label['peer_count']),
                # Exported offset is an integer-second display field; the
                # independent candidate selection above retains full precision.
                'match_offset_s':int(abs((onset-start).total_seconds()))}
            windows[eid].append((label['id'],low,high))
        assert {r['radar_id'] for r in rows}==set(wanted),'prefix match completeness'
        assert set(saved['ambiguous_radar_ids'])==set(ambiguous),'prefix ambiguous matches'
        equal(sorted(saved['censored_matches'],key=lambda r:r['radar_id']),sorted(censored,key=lambda r:r['radar_id']),'prefix censored')
        outputs={}
        with ProcessPoolExecutor(max_workers=8,mp_context=multiprocessing.get_context("spawn")) as pool:
            for relative,digest,result in pool.map(raw_prefix_group,[(data,eid,group) for eid,group in windows.items()]):
                raw_hashes[relative]=digest;outputs.update(result)
        for row in rows:
            for key,value in wanted[row['radar_id']].items():equal(row[key],value,'prefix match '+key)
            equal(json.loads(row['prefixes']),outputs[row['radar_id']],'raw prefix set')
    rpki_ambiguity={}
    for year in (2024,2025):
        base=f'eventset/{year}'
        table=read(base+'/radar_rpki_agreement.parquet',evidence).to_dicts()
        summary=read(base+'/radar_rpki_agreement.json',evidence)
        validity={r['event_id']:r['validity'] for r in read(base+'/rpki_validity.parquet').to_dicts()}
        manifest=read(f'inventory/{year}/replay_manifest.tsv').to_dicts()
        check_rpki_summary(table,summary,validity)
        if not raw:continue
        radar=read(f'labels/{year}-01-01_{year+1}-01-01/cloudflare_hijacks.parquet',raw_hashes).to_dicts()
        equal(summary['radar_events'],len(radar),'rpki/radar population')
        overall=Counter(tag(r['tags']) for r in radar)
        equal(summary['radar_rpki_new_origin_tags'],json.loads(json.dumps(overall)),'rpki/overall tags')
        by_origin=defaultdict(list)
        for label in radar:
            try:origin=int(label['hijacker_asn'])
            except (ValueError,TypeError):continue
            when=timestamp(label['min_hijack_ts'])
            if when is not None:by_origin[origin].append((when,label))
        for group in by_origin.values():group.sort(key=lambda r:r[0])
        possible={}
        for event in manifest:
            if event['event_id'] not in validity:continue
            group=by_origin.get(int(event['new_origin']),[]);when=timestamp(event['t0']);times=[t for t,_ in group]
            nearby=group[bisect_left(times,when-dt.timedelta(minutes=10)):bisect_right(times,when+dt.timedelta(minutes=10))]
            matching=[label for _,label in nearby if event['prefix'] in set(re.findall(r'[0-9a-fA-F:.]+/\d+',label['prefixes'] or ''))]
            if matching:possible[event['event_id']]=matching
        conflicts=sorted(eid for eid,group in possible.items() if len({tag(r['tags']) for r in group})>1)
        multiple=sum(len(g)>1 for g in possible.values())
        equal(summary['match_policy'],'exclude conflicting RPKI tags; nearest timestamp then Radar ID among same-tag matches','rpki policy')
        equal(summary['matched_events_before_ambiguity_filter'],len(possible),'rpki matches before filter')
        equal(summary['multiple_match_events'],multiple,'rpki multiple matches')
        equal(summary['conflicting_tag_events_excluded'],len(conflicts),'rpki conflicts')
        equal(summary['conflicting_tag_event_ids'],conflicts,'rpki conflict IDs')
        assert set(possible)-set(conflicts)=={r['event_id'] for r in table},'rpki match completeness'
        event_by_id={r['event_id']:r for r in manifest}
        for row in table:
            onset=timestamp(event_by_id[row['event_id']]['t0'])
            candidates=[]
            for label in possible[row['event_id']]:
                candidates.append({'event_id':row['event_id'],'radar_id':label['id'],
                    'ours':validity[row['event_id']],'radar':tag(label['tags']),
                    'confidence':label['confidence_score'],
                    'match_offset_s':abs((onset-timestamp(label['min_hijack_ts'])).total_seconds())})
            wanted=min(candidates,key=lambda r:(r['match_offset_s'],str(r['radar_id']),json.dumps(r,sort_keys=True)))
            equal(row,wanted,'rpki deterministic raw match')
        rpki_ambiguity[year]={'multiple_matches':multiple,'conflicting_rpki_tags':len(conflicts)}
    for category in (sources,evidence,raw_hashes):
        for relative,digest in category.items():assert sha(path(relative))==digest,(relative,'changed during audit')
    return {'status':'passed','mode':'private_source_audit','outputs':[PREFIX_STEM,*[f'eventset/{y}/radar_rpki_agreement' for y in (2024,2025)]],
            'source_sha256':sources,'evidence_sha256':evidence,'raw_source_sha256':raw_hashes,'rpki_ambiguity':rpki_ambiguity}


def verify_public(data,proof_path):
    proof=json.loads(proof_path.read_text());assert proof['status']=='passed' and proof['mode']=='private_source_audit'
    current=audit(data)
    for key in ('outputs','source_sha256','evidence_sha256'):equal(proof[key],current[key],'radar proof/'+key)
    return {'status':'passed','outputs':current['outputs']}


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('data',type=Path)
    ap.add_argument('--output',type=Path,required=True);ap.add_argument('--run-layout',action='store_true')
    ap.add_argument('--wait-for-marker',type=Path,action='append',default=[]);args=ap.parse_args()
    while not all(p.exists() for p in args.wait_for_marker):time.sleep(10)
    result=audit(args.data,True,args.run_layout)
    pending=args.output.with_suffix('.pending.json');pending.write_text(json.dumps(result,indent=2)+'\n');pending.replace(args.output)
    print(json.dumps({'status':'passed','outputs':result['outputs'],'rpki_ambiguity':result['rpki_ambiguity']}),flush=True)


if __name__=='__main__':main()
