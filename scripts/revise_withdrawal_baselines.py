"""Version withdrawal eligibility against the documented seven-day RIB baseline."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

import polars as pl


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def content_sha(table):
    rows = table.sort('event_id').select(sorted(table.columns)).to_dicts()
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


def classify(table, events):
    """Preserve identifiers/observations; censor unsupported path-loss labels."""
    lookup = {row['event_id']: row for row in events}
    if len(lookup) != len(events) or set(lookup) != set(table['event_id']):
        raise ValueError('baseline audit and selected event populations differ')
    reasons = {}
    for row in table.iter_rows(named=True):
        audit = lookup[row['event_id']]
        if row['error'] != audit['existing_error']:
            raise ValueError('baseline audit refers to another event-table revision')
        if audit['supported'] != (not audit['missing_baseline_collectors'] and not audit['stale_baseline_collectors']):
            raise ValueError('inconsistent baseline eligibility')
        if row['error'] is None and not audit['supported']:
            reasons[row['event_id']] = ('missing_required_weekly_rib' if audit['missing_baseline_collectors']
                                        else 'stale_required_weekly_rib')
    measured = [c for c in table.columns if c.startswith(('set_', 'asns_', 'vp_'))
                or c in ('t90_s', 'sessions_carrying', 'sessions_switched', 'persistence_extent_asns')]
    if not reasons:
        return table, reasons, measured
    bad = pl.col('event_id').is_in(list(reasons))
    revised = table.with_columns(
        [pl.when(bad).then(pl.lit(None, dtype=table.schema[c])).otherwise(pl.col(c)).alias(c) for c in measured]
        + [pl.col('event_id').replace_strict(reasons, default=pl.col('error')).alias('error')])
    return revised, reasons, measured


def revise(run):
    from bgbench import config
    from bgbench.eventset import run as summarize
    from bgbench.eventset import per_vp_and_duration

    audit_path = run / 'withdrawal-baseline-availability-audit.json'
    audit = json.loads(audit_path.read_text())
    if audit['status'] != 'passed' or audit['policy']['maximum_age_seconds'] != 604800 or len(audit['policy']['required_collectors']) != 10:
        raise ValueError('unexpected baseline policy or failed availability audit')
    source_gate = run / 'crossday-source-complete.json'
    source = json.loads(source_gate.read_text())
    root = run / 'withdrawal-baseline-v2'
    data = root / 'data'
    data.mkdir(parents=True, exist_ok=True)
    replay_link = data / 'events_replay_withdrawal'
    if not replay_link.exists():
        replay_link.symlink_to(run / 'data/events_replay_withdrawal', target_is_directory=True)
    config.DATA_ROOT = data
    tables = []
    for year in range(2022, 2027):
        relative = f'eventset/{year}_withdrawal/events.parquet'
        original = run / 'data' / relative
        before_sha = sha(original)
        if source['event_tables_sha256'][relative] != before_sha:
            raise ValueError(f'original source changed: {relative}')
        old = pl.read_parquet(original)
        events = [e for e in audit['events'] if e['year'] == year]
        revised, reasons, measured = classify(old, events)
        output = data / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        if reasons:
            summarize(year, 'withdrawal', output_dir=output.parent, table_override=revised)
            empty = pl.DataFrame(schema={'delta':pl.String,'target':pl.String,'events':pl.UInt32,
                    'jaccard_mean':pl.Float64,'jaccard_p50':pl.Float64,'recall_mean':pl.Float64,
                    'size_ratio_p50':pl.Float64,'frac_events_fully_grown_at_delta':pl.Float64})
            for split in ('train','test'):
                if revised.filter(pl.col('error').is_null() & (pl.col('split') == split)).is_empty():
                    empty.write_csv(output.parent/f'persistence_{split}.csv')
            if revised['error'].null_count() == 0:
                summary_path = output.parent/'summary.json'
                summary = json.loads(summary_path.read_text())
                summary.update({'usable_events':0,'clean_events':0,'persistence_train':[],
                                'persistence_test':[],'persistence_train_clean':[],'persistence_test_clean':[]})
                summary_path.write_text(json.dumps(summary,indent=1))
        else:
            for name in ('events.parquet', 'summary.json', 'persistence_train.csv', 'persistence_test.csv'):
                file = original.parent / name
                if file.exists():
                    shutil.copy2(file, output.parent / name)
        per_vp_and_duration(year, 'withdrawal')
        if sha(original) != before_sha:
            raise ValueError(f'original source changed during revision: {relative}')
        changes = [{'event_id':event_id, 'reason':reason,
                    'before':old.filter(pl.col('event_id') == event_id).row(0, named=True),
                    'after':revised.filter(pl.col('event_id') == event_id).row(0, named=True)}
                   for event_id, reason in sorted(reasons.items())]
        tables.append({'year':year, 'path':relative, 'before_sha256':before_sha,
                       'after_sha256':sha(output), 'selected':old.height,
                       'before_content_sha256':content_sha(old), 'after_content_sha256':content_sha(revised),
                       'columns':old.columns,
                       'usable_before':old['error'].null_count(), 'usable_after':revised['error'].null_count(),
                       'nulled_columns':measured, 'changes':changes,
                       'unchanged_bytes':not reasons and sha(output) == before_sha})
    selected = {str(p.relative_to(data)):sha(p) for p in sorted((data/'eventset').rglob('*')) if p.is_file()}
    proof = {'status':'complete', 'data_root':'withdrawal-baseline-v2/data',
             'source_gate_sha256':sha(source_gate), 'availability_audit_sha256':sha(audit_path),
             'producer_sha256':sha(Path(__file__)), 'policy':audit['policy'], 'tables':tables,
             'selected_artifact_sha256':selected}
    destination = run / 'withdrawal-baseline-revision.json'
    temporary = destination.with_suffix('.tmp')
    temporary.write_text(json.dumps(proof, indent=1, default=str)); temporary.replace(destination)
    print(json.dumps({'status':'complete', 'tables':[{k:t[k] for k in ('year','selected','usable_before','usable_after')} for t in tables]}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    revise(parser.parse_args().run)
