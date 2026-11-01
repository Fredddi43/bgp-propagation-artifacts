"""Input-only shared-history intervention; primary library and fitted models stay unchanged.

This module is not wired into any production forecast or protected-period path.
The caller must bind the reviewed source-evidence list and final canonical inputs.
"""
from collections import Counter
import hashlib
import json

import numpy as np

from .forecast_history import HistorySnapshot


def withhold_snapshot(snapshot, event_ids, *, policy_sha256):
    """Remove matured donor contributions, preserving issue/maturity/panel clocks."""
    ids = frozenset(event_ids)
    if len(policy_sha256) != 64 or any(c not in '0123456789abcdef' for c in policy_sha256):
        raise ValueError('A frozen policy SHA256 is required')
    kept = tuple(e for e in snapshot.events if e.event_id not in ids)
    # Recompute independently: subtraction can conceal inconsistent primary counts.
    original = Counter(a for e in snapshot.events for a in e.target_asns)
    if dict(original) != snapshot.participation:
        raise ValueError('Primary snapshot participation does not match its donors')
    counts = dict(Counter(a for e in kept for a in e.target_asns))
    provenance = dict(snapshot.provenance)
    provenance.update(library_events=len(kept), library_event_ids_sha256=hashlib.sha256(
        '\n'.join(e.event_id for e in kept).encode()).hexdigest(),
        history_intervention={'kind': 'withhold_unavailable_source_donors',
                              'policy_sha256': policy_sha256,
                              'withheld_ids_sha256': hashlib.sha256(
                                  '\n'.join(sorted(ids)).encode()).hexdigest(),
                              'parent_provenance_sha256': hashlib.sha256(json.dumps(
                                  snapshot.provenance, sort_keys=True).encode()).hexdigest()})
    return HistorySnapshot(kept, counts, provenance)


def _neighbors(snapshot, query_signature, delta_s, k):
    # Identical standardization and stable tie order to predict_history.
    if not snapshot.events:
        return (), np.zeros(3)
    values = np.stack([e.signature(delta_s) for e in snapshot.events])
    scale = values.std(axis=0) + 1e-9
    nearest = np.argsort(np.square((values-query_signature)/scale).sum(axis=1), kind='stable')[:k]
    return tuple(snapshot.events[i].event_id for i in nearest), scale


def input_impact(primary, withheld, query_signature, *, delta_s, k=20):
    """Count changed inference inputs only; never accept targets or forecast scores."""
    if k < 1:
        raise ValueError('k must be positive')
    for key in ('issue_time', 'availability_cutoff', 'source_digest', 'excluded_event_id'):
        if primary.provenance.get(key) != withheld.provenance.get(key):
            raise ValueError('Intervention changed the source or forecast clock')
    before, scale_before = _neighbors(primary, query_signature, delta_s, k)
    after, scale_after = _neighbors(withheld, query_signature, delta_s, k)
    changed = {a for a in primary.participation.keys() | withheld.participation.keys()
               if primary.participation.get(a, 0) != withheld.participation.get(a, 0)}
    return {'matured_donors_removed': len(primary.events)-len(withheld.events),
            'participation_entries_changed': len(changed),
            'native_history_asns_removed': len(primary.participation.keys()-withheld.participation.keys()),
            'knn_neighbor_ids_changed': before != after,
            'knn_neighbors_removed': len(set(before)-set(after)),
            'knn_scale_changed': not np.array_equal(scale_before, scale_after),
            'scope': 'input_only_no_forecast_scoring', 'k': k}
