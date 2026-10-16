"""Scope PCH comparisons to non-crossday windows and a common public onset.

Uses retained membership only; never changes original replay inputs. Missing PCH
archives remain an explicit coverage limitation, rather than inferred absence at
all seventeen sites. Outputs replace only the correction-root PCH event tables.
"""
from __future__ import annotations
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import json
import hashlib
import time
from pathlib import Path
import shutil
import subprocess
import sys
import polars as pl
from bgbench import config
from bgbench.eventset import DELTAS_S, run
from bgbench.extent import TARGETS_S


def horizon_sets(first: pl.DataFrame, t0: dt.datetime):
    return {key: sorted(first.filter(pl.col("first") <= pl.lit(t0+dt.timedelta(seconds=seconds)))["asn"].to_list()) if first.height else []
            for key, seconds in {**DELTAS_S, **TARGETS_S}.items()}


def vp_counts(vp: pl.DataFrame | None, t0: dt.datetime):
    counts = {"vp_" + key: vp.filter(pl.col("first") <= pl.lit(t0 + dt.timedelta(seconds=seconds))).height if vp is not None else 0
              for key, seconds in {**DELTAS_S, **TARGETS_S}.items()}
    counts["collectors_seeing"] = (vp.filter(pl.col("first") <= pl.lit(t0 + dt.timedelta(hours=2)))["collector"].n_unique() if vp is not None else 0)
    return counts


def table_hash(file: Path):
    table = pl.read_parquet(file)
    return hashlib.sha256(table.sort("event_id").select(sorted(table.columns)).write_json().encode()).hexdigest()


def rebuild(original: Path, workers=8, final_source=False):
    root = config.DATA_ROOT.parent
    gate = root / 'crossday-source-complete.json'
    if final_source:
        while not gate.exists():
            time.sleep(30)
    public_files = [config.DATA_ROOT/'eventset'/name/'events.parquet' for name in ('2024', '2024_leak')]
    source_hashes = {str(file.relative_to(config.DATA_ROOT)): table_hash(file) for file in public_files}
    code_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    reports = []
    for tag, public_tag in [('leakpch', 'leak'), ('pchorigin', '')]:
        folder = config.DATA_ROOT / 'eventset' / ('2024_' + tag)
        table_file = folder / 'events.parquet'
        backup = folder / 'events.before-pch-correction.parquet'
        if not backup.exists():
            shutil.copy2(table_file, backup)
        old = pl.read_parquet(backup)
        public_folder = config.DATA_ROOT / 'eventset' / ('2024_' + public_tag if public_tag else '2024')
        public = {r['event_id']: r for r in pl.read_parquet(public_folder / 'events.parquet').iter_rows(named=True)}
        coverage = {}
        markers = list((original / ('events_replay_parts_' + tag) / '_done').glob('*/*.json'))
        def marker(file):
            row = json.loads(file.read_text())
            counts = [int(n) for n in row.get('files', '0/1440').split('/')]
            return file.stem, {'collector': file.parent.name, 'fetched': counts[0], 'expected': counts[1]}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for day, row in pool.map(marker, markers):
                coverage.setdefault(day, []).append(row)
        exclusions = []
        def one(row):
            eid = row['event_id']
            original_onset = row.get('t0_obs')
            identifier = dt.datetime.strptime(eid.split('_')[0], '%Y%m%dT%H%M%S').replace(tzinfo=dt.UTC)
            crossday = (identifier - dt.timedelta(hours=1)).date() != (identifier + dt.timedelta(hours=3)).date()
            pub = public.get(eid)
            reason = ('legacy_crossday_pch_window' if crossday else
                      'missing_usable_public_clock' if pub is None or pub.get('error') or not pub.get('t0_obs') else row.get('error'))
            t0 = dt.datetime.fromisoformat(pub['t0_obs']) if not reason else None
            if t0 and not t0.tzinfo:
                t0 = t0.replace(tzinfo=dt.UTC)
            if t0 and t0+dt.timedelta(hours=2) > identifier+dt.timedelta(hours=3):
                reason = 'insufficient_planned_followup'
            row['measurement_definition'] = 'same_day_pch_observed_paths_common_public_clock_v1'
            row['measurement_scope'] = 'available_retained_PCH_feeds; archive_gaps_do_not_prove_route_absence'
            cov = coverage.get(identifier.date().isoformat(), [])
            row['measurement_pch_collectors_with_archives'] = sum(c['fetched'] > 0 for c in cov)
            row['measurement_pch_collectors_full_day'] = sum(c['fetched'] == c['expected'] and c['expected'] > 0 for c in cov)
            row['measurement_pch_expected_collectors'] = 17
            row['measurement_pch_archives_fetched'] = sum(c['fetched'] for c in cov)
            row['measurement_pch_archives_expected'] = sum(c['expected'] for c in cov)
            if reason:
                row['error'] = reason
                for column in row:
                    if column.startswith(('asns_', 'vp_', 'set_')) or column in ('t0_obs', 't90_s', 'trigger_lag_s', 'observation_lag_s', 'collectors_seeing'):
                        row[column] = None
                return row
            path = original / ('events_replay_' + tag) / eid
            file = path / 'membership.parquet'
            if not file.exists() and row.get('asns_final_2h', 0):
                raise ValueError(f'missing membership for nonempty PCH event: {eid}')
            first = (pl.read_parquet(file).group_by('asn').agg(first=pl.col('first_seen').min()) if file.exists()
                     else pl.DataFrame(schema={'asn': pl.UInt32, 'first': pl.Datetime('us', 'UTC')}))
            for key, members in horizon_sets(first, t0).items():
                row['set_'+key], row['asns_'+key] = members, len(members)
            vfile = path / 'anomalous.parquet'
            vp = (pl.read_parquet(vfile, columns=['collector','peer_ip','ts']).group_by('collector','peer_ip').agg(first=pl.col('ts').min()) if vfile.exists() else None)
            if vp is None and first.height:
                raise ValueError(f'nonempty membership without VP timestamps: {eid}')
            row.update(vp_counts(vp, t0))
            final = first.filter(pl.col('first') <= pl.lit(t0+dt.timedelta(hours=2))).sort('first') if first.height else first
            if final.height:
                import math
                row['t90_s'] = max(0., (final['first'][math.ceil(.9*final.height)-1]-t0).total_seconds())
            else:
                row['t90_s'] = None
            row['t0_obs'] = t0.isoformat()
            row['trigger_lag_s'] = (identifier-t0).total_seconds()
            row['measurement_original_pch_t0_obs'] = original_onset
            row['observation_lag_s'] = (t0-identifier).total_seconds()
            return row
        with ThreadPoolExecutor(max_workers=workers) as pool:
            rows = list(pool.map(one, old.iter_rows(named=True)))
        corrected = pl.DataFrame(rows, strict=False, infer_schema_length=None)
        run(2024, tag, table_override=corrected)
        subprocess.run([sys.executable, str(Path(__file__).with_name('pch_vs_public.py')), '2024', public_tag, tag], check=True)
        report = {'tag': tag, 'selected_events': corrected.height, 'usable_same_day_events': corrected.filter(pl.col('error').is_null()).height,
                  'exclusions': dict(Counter(r['error'] for r in rows if r.get('error'))),
                  'excluded_events': [{'event_id':r['event_id'],'reason':r['error']} for r in rows if r.get('error')],
                  'collector_day_archive_coverage': coverage, 'beacon_RIB_analyses_affected': False}
        (folder/'pch_correction_scope.json').write_text(json.dumps(report, indent=1))
        reports.append({k:v for k,v in report.items() if k not in ('excluded_events','collector_day_archive_coverage')})
    (config.DATA_ROOT.parent/'pch-correction-complete.json').write_text(json.dumps(reports, indent=1))
    if source_hashes != {str(file.relative_to(config.DATA_ROOT)): table_hash(file) for file in public_files}:
        raise RuntimeError('Public PCH comparison inputs changed during reconstruction')
    if code_hash != hashlib.sha256(Path(__file__).read_bytes()).hexdigest():
        raise RuntimeError('PCH reconstruction code changed during execution')
    if final_source:
        proof = {'passed': True, 'source_gate': gate.name, 'source_gate_sha256': hashlib.sha256(gate.read_bytes()).hexdigest(),
                 'public_table_content_sha256': source_hashes, 'rebuild_code_sha256': code_hash,
                 'finished_utc': dt.datetime.now(dt.UTC).isoformat(), 'reports': reports,
                 'pch_table_content_sha256': {tag: table_hash(config.DATA_ROOT/'eventset'/('2024_'+tag)/'events.parquet') for tag in ('leakpch', 'pchorigin')}}
        destination = root/'pch-final-source-verification.json'
        temporary = destination.with_suffix('.tmp')
        temporary.write_text(json.dumps(proof, indent=1)); temporary.replace(destination)
    print(json.dumps(reports), flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--final-source', action='store_true', help='Wait for the full source gate, then emit final source proof')
    args=parser.parse_args()
    rebuild(args.original,args.workers,args.final_source)
