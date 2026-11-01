"""Development-only precision planning for fixed future calendar windows.

Resample whole incident-assigned UTC days and paired training seeds. Empty days
remain in the calendar. This empirical stationarity calculation is a planning
diagnostic, not power, equivalence, or a guarantee under distribution shift.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np


def calendar_precision(left, right, event_days, *, calendar_start, calendar_end,
                       candidate_days, development_split, repetitions=2000,
                       seed=1701, half_width_target=.01):
    """Estimate paired event-macro interval widths for prespecified day counts.

    End date is exclusive. Scores are paired seed x event arrays, with a
    deterministic one-row arm broadcast when needed. A sampled seed applies to
    every sampled day, so seed variability does not vanish with more days.
    Event days must come from incident_day_blocks, retaining whole incidents.
    Labels/scores from the locked period must never be supplied to this function.
    """
    if development_split not in ("train", "validation"):
        raise ValueError("Precision planning requires development scores only")
    a, b = np.atleast_2d(left).astype(float), np.atleast_2d(right).astype(float)
    if a.shape[1] != len(event_days) or b.shape[1] != len(event_days) or not len(event_days):
        raise ValueError("Identical nonempty event cohorts are required")
    if a.shape[0] != b.shape[0] and min(a.shape[0], b.shape[0]) != 1:
        raise ValueError("Training seeds must be paired or one arm deterministic")
    if not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError("Undefined scores cannot silently change planning population")
    if ((a < 0) | (a > 1)).any() or ((b < 0) | (b > 1)).any():
        raise ValueError("This precision target is for scores on the unit interval")
    start, end = date.fromisoformat(calendar_start), date.fromisoformat(calendar_end)
    days = (end - start).days
    if days < 2 or repetitions < 100 or not 0 < half_width_target < 1:
        raise ValueError("Need multiple calendar days, >=100 draws and a valid target")
    candidates = sorted(set(candidate_days))
    if not candidates or any(type(n) is not int or n < 2 for n in candidates):
        raise ValueError("Candidate windows must be prespecified integer day counts >=2")
    calendar = {(start + timedelta(days=i)).isoformat(): i for i in range(days)}
    if any(day not in calendar for day in event_days):
        raise ValueError("Incident day lies outside development calendar")
    difference = a - b
    if len(difference) < 2:
        raise ValueError("Multiple training seeds required to include seed uncertainty")
    sizes = np.zeros(days, dtype=int)
    sums = np.zeros((difference.shape[0], days))
    for index, day in enumerate(event_days):
        column = calendar[day]
        sizes[column] += 1
        sums[:, column] += difference[:, index]
    if np.count_nonzero(sizes) < 2:
        raise ValueError("At least two event-bearing incident-day blocks required")
    rng = np.random.default_rng(seed)
    results = []
    for duration in candidates:
        means, event_counts = [], []
        for _ in range(repetitions):
            selected = rng.integers(days, size=duration)
            chosen_seeds = rng.integers(len(sums), size=len(sums))
            count = int(sizes[selected].sum())
            event_counts.append(count)
            if count:
                means.append(float(sums[np.ix_(chosen_seeds, selected)].sum() / (len(sums) * count)))
        empty_fraction = 1 - len(means) / repetitions
        interval = np.quantile(means, [.025, .975]).tolist() if means else None
        width = (interval[1] - interval[0]) / 2 if interval else None
        results.append({"calendar_days": duration, "ci95_half_width": width,
                        "planning_interval": interval, "empty_replicate_fraction": empty_fraction,
                        "event_count_quantiles": np.quantile(event_counts, [.025, .5, .975]).tolist(),
                        "meets_target": width is not None and width <= half_width_target and empty_fraction == 0})
    eligible = [r['calendar_days'] for r in results if r['meets_target']]
    return {"development_split": development_split, "calendar_start": calendar_start,
            "calendar_end_exclusive": calendar_end, "observed_calendar_days": days,
            "event_bearing_days": int(np.count_nonzero(sizes)), "events": len(event_days),
            "training_seeds": len(sums), "repetitions": repetitions, "rng_seed": seed,
            "half_width_target": half_width_target, "candidate_windows": results,
            "first_supported_candidate_days": min(eligible) if eligible else None,
            "assumption": "Exchangeable development incident-day blocks and paired seed effects; not a guarantee under temporal shift",
            "estimand": "event-macro paired difference averaged across training seeds"}
