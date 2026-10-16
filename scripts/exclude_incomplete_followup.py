"""Exclude legacy event rows whose observed onset leaves less than two hours in the planned source window."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import polars as pl
from bgbench import config
from bgbench.eventset import run


def exclude(years, tags):
    report=[]
    for year in years:
        for tag in tags:
            folder=config.DATA_ROOT/'eventset'/(str(year)+('_'+tag if tag else ''))
            file=folder/'events.parquet'
            if not file.exists():continue
            table=pl.read_parquet(file)
            bad=pl.col('error').is_null() & (pl.col('observation_lag_s')>3600)
            ids=table.filter(bad)['event_id'].to_list()
            # An earlier publication may already have excluded all late rows.
            # Refresh its derived coverage flag after replay patches as well.
            if not ids and 'measurement_full_followup_within_planned_window' not in table.columns:continue
            backup=folder/'events.before-followup-exclusion.parquet'
            if ids and not backup.exists():shutil.copy2(file,backup)
            measured=[c for c in table.columns if c.startswith(('set_','asns_','vp_')) or c in ('t90_s',)]
            table=table.with_columns([pl.when(bad).then(None).otherwise(pl.col(c)).alias(c) for c in measured]+[
                pl.when(bad).then(pl.lit('insufficient_planned_followup')).otherwise(pl.col('error')).alias('error'),
                (pl.col('observation_lag_s')<=3600).alias('measurement_full_followup_within_planned_window')])
            run(year,tag,table_override=table)
            if ids:report.append({'year':year,'tag':tag,'excluded_events':ids})
    print(json.dumps(report),flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--years',type=int,nargs='+',default=list(range(2022,2027)))
    parser.add_argument('--tags',nargs='+',default=['origin','leak','withdrawal'])
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    args.report.write_text(json.dumps(exclude(args.years,['' if t=='origin' else t for t in args.tags]),indent=1))
