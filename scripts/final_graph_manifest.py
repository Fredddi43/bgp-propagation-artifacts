"""Enumerate cited graph reruns and their input cohorts before final publication."""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('original_tgn', type=Path)
parser.add_argument('output', type=Path)
args = parser.parse_args()
cohorts, experiments, archived = set(), [], []
expected = {'model_tables': [], 'model_targets': {}, 'model_checkpoints': [], 'event_tables': [], 'model_cohorts': {}}
target_tables = set()


def add_expected(summary, years, tag, delta, online=False):
    relative = Path('tgn') / summary.relative_to(args.original_tgn)
    if online:
        relative = relative.with_name(relative.name.replace('hist_avg', 'hist_avg_online_completed', 1))
    csv = str(relative).replace('_summary.json', '_test_per_event.csv')
    expected['model_tables'].append(csv)
    base, _, options = tag.partition('@')
    options = dict(part.split('=', 1) for part in options.split(',') if '=' in part)
    family = 'leak' if base.startswith('leak') else '' if base in ('rpkivalid', 'rpkiinvalid') else base
    test_years = str(years).split('>')[-1].split(',')
    tables = [y + ('_' + family if family else '') for y in test_years]
    target = {'horizon': {30: 'd30s', 60: 'd1m', 300: 'd5m', 900: 'd15m'}[delta],
              'count_forecast': 'final' if summary.name.startswith('hist_avg') else 'curve'}
    target['membership_predictions'] = ({'hist': 'predicted_asns_hist'} if summary.name.startswith('hist_avg') else
                                        {'model': 'predicted_asns_at05', 'model_tuned': 'predicted_asns_tuned'})
    target.update({'event_table': tables[0]} if len(tables) == 1 else {'event_tables': tables})
    if 'vp' in options:
        target['membership_source'] = {'replay_family': family, 'collector': options['vp']}
    if tag == 'leak200' and str(years) in ('2024', '2025') and delta in (30, 60) and summary.name in {m + '_summary.json' for m in ('sage', 'gat', 'tgn', 'dyrep')}:
        target['probability_evidence'] = csv.replace('_test_per_event.csv', '_test_probs.pt')
    expected['model_targets'][csv] = target
    expected['model_cohorts'][csv] = {
        'index_tables': [str(Path('tgn') / (y + ('_' + tag if tag else '')) / f'd{delta}s' / 'index.csv') for y in test_years],
        'split': 'all' if '>' in str(years) else 'test'}
    target_tables.update(tables)
    if not summary.name.startswith('hist_avg'):
        expected['model_checkpoints'].append(str(relative).replace('_summary.json', '_model.pt'))
for path in sorted(args.original_tgn.glob('*/*/_results/*_summary.json')):
    setting = path.parents[2].name
    if setting in ('2024', '2024_leak'):
        archived.append(str(path))
        continue
    year, _, tag = setting.partition('_')
    delta = int(path.parents[1].name[1:-1])
    info = json.loads(path.read_text())
    protocol = str(info.get('years', year))
    years = protocol.replace('>', ',').split(',')
    cohorts.update((int(y), tag, delta) for y in years)
    experiments.append(str(path))
    add_expected(path, protocol, tag, delta)
    if tag == 'leak200' and delta in (30, 60) and path.name.startswith('hist_avg') and year in ('2024', '2025'):
        add_expected(path, protocol, tag, delta, online=True)
# Saved-model evaluations have input cohorts but no training summary of their own.
cohorts.update((2025, f'leak200@t0={shift}', 30) for shift in (-30, 60, 300, 900))
cohorts.update((2024, 'withdrawal', delta) for delta in (30, 60))
cohorts = sorted(cohorts, key=lambda x: (x[1] != 'leak200', x[2] not in (30, 60), x))
args.output.mkdir(parents=True, exist_ok=True)
(args.output / 'manifest.json').write_text(json.dumps({'cohorts': cohorts, 'experiments': experiments, 'archived_unused': archived}, indent=2))
expected['event_tables'] = sorted(target_tables)
(args.output / 'expected-verification.json').write_text(json.dumps(expected, indent=2))
for name, subset in [('all', cohorts), ('leak', [c for c in cohorts if c[1].startswith('leak')]),
                     ('origin-withdrawal', [c for c in cohorts if not c[1].startswith('leak')])]:
    (args.output / (name + '.txt')).write_text(''.join(f'{y} {tag} {delta}\n' for y, tag, delta in subset))
print(json.dumps({'cohorts': len(cohorts), 'experiments': len(experiments), 'archived_unused': len(archived)}))
