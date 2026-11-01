"""Membership scoring on full observed truth, with candidate-only diagnostics.

The learned head only proposes candidate ASes. Every observed seed remains in its
prediction, including seeds absent from CAIDA. True members outside the candidate
universe count as misses; candidate pruning must never silently prune the target.
"""
from __future__ import annotations

import numpy as np


def _array(value):
    return value.detach().cpu().numpy() if hasattr(value, "detach") else np.asarray(value)


def membership_metrics(event: dict, candidate_prediction) -> dict:
    if "target_asns" not in event or "seed_asns" not in event:
        raise ValueError("Full observed target/seed ASNs missing; refresh graph tensors before scoring")
    candidates = _array(event["asn"])
    truth = set(map(int, _array(event["target_asns"])))
    seeds = set(map(int, _array(event["seed_asns"])))
    universe = set(map(int, candidates))
    selected = set(map(int, candidates[_array(candidate_prediction).astype(bool)]))
    prediction = seeds | selected
    restricted_truth, restricted_seed = truth & universe, seeds & universe
    restricted_pred = selected | restricted_seed

    def jaccard(a, b):
        return len(a & b) / len(a | b) if a | b else float("nan")

    return {"jaccard": jaccard(truth, prediction), "jaccard_persist": jaccard(truth, seeds),
            "precision": len(truth & prediction) / max(len(prediction), 1),
            "recall": len(truth & prediction) / max(len(truth), 1),
            "size_ratio": len(prediction) / max(len(truth), 1),
            "true_size": len(truth), "new_true_size": len(truth - seeds),
            "candidate_target_coverage": len(restricted_truth) / max(len(truth), 1),
            "true_outside_candidates": len(truth - universe),
            "candidate_jaccard": jaccard(restricted_truth, restricted_pred),
            "candidate_jaccard_persist": jaccard(restricted_truth, restricted_seed)}


def message_stream(timestamps, paths, candidate_asns, onset):
    """Map actual AS numbers to local tensor indices, preserving route-flow direction."""
    position = {int(asn): i for i, asn in enumerate(candidate_asns)}
    rows = []
    for timestamp, path in zip(timestamps, paths):
        if not path:
            continue
        for collector_side, origin_side in zip(path, path[1:]):
            if collector_side in position and origin_side in position:
                rows.append(((timestamp - onset).total_seconds(), position[origin_side], position[collector_side]))
    return np.array(rows, dtype=np.float64).reshape(-1, 3)


def learned_from_customers(paths, relationships):
    """AS_PATH is collector-to-origin; each AS learns from its next hop."""
    learned = set()
    for path in paths:
        if not path:
            continue
        for receiver, origin_side in zip(path, path[1:]):
            if receiver is not None and origin_side is not None and relationships.get((receiver, origin_side)) == "customer":
                learned.add(int(receiver))
    return learned


def completed_event_histories(onsets, targets, horizon_seconds=7200, query_offset_seconds=0):
    """Only finalized event footprints are available when the next event starts."""
    from collections import deque
    from datetime import datetime, timedelta
    parsed = {eid: datetime.fromisoformat(t) if isinstance(t, str) else t for eid, t in onsets.items()}
    pending, counts, histories = deque(), {}, {}
    for event_id in sorted(parsed, key=lambda eid: (parsed[eid], eid)):
        onset = parsed[event_id]
        while pending and pending[0][0] <= onset + timedelta(seconds=query_offset_seconds):
            _, previous = pending.popleft()
            for asn in targets.get(previous) or []:
                counts[int(asn)] = counts.get(int(asn), 0) + 1
        histories[event_id] = dict(counts)
        pending.append((onset + timedelta(seconds=horizon_seconds), event_id))
    return histories


def legacy_window_crosses_midnight(event_id):
    """Legacy replay partitions span identifier minus 1h through plus 3h."""
    from datetime import datetime, timedelta
    trigger = datetime.strptime(event_id[:15], "%Y%m%dT%H%M%S")
    return (trigger - timedelta(hours=1)).date() != (trigger + timedelta(hours=3)).date()


def embargo_training_events(training, testing, onsets, horizon_seconds=7200):
    """A fixed prospective fit may only use labels complete at its first test onset."""
    from datetime import datetime, timedelta
    parsed = {eid: datetime.fromisoformat(t) if isinstance(t, str) else t for eid, t in onsets.items()}
    cutoff = min(parsed[d['event_id']] for d in testing)
    kept, dropped = [], []
    for event in training:
        (kept if parsed[event['event_id']] + timedelta(seconds=horizon_seconds) <= cutoff else dropped).append(event)
    return kept, {'first_test_onset': cutoff.isoformat(), 'label_horizon_seconds': horizon_seconds,
                  'dropped_training_ids': [d['event_id'] for d in dropped]}
