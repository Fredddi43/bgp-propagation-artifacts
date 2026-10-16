"""Independently match corrected beacon cycles to retained raw observations."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

import polars as pl


def verify(observations, cycles):
    observed=pl.read_parquet(observations)
    raw=observed.filter(pl.col('elem_type')=='A')
    output=pl.read_parquet(cycles)
    # Calendar arithmetic deliberately independent of the producer's truncate.
    mapping=[]
    for kind,origin in raw.select('kind','orig_ts').unique().drop_nulls().iter_rows():
        step=1200 if kind=='fast' else 14400
        midnight=origin.replace(hour=0,minute=0,second=0,microsecond=0)
        seconds=(origin-midnight).total_seconds()
        mapping.append({'kind':kind,'orig_ts':origin,'decoded_slot':midnight+dt.timedelta(seconds=int(seconds//step)*step)})
    raw=(raw.join(pl.DataFrame(mapping),on=['kind','orig_ts'],how='left',validate='m:1')
        .with_columns(slot_ts=pl.coalesce('decoded_slot','slot_ts'),origin_known=pl.col('orig_ts').is_not_null()))
    keys=['prefix','kind','setup','slot_ts','collector','peer_ip','peer_asn','origin_known']
    minima=raw.group_by(keys).agg(first_a_ts=pl.col('ts').min(),n_a=pl.len())
    matched=output.join(minima,on=keys,how='full',suffix='_raw',coalesce=True,validate='1:1')
    failures={
        'missing_or_unexpected_cycles':matched.filter(pl.col('n_a').is_null()|pl.col('n_a_raw').is_null()).height,
        'first_timestamp_mismatch':matched.filter(pl.col('first_a_ts').ne_missing(pl.col('first_a_ts_raw'))).height,
        'announcement_count_mismatch':matched.filter(pl.col('n_a').ne_missing(pl.col('n_a_raw'))).height,
    }
    first_rows=raw.join(minima.select(*keys,pl.col('first_a_ts').alias('ts')),on=keys+['ts'],how='inner')
    expected=first_rows.group_by(keys).agg(orig_ts=pl.col('orig_ts').min(),
        ambiguous=pl.col('orig_ts').drop_nulls().n_unique()>1)
    matched=output.join(expected,on=keys,how='inner',suffix='_raw',validate='1:1')
    failures['first_origin_pair_mismatch']=matched.filter(pl.col('orig_ts').ne_missing(pl.col('orig_ts_raw'))).height
    failures['ambiguity_flag_mismatch']=matched.filter(pl.col('first_a_origin_ambiguous')!=pl.col('ambiguous')).height
    withdrawal_keys=['prefix','slot_ts','collector','peer_ip']
    withdrawals=observed.filter(pl.col('elem_type')=='W').group_by(withdrawal_keys).agg(
        first_w_ts=pl.col('ts').min(),n_w=pl.len())
    matched=output.join(withdrawals,on=withdrawal_keys,how='left',suffix='_raw',validate='m:1')
    failures['first_withdrawal_mismatch']=matched.filter(pl.col('first_w_ts').ne_missing(pl.col('first_w_ts_raw'))).height
    failures['withdrawal_count_mismatch']=matched.filter(pl.col('n_w').ne_missing(pl.col('n_w_raw'))).height
    scheduled=pl.col('slot_ts')+pl.when(pl.col('kind')=='fast').then(pl.duration(minutes=10)).otherwise(pl.duration(hours=2))
    failures['withdrawal_schedule_mismatch']=output.filter(pl.col('first_w_ts').is_not_null() & pl.col('sched_wd_ts').ne_missing(scheduled)).height
    return {'source_announcement_rows':raw.height,'cycle_strata':output.height,'failures':failures,
        'source_sha256':hashlib.sha256(observations.read_bytes()).hexdigest(),
        'cycles_sha256':hashlib.sha256(cycles.read_bytes()).hexdigest(),
        'scope':'Exact cycle-stratum population, first raw arrival and its own origin, tie ambiguity announcement counts and first withdrawal/scheduled clocks; no producer functions imported'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('observations',type=Path)
    parser.add_argument('cycles',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    result=verify(args.observations,args.cycles)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
    raise SystemExit(int(any(result['failures'].values())))
