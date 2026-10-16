"""Verify versioned withdrawal eligibility without altering historical sources."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import hashlib
import json
from pathlib import Path

import polars as pl


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(8*1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def row_digest(rows):
    rows = sorted(rows, key=lambda r:r['event_id'])
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


def verify(data, revision_path, audit_path, proof_path=None, *, private_run=None):
    revision = json.loads(revision_path.read_text())
    audit = json.loads(audit_path.read_text())
    failures = []
    def require(condition, reason):
        if not condition:
            failures.append(reason)
    require(revision['status'] == 'complete', 'revision incomplete')
    require(audit['status'] == 'passed', 'availability audit failed')
    policy = audit['policy']
    require(policy == revision['policy'], 'policy mismatch')
    require(sha(audit_path) == revision['availability_audit_sha256'], 'revision availability binding')
    require(policy['maximum_age_seconds'] == 604800, 'weekly cadence changed')
    collectors = set(policy['required_collectors'])
    require(len(collectors) == 10, 'required collector population')
    require(len(revision['tables']) == 5 and
            {(t['year'],t['path']) for t in revision['tables']} ==
            {(year,f'eventset/{year}_withdrawal/events.parquet') for year in range(2022,2027)},
            'exact five withdrawal tables')
    if private_run:
        require(sha(audit_path) == revision['availability_audit_sha256'], 'availability audit bytes')
        require(sha(private_run/'crossday-source-complete.json') == revision['source_gate_sha256'], 'historical source gate')
    events = {e['event_id']:e for e in audit['events']}
    require(len(events) == len(audit['events']) == 301, 'selected audit population')
    supported_paths = set()
    expected_reasons = {}
    for event in audit['events']:
        eid = event['event_id']
        t0 = dt.datetime.fromisoformat(event['t0'])
        rows = {c['collector']:c for c in event['collectors']}
        require(len(rows) == len(event['collectors']) and set(rows) == collectors, eid+': collectors')
        missing, stale = [], []
        for collector, baseline in rows.items():
            candidates = []
            for filename in audit['rib_filename_inventory'][collector]:
                timestamp = dt.datetime.strptime(Path(filename).stem, '%Y-%m-%dT%H%M').replace(tzinfo=dt.UTC)
                if timestamp <= t0:
                    candidates.append((timestamp, filename))
            latest = max(candidates) if candidates else None
            if latest is None:
                missing.append(collector)
                require(baseline['rib_path'] is None and baseline['rib_timestamp'] is None and baseline['age_seconds'] is None and baseline['status'] == 'missing', eid+': missing '+collector)
                continue
            timestamp, filename = latest
            age = (t0-timestamp).total_seconds()
            require(Path(baseline['rib_path']).name == filename and dt.datetime.fromisoformat(baseline['rib_timestamp']) == timestamp and baseline['age_seconds'] == age, eid+': latest baseline '+collector)
            if age > 604800:
                stale.append(collector)
            require(baseline['status'] == ('stale' if age > 604800 else 'supported'), eid+': baseline status '+collector)
        eligible = not missing and not stale
        require(set(missing) == set(event['missing_baseline_collectors']) and set(stale) == set(event['stale_baseline_collectors']) and eligible == event['supported'], eid+': eligibility')
        if eligible:
            supported_paths.update(c['rib_path'] for c in event['collectors'])
        elif event['existing_error'] is None:
            expected_reasons[eid] = 'missing_required_weekly_rib' if missing else 'stale_required_weekly_rib'
    seen = set(); tables = []
    for contract in revision['tables']:
        path = data/contract['path']
        table = pl.read_parquet(path)
        rows = {r['event_id']:r for r in table.iter_rows(named=True)}
        expected = {eid:e for eid,e in events.items() if e['year'] == contract['year']}
        require(table.height == len(rows) == contract['selected'] and set(rows) == set(expected), contract['path']+': selection')
        require(table.columns == contract['columns'], contract['path']+': columns')
        require(row_digest(list(rows.values())) == contract['after_content_sha256'], contract['path']+': final content')
        require(sha(path) == contract['after_sha256'], contract['path']+': final bytes')
        changes = {c['event_id']:c for c in contract['changes']}
        require(len(changes) == len(contract['changes']) and set(changes) == set(rows)&set(expected_reasons), contract['path']+': exclusion set')
        measured = [c for c in table.columns if c.startswith(('set_','asns_','vp_')) or c in ('t90_s','sessions_carrying','sessions_switched','persistence_extent_asns')]
        require(measured == contract['nulled_columns'], contract['path']+': censored fields')
        restored = dict(rows)
        for eid, change in changes.items():
            before = change['before']; after = dict(before)
            after.update({c:None for c in measured}); after['error'] = expected_reasons[eid]
            require(change['reason'] == expected_reasons[eid] and before['error'] is None and after == change['after'] == rows[eid], eid+': exact permitted change')
            restored[eid] = before
        require(row_digest(list(restored.values())) == contract['before_content_sha256'], contract['path']+': original reconstruction')
        require(sum(r['error'] is None for r in rows.values()) == contract['usable_after'], contract['path']+': usable count')
        for eid, row in rows.items():
            if row['error'] is None:
                require(expected[eid]['supported'], eid+': retained unsupported row')
        if private_run:
            original = private_run/'data'/contract['path']
            require(sha(original) == contract['before_sha256'], contract['path']+': original bytes')
            require(row_digest(pl.read_parquet(original).to_dicts()) == contract['before_content_sha256'], contract['path']+': original decoded content')
            require(sha(path) == contract['after_sha256'], contract['path']+': revised bytes')
            if not changes:
                require(sha(original) == sha(path) and contract['unchanged_bytes'], contract['path']+': gratuitous unchanged-year rewrite')
        seen.update(rows)
        tables.append({'path':contract['path'],'sha256':sha(path),'content_sha256':row_digest(list(rows.values()))})
    require(set(events) == seen, 'all selected events retained')
    for relative, expected_sha in revision['selected_artifact_sha256'].items():
        require((data/relative).is_file() and sha(data/relative) == expected_sha, relative+': selected artifact bytes')
    baseline_hashes = {}
    if private_run:
        rib_root = private_run/'data/ribs'
        for collector in collectors:
            names = sorted(p.name for p in (rib_root/collector).glob('*.parquet'))
            require(names == sorted(audit['rib_filename_inventory'][collector]), collector+': baseline inventory changed')
        def hash_baseline(relative):
            path = Path(relative)
            if not path.is_absolute():
                path = private_run/'data'/path
            return relative, sha(path)
        with ThreadPoolExecutor(max_workers=16) as pool:
            baseline_hashes = dict(pool.map(hash_baseline, sorted(supported_paths)))
    else:
        require(proof_path is not None, 'private baseline source proof required')
        if proof_path is not None:
            proof = json.loads(proof_path.read_text())
            require(proof['status'] == 'passed' and proof['failures'] == [], 'private baseline proof failed')
            require(proof.get('mode') == 'private_source_audit', 'private proof mode')
            require(proof['revision_sha256'] == sha(revision_path) and proof['audit_sha256'] == sha(audit_path), 'private proof binding')
            require(proof['source_gate_sha256'] == revision['source_gate_sha256'], 'private proof historical source gate')
            require(proof['source_sha256'] == {t['path']:t['sha256'] for t in tables}, 'private proof released table bytes')
            baseline_hashes = proof['supported_baseline_sha256']
            require(set(baseline_hashes) == supported_paths, 'private proof baseline population')
    result = {'status':'passed' if not failures else 'failed','mode':'private_source_audit' if private_run else 'public_reconstruction',
              'failures':failures,'events':len(seen),
              'new_exclusions':len(expected_reasons),'revision_sha256':sha(revision_path),'audit_sha256':sha(audit_path),
              'source_gate_sha256':revision['source_gate_sha256'],'supported_baseline_sha256':baseline_hashes,
              'tables':tables,'verifier_sha256':sha(Path(__file__)),
              'source_sha256':{t['path']:t['sha256'] for t in tables},
              'evidence_sha256':{'analysis/withdrawal-baseline-revision.json':sha(revision_path),
                                 'analysis/withdrawal-baseline-availability-audit.json':sha(audit_path)}}
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run',type=Path)
    args = parser.parse_args()
    result = verify(args.run/'withdrawal-baseline-v2/data',args.run/'withdrawal-baseline-revision.json',
                    args.run/'withdrawal-baseline-availability-audit.json',private_run=args.run)
    output = args.run/'withdrawal-baseline-verification.json';temporary=output.with_suffix('.tmp')
    temporary.write_text(json.dumps(result,indent=1));temporary.replace(output)
    print(json.dumps({k:v for k,v in result.items() if k not in ('tables','supported_baseline_sha256')}),flush=True)
    raise SystemExit(0 if result['status']=='passed' else 1)
