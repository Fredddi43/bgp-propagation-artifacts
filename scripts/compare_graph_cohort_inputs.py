"""Exact tensor equivalence before reusing an existing fitted checkpoint."""
import argparse
import json
from pathlib import Path

import polars as pl
import torch

from audit_graph_boundary_inputs import digest, tensor_differences


def compare(before, after):
    a = pl.read_csv(before / 'index.csv')
    b = pl.read_csv(after / 'index.csv')
    report = {'before': str(before.resolve()), 'after': str(after.resolve()),
              'index_before_sha256': digest(before / 'index.csv'), 'index_after_sha256': digest(after / 'index.csv'),
              'training_equal': True, 'test_equal': True, 'events': {}}
    old_splits = dict(zip(a['event_id'], a['split']))
    new_splits = dict(zip(b['event_id'], b['split']))
    for eid in sorted(set(old_splits) | set(new_splits)):
        old, new = before / f'{eid}.pt', after / f'{eid}.pt'
        if old_splits.get(eid) != new_splits.get(eid) or not old.exists() or not new.exists():
            fields = ['event_or_split']
        else:
            fields = tensor_differences(torch.load(old, weights_only=False, map_location='cpu', mmap=True),
                                       torch.load(new, weights_only=False, map_location='cpu', mmap=True))
        if fields:
            for split in {old_splits.get(eid), new_splits.get(eid)}:
                if split == 'train': report['training_equal'] = False
                if split == 'test': report['test_equal'] = False
        report['events'][eid] = {'split_before': old_splits.get(eid), 'split_after': new_splits.get(eid),
            'fields': fields, 'before_sha256': digest(old) if old.exists() else None,
            'after_sha256': digest(new) if new.exists() else None}
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('before', type=Path)
    parser.add_argument('after', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = compare(args.before, args.after)
    args.output.write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != 'events'}))
