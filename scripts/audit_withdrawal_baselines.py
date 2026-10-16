"""Audit retained pre-event RIB availability/age for every withdrawal candidate."""
from __future__ import annotations
import argparse,bisect,datetime as dt,hashlib,json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import polars as pl
import pyarrow.parquet as pq
TEN=['rrc25','rrc00','rrc12','rrc01','route-views3','rrc03','route-views2','rrc20','rrc15','route-views.linx']


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def audit(data):
    ribs={}
    for collector in TEN:
        ribs[collector]=sorted((dt.datetime.strptime(p.stem,'%Y-%m-%dT%H%M').replace(tzinfo=dt.UTC),p) for p in (data/'ribs'/collector).glob('*.parquet'))
    timestamps={c:[x[0] for x in v] for c,v in ribs.items()}
    paths=[];sources={}
    for year in range(2022,2027):
        p=data/f'eventset/{year}_withdrawal/events.parquet';sources[str(p.relative_to(data))]=sha(p)
        for row in pl.read_parquet(p).iter_rows(named=True):paths.append((year,row))
    def event(item):
        year,row=item;eid=row['event_id']
        summary_path=data/'events_replay_withdrawal'/eid/'summary.json'
        summary=json.loads(summary_path.read_text())
        onset=dt.datetime.fromisoformat(summary['t0'])
        parts=sorted((data/'events_replay_parts_withdrawal'/eid).glob('*.parquet'))
        assert parts,(eid,'no original part files')
        actual=[];parts_metadata=[]
        for path in parts:
            assert path.stem in TEN,(eid,'unexpected part filename',path.name)
            metadata=pq.ParquetFile(path).metadata
            parts_metadata.append({'collector':path.stem,'rows':metadata.num_rows,'bytes':path.stat().st_size})
            if metadata.num_rows:actual.append(path.stem)
        records=[]
        # Every requested collector is required by the declared replay design;
        # actual nonempty parts are separately reported, not a smaller denominator.
        for collector in TEN:
            index=bisect.bisect_right(timestamps[collector],onset)-1
            selected=ribs[collector][index] if index>=0 else None
            age=(onset-selected[0]).total_seconds() if selected else None
            records.append({'collector':collector,'has_nonempty_part':collector in actual,
                            'rib_path':str(selected[1].relative_to(data)) if selected else None,
                            'rib_timestamp':selected[0].isoformat() if selected else None,'age_seconds':age,
                            'status':'missing' if selected is None else 'stale' if age>7*86400 else 'supported'})
        missing=[r['collector'] for r in records if r['status']=='missing'];stale=[r['collector'] for r in records if r['status']=='stale']
        no_baselines=all(r['rib_path'] is None for r in records if r['has_nonempty_part'])
        return {'event_id':eid,'year':year,'split':row['split'],'existing_error':row['error'],'t0':onset.isoformat(),
                'required_collectors':TEN,'actual_nonempty_part_collectors':sorted(actual),'parts_metadata':parts_metadata,
                'collectors':records,'missing_baseline_collectors':missing,'stale_baseline_collectors':stale,
                'supported':not missing and not stale,'rib_vp_prefix_rows':summary.get('rib_vp_prefix_rows'),
                'wave_prefixes':summary.get('wave_prefixes'),'zero_baseline_reason':('no_pre_event_rib_snapshots' if no_baselines else 'no_matching_wave_prefix_rows') if summary.get('rib_vp_prefix_rows')==0 else None,
                'summary_path':str(summary_path.relative_to(data)),'summary_sha256':sha(summary_path)}
    with ThreadPoolExecutor(max_workers=16) as pool:rows=list(pool.map(event,paths))
    summary={str(y):{'events':sum(r['year']==y for r in rows),'supported':sum(r['year']==y and r['supported'] for r in rows),
                    'missing':sum(r['year']==y and bool(r['missing_baseline_collectors']) for r in rows),
                    'stale':sum(r['year']==y and bool(r['stale_baseline_collectors']) for r in rows)} for y in range(2022,2027)}
    return {'status':'passed','scope':'All selected withdrawal candidates and all ten requested collectors; latest available RIB at or before identifier, maximum age seven days.',
            'policy':{'required_collectors':TEN,'maximum_age_seconds':7*86400},'events':rows,'by_year':summary,'source_sha256':sources,
            'rib_filename_inventory':{c:[p.name for _,p in v] for c,v in ribs.items()}}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('data',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=audit(a.data);a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result['by_year']))
