"""Paired comparisons of declared final model outputs on identical event populations.

Candidate/feature ablations are comparable on full observed truth. Collector and
RPKI-class cohorts remain separate. Missing declared files and unequal IDs fail.
"""
import argparse
from collections import defaultdict
import itertools
import json
from pathlib import Path

import numpy as np
import polars as pl

parser = argparse.ArgumentParser()
parser.add_argument('data', type=Path)
parser.add_argument('expected_manifest', type=Path)
parser.add_argument('output', type=Path)
parser.add_argument('--years')
parser.add_argument('--delta', type=int)
parser.add_argument('--base')
parser.add_argument('--core-only', action='store_true', help='Compare main architectures and historical baselines without feature/candidate ablations')
args = parser.parse_args()
expected = json.loads(args.expected_manifest.read_text())
groups = defaultdict(list)
for relative in expected['model_tables']:
    path = args.data / relative
    setting, delta_dir = path.parents[2].name, path.parents[1].name
    year, _, tag = setting.partition('_')
    base, _, options = tag.partition('@')
    options = dict(part.split('=', 1) for part in options.split(',') if '=' in part)
    if args.delta is not None and delta_dir != f'd{args.delta}s':
        continue
    if args.base and base != args.base:
        continue
    summary_path = path.with_name(path.name.replace('_test_per_event.csv', '_summary.json'))
    # Read the expected protocol from the filename even if this required run is missing.
    suffix = path.name.removesuffix('_test_per_event.csv')
    protocol = suffix.rsplit('_', 1)[-1]
    if '+' in protocol or '_to_' in suffix:
        protocol = suffix[suffix.find('_20')+1:].replace('_to_', '>').replace('+', ',')
    else:
        protocol = year
    if args.years and protocol != args.years:
        continue
    main_name = suffix.split('_20', 1)[0]
    if args.core_only and (options or main_name not in ('sage', 'gat', 'tgn', 'dyrep', 'hist_avg', 'hist_avg_online_completed')):
        continue
    summary = json.loads(summary_path.read_text())
    years = str(summary.get('years', year))
    frame = pl.read_csv(path)
    if frame['event_id'].n_unique() != frame.height:
        raise ValueError(f'Duplicate event IDs: {path}')
    score = 'jaccard_hist' if suffix.startswith('hist_avg') else 'jaccard_model_tuned'
    key = (years, base, options.get('vp', 'pooled_collectors'), delta_dir)
    groups[key].append((relative, frame.select('event_id', 'jaccard_persist', pl.col(score).alias('score'))))

comparisons = []
for key, entries in sorted(groups.items()):
    for (name_a, a), (name_b, b) in itertools.combinations(entries, 2):
        if set(a['event_id']) != set(b['event_id']):
            raise ValueError(f'Population mismatch: {name_a} versus {name_b}')
        joined = a.join(b, on='event_id', suffix='_b').sort('event_id')
        if not np.allclose(joined['jaccard_persist'], joined['jaccard_persist_b'], atol=1e-10, rtol=0):
            raise ValueError(f'Target/persistence mismatch: {name_a} versus {name_b}')
        diff = (joined['score'] - joined['score_b']).to_numpy()
        rng = np.random.default_rng(0)
        means = [diff[rng.integers(0, len(diff), len(diff))].mean() for _ in range(2000)]
        interval = np.quantile(means, [.025, .975]).tolist()
        comparisons.append({'years': key[0], 'base': key[1], 'collector_scope': key[2], 'delta': key[3],
            'model_a': name_a, 'model_b': name_b, 'events': len(diff), 'mean_a': joined['score'].mean(),
            'mean_b': joined['score_b'].mean(), 'difference_a_minus_b': float(diff.mean()), 'ci95': interval})
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps({'comparisons': comparisons, 'interval_method': '2000 paired event bootstrap resamples, seed0, unadjusted percentile95'}, indent=2))
print(json.dumps({'groups': len(groups), 'paired_comparisons': len(comparisons), 'output': str(args.output)}))
