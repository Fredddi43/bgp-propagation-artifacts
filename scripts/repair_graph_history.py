"""Cheap post-refresh causal history repair, without rereading announcement tables."""
import json
import sys
from pathlib import Path

import numpy as np
import polars as pl
import torch

from bgbench import config
from bgbench.graph_metrics import completed_event_histories
from bgbench.tgn_data import parse_tag, replay_tag, feature_width

folder = Path(sys.argv[1])
year, _, tag = folder.parent.name.partition('_')
base, options = parse_tag(tag)
replay = replay_tag(tag)
table = pl.read_parquet(config.DATA_ROOT / 'eventset' / (year + ('_' + replay if replay else '')) / 'events.parquet').filter(pl.col('error').is_null()).unique('event_id')
if replay == 'leak':
    table = table.filter(pl.col('observation_lag_s').is_null() | (pl.col('observation_lag_s') >= -60))
if base == 'leak200':
    table = table.filter(pl.col('set_final_2h').list.len() >= 200)
if base in ('rpkivalid', 'rpkiinvalid'):
    validity = pl.read_parquet(config.DATA_ROOT / 'eventset' / year / 'rpki_validity.parquet')
    table = table.join(validity.filter(pl.col('validity') == base[4:]).select('event_id'), on='event_id', how='semi')
histories = completed_event_histories(dict(zip(table['event_id'], table['t0_obs'])), dict(zip(table['event_id'], table['set_final_2h'].to_list())), query_offset_seconds=float(options.get('t0', 0)))
changed, total, already_current = 0, 0, 0
for f in folder.glob('*.pt'):
    event = torch.load(f, weights_only=False)
    if event.get('history_version') == 2:
        already_current += 1
        continue
    values = torch.tensor([np.log1p(histories[event['event_id']].get(int(a), 0)) for a in event['asn']], dtype=event['x'].dtype)
    changed += int(not torch.equal(values, event['x'][:, 10])); total += 1
    event['x'][:, 10] = values
    if 'first_s' in event:
        event['first_s'][event['y'] == 0] = -1
    feature_dim = feature_width(tag)
    event['x'] = event['x'][:, :feature_dim].contiguous()
    if feature_dim > 18:
        event['x'][:, 18] = 0  # undated RoVista country snapshot is unavailable prospectively
    event['feature_dim'] = feature_dim
    event['history_version'] = 2
    torch.save(event, f)
(folder / 'history-correction.json').write_text(json.dumps({'events': total + already_current, 'already_current': already_current, 'changed_events': changed, 'rule': 'prior_onset_plus_7200_le_current_trigger'}, indent=2))
print(json.dumps({'folder': str(folder), 'events': total, 'changed_events': changed}), flush=True)
