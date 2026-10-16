"""Independent check that completed pooled graph runs use the canonical full target.

VP-conditioned and shifted-trigger runs have different inputs and are excluded here;
their tensor metadata are validated by the scorer. The main ladder must exactly
reproduce event-table persistence for every scored event, across pooled splits.
"""
import json
from pathlib import Path

import polars as pl

from bgbench import config

cache = {}
checks, failures = 0, []
for f in sorted((config.DATA_ROOT / 'tgn').glob('*/*/_results/*_test_per_event.csv')):
    setting = f.parents[2].name
    if '@' in setting:
        continue
    _, _, tag = setting.partition('_')
    family = 'leak' if tag.startswith('leak') else '' if tag in ('rpkivalid','rpkiinvalid') else tag
    delta = int(f.parents[1].name[1:-1])
    delta_name = {30:'d30s',60:'d1m',300:'d5m',900:'d15m'}[delta]
    rows = pl.read_csv(f)
    if 'jaccard_persist' not in rows.columns:
        continue
    for row in rows.iter_rows(named=True):
        year = row['event_id'][:4]
        key = (year, family)
        if key not in cache:
            path = config.DATA_ROOT / 'eventset' / (year+('_'+family if family else '')) / 'events.parquet'
            cache[key] = {r['event_id']: r for r in pl.read_parquet(path).iter_rows(named=True)}
        canonical = cache[key][row['event_id']]
        seeds, truth = set(canonical['set_'+delta_name]), set(canonical['set_final_2h'])
        expected = len(seeds & truth) / len(seeds | truth) if seeds | truth else float('nan')
        checks += 1
        if abs(expected-row['jaccard_persist']) > 1e-10:
            failures.append({'file':str(f),'event_id':row['event_id'],'expected':expected,'observed':row['jaccard_persist']})
report = {'persistence_checks':checks,'failures':failures,'data_root':str(config.DATA_ROOT)}
print(json.dumps(report,indent=2))
if failures:
    raise SystemExit(1)
