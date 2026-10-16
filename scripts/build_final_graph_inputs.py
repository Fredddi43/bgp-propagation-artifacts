"""Build one final graph cohort in an isolated DATA_ROOT after replay publication.

This deliberately starts from corrected replay instead of patching tensors in use
by preliminary jobs. The original invalid-slice sample budget and RNG are retained.
"""
import argparse
import hashlib
import json
from pathlib import Path

from bgbench import config
from bgbench.tgn_data import build_split, parse_tag, replay_tag, feature_width

parser = argparse.ArgumentParser()
parser.add_argument('year', type=int)
parser.add_argument('tag')
parser.add_argument('delta', type=int)
args = parser.parse_args()
folder = config.tgn_dir(args.year, args.delta, args.tag)
base, _ = parse_tag(args.tag)
max_events = 3000 if base == 'rpkiinvalid' else None
result = build_split(args.year, args.delta, max_events=max_events, tag=args.tag)
(folder / 'history-correction.json').write_text(json.dumps({'events': result['built'], 'already_current': result['built'],
    'changed_events': 0, 'rule': 'prior_onset_plus_7200_le_current_trigger', 'feature_dim': feature_width(args.tag)}, indent=2))
family = replay_tag(args.tag)
table = config.DATA_ROOT / 'eventset' / (str(args.year) + ('_' + family if family else '')) / 'events.parquet'
result.update(rebuilt_from_replay=True, sampling_seed=0, max_events=max_events,
              event_table_sha256=hashlib.sha256(table.read_bytes()).hexdigest(),
              source_root=str(config.DATA_ROOT.resolve()), final_replay=True)
(folder / 'correction-impact.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result), flush=True)
