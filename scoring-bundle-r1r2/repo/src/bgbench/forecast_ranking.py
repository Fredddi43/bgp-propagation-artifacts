"""New-member ranking metrics: the primary forecasting metric (PRIMARY-METRIC-REVISION.md).

Every function here consumes committed predictions and evaluator-owned labels. None is
called while fitting or while generating protected inputs.

Definitions (exactly as pre-registered):

* The **new members** of an event are ``target - input_seen``: the 2-h target ASes that the
  forecast's own input had not observed by issue time. For the pooled reference input panel
  this equals reference-new; for a reduced H3 panel the caller passes that panel's input
  seeds (input-new) or the reference seeds (reference-new) explicitly.
* An arm's **ranking** is a score per candidate AS. Candidates already in ``input_seen`` are
  removed before ranking. Higher score ranks earlier. Tied scores are treated as an
  unordered group: every metric is the exact **expectation over uniformly random orderings
  within each tie group** (McSherry and Najork 2008), so no tie-breaking rule (ASN order,
  candidate order) can move a score.
* **Average precision** is candidate-complete: ``AP = (1/R) * sum over ranked new members of
  precision at their rank``, with ``R`` the number of *all* new members, including those the
  candidate generator never offered. Omitted members therefore count as never retrieved, and
  arms with different candidate sets are compared on one denominator.
* **Precision at k** is ``(new members among the first k ranked) / k``. The budget is fixed:
  an arm that ranks fewer than k candidates gets no credit for the empty slots.
* An event with ``R = 0`` has no defined AP or precision-at-k contribution; it is
  **ineligible**, counted and reported, never silently dropped.
* A **no-input abstention** (PROTOCOL-DECISIONS.md: empty predicted AS set) ranks nothing.
  On an eligible event it contributes AP 0 and precision 0 and stays in the denominator.
* A **technical-failure abstention** (NEW-PERIOD-PROTOCOL.md: source, parser or inference
  failure flagged on an event whose target is scorable) is scored the same way but keeps its
  own status and count; it is never relabelled as no-input. Events without a scorable target
  never reach this module: they belong to the coverage/censoring ledger.
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np

from .forecast_analysis import incident_day_blocks

BUDGETS = (5, 10, 20, 50)
PRIMARY_BUDGET = 10
METRIC_VERSION = "ranking-v1"
ABSTENTION_STATUSES = ("no_input", "technical_failure")


def _clean_ranking(candidate_asns, scores, input_seen):
    asns = np.asarray(list(candidate_asns), dtype=np.int64)
    values = np.asarray(list(scores), dtype=np.float64)
    if asns.shape != values.shape:
        raise ValueError("Every candidate needs exactly one score")
    if len(np.unique(asns)) != len(asns):
        raise ValueError("Duplicate candidate ASN in a ranking")
    if not np.isfinite(values).all():
        raise ValueError("Ranking scores must be finite")
    keep = ~np.isin(asns, np.fromiter((int(a) for a in input_seen), dtype=np.int64))
    return asns[keep], values[keep]


def _tie_groups(asns, values, new):
    """(size, relevant) per tie group in descending score order."""
    if not len(values):
        return np.zeros(0, int), np.zeros(0, int)
    unique, inverse = np.unique(-values, return_inverse=True)  # ascending -score = descending score
    sizes = np.bincount(inverse, minlength=len(unique))
    relevant = np.bincount(inverse, weights=np.isin(asns, new).astype(float), minlength=len(unique))
    return sizes.astype(int), relevant.astype(int)


def expected_average_precision(sizes, relevant, total_relevant):
    """Expected AP over random orderings within tie groups, candidate-complete denominator.

    For a group of n slots after c earlier slots holding h relevant items, with r relevant
    among the n: a slot at offset t is relevant with probability r/n and, given that, the
    expected number of relevant items before it inside the group is (t-1)(r-1)/(n-1).
    Summing (h + 1 + that) / (c + t) uses harmonic numbers, so the cost is linear.
    """
    if total_relevant <= 0:
        raise ValueError("AP is undefined for an event without new members")
    sizes, relevant = np.asarray(sizes, int), np.asarray(relevant, int)
    if relevant.sum() > total_relevant:
        raise ValueError("More ranked relevant items than new members")
    length = int(sizes.sum())
    harmonic = np.concatenate([[0.0], np.cumsum(1.0 / np.arange(1, length + 1))])
    starts = np.concatenate([[0], np.cumsum(sizes)[:-1]])
    before = np.concatenate([[0], np.cumsum(relevant)[:-1]])
    total = 0.0
    for n, r, c, h in zip(sizes, relevant, starts, before):
        if r == 0:
            continue
        s0 = harmonic[c + n] - harmonic[c]          # sum_t 1/(c+t)
        s1 = n - (c + 1) * s0                       # sum_t (t-1)/(c+t)
        inner = (r - 1) / (n - 1) if n > 1 else 0.0
        total += (r / n) * ((h + 1) * s0 + inner * s1)
    return float(total / total_relevant)


def expected_hits_at(sizes, relevant, k):
    """Expected new members among the first k ranked (fractional inside a straddling tie)."""
    hits, position = 0.0, 0
    for n, r in zip(sizes, relevant):
        if position >= k:
            break
        take = min(n, k - position)
        hits += r * take / n
        position += n
    return hits


def event_ranking_metrics(candidate_asns, scores, target, input_seen, *, budgets=BUDGETS,
                          status="available"):
    """Per-event AP, precision@k and recall@k of new members; see the module docstring.

    ``status`` must be ``available``, ``no_input`` or ``technical_failure``. An abstention
    (either of the last two) must carry no candidates; it ranks nothing and is scored as an
    explicit abstention under its own status.
    """
    if status not in ("available", *ABSTENTION_STATUSES):
        raise ValueError(f"Unknown status {status!r}")
    if any(int(b) < 1 for b in budgets):
        raise ValueError("Budgets must be positive")
    new = np.fromiter((int(a) for a in set(map(int, target)) - set(map(int, input_seen))), dtype=np.int64)
    total = len(new)
    if status in ABSTENTION_STATUSES:
        if len(list(candidate_asns)):
            raise ValueError(f"A {status} abstention must rank no candidates")
        asns, values = np.zeros(0, np.int64), np.zeros(0)
    else:
        asns, values = _clean_ranking(candidate_asns, scores, input_seen)
    sizes, relevant = _tie_groups(asns, values, new)
    result = {"status": status, "new_members": total, "ranked": int(len(asns)),
              "new_members_ranked": int(relevant.sum()), "eligible": total > 0,
              # Best AP (and recall) any ranking of these candidates could reach.
              "coverage_ceiling": float(relevant.sum() / total) if total else None,
              "metric_version": METRIC_VERSION}
    if not total:
        result.update(average_precision=None, precision_at={str(b): None for b in budgets},
                      recall_at={str(b): None for b in budgets})
        return result
    result["average_precision"] = expected_average_precision(sizes, relevant, total)
    hits = {int(b): expected_hits_at(sizes, relevant, int(b)) for b in budgets}
    result["precision_at"] = {str(b): hits[b] / b for b in hits}
    result["recall_at"] = {str(b): hits[b] / total for b in hits}
    return result


def cohort_ranking(per_event, *, budget=PRIMARY_BUDGET):
    """Event-macro means over eligible events, with the full event accounting.

    ``per_event`` is a list of ``event_ranking_metrics`` outputs (one training seed).
    """
    per_event = list(per_event)
    eligible = [e for e in per_event if e["eligible"]]
    abstained = [e for e in per_event if e["status"] in ABSTENTION_STATUSES]
    return {"events": len(per_event), "eligible_events": len(eligible),
            "events_without_new_members": len(per_event) - len(eligible),
            "abstentions": len(abstained),
            "eligible_abstentions": sum(e["eligible"] for e in abstained),
            "abstentions_by_reason": {s: sum(e["status"] == s for e in abstained) for s in ABSTENTION_STATUSES},
            "mean_average_precision": float(np.mean([e["average_precision"] for e in eligible])) if eligible else None,
            "mean_precision_at_budget": float(np.mean([e["precision_at"][str(budget)] for e in eligible]))
            if eligible else None,
            "budget": budget, "estimand": "event_macro_mean_over_events_with_new_members",
            "metric_version": METRIC_VERSION}


def eligible_matrix(per_seed_events, metric="average_precision", *, budget=PRIMARY_BUDGET):
    """Training-seed x eligible-event matrix for ``paired_interval``.

    ``per_seed_events`` is a list (one per training seed) of per-event metric lists in one
    common event order. Eligibility depends only on the target and input seeds, so it must
    agree across seeds; disagreement means the rows were not built on one cohort.
    """
    masks = [np.array([e["eligible"] for e in events]) for events in per_seed_events]
    if any(len(m) != len(masks[0]) or (m != masks[0]).any() for m in masks):
        raise ValueError("Training seeds disagree on the eligible cohort")
    pick = (lambda e: e["average_precision"]) if metric == "average_precision" else \
        (lambda e: e["precision_at"][str(budget)])
    return np.array([[pick(e) for e, keep in zip(events, masks[0]) if keep] for events in per_seed_events]), masks[0]


def paired_bootstrap(left, right, blocks, *, repetitions=5000, seed=1701):
    """``paired_interval`` plus a two-sided percentile-bootstrap p-value of zero difference.

    The resampling (training seeds, then whole blocks) and its RNG sequence are identical
    to ``forecast_analysis.paired_interval``, so the interval matches it exactly. The
    p-value is ``min(1, 2 * min(P*(d <= 0), P*(d >= 0)))`` with the add-one correction
    ``(count + 1) / (repetitions + 1)``; it is only used for the Holm family.
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
        selected = rng.integers(len(indices), size=len(indices))
        samples[repetition] = sums[np.ix_(seeds, selected)].sum() / (len(seeds) * sizes[selected].sum())
    low = (np.sum(samples <= 0) + 1) / (repetitions + 1)
    high = (np.sum(samples >= 0) + 1) / (repetitions + 1)
    return {"difference": float(difference.mean()), "ci95": np.quantile(samples, [.025, .975]).tolist(),
            "p_value": float(min(1.0, 2 * min(low, high))), "events": len(blocks), "blocks": len(groups),
            "training_seeds": difference.shape[0], "repetitions": repetitions, "rng_seed": seed,
            "estimand": "event_macro_mean_then_training_seed_mean",
            "interval": "paired_training_seed_and_block_percentile_ordinary_95"}


def ranking_contrast(left_seeds, right_seeds, rows, *, metric="average_precision", budget=PRIMARY_BUDGET,
                     repetitions=10000, seed=1701):
    """One primary contrast: eligible events only, incident-day blocks, paired seeds.

    ``left_seeds``/``right_seeds``: per training seed, per-event metric lists aligned with
    ``rows`` (each row needs ``incident_id`` and ``onset``). A deterministic baseline passes
    one seed. Both arms must agree on eligibility (same target and input seeds).
    """
    left, mask = eligible_matrix(left_seeds, metric, budget=budget)
    right, other = eligible_matrix(right_seeds, metric, budget=budget)
    if len(mask) != len(rows) or (mask != other).any():
        raise ValueError("Arms disagree on the eligible cohort; compare on one input panel")
    kept = [r for r, keep in zip(rows, mask) if keep]
    result = paired_bootstrap(left, right, incident_day_blocks(kept), repetitions=repetitions, seed=seed)
    result.update(metric=metric, budget=budget if metric != "average_precision" else None,
                  eligible_events=int(mask.sum()), events_without_new_members=int((~mask).sum()))
    return result


def holm(p_values):
    """Holm step-down adjusted p-values, in the input order (monotone, capped at 1)."""
    names = list(p_values)
    values = np.array([p_values[n] for n in names], dtype=float)
    if not len(values) or not np.all((values >= 0) & (values <= 1)):
        raise ValueError("Need p-values in [0, 1]")
    order = np.argsort(values, kind="stable")
    m = len(values)
    adjusted = np.empty(m)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (m - rank) * values[index]))
        adjusted[index] = running
    return {n: float(a) for n, a in zip(names, adjusted)}


SLICE_OUTCOME_NEW_MEMBERS = 100
SLICE_VARIABLES = ("early_growth", "seeds_at_issue")


def select_issue_time_slice(variables, new_member_counts, *, large=SLICE_OUTCOME_NEW_MEMBERS,
                            order=SLICE_VARIABLES):
    """Pick the issue-time slice variable and cut on TRAINING events only.

    ``variables`` maps each declared issue-time variable (``order``) to one integer per
    training event. For each, ``issue_time_slice_cut`` finds the F1-maximising cut for the
    outcome "at least ``large`` new members by 2 h"; the variable with the highest F1 wins,
    ties going to the earlier variable in ``order``. Validation and test outcomes never enter.
    """
    if set(variables) != set(order):
        raise ValueError(f"Declared slice variables are {order}")
    candidates = {name: issue_time_slice_cut(variables[name], new_member_counts, large=large) for name in order}
    best = max(order, key=lambda n: (candidates[n]["f1"], -order.index(n)))
    return {"variable": best, **candidates[best], "outcome": f"new_members_2h >= {large}",
            "candidates": candidates}


def issue_time_slice_cut(issue_seed_counts, final_sizes, *, large):
    """Cut for one issue-time slice variable, chosen on TRAINING events only.

    Returns the smallest integer c maximising F1 of the rule ``variable >= c`` for the
    outcome ``outcome >= large`` (the arguments keep their historical names: the variable
    can be any issue-time count and the outcome any training label count). The caller is
    responsible for passing training-split events only. ``large`` has no default: the
    outcome threshold is always stated by the caller.
    """
    seeds = np.asarray(issue_seed_counts, dtype=np.int64)
    final = np.asarray(final_sizes, dtype=np.int64)
    if seeds.shape != final.shape or not len(seeds):
        raise ValueError("Need one seed count and one final size per training event")
    positive = final >= large
    if not positive.any():
        raise ValueError("No large training events; the cut is undefined")
    best, best_f1 = None, -1.0
    for cut in np.unique(seeds):
        chosen = seeds >= cut
        tp = int((chosen & positive).sum())
        f1 = 2 * tp / (chosen.sum() + positive.sum())
        if f1 > best_f1 + 1e-15:
            best, best_f1 = int(cut), f1
    chosen = seeds >= best
    return {"cut": best, "f1": best_f1, "large": large, "training_events": int(len(seeds)),
            "slice_events": int(chosen.sum()), "slice_fraction": float(chosen.mean()),
            "precision": float((chosen & positive).sum() / chosen.sum()),
            "recall": float((chosen & positive).sum() / positive.sum()),
            "rule": "smallest integer c maximising F1 of variable >= c for outcome >= large"}


# Pre-registered descriptive stratification (no tests): new-member count bins, inclusive.
NEW_MEMBER_STRATA = ((1, 1), (2, 9), (10, 99), (100, None))


def _stratum_name(low, high):
    return f">={low}" if high is None else str(low) if low == high else f"{low}-{high}"


def stratify_by_new_members(per_event, strata=NEW_MEMBER_STRATA):
    """Descriptive AP and candidate-coverage ceiling by new-member count (one training seed).

    Every eligible event falls in exactly one declared stratum; ineligible events are
    counted separately. Empty strata report ``None`` means. No test is attached.
    """
    per_event = list(per_event)
    report = {}
    placed = 0
    for low, high in strata:
        chosen = [e for e in per_event if e["eligible"] and e["new_members"] >= low
                  and (high is None or e["new_members"] <= high)]
        placed += len(chosen)
        report[_stratum_name(low, high)] = {
            "events": len(chosen),
            "mean_average_precision": float(np.mean([e["average_precision"] for e in chosen])) if chosen else None,
            "mean_coverage_ceiling": float(np.mean([e["coverage_ceiling"] for e in chosen])) if chosen else None}
    eligible = sum(e["eligible"] for e in per_event)
    if placed != eligible:
        raise ValueError("Strata must partition the eligible events")
    return {"strata": report, "eligible_events": eligible,
            "events_without_new_members": len(per_event) - eligible, "descriptive_only": True,
            "metric_version": METRIC_VERSION}


def _dense_order(values):
    return np.unique(-np.asarray(values, dtype=np.float64), return_inverse=True)[1]


def check_participation_feature(candidate_asns, participation, feature, *, atol=1e-6):
    """Does a committed library participation count reproduce tensor column 10 for one event?

    Column 10 is float32 log1p(participation). ``matches`` compares values; ``order_identical``
    compares the induced ranking including tie groups, which is what the history ranking uses.
    """
    asns = [int(a) for a in candidate_asns]
    feature = np.asarray(feature, dtype=np.float64)
    if len(feature) != len(asns):
        raise ValueError("Feature length differs from the candidate list")
    expected = np.log1p(np.array([participation.get(a, 0) for a in asns], dtype=np.float32)).astype(np.float64)
    close = np.isclose(expected, feature, rtol=0, atol=atol)
    return {"candidates": len(asns), "matches": bool(close.all()),
            "order_identical": bool(np.array_equal(_dense_order(expected), _dense_order(feature))),
            "mismatched_asns": sorted(a for a, ok in zip(asns, close) if not ok)}


def check_participation_cohort(events):
    """Run ``check_participation_feature`` over events; any mismatch raises, naming the events.

    Each event: ``event_id``, ``asn`` (tensor order), ``participation`` (committed library
    counts at issue time) and ``feature`` (tensor column 10).
    """
    events = list(events)
    bad = [e["event_id"] for e in events
           if not (lambda r: r["matches"] and r["order_identical"])(
               check_participation_feature(e["asn"], e["participation"], e["feature"]))]
    if bad:
        raise ValueError(f"Library participation does not reproduce column 10 for {len(bad)} events: {bad[:10]}")
    return {"events": len(events), "mismatched_events": 0,
            "check": "library participation reproduces tensor column 10"}
