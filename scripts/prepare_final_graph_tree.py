"""Freeze published event tables and replay directory targets for final graph builds.

Families/years may be added as their independent repair publications complete.
An existing table is never silently replaced beneath running graph jobs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

import polars as pl

parser = argparse.ArgumentParser()
parser.add_argument('source', type=Path)
parser.add_argument('destination', type=Path)
parser.add_argument('publication_marker', type=Path)
parser.add_argument('tables', nargs='+')
args = parser.parse_args()
if not args.publication_marker.is_file():
    raise SystemExit('Replay/event-table publication marker is required')
marker_hash = hashlib.sha256(args.publication_marker.read_bytes()).hexdigest()
args.destination.mkdir(parents=True, exist_ok=True)
for name in ('graphs', 'rpki'):
    link = args.destination / name
    if not link.exists():
        link.symlink_to((args.source / name).resolve(), target_is_directory=True)
for name in ('tgn', 'eventset', '_publications'):
    (args.destination / name).mkdir(exist_ok=True)
for table in args.tables:
    year, _, family = table.partition('_')
    if family not in ('', 'leak', 'withdrawal'):
        raise ValueError(f'Unexpected graph event family {table}')
    source = args.source / 'eventset' / table
    destination = args.destination / 'eventset' / table
    record = {'table': table, 'publication_marker': str(args.publication_marker),
              'publication_sha256': marker_hash, 'table_files': {}, 'replay_targets': {}}
    for name in ('events.parquet', 'rpki_validity.parquet'):
        file = source / name
        if not file.exists():
            continue
        digest = hashlib.sha256(file.read_bytes()).hexdigest()
        target = destination / name
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise RuntimeError(f'Refusing to replace frozen table {target}')
        destination.mkdir(exist_ok=True)
        if not target.exists():
            shutil.copy2(file, target)
        record['table_files'][name] = digest
    replay_name = 'events_replay' + ('_' + family if family else '')
    replay = args.destination / replay_name
    replay.mkdir(exist_ok=True)
    ids = pl.read_parquet(destination / 'events.parquet', columns=['event_id', 'error']).filter(pl.col('error').is_null())['event_id']
    for event_id in ids:
        original = (args.source / replay_name / event_id).resolve()
        if not original.is_dir():
            raise RuntimeError(f'Missing successful event replay {original}')
        target = replay / event_id
        if target.is_symlink() and target.resolve() != original:
            raise RuntimeError(f'Refusing to replace frozen replay {target}')
        if not target.exists():
            target.symlink_to(original, target_is_directory=True)
        record['replay_targets'][event_id] = str(original)
    (args.destination / '_publications' / (table + '.json')).write_text(json.dumps(record, indent=2))
    print(json.dumps({'frozen': table, 'events': len(record['replay_targets'])}), flush=True)
