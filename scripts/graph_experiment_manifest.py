"""List cited experiment reruns whose corrected tensors are ready, without overwriting prior manifests."""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('original_tgn', type=Path)
parser.add_argument('corrected_tgn', type=Path)
parser.add_argument('out', type=Path)
parser.add_argument('--exclude-manifests', nargs='*', type=Path, default=[])
args = parser.parse_args()
ready, waiting, archived = [], [], []
submitted = {r['original_summary'] for f in args.exclude_manifests for r in json.loads(f.read_text())['ready']}
for summary in sorted(args.original_tgn.glob('*/*/_results/*_summary.json')):
    if str(summary) in submitted:
        continue
    setting = summary.parents[2].name
    if setting in ('2024', '2024_leak'):
        archived.append(str(summary)); continue
    info = json.loads(summary.read_text())
    year, _, tag = setting.partition('_')
    years = str(info.get('years', year)).replace('>', ',').split(',')
    prerequisites = [args.corrected_tgn / (y + ('_' + tag if tag else '')) / summary.parents[1].name for y in years]
    def complete(d):
        f = d / "correction-impact.json"
        if not f.exists():
            return False
        impact = json.loads(f.read_text())
        return bool(impact.get("events") or impact.get("added_ids") or impact.get("rebuilt_from_replay"))
    valid = all(complete(d) and (d / 'correction-impact.json').exists() and (d / 'history-correction.json').exists() and next(d.glob('*.pt'), None) is not None for d in prerequisites)
    row = {'original_summary': str(summary), 'prerequisites': [str(d) for d in prerequisites], 'kind': 'cpu' if summary.name.startswith('hist_avg') else 'gpu'}
    row['resource_class'] = 'cpu' if row['kind'] == 'cpu' else 'temporal' if summary.name.startswith(('dyrep', 'tgn')) else 'static'
    (ready if valid else waiting).append(row)
args.out.mkdir(parents=True, exist_ok=True)
(args.out / 'manifest.json').write_text(json.dumps({'ready': ready, 'waiting': waiting, 'archived_unused': archived}, indent=2))
for kind in ('gpu', 'cpu'):
    (args.out / (kind + '.txt')).write_text(''.join(x['original_summary']+'\n' for x in ready if x['kind']==kind))
for kind in ('temporal', 'static'):
    (args.out / (kind + '.txt')).write_text(''.join(x['original_summary']+'\n' for x in ready if x['resource_class']==kind))
print(json.dumps({'ready': len(ready), 'waiting': len(waiting), 'archived_unused': len(archived)}))
