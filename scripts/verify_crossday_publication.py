"""Bind audited crossday deltas to the fifteen published event tables."""
from __future__ import annotations
import argparse
from collections import defaultdict
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import time
import polars as pl


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_row(before, published, change, followup_excluded=False):
    errors = []
    expected_error = 'insufficient_planned_followup' if followup_excluded else change['new_error']
    if published.get('error') != expected_error:
        errors.append('error')
    old_clock, new_clock = published.get('t0_obs'), change['new_t0_obs']
    if (dt.datetime.fromisoformat(old_clock) if old_clock else None) != (dt.datetime.fromisoformat(new_clock) if new_clock else None):
        errors.append('t0_obs')
    expected_t90 = None if followup_excluded else change['new_t90_s']
    got_t90 = published.get('t90_s')
    if (got_t90 is None) != (expected_t90 is None) or (got_t90 is not None and not math.isclose(got_t90, expected_t90, abs_tol=1e-9, rel_tol=0)):
        errors.append('t90_s')
    for key, delta in change['sets'].items():
        prior = set(before.get(key) or [])
        added, removed = set(delta['added']), set(delta['removed'])
        expected = (prior | added) - removed
        if len(prior) != delta['old_n'] or not removed <= prior or added & prior or len(expected) != delta['new_n']:
            errors.append(key + ':invalid_delta')
        if expected_error:
            if published.get(key) is not None:
                errors.append(key + ':excluded_not_null')
        elif set(published.get(key) or []) != expected or len(published.get(key) or []) != len(expected):
            errors.append(key)
    return errors


def verify(run: Path, wait=False):
    gate_file = run/'crossday-source-complete.json'
    audit_file = run/'full-replay-invariants.json'
    if wait:
        while not gate_file.exists() or not audit_file.exists():
            time.sleep(15)
    gate = json.loads(gate_file.read_text())
    audit = json.loads(audit_file.read_text())
    repair = Path(gate.get('repair_root','crossday-repair'))
    if not repair.is_absolute():repair=run/repair
    changes_file = repair/'input-changes.json'
    changes_hash = sha(changes_file)
    failures = []
    if audit.get('failures') != []:
        failures.append({'scope':'raw_audit','reason':'failed_or_missing_failure_list'})
    if changes_hash not in audit.get('inputs_sha256', {}).values():
        failures.append({'scope':'raw_audit','reason':'comparison_hash_not_bound'})
    if gate.get('changes_sha256') != changes_hash:
        failures.append({'scope':'source_gate','reason':'comparison_hash_mismatch'})
    grouped = defaultdict(list)
    for change in json.loads(changes_file.read_text()):
        grouped[(change['year'],change['tag'])].append(change)
    followup = set()
    followup_file = run/'followup-exclusions-all.json'
    for row in json.loads(followup_file.read_text()):
        followup.update((row['year'],row['tag'],event_id) for event_id in row['excluded_events'])
    hashes = {}; totals = []; seen = set()
    for year in range(2022,2027):
        for tag in ('','leak','withdrawal'):
            name = str(year)+('_'+tag if tag else '')
            relative = f'eventset/{name}/events.parquet'
            path = run/'data'/relative
            hashes[relative] = sha(path)
            if gate['event_tables_sha256'].get(relative) != hashes[relative]:
                failures.append({'scope':name,'reason':'source_table_hash_mismatch'})
            published = pl.read_parquet(path)
            before = pl.read_parquet(path.with_name('events.before-crossday-repair.parquet'))
            ids = [c['event_id'] for c in grouped[(year,tag)]]
            new_rows = {r['event_id']:r for r in published.filter(pl.col('event_id').is_in(ids)).iter_rows(named=True)}
            old_rows = {r['event_id']:r for r in before.filter(pl.col('event_id').is_in(ids)).iter_rows(named=True)}
            if published['event_id'].n_unique() != published.height or set(published['event_id']) != set(before['event_id']):
                failures.append({'scope':name,'reason':'selected_population_changed'})
            for c in grouped[(year,tag)]:
                key=(year,tag,c['event_id'])
                if key in seen:failures.append({'event_id':c['event_id'],'reason':'duplicate_comparison'})
                seen.add(key)
                if c['event_id'] not in new_rows or c['event_id'] not in old_rows:
                    failures.append({'event_id':c['event_id'],'reason':'missing_event'});continue
                errors=check_row(old_rows[c['event_id']],new_rows[c['event_id']],c,key in followup)
                if errors:failures.append({'event_id':c['event_id'],'tag':tag,'errors':errors})
            totals.append({'table':name,'repaired_rows':len(ids),'selected_rows':published.height})
    if len(seen) != gate['events']:
        failures.append({'scope':'population','reason':'comparison_count_mismatch','rows':len(seen),'expected':gate['events']})
    if hashes != {p:sha(run/'data'/p) for p in hashes}:
        failures.append({'scope':'immutability','reason':'table_changed_during_check'})
    result={'status':'passed' if not failures else 'failed','passed':not failures,'repaired_rows':len(seen),
            'tables':totals,'published_event_tables_sha256':hashes,'changes_sha256':changes_hash,
            'audit_sha256':sha(audit_file),'source_gate_sha256':sha(gate_file),'followup_exclusions_sha256':sha(followup_file),
            'explicit_additional_followup_exclusions':len(seen & followup),'failures':failures}
    destination=run/'full-publication-verification.json'; temporary=destination.with_suffix('.tmp')
    temporary.write_text(json.dumps(result,indent=1)); temporary.replace(destination)
    print(json.dumps(result),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run',type=Path);parser.add_argument('--wait',action='store_true')
    args=parser.parse_args(); result=verify(args.run,args.wait)
    raise SystemExit(0 if result['passed'] else 1)
