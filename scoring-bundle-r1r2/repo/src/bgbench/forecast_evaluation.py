"""Population-level evaluation built on the per-event functions in forecast_analysis.

Everything here consumes committed predictions and evaluator-owned labels and
is never called while fitting or generating protected inputs. It adds three
things the per-event functions do not provide: resampling under several
cluster definitions, population aggregation of the membership decompositions,
and a budgeted monitoring curve with measured delay kept apart from the
observation cutoff.
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np

from .forecast_analysis import (incident_day_blocks, membership_decomposition,
                                monitoring_utility, paired_interval)


def connected_blocks(rows, keys=("incident_id", "actor", "day")):
    """Label events by connected component over shared values of any key.

    ``day`` is derived like ``incident_day_blocks`` (an incident sits on its first
    onset's UTC day). Two events sharing an incident, an actor or a day end up
    in one block, so no dependence through any declared key crosses a block.
    This is the most conservative clustering and can collapse to few blocks.
    """
    rows = list(rows)
    days = incident_day_blocks(rows) if "day" in keys else None
    parent = list(range(len(rows)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    seen = {}
    for index, row in enumerate(rows):
        for key in keys:
            value = days[index] if key == "day" else row.get(key)
            if value is None:
                raise ValueError(f"Missing clustering key {key!r} for event {row.get('event_id', index)}")
            owner = seen.setdefault((key, str(value)), index)
            parent[find(index)] = find(owner)
    roots = {}
    return [str(roots.setdefault(find(i), len(roots))) for i in range(len(rows))]


def clustering_sensitivity(left, right, rows, *, repetitions=5000, seed=1701, min_blocks=10):
    """Paired seed-and-cluster interval under each declared clustering.

    ``incident_day`` is the protocol's primary unit. The others are sensitivity
    analyses. Every scheme reports its block count. A clustering with fewer than
    two blocks is reported as unavailable with its reason, never silently dropped
    or replaced. A scheme with fewer than ``min_blocks`` blocks is flagged
    ``low_block``: a percentile block bootstrap over so few blocks is unreliable,
    so it is listed in ``low_block_schemes`` and never chosen as
    ``widest_available`` (``None`` when no scheme has enough blocks).
    """
    rows = list(rows)
    missing = [r.get("event_id", i) for i, r in enumerate(rows) if r.get("actor") is None]
    if missing:
        raise ValueError(f"Every event needs an actor for the actor and connected clusterings; "
                         f"missing for {missing[:5]}")
    schemes = {"incident_day": incident_day_blocks(rows),
               "actor": [str(r["actor"]) for r in rows],
               "connected": connected_blocks(rows)}
    report = {}
    for name, blocks in schemes.items():
        count = len(set(blocks))
        try:
            report[name] = paired_interval(left, right, blocks, repetitions=repetitions, seed=seed)
        except ValueError as error:
            if "two independent" not in str(error):
                raise
            report[name] = {"unavailable": str(error), "blocks": count}
        report[name]["low_block"] = count < min_blocks
    eligible = {k: v for k, v in report.items() if "ci95" in v and not v["low_block"]}
    report["min_blocks"] = min_blocks
    report["low_block_schemes"] = [k for k in schemes if report[k]["low_block"]]
    report["widest_available"] = (max(eligible, key=lambda k: eligible[k]["ci95"][1] - eligible[k]["ci95"][0])
                                  if eligible else None)
    report["primary"] = "incident_day"
    return report


def event_membership(target, reference_seeds, input_seen):
    """Reference-new and input-new members of one event, kept separate.

    Reference-new subtracts the fixed reference-panel seeds; input-new subtracts
    what the chosen input panel already observed. The two sets differ whenever
    the input seeds differ from the reference seeds: a strict input subset leaves
    reference seeds the input never saw in ``input_new`` (seeds {1, 2}, input {1},
    truth {1, 2, 3} gives reference_new {3}, input_new {2, 3}), and input members
    outside the reference panel can already have seen reference-new ASes, which
    ``seen_by_input_only`` lists.
    """
    truth = set(target)
    reference_new = truth - set(reference_seeds)
    input_new = truth - set(input_seen)
    return {"reference_new": sorted(reference_new), "input_new": sorted(input_new),
            "seen_by_input_only": sorted(reference_new - input_new)}


def aggregate_decompositions(per_event):
    """Pool per-event decompositions: micro counts plus macro fractions of new truth.

    Events with no new truth count toward ``events`` and ``events_without_new_truth``
    and are left out of the macro fractions, which would otherwise be 0/0.
    """
    per_event = list(per_event)
    if not per_event:
        raise ValueError("No events to aggregate")
    keys = set(per_event[0])
    if any(set(d) != keys for d in per_event):
        raise ValueError("Decompositions must come from one function with identical keys")
    counts = {k: sum(d[k] for d in per_event) for k in sorted(keys)}
    with_truth = [d for d in per_event if d["new_true"]]
    # The disjoint parts that sum to new_true, per decomposition kind.
    parts = (["original_target_candidates", "recovered_from_cap", "recovered_outside_two_hop",
              "still_omitted_by_cap", "still_outside_two_hop"] if "original_target_candidates" in keys
             else ["outside_uncapped", "removed_by_cap", "candidate_ranking_miss", "new_true_positive"])
    if not set(parts) <= keys:
        raise ValueError("Unrecognised decomposition keys")
    macro = {k: float(np.mean([d[k] / d["new_true"] for d in with_truth])) if with_truth else None
             for k in parts}
    return {"events": len(per_event), "events_without_new_truth": len(per_event) - len(with_truth),
            "micro": counts,
            "micro_fraction_of_new_true": {k: counts[k] / counts["new_true"] if counts["new_true"] else None
                                           for k in parts},
            "macro_fraction_of_new_true": macro}


def decompose_population(events):
    """Per-event membership_decomposition over a cohort, then aggregate."""
    return aggregate_decompositions(
        membership_decomposition(e["target"], e["seeds"], e["candidates"], e["predicted"], e["uncapped"])
        for e in events)


def monitoring_curve(events, budgets, *, pipeline_seconds=None):
    """Budgeted input-new monitoring over a cohort at several budgets.

    Each event: ``ranked_asns, target, input_seen, first_seen_seconds,
    observation_cutoff_seconds`` and an explicit ``status`` (``available`` or
    ``no_input``); a missing status fails rather than defaulting. A ``no_input``
    event is an abstention: it must carry no ranked ASNs, nothing is selected, and
    its input-new truth still counts in recall so abstention is penalised, not hidden.

    ``pipeline_seconds`` selects how delay is treated and says so in the output:
    ``None`` is an offline upper bound with zero delay; a number is an assumed
    constant; ``"measured"`` reads a per-event ``measured_pipeline_seconds`` and
    fails if an available event lacks it. Delay is subtracted once, from the
    observation cutoff, and is never mixed into lead times from the cutoff. Any
    other ``pipeline_seconds`` value fails up front.
    """
    events = list(events)
    if not events or not budgets:
        raise ValueError("Need events and at least one budget")
    measured = isinstance(pipeline_seconds, str) and pipeline_seconds == "measured"
    if not (pipeline_seconds is None or measured
            or (isinstance(pipeline_seconds, (int, float)) and not isinstance(pipeline_seconds, bool)
                and np.isfinite(pipeline_seconds) and pipeline_seconds >= 0)):
        raise ValueError(f"pipeline_seconds must be None, 'measured' or a finite non-negative number, "
                         f"not {pipeline_seconds!r}")
    for index, event in enumerate(events):
        name = event.get("event_id", index)
        if "status" not in event:
            raise ValueError(f"Event {name} has no status; it must be explicitly 'available' or 'no_input'")
        if event["status"] not in ("available", "no_input"):
            raise ValueError(f"Unknown status {event['status']!r} for event {name}")
        if event["status"] == "no_input" and event.get("ranked_asns"):
            raise ValueError(f"A no_input event must have no ranked_asns (event {name})")
    if measured and any(e["status"] == "available" and "measured_pipeline_seconds" not in e
                        for e in events):
        raise ValueError("Measured mode needs measured_pipeline_seconds for every available event")
    source = "measured_per_event" if measured else "none_offline_upper_bound" if pipeline_seconds is None \
        else "assumed_constant"
    curve = []
    for budget in budgets:
        selected = true_selected = new_true = abstained = actionable = 0
        false_selected = 0
        recalls, from_cutoff, from_output = [], [], []
        for event in events:
            future = set(event["target"]) - set(event["input_seen"])
            new_true += len(future)
            if event["status"] == "no_input":
                abstained += 1
                recalls.append(0.0 if future else None)
                continue
            delay = event["measured_pipeline_seconds"] if measured else (pipeline_seconds or 0)
            one = monitoring_utility(event["ranked_asns"], event["target"], event["input_seen"],
                                     event["first_seen_seconds"],
                                     observation_cutoff_seconds=event["observation_cutoff_seconds"],
                                     budget=budget, pipeline_seconds=delay)
            selected += one["selected"]
            true_selected += one["true_selected"]
            false_selected += one["false_selected"]
            actionable += one["actionable_true_selected"]
            from_cutoff += one["lead_from_observation_cutoff_seconds"]
            from_output += one["lead_from_forecast_output_seconds"]
            recalls.append(one["recall"])
        defined = [r for r in recalls if r is not None]
        curve.append({
            "budget": budget, "events": len(events), "abstained_events": abstained,
            "selected": selected, "true_selected": true_selected, "false_selected": false_selected,
            "new_true": new_true,
            "micro_precision": true_selected / selected if selected else None,
            "micro_recall": true_selected / new_true if new_true else None,
            "macro_recall": float(np.mean(defined)) if defined else None,
            "actionable_true_selected": actionable,
            "too_late_fraction": (true_selected - actionable) / true_selected if true_selected else None,
            "lead_from_observation_cutoff_seconds_quantiles": _quantiles(from_cutoff),
            "lead_from_forecast_output_seconds_quantiles": _quantiles(from_output)})
    return {"pipeline_source": source,
            "pipeline_seconds": pipeline_seconds if isinstance(pipeline_seconds, (int, float)) else None,
            "curve": curve}


def _quantiles(values):
    if not values:
        return None
    return dict(zip(("p10", "p50", "p90"), np.quantile(values, [.1, .5, .9]).tolist()))
