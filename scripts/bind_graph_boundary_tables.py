"""Add explicit whole-table identities already covered by a passed input audit."""
import argparse
import hashlib
import json
from pathlib import Path

import polars as pl


def bind(report):
    value = json.loads(report.read_text())
    if value['status'] != 'passed':
        raise ValueError('Only a passed immutable-source audit can be bound')
    frozen, candidate = Path(value['frozen_root']), Path(value['candidate_root'])
    tables = {}
    for row in value['cohorts']:
        year, tag, _ = row['cohort']
        base = tag.split('@')[0]
        family = 'leak' if base.startswith('leak') else '' if base.startswith('rpki') else base
        relative = str(Path('eventset') / (str(year) + ('_' + family if family else '')) / 'events.parquet')
        record = {}
        for label, root in [('before', frozen), ('after', candidate)]:
            path = (root / relative).resolve()
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if value['source_sha256'].get(str(path)) != actual or row['source_' + label + '_sha256'] != actual:
                raise ValueError(f'Table not bound by passed audit: {path}')
            record[label] = {'path': str(path), 'sha256': actual}
        if relative in tables and tables[relative] != record:
            raise ValueError('Inconsistent duplicate table binding')
        tables[relative] = record
    indexes = {}
    for row in value['cohorts']:
        year, tag, delta = row['cohort']
        path = (frozen / 'tgn' / f'{year}_{tag}' / f'd{delta}s' / 'index.csv').resolve()
        index = pl.read_csv(path)
        ids = set(index['event_id'])
        if len(ids) != index.height or ids != set(row['tensors']):
            raise ValueError(f'Incomplete tensor evidence for index: {path}')
        if tag.startswith('leak') or tag == 'withdrawal':
            if ids != set(row.get('collector_membership', {})):
                raise ValueError(f'Incomplete collector evidence for index: {path}')
        indexes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    value['index_sha256'] = indexes
    value['event_table_bindings'] = tables
    pending = report.with_suffix('.pending.json')
    pending.write_text(json.dumps(value, indent=2)); pending.replace(report)
    return tables


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    print(json.dumps({'bound_event_tables': len(bind(args.report))}))
