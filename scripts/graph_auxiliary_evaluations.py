"""Post-training evaluations cited by the paper, using corrected frozen inputs."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

import polars as pl

from bgbench import config
from bgbench.robustness import cross_eval, run

parser = argparse.ArgumentParser()
parser.add_argument('kind', choices=['robustness', 'transfer', 'trigger', 'prf1', 'per-vp', 'historical-online'])
parser.add_argument('year', type=int)
parser.add_argument('delta', type=int)
args = parser.parse_args()
scripts = Path(__file__).parent
if args.kind == 'robustness':
    result = run(args.year, args.delta, 'leak200')
elif args.kind == 'historical-online':
    from bgbench.hist_avg import run as historical
    result = historical(args.year, args.delta, 'leak200', online_completed=True)
elif args.kind == 'transfer':
    result = cross_eval(args.year, 'leak200', args.year, 'withdrawal', args.delta)
elif args.kind == 'trigger':
    frames, summaries = {}, {}
    for shift in (0, -30, 60, 300, 900):
        tag = 'leak200' + (f'@t0={shift}' if shift else '')
        result = cross_eval(args.year, 'leak200', args.year, tag, args.delta)
        if 'error' in result:
            raise RuntimeError(result)
        summaries[shift] = result
        frames[shift] = pl.read_csv(config.tgn_dir(args.year, args.delta, tag) / '_results' / f'cross_sage_leak200{args.year}_per_event.csv')
    common = set.intersection(*(set(frame['event_id']) for frame in frames.values()))
    paired = {}
    for shift, frame in frames.items():
        frame = frame.filter(pl.col('event_id').is_in(sorted(common)))
        paired[shift] = {'events': frame.height, 'jaccard_model': frame['jaccard_thr'].mean(),
                         'jaccard_persist': frame['jaccard_persist'].mean()}
    result = {'all_eligible_by_shift': summaries, 'common_event_ids': sorted(common), 'paired_common_cohort': paired}
    out = config.tgn_dir(args.year, args.delta, 'leak200') / '_results' / 'trigger_error_common_cohort.json'
    out.write_text(json.dumps(result, indent=2))
else:
    prefixes = ('sage',) if args.kind == 'prf1' else ('sage', 'gat', 'tgn', 'dyrep')
    for prefix in prefixes:
        subprocess.run([sys.executable, str(scripts / ('prf1_from_probs.py' if args.kind == 'prf1' else 'per_vp_model_eval.py')),
                        str(args.year), 'leak200', str(args.delta), prefix], check=True)
    result = {'evaluated': args.kind, 'year': args.year, 'delta': args.delta}
if 'error' in result:
    raise RuntimeError(result)
print(json.dumps(result, indent=2), flush=True)
