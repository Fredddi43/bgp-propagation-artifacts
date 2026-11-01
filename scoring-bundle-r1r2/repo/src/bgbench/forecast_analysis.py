"""Forecast mechanism and uncertainty analyses with explicit units of resampling.

These functions consume committed predictions and evaluator-owned labels. They
are not called during model fitting or protected-input generation.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

import numpy as np


def recurrence_metadata(history_rows, queries, *, frozen_at=None, availability_delay_s=0):
    """Actor familiarity from only completed history, with cross-year carry-over.

    Rows must be the same successful source-family library used by all models.
    The caller supplies actual label availability when recorded; otherwise the
    two-hour endpoint plus availability_delay_s is the declared replay
    availability approximation. Recorded availability takes precedence, matching
    CompletedEventLibrary. frozen_at caps availability without changing issue
    time or actor recency.
    """
    from .forecast_protocol import utc
    if not np.isfinite(availability_delay_s) or availability_delay_s < 0:
        raise ValueError("History availability delay must be finite and nonnegative")
    frozen = utc(frozen_at) if frozen_at is not None else None
    history = []
    for row in history_rows:
        if row.get("error") is not None:
            continue
        onset = utc(row.get("onset") or row["t0_obs"])
        available = utc(row["label_available_at"]) if row.get("label_available_at") else onset + timedelta(hours=2, seconds=availability_delay_s)
        if available < onset + timedelta(hours=2):
            raise ValueError("Historical label availability precedes its target")
        actor = row.get("actor", row.get("a", row.get("new_origin")))
        if actor is None:
            raise ValueError("Actor metadata required for recurrence analysis")
        history.append((available, str(row["event_id"]), str(actor), onset))
    history.sort()
    if len({r[1] for r in history}) != len(history):
        raise ValueError("Duplicate history event")
    index, completed, actors, result = 0, {}, defaultdict(dict), []
    for query in sorted(queries, key=lambda r: (utc(r["issue_time"]), r["event_id"])):
        issue = utc(query["issue_time"])
        cutoff = min(issue, frozen) if frozen is not None else issue
        while index < len(history) and history[index][0] <= cutoff:
            available, eid, actor, onset = history[index]
            completed[eid] = (actor, onset)
            actors[actor][eid] = onset
            index += 1
        actor_events = {eid: onset for eid, onset in actors[str(query["actor"])].items()
                        if eid != query["event_id"]}
        count = len(actor_events)
        result.append({"event_id": query["event_id"], "availability_cutoff": cutoff.isoformat(),
                       "availability_delay_s": availability_delay_s, "completed_history_events": len(completed) - int(query["event_id"] in completed),
                       "actor_history_events": count,
                       "actor_recency_seconds": (issue - max(actor_events.values())).total_seconds() if count else None,
                       "actor_support_bin": "0" if count == 0 else "1-5" if count <= 5 else "6-20" if count <= 20 else "21+"})
    return result


def incident_day_blocks(rows):
    """Keep each incident together, assigning it to its first onset's UTC day."""
    from .forecast_protocol import utc
    first = {}
    for row in rows:
        incident, onset = row["incident_id"], utc(row["onset"])
        first[incident] = min(first.get(incident, onset), onset)
    return [first[row["incident_id"]].date().isoformat() for row in rows]


def paired_interval(left, right, blocks, *, repetitions=5000, seed=1701):
    """Event-macro difference, resampling paired training seeds and whole blocks.

    Arrays are training-seed x event. A deterministic baseline can have one row;
    it is broadcast to all learned fits. Missing scores fail rather than silently
    change the compared cohort. This is an ordinary percentile interval, not a
    simultaneous interval or an equivalence test.
    """
    a, b = np.atleast_2d(left).astype(float), np.atleast_2d(right).astype(float)
    if a.shape[1] != len(blocks) or b.shape[1] != len(blocks) or not len(blocks):
        raise ValueError("Both arms must cover the identical nonempty event cohort")
    if a.shape[0] != b.shape[0] and min(a.shape[0], b.shape[0]) != 1:
        raise ValueError("Training seeds must be paired, or one arm deterministic")
    if not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError("Undefined scores require an explicitly declared analysis population")
    if repetitions < 100:
        raise ValueError("Too few bootstrap repetitions")
    difference = a - b
    groups = defaultdict(list)
    for index, block in enumerate(blocks):
        groups[str(block)].append(index)
    if len(groups) < 2:
        raise ValueError("At least two independent resampling blocks required")
    indices = [np.asarray(v) for _, v in sorted(groups.items())]
    sizes = np.array([len(i) for i in indices])
    sums = np.stack([difference[:, i].sum(axis=1) for i in indices], axis=1)
    rng = np.random.default_rng(seed)
    samples = np.empty(repetitions)
    for repetition in range(repetitions):
        seeds = rng.integers(difference.shape[0], size=difference.shape[0])
        selected_blocks = rng.integers(len(indices), size=len(indices))
        samples[repetition] = sums[np.ix_(seeds, selected_blocks)].sum() / (len(seeds) * sizes[selected_blocks].sum())
    return {"difference": float(difference.mean()), "ci95": np.quantile(samples, [.025, .975]).tolist(),
            "per_seed_difference": difference.mean(axis=1).tolist(), "events": len(blocks),
            "blocks": len(groups), "training_seeds": difference.shape[0],
            "repetitions": repetitions, "rng_seed": seed,
            "estimand": "event_macro_mean_then_training_seed_mean",
            "interval": "paired_training_seed_and_block_percentile_ordinary_95"}


def membership_decomposition(target, seeds, candidates, predicted, uncapped_candidates):
    """Disjoint new-member misses: uncapped exclusion, cap loss, ranking miss."""
    truth, seen, candidate, prediction, uncapped = map(set, (target, seeds, candidates, predicted, uncapped_candidates))
    if not candidate <= uncapped:
        raise ValueError("Capped candidates must be contained in the uncapped universe")
    if not prediction <= (candidate | seen):
        raise ValueError("This decomposition is for the declared candidate-constrained predictor")
    future = truth - seen
    result = {"new_true": len(future), "outside_uncapped": len(future - uncapped),
              "removed_by_cap": len((future & uncapped) - candidate),
              "candidate_ranking_miss": len((future & candidate) - prediction),
              "new_true_positive": len(future & prediction),
              "new_false_positive": len((prediction - seen) - truth)}
    assert sum(result[k] for k in ("outside_uncapped", "removed_by_cap", "candidate_ranking_miss", "new_true_positive")) == len(future)
    return result


def expanded_membership_decomposition(target, seeds, original_candidates, expanded_candidates,
                                      predicted, original_uncapped_candidates):
    """Keep the original topology boundary fixed while separating recovered misses."""
    truth, seen, original, expanded, prediction, uncapped = map(
        set, (target, seeds, original_candidates, expanded_candidates, predicted, original_uncapped_candidates))
    if not seen <= original or not original <= uncapped or not original <= expanded:
        raise ValueError('Expansion must preserve seeds, original candidates and original topology boundary')
    if not prediction <= expanded:
        raise ValueError('Expanded predictor selected an undeclared candidate')
    future, added = truth - seen, expanded - original
    result = {'new_true': len(future), 'original_target_candidates': len(future & original),
              'recovered_from_cap': len(future & added & uncapped),
              'recovered_outside_two_hop': len((future & added) - uncapped),
              'still_omitted_by_cap': len((future & uncapped) - expanded),
              'still_outside_two_hop': len(future - (expanded | uncapped)),
              'expanded_ranking_miss': len((future & expanded) - prediction),
              'new_true_positive': len(future & prediction),
              'new_false_positive': len((prediction - seen) - truth)}
    assert sum(result[k] for k in ('original_target_candidates', 'recovered_from_cap',
        'recovered_outside_two_hop', 'still_omitted_by_cap', 'still_outside_two_hop')) == len(future)
    assert sum(result[k] for k in ('expanded_ranking_miss', 'new_true_positive',
        'still_omitted_by_cap', 'still_outside_two_hop')) == len(future)
    return result


def monitoring_utility(ranked_asns, target, input_seen, first_seen_seconds, *,
                       observation_cutoff_seconds, budget, pipeline_seconds=0):
    """Budgeted input-new monitoring; lead time refers to reference first sighting.

    Pipeline time is the measured delay from the observation cutoff to usable
    forecast output. It is subtracted exactly once when deciding actionability.
    A zero default means an offline upper bound, not an operational latency claim.
    """
    if budget < 1 or pipeline_seconds < 0:
        raise ValueError("Budget must be positive and pipeline delay nonnegative")
    observed, truth, selected = set(input_seen), set(target), []
    visited = set()
    for asn in ranked_asns:
        if asn not in observed and asn not in visited:
            selected.append(asn)
            visited.add(asn)
        if len(selected) == budget:
            break
    future = truth - observed
    true_selected = set(selected) & future
    missing = true_selected - set(first_seen_seconds)
    if missing:
        raise ValueError("True selections lack reference first-observation times")
    leads = [float(first_seen_seconds[a]) - observation_cutoff_seconds for a in sorted(true_selected)]
    # Inputs outside the reference panel can already have seen reference-new
    # members. Removing all input_seen above prevents calling those discoveries.
    return {"budget": budget, "selected": len(selected), "true_selected": len(true_selected),
            "false_selected": len(set(selected) - truth), "new_true": len(future),
            "precision": len(true_selected) / len(selected) if selected else None,
            "recall": len(true_selected) / len(future) if future else None,
            "lead_from_observation_cutoff_seconds": leads,
            "lead_from_forecast_output_seconds": [lead - pipeline_seconds for lead in leads],
            "actionable_true_selected": sum(lead > pipeline_seconds for lead in leads),
            "too_late_fraction": sum(lead <= pipeline_seconds for lead in leads) / len(leads) if leads else None,
            "pipeline_seconds": pipeline_seconds}
