"""Independent RPKI control and collector-summary audit.

Public checks recompute controls and follow-up aggregates from released tables;
collector scores are bound to a separate private raw-membership audit.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import statistics
import time
import polars as pl


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def quantile(values, q):
    values = sorted(v for v in values if v is not None)
    return values[math.floor((len(values)-1)*q+.5)] if values else None


def median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def mean(values, digits=None):
    values = [v for v in values if v is not None]
    value = statistics.mean(values) if values else None
    return round(value, digits) if value is not None and digits is not None else value


def equal(actual, expected, context):
    if isinstance(expected, dict):
        assert set(actual) == set(expected), (context, 'keys', set(actual)^set(expected))
        for key in expected:
            equal(actual[key], expected[key], f'{context}/{key}')
    elif isinstance(expected, list):
        assert len(actual) == len(expected), (context, 'length')
        for i, (a,b) in enumerate(zip(actual, expected)):
            equal(a,b,f'{context}/{i}')
    elif isinstance(expected, (int,float)) and not isinstance(expected,bool):
        assert actual is not None and (math.isnan(expected) and math.isnan(actual) or math.isclose(actual, expected, abs_tol=1e-9, rel_tol=1e-9)), (context,actual,expected)
    else:
        assert actual == expected, (context,actual,expected)


def groups(rows, key):
    out = defaultdict(list)
    for row in rows:
        out[key(row)].append(row)
    return out


def summary(rows, year, exclude):
    rows = [r for r in rows if exclude is None or r['reason'] != exclude]
    def strat(group):
        test = [r for r in group if r['split']=='test']
        return {'n':len(group), 'asns_final_2h_p50':median([r['asns_final_2h'] for r in group]),
                'duration_min_p50':median([r['duration_min'] for r in group]),
                'persist_j30_test_mean':mean([r['j30'] for r in test],4), 'n_test':len(test),
                'growing_at_30s_frac':mean([r['growing30'] for r in group],4),
                'labelled_share':mean([r['labelled'] for r in group],4)}
    validity = groups(rows,lambda r:r['validity'])
    by_validity = {}
    for v, group in validity.items():
        rec = strat(group)
        rec.update(share=round(len(group)/len(rows),4),
                   asns_final_2h_p90=quantile([r['asns_final_2h'] for r in group],.9),
                   collectors_seeing_p50=median([r['collectors_seeing'] for r in group]))
        by_validity[v]=rec
    def plen(r):
        p=r['plen']
        return '<=16' if p<=16 else '17-22' if p<=22 else '24' if p==24 else '23' if p<24 else 'v6/other'
    def cone(r):
        c=r['cone']
        return 'cone=?' if c is None else 'cone=1 (stub)' if c<=1 else 'cone 2-10' if c<=10 else 'cone 11-100' if c<=100 else 'cone >100'
    def providers(r):
        n=r['n_providers']
        return '1 provider' if n is not None and n<=1 else '2-3 providers' if n is not None and n<=3 else '>3 providers'
    controls = {'by_validity_x_prev':lambda r:f"{r['validity']}|prev={r['prev_validity']}",
        'by_validity_x_plen':lambda r:f"{r['validity']}|/{plen(r)}",
        'by_validity_x_labelled':lambda r:f"{r['validity']}|radar={r['labelled']}",
        'by_invalid_reason':lambda r:f"{r['validity']}|{r['invalid_reason'] or '-'}",
        'by_validity_x_cone':lambda r:f"{r['validity']}|{cone(r)}",
        'by_validity_x_providers':lambda r:f"{r['validity']}|{providers(r)}"}
    incidents = {}
    for v, group in validity.items():
        incident_groups=groups(group,lambda r:f"{r['new_origin']}@{r['event_id'][:11]}")
        sizes=[len(g) for g in incident_groups.values()]
        test_means=[mean([r['j30'] for r in g if r['split']=='test']) for g in incident_groups.values()]
        incidents[v]={'incidents':len(sizes),'events':len(group),
            'test_incidents':sum(v is not None for v in test_means),
            'mixed_split_incidents':sum(len({r['split'] for r in g})>1 for g in incident_groups.values()),
            'events_per_incident_p50_p90_max':[quantile(sizes,.5),quantile(sizes,.9),max(sizes)],
            'largest_incident':min(incident_groups,key=lambda k:(-len(incident_groups[k]),k)),
            'persist_j30_incident_mean':mean(test_means,4),
            'reach_p50_of_incident_medians':median([median([r['asns_final_2h'] for r in g]) for g in incident_groups.values()]),
            'growing_at_30s_incident_mean':mean([mean([r['growing30'] for r in g]) for g in incident_groups.values()],4)}
    return {'year':year,'events':len(rows),'exclude_reason':exclude,'by_validity':by_validity,
        **{name:{k:strat(g) for k,g in groups(rows,key).items() if len(g)>=50} for name,key in controls.items()},
        'by_validity_incident_weighted':incidents,
        'grip':{'grip_labelled_share_by_validity':{v:mean([r['grip_labelled'] for r in g],4) for v,g in validity.items()},
                'grip_newcomer_rpki_tag_by_validity':{v:dict(Counter(r['grip_rpki_newcomer'] for r in g if r['grip_labelled']).most_common(4)) for v,g in validity.items()}}}



def validate_top_counts(published, counts, limit=4):
    """Allow arbitrary ordering only for genuinely tied boundary categories."""
    counts={"null" if key is None else key:value for key,value in counts.items()}
    assert len(published)==min(limit,len(counts)), "incorrect number of top categories"
    assert all(key in counts and value==counts[key] for key,value in published.items()), "incorrect category count"
    if published:
        assert all(value<=min(published.values()) for key,value in counts.items() if key not in published), "omitted larger category"


def collector_rows(scores, labelled=False):
    grouped=groups(scores,lambda r:((r['validity'],) if labelled else ())+ (r['collector'],r['delta']))
    return [dict(zip((['validity'] if labelled else [])+['collector','delta'],key),n=len(g),jaccard_mean=mean([r['jaccard'] for r in g],3)) for key,g in grouped.items()]


def spread(rows, labelled=False):
    output=[]
    for key,g in groups(rows,lambda r:((r['validity'],) if labelled else ())+(r['delta'],)).items():
        values=[r['jaccard_mean'] for r in g]
        output.append(dict(zip((['validity'] if labelled else [])+['delta'],key),
            **({'collectors':len(values)} if labelled else {}),min=min(values),max=max(values),
            std=round(statistics.stdev(values),3) if len(values)>1 else None))
    return output


def row_equal(actual,expected,keys,context):
    def key(row): return tuple(row[k] for k in keys)
    assert len({key(r) for r in actual})==len(actual),(context,'duplicate rows')
    equal(sorted(actual,key=key),sorted(expected,key=key),context)


def audit_year(data,year,raw=False):
    sources,evidence,raw_hashes={},{},{}
    def read(relative,category=sources):
        path=data/relative
        category[relative]=sha(path)
        if path.suffix=='.parquet': return pl.read_parquet(path)
        if path.suffix in ('.tsv','.csv'): return pl.read_csv(path,separator='\t' if path.suffix=='.tsv' else ',')
        return json.loads(path.read_text())
    base=f'eventset/{year}'
    ev=read(f'{base}/events.parquet').filter(pl.col('error').is_null())
    val=read(f'{base}/rpki_validity.parquet')
    man=read(f'inventory/{year}/replay_manifest.tsv')
    assert ev['event_id'].n_unique()==ev.height and val['event_id'].n_unique()==val.height
    assert man['event_id'].n_unique()==man.height
    labels={r['event_id']:r for r in val.to_dicts()}
    manifests={r['event_id']:r for r in man.to_dicts()}
    rows=[]
    for r in ev.to_dicts():
        eid=r['event_id']; m=manifests[eid]
        r.update({k:v for k,v in labels[eid].items() if k!='split'})
        r.update(plen=int(m['prefix'].rsplit('/',1)[1]),new_origin=int(m['new_origin']))
        seed,final=set(r['set_d30s'] or []),set(r['set_final_2h'] or [])
        r.update(j30=len(seed&final)/max(1,len(seed|final)),growing30=len(final)>len(seed))
        rows.append(r)
    for suffix,exclude in [('',None),('_labelled','rpki_invalid_sample')]:
        expected=summary(rows,year,exclude)
        saved=read(f'{base}/rpki_validity_summary{suffix}.json',evidence)
        # JSON coerces a missing GRIP tag dictionary key to "null".
        expected=json.loads(json.dumps(expected))
        population=[r for r in rows if exclude is None or r['reason']!=exclude]
        for validity,group in groups(population,lambda r:r['validity']).items():
            counts=Counter(r['grip_rpki_newcomer'] for r in group if r['grip_labelled'])
            published=saved['grip']['grip_newcomer_rpki_tag_by_validity'][validity]
            validate_top_counts(published,counts)
            expected['grip']['grip_newcomer_rpki_tag_by_validity'][validity]=published
        equal(saved,expected,f'{year}/rpki{suffix}')
    follow=read(f'{base}/later_validity.parquet')
    saved=read(f'{base}/later_validity.json',evidence)
    invalid={r['event_id']:r for r in rows if r['validity']=='invalid'}
    assert follow['event_id'].n_unique()==follow.height and set(follow['event_id'])==set(invalid),(year,'later cohort')
    later=[]
    for r in follow.to_dicts():
        source=invalid[r['event_id']]
        r['population']='label-free stratum' if source['reason']=='rpki_invalid_sample' else 'stratified' if source['reason']=='stratified' else 'catalogue'
        equal(r['later_valid'],any(r[f'state_{h}d']=='valid' for h in saved['days']),(year,'later flag'))
        later.append(r)
    expected={'year':year,'days':saved['days'],'by_population':{}}
    for pop,g in groups(later,lambda r:r['population']).items():
        rec={'n':len(g),'valid_any':mean([r['later_valid'] for r in g],3)}
        for h in saved['days']:
            for label,state in [('valid','valid'),('unknown','unknown'),('no_data','no_roa_data')]:
                rec[f'{label}_{h}d']=mean([r[f'state_{h}d']==state for r in g],3)
        expected['by_population'][pop]=rec
    equal(saved,expected,f'{year}/later')
    suffix='' if year==2022 else '_labelled'
    vp=read(f'{base}/per_vp_by_validity{suffix}.json',evidence)
    csv=read(f'{base}/persistence_per_vp_by_validity_test{suffix}.csv',evidence).to_dicts()
    row_equal(vp['per_vp_by_validity'],csv,['validity','collector','delta'],f'{year}/vp csv')
    row_equal(vp['spread'],spread(csv,True),['validity','delta'],f'{year}/vp spread')
    ordering=groups([r for r in csv if r['delta']=='d30s'],lambda r:r['collector'])
    totals=0; ordered=0
    for g in ordering.values():
        values={r['validity']:r['jaccard_mean'] for r in g}
        if {'invalid','unknown','valid'}<=set(values):
            totals+=1; ordered+=values['invalid']>values['unknown']>values['valid']
    equal(vp['ordering_at_30s'],{'d30s':{'collectors_with_all_classes':totals,'invalid>unknown>valid':ordered}},f'{year}/order')
    generic=read(f'{base}/per_vp_duration.json',evidence)
    generic_csv=read(f'{base}/persistence_per_vp_test.csv',evidence).to_dicts()
    row_equal(generic['per_vp_test'],generic_csv,['collector','delta'],f'{year}/generic csv')
    row_equal(generic['per_vp_spread'],spread(generic_csv),['delta'],f'{year}/generic spread')
    equal(generic['events'],len(rows),f'{year}/generic events')
    durations=read(f'{base}/durations.parquet')
    duration_rows=durations.to_dicts()
    duration_by_id={r['event_id']:r for r in duration_rows}
    assert len(duration_by_id)==durations.height and set(duration_by_id)=={r['event_id'] for r in rows},(year,'duration cohort')
    for r in rows:
        d=duration_by_id[r['event_id']]
        equal(d['split'],r['split'],f'{year}/duration split')
        wanted='ephemeral <60 s' if d['duration_s']<60 else '1-10 min' if d['duration_s']<600 else 'persistent >10 min'
        equal(d['bucket'],wanted,f'{year}/duration bucket')
    shares=[{'bucket':bucket,'n':len(g),'frac':len(g)/len(rows)} for bucket,g in groups(duration_rows,lambda r:r['bucket']).items()]
    row_equal(generic['duration_share_all'],shares,['bucket'],f'{year}/duration shares')
    by_duration=[]
    for bucket,g in groups([r for r in rows if r['split']=='test'],lambda r:duration_by_id[r['event_id']]['bucket']).items():
        scores={}
        for delta in ('d30s','d1m','d5m','d15m'):
            values=[]
            for r in g:
                early,final=set(r['set_'+delta] or []),set(r['set_final_2h'] or [])
                values.append(len(early&final)/max(1,len(early|final)))
            scores['J_'+delta]=mean(values,3)
        by_duration.append({'bucket':bucket,'n':len(g),**scores})
    row_equal(generic['persistence_by_duration_test'],by_duration,['bucket'],f'{year}/duration floors')
    row_equal(read(f'{base}/persistence_by_duration_test.csv',evidence).to_dicts(),by_duration,['bucket'],f'{year}/duration csv')
    if raw:
        all_scores=[]
        for r in rows:
            if r['split']!='test': continue
            relative=f"events_replay/{r['event_id']}/membership.parquet"
            mem=read(relative,raw_hashes)
            start=dt.datetime.fromisoformat(r['t0_obs'])
            firsts=defaultdict(dict)
            for collector,asn,ts in mem.select('collector','asn','first_seen').iter_rows():
                elapsed=(ts-start).total_seconds()
                if elapsed<=7200:
                    firsts[collector][asn]=min(firsts[collector].get(asn,float('inf')),elapsed)
            for collector,arrivals in firsts.items():
                for delta,seconds in [('d30s',30),('d1m',60),('d5m',300),('d15m',900)]:
                    all_scores.append({'event_id':r['event_id'],'reason':r['reason'],'validity':r['validity'],
                        'collector':collector,'delta':delta,'jaccard':sum(t<=seconds for t in arrivals.values())/len(arrivals)})
        row_equal(generic_csv,collector_rows(all_scores),['collector','delta'],f'{year}/raw generic')
        selected=[r for r in all_scores if r['delta'] in ('d30s','d1m') and (year==2022 or r['reason']!='rpki_invalid_sample')]
        row_equal(csv,collector_rows(selected,True),['validity','collector','delta'],f'{year}/raw validity')
        equal(vp['events'],len({r['event_id'] for r in selected}),f'{year}/raw vp events')
    for collection in (sources,evidence,raw_hashes):
        for relative,digest in collection.items(): assert sha(data/relative)==digest,(relative,'changed during audit')
    return {'year':year,'events':len(rows),'source_sha256':sources,'evidence_sha256':evidence,'raw_source_sha256':raw_hashes}


def verify_public(data,proof_path):
    proof=json.loads(proof_path.read_text())
    assert proof['status']=='passed' and proof['mode']=='private_source_audit'
    assert proof['years']==list(range(2022,2027))
    results=[audit_year(data,y) for y in proof['years']]
    for category in ('source_sha256','evidence_sha256'):
        current={k:v for r in results for k,v in r[category].items()}
        equal(proof[category],current,category)
    return {'status':'passed','years':proof['years'],'events':sum(r['events'] for r in results)}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('data',type=Path); ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--wait-for-marker',type=Path,action='append',default=[])
    args=ap.parse_args()
    while not all(p.exists() for p in args.wait_for_marker): time.sleep(10)
    with ProcessPoolExecutor(max_workers=5) as pool:
        results=list(pool.map(audit_year,[args.data]*5,range(2022,2027),[True]*5))
    proof={'status':'passed','mode':'private_source_audit','years':list(range(2022,2027)),
        **{category:{k:v for r in results for k,v in r[category].items()} for category in ('source_sha256','evidence_sha256','raw_source_sha256')}}
    args.output.write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps({'status':'passed','events':sum(r['events'] for r in results)}),flush=True)


if __name__=='__main__': main()
