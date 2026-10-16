"""Rebuild boundary-affected graph cohorts and prove exact consumed-input equality.

This never replaces frozen inputs or authorizes reuse of a changed tensor. A
passing report binds all declared model/auxiliary dependencies to two immutable
source snapshots. The release assembler must separately check the exact allowed
event-table changes and the independent numerical evidence.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import polars as pl


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def canonical(frame, columns):
    """Canonical semantic rows; list-valued source columns represent sets."""
    rows = []
    for row in frame.select(columns).iter_rows(named=True):
        rows.append({k: sorted(v) if isinstance(v, list) else v for k, v in row.items()})
    rows.sort(key=lambda r: str(r.get('event_id', json.dumps(r, sort_keys=True, default=str))))
    return json.dumps(rows, sort_keys=True, default=str, separators=(',', ':'))


@lru_cache(maxsize=None)
def selected_source(data, year, tag):
    """Independent source-pool and fixed-seed sampling reconstruction."""
    base = tag.split('@')[0]
    family = 'leak' if base.startswith('leak') else '' if base in ('rpkivalid', 'rpkiinvalid') else base
    table = data / 'eventset' / (str(year) + ('_' + family if family else '')) / 'events.parquet'
    frame = pl.read_parquet(table).filter(pl.col('error').is_null())
    if family == 'leak':
        frame = frame.filter(pl.col('observation_lag_s').is_null() | (pl.col('observation_lag_s') >= -60))
    if base == 'leak200':
        frame = frame.filter(pl.col('set_final_2h').list.len() >= 200)
    if base in ('rpkivalid', 'rpkiinvalid'):
        valid = pl.read_parquet(data / 'eventset' / str(year) / 'rpki_validity.parquet')
        frame = frame.join(valid.filter(pl.col('validity') == base[4:]).select('event_id'), on='event_id', how='semi')
    if frame['event_id'].n_unique() != frame.height:
        raise ValueError(f'Duplicate source IDs: {table}')
    if base == 'rpkiinvalid':
        rng = np.random.default_rng(0)
        selected = []
        for split in ('train', 'test'):
            pool = frame.filter(pl.col('split') == split)['event_id'].to_list()
            selected.extend(pool[i] for i in sorted(rng.choice(len(pool), size=min(1500, len(pool)), replace=False)))
    else:
        selected = sorted(frame['event_id'].to_list())
    return family, table, frame, selected


def tensor_differences(before, after):
    import torch
    differences = []
    for key in sorted(set(before) | set(after)):
        if key not in before or key not in after:
            differences.append(key)
            continue
        a, b = before[key], after[key]
        if isinstance(a, torch.Tensor) and isinstance(b, torch.Tensor):
            equal = a.dtype == b.dtype and a.shape == b.shape and torch.equal(a, b)
        else:
            equal = type(a) is type(b) and a == b
        if not equal:
            differences.append(key)
    return differences


def source_evaluation_projection(frame, ids):
    # Onsets drive the training-label embargo and online baseline library. Sets
    # drive independent evaluation, including out-of-candidate targets/counts.
    columns = [c for c in frame.columns if c in ('event_id', 'error', 'split', 't0_obs', 'observation_lag_s') or c.startswith('set_')]
    return canonical(frame.filter(pl.col('event_id').is_in(sorted(ids))), sorted(columns))


def membership_projection(data, family, event_id, onset):
    """Collector targets consumed by per-VP and transfer/trigger evaluation."""
    import datetime as dt
    path = data / ('events_replay' + ('_' + family if family else '')) / event_id / 'membership.parquet'
    if not path.exists():
        raise FileNotFoundError(path)
    cutoff = dt.datetime.fromisoformat(onset) + dt.timedelta(hours=2) if isinstance(onset, str) else onset + dt.timedelta(hours=2)
    frame = pl.read_parquet(path).filter(pl.col('first_seen') <= cutoff)
    frame = frame.group_by('collector', 'asn').agg(pl.col('first_seen').min()).sort('collector', 'asn')
    return canonical(frame, ['collector', 'asn', 'first_seen'])


def dependency_closure(frozen, cohorts, models, auxiliary):
    covered = {str(Path('tgn') / f'{year}_{tag}' / f'd{delta}s') for year, tag, delta in cohorts}
    dependencies = {}
    for relative in models['model_tables']:
        summary = json.loads((frozen / relative.replace('_test_per_event.csv', '_summary.json')).read_text())
        years = str(summary['years']).replace('>', ',').split(',')
        required = {str(Path('tgn') / f'{y}_{summary["tag"]}' / f'd{summary["delta_s"]}s') for y in years}
        required.update(str(Path(p).parent) for p in models['model_cohorts'][relative]['index_tables'])
        if not required <= covered:
            raise ValueError(f'Unaudited model dependencies for {relative}: {sorted(required - covered)}')
        dependencies[relative] = sorted(required)
    for relative in auxiliary['auxiliary_files']:
        path = Path(relative)
        if path.parts[0] == 'analysis':
            required = covered.copy()
        else:
            required = {str(Path(*path.parts[:3]))}
            if path.name.startswith('cross_sage_leak200'):
                year = path.name.removeprefix('cross_sage_leak200')[:4]
                required.add(str(Path('tgn') / f'{year}_leak200' / path.parts[2]))
        if not required <= covered:
            raise ValueError(f'Unaudited auxiliary dependencies for {relative}: {sorted(required - covered)}')
        dependencies[relative] = sorted(required)
    return dependencies


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('frozen', type=Path)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('changes', type=Path, help='JSON changes:[{year,family,event_ids}] with origin family empty or origin')
    parser.add_argument('build_manifest', type=Path, help='Final manifest.json containing every tensor cohort')
    parser.add_argument('model_manifest', type=Path)
    parser.add_argument('auxiliary_manifest', type=Path)
    parser.add_argument('output', type=Path, help='New isolated audit directory')
    parser.add_argument('--workers', type=int, default=8)
    args = parser.parse_args()
    import torch

    if args.frozen.resolve() == args.candidate.resolve():
        raise ValueError('Candidate must be a separate snapshot')
    if args.output.exists():
        raise FileExistsError('Use a new audit directory; do not reuse possibly stale tensors')
    args.output.mkdir(parents=True)
    working = args.output / 'data'
    working.mkdir()
    for name in ('graphs', 'rpki', 'eventset', 'events_replay', 'events_replay_leak', 'events_replay_withdrawal'):
        target = args.candidate / name
        if target.exists():
            (working / name).symlink_to(target.resolve(), target_is_directory=True)
    (working / 'tgn').mkdir()
    changes = json.loads(args.changes.read_text())
    scopes = {(int(row['year']), '' if row['family'] == 'origin' else row['family']) for row in changes['changes']}
    cohorts = json.loads(args.build_manifest.read_text())['cohorts']
    models = json.loads(args.model_manifest.read_text())
    auxiliary = json.loads(args.auxiliary_manifest.read_text())
    report = {'status': 'running', 'frozen_root': str(args.frozen.resolve()), 'candidate_root': str(args.candidate.resolve()),
              'contract_sha256': {str(p): digest(p) for p in (args.changes, args.build_manifest, args.model_manifest, args.auxiliary_manifest)},
              'model_tables': models['model_tables'], 'auxiliary_files': auxiliary['auxiliary_files'], 'cohorts': [], 'failures': []}
    report['dependency_closure'] = dependency_closure(args.frozen, cohorts, models, auxiliary)
    # All non-replay auxiliary inputs must retain their exact frozen paths. The
    # candidate snapshot must not silently substitute new graph or ROV data.
    for name in ('graphs', 'rpki'):
        if (args.frozen / name).resolve() != (args.candidate / name).resolve():
            raise ValueError(f'Changed shared dependency root: {name}')
    code = Path(__file__).resolve().parents[1]
    producer_files = sorted((code / 'src/bgbench').glob('*.py')) + [code / 'scripts/build_final_graph_inputs.py']
    report['producer_sha256'] = {str(p.relative_to(code)): digest(p) for p in producer_files}
    # Bind every source file read while considering the sampled event pool,
    # including events that the graph-availability cut eventually drops.
    source_files = set()
    replay_files = {}
    for year, tag, delta in cohorts:
        base = tag.split('@')[0]
        for root in (args.frozen, args.candidate):
            family, table, frame, ids = selected_source(root, year, base)
            source_files.add(table.resolve())
            if family == '':
                source_files.add((root / 'eventset' / str(year) / 'rpki_validity.parquet').resolve())
            for event_id in ids:
                replay = root / ('events_replay' + ('_' + family if family else '')) / event_id
                for filename in ('summary.json', 'membership.parquet', 'anomalous.parquet'):
                    path = (replay / filename).resolve()
                    if not path.is_file():
                        raise FileNotFoundError(path)
                    source_files.add(path)
                    replay_files[(str(root), event_id, filename)] = path
            for month in {eid[:6] for eid in ids}:
                source_files.update(path.resolve() for path in (root / 'graphs').glob(month + '*') if path.is_file())
            for relative in ('graphs/asn_country.parquet', 'rpki/rovista/as_rov_series.parquet', 'rpki/rovista/country_scores.json'):
                if (root / relative).is_file():
                    source_files.add((root / relative).resolve())
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        hashes = dict(zip(map(str, sorted(source_files)), pool.map(digest, sorted(source_files))))
    report['source_sha256'] = hashes
    (args.output / 'report.json').write_text(json.dumps(report, indent=2))

    def audit_cohort(cohort):
        year, tag, delta = cohort
        relative = Path('tgn') / f'{year}_{tag}' / f'd{delta}s'
        old_dir = args.frozen / relative
        family, old_table, old_source, old_selected = selected_source(args.frozen, year, tag.split('@')[0])
        _, new_table, new_source, new_selected = selected_source(args.candidate, year, tag.split('@')[0])
        affected = (year, family) in scopes
        record = {'cohort': cohort, 'rebuilt': affected, 'source_before_sha256': digest(old_table),
                  'source_after_sha256': digest(new_table), 'differences': [], 'tensors': {}}
        old_projection = source_evaluation_projection(old_source, old_source['event_id'])
        new_projection = source_evaluation_projection(new_source, new_source['event_id'])
        record['history_pool_before_sha256'] = hashlib.sha256(old_projection.encode()).hexdigest()
        record['history_pool_after_sha256'] = hashlib.sha256(new_projection.encode()).hexdigest()
        record['selected_ids_before'] = old_selected
        record['selected_ids_after'] = new_selected
        raw_equal = old_selected == new_selected and all(
            hashes[str(replay_files[(str(args.frozen), eid, name)])] == hashes[str(replay_files[(str(args.candidate), eid, name)])]
            for eid in set(old_selected) & set(new_selected)
            for name in ('summary.json', 'membership.parquet', 'anomalous.parquet'))
        record['sampled_replay_files_equal'] = raw_equal
        if old_selected != new_selected:
            record['differences'].append('source_selection_or_sampling')
        if not affected and (old_projection != new_projection or not raw_equal):
            raise ValueError(f'Undeclared source-pool or replay change: {cohort}')
        source_hashes = {str(p): digest(p) for p in (old_table, new_table)}
        if family == '':
            for root in (args.frozen, args.candidate):
                path = root / 'eventset' / str(year) / 'rpki_validity.parquet'
                source_hashes[str(path)] = digest(path)
            if len(set(source_hashes[str(root / 'eventset' / str(year) / 'rpki_validity.parquet')] for root in (args.frozen, args.candidate))) != 1:
                raise ValueError('Boundary audit cannot substitute different validity labels')
        # Exact equality of the complete eligibility/history projection and all
        # sampled replay bytes is already a consumed-input equality proof. Only
        # rebuild when one of those inputs actually differs.
        rebuild = affected and (old_projection != new_projection or not raw_equal)
        record['rebuilt'] = rebuild
        if rebuild:
            env = dict(os.environ, BGBENCH_DATA_ROOT=str(working), PYTHONPATH=str(code / 'src'),
                       POLARS_MAX_THREADS='2', OMP_NUM_THREADS='2', MKL_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2')
            log = args.output / (str(relative).replace('/', '__') + '.log')
            with log.open('w') as stream:
                subprocess.run([sys.executable, str(code / 'scripts/build_final_graph_inputs.py'), str(year), tag, str(delta)],
                               env=env, stdout=stream, stderr=subprocess.STDOUT, check=True)
            new_dir = working / relative
        else:
            new_dir = old_dir
        before = pl.read_csv(old_dir / 'index.csv').sort('event_id')
        after = pl.read_csv(new_dir / 'index.csv').sort('event_id')
        if not before.equals(after):
            record['differences'].append('graph_index')
        ids = set(before['event_id']) | set(after['event_id'])
        old_evaluation = source_evaluation_projection(old_source, ids)
        new_evaluation = source_evaluation_projection(new_source, ids)
        if old_evaluation != new_evaluation:
            record['differences'].append('evaluation_source_projection')
        record['evaluation_before_sha256'] = hashlib.sha256(old_evaluation.encode()).hexdigest()
        record['evaluation_after_sha256'] = hashlib.sha256(new_evaluation.encode()).hexdigest()
        for event_id in sorted(ids):
            old_file, new_file = old_dir / f'{event_id}.pt', new_dir / f'{event_id}.pt'
            if not old_file.is_file() or not new_file.is_file():
                record['tensors'][event_id] = {'equal': False, 'fields': ['missing_event']}
                continue
            before_hash = digest(old_file)
            after_hash = before_hash if old_file.resolve() == new_file.resolve() else digest(new_file)
            if before_hash == after_hash:
                differences = []
                method = 'identical_tensor_bytes'
            else:
                old = torch.load(old_file, weights_only=False, map_location='cpu', mmap=True)
                new = torch.load(new_file, weights_only=False, map_location='cpu', mmap=True)
                differences = tensor_differences(old, new)
                method = 'all_tensor_fields'
            record['tensors'][event_id] = {'equal': not differences, 'fields': differences,
                'method': method, 'before_sha256': before_hash, 'after_sha256': after_hash}
        # Rebuilt pooled tensors alone cannot prove per-collector evaluation
        # targets unchanged. Independently bind each collector's first sightings.
        if family in ('leak', 'withdrawal'):
            old_onsets = dict(zip(old_source['event_id'], old_source['t0_obs']))
            new_onsets = dict(zip(new_source['event_id'], new_source['t0_obs']))
            collector = {}
            for event_id in sorted(ids & set(old_onsets) & set(new_onsets)):
                a_hash = hashes[str(replay_files[(str(args.frozen), event_id, 'membership.parquet')])]
                b_hash = hashes[str(replay_files[(str(args.candidate), event_id, 'membership.parquet')])]
                if a_hash == b_hash and old_onsets[event_id] == new_onsets[event_id]:
                    collector[event_id] = {'equal': True, 'method': 'identical_membership_bytes_and_onset',
                                           'before_sha256': a_hash, 'after_sha256': b_hash}
                else:
                    a = membership_projection(args.frozen, family, event_id, old_onsets[event_id])
                    b = membership_projection(args.candidate, family, event_id, new_onsets[event_id])
                    collector[event_id] = {'equal': a == b, 'method': 'collector_first_seen_projection',
                        'before_sha256': hashlib.sha256(a.encode()).hexdigest(), 'after_sha256': hashlib.sha256(b.encode()).hexdigest()}
            record['collector_membership'] = collector
            if any(not row['equal'] for row in collector.values()):
                record['differences'].append('collector_membership')
        if any(not row['equal'] for row in record['tensors'].values()):
            record['differences'].append('consumed_tensors')
        if source_hashes != {p: digest(p) for p in source_hashes}:
            raise ValueError(f'Sources changed during cohort audit: {cohort}')
        record['status'] = 'changed' if record['differences'] else 'equivalent'
        return record

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for record in pool.map(audit_cohort, cohorts):
            report['cohorts'].append(record)
            if record['status'] != 'equivalent':
                report['failures'].append({'cohort': record['cohort'], 'differences': record['differences']})
            print(json.dumps({k: record[k] for k in ('cohort', 'rebuilt', 'status', 'differences')}), flush=True)
            (args.output / 'report.json').write_text(json.dumps(report, indent=2))
    if report['producer_sha256'] != {str(p.relative_to(code)): digest(p) for p in producer_files}:
        raise ValueError('Producer code changed during audit')
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        after_hashes = dict(zip(map(str, sorted(source_files)), pool.map(digest, sorted(source_files))))
    if hashes != after_hashes:
        raise ValueError('Source files changed during audit')
    report['status'] = 'changed' if report['failures'] else 'passed'
    (args.output / 'report.json').write_text(json.dumps(report, indent=2))
    if report['failures']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
