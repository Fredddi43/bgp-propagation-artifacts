"""Exact auxiliary evaluation allowlist, independent of which jobs have finished."""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('output', type=Path)
args = parser.parse_args()
paths = ['analysis/graph_paired_comparisons.json', 'analysis/graph_auxiliary_verification.json']
for delta in (30, 60):
    folder = f'tgn/2024_leak200/d{delta}s/_results/'
    paths.extend(folder + 'sage_robustness' + suffix for suffix in ('.json', '.csv', '_per_event.csv'))
    paths.extend(folder + model + '_per_vp' + suffix for model in ('sage', 'gat', 'tgn', 'dyrep')
                 for suffix in ('.csv', '_per_event.csv'))
    paths.extend(f'tgn/2024_withdrawal/d{delta}s/_results/cross_sage_leak2002024' + suffix
                 for suffix in ('.json', '_per_event.csv'))
    for year in (2024, 2025):
        paths.extend(f'tgn/{year}_leak200/d{delta}s/_results/sage_prf1' + suffix
                     for suffix in ('.json', '_per_event.csv'))
for shift in (0, -30, 60, 300, 900):
    tag = 'leak200' + (f'@t0={shift}' if shift else '')
    paths.extend(f'tgn/2025_{tag}/d30s/_results/cross_sage_leak2002025' + suffix
                 for suffix in ('.json', '_per_event.csv'))
paths.append('tgn/2025_leak200/d30s/_results/trigger_error_common_cohort.json')
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps({'auxiliary_files': paths, 'requires': 'graph-final-models-complete.json'}, indent=2))
print(json.dumps({'files': len(paths)}))
