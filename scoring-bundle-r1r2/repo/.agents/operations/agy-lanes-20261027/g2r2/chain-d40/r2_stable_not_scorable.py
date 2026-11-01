"""D-A40: the stable lane's not-scorable rule, on the stable consumer's scoring path only (no pinned file is edited).

Rule (<AUTHOR>, 2026-10-31T23:24Z, with the approval of ONE disclosed third label read for the stable-peer lane only): an event whose
stable-peer target AND forecast are both empty is NOT SCORABLE in the stable lane; it is excluded from that lane's scored events and
counted; nothing else changes.

Why. D-A39 (job 52728251) scored every secondary family except stable, which failed in the pinned evaluator:
bgbench/forecast_custodian_eval.py:409 `_jaccard` raises "Empty target and prediction: Jaccard undefined on a scorable event",
reached from per_event_rows:514 via components/composition/components/stable/reviewed_membership.py:247 score_cell. An input
abstention forecasts nothing (per_event_rows sets `predicted = set()`), so a scorable event whose stable-peer target is empty has an
empty union.

What `install(consumer)` changes. The stable consumer's evaluate (consumer.py) scores each committed cell through exactly two entry
points, both looked up at call time: `persistence(cell,e,stable_table)` for the persistence baseline and
`m.score_cell(cell,e,stable_table)` for every other committed cell (shape-checked below). Both are replaced, on the stable consumer's
own module objects only (the consumer module and its private `m`), by one narrow wrapper that, for a committed cell:
  1. takes the cell's empty-forecast events from the label-free pre-check (`check_prepared` + `freeze_expected`, run before the
     label read) and refuses when the cell's rows no longer give exactly that set (no record: refused, nothing is scored);
  2. reads the cell's labels with the pinned `labels_for` (the labels the pinned scorer itself reads) and excludes exactly the events
     of that set whose label is `scorable` with an empty target set: the exclusion uses target emptiness and forecast emptiness only;
  3. calls the UNCHANGED pinned scorer with those events removed from the cell (rows, predictions, inputs) and from the cell's label
     horizon, so every metric of the cell leaves them out alike (ranking AP/P@k/recall and AP eligibility, Jaccard, the
     membership/extent/curve/calibration terms of score_membership and the abstention penalties); with no excluded event the pinned
     scorer runs on the original, unmodified objects;
  4. restores the two population descriptors the restriction would otherwise shrink, `reference_events` (the full reference
     population, as the pinned scorer reports it) and `input_status_counts` (over every cell row), and adds FIELD
     {rule, count, event_ids, input_status_counts}; it checks reference_events == scorable_events + censored_events + count and
     that no excluded event was scored. Cells that are not committed pass through untouched.
The forecast set is per_event_rows' own `predicted` (forecast_custodian_eval.py lines 498-509): the committed predicted_asns for an
available input, the empty set for an input abstention (whose row the pinned label-free check requires to predict nothing). Stable
cells carry no slice rule (the pre-check refuses one), so the full-target Jaccard is the only Jaccard that can meet an empty union.

Pairing. `check_prepared` requires, per horizon, the identical empty-forecast event set in every committed stable cell. A cell at
horizon d reads the one stable label horizon d, so the exclusion (that set intersected with the per-event target emptiness) is the
same for every arm of a horizon and the arms stay paired on the same scored events.
"""
import ast
import hashlib
from collections import Counter
from pathlib import Path

CONSUMER_SHA = "deb124b1931cfa36f0dff0fdc3a2a4d592edbd2147c0d662e44986c09aabb712"     # components/composition/components/stable/consumer.py
MEMBERSHIP_SHA = "5cd8c4720675273f232940d39b3dfe7bbdc7a1a72d7c6b21b24f3823575fbfde"   # components/composition/components/stable/reviewed_membership.py
CUSTODIAN_EVAL_SHA = "1619b3286cc5a61c6ceb4aee1ae7bb32c78262c47faf5ea4730c3b647f6fe078"  # bgbench/forecast_custodian_eval.py
RULE = ("D-A40: an event whose stable-peer target set and forecast set are both empty is not scorable in the stable lane; it is "
        "excluded from the cell's scored events (every metric) and counted; every other event is scored by the unchanged pinned code")
FIELD = "not_scorable_empty_target_and_forecast"
MARK = "_d_a40_not_scorable"

EXPECTED = {}   # arm_id -> frozenset of empty-forecast event ids, fixed label-free by freeze_expected() before the label read
RECORDS = []    # one exclusion record per committed cell the wrapper scored


def need(ok, why):
    if not ok:
        raise ValueError("D-A40 stable not-scorable: " + why)


def reset():
    """Forget the frozen pre-check and the records (tests only; a run freezes once)."""
    EXPECTED.clear()
    RECORDS.clear()


# ------------------------------------------------------------------------------------------------------------- label-free part

def forecast_set(meta, row):
    """per_event_rows' `predicted` for one event: the committed decision for an available input, nothing for an abstention."""
    if meta.get("input_status", "available") == "available":
        return set(map(int, row["predicted_asns"]))
    return set()


def empty_forecast_ids(cell):
    """Sorted ids of the cell's events whose forecast set is empty (label-free)."""
    predictions = {p["event_id"]: p for p in cell["predictions"]}
    return sorted(meta["event_id"] for meta in cell["rows"] if not forecast_set(meta, predictions[meta["event_id"]]))


def check_prepared(stable=()):
    """Label-free pre-check over prepared stable stage results (the objects the stable stage returned).

    Per committed cell: the empty-forecast events, and whether they are exactly the cell's input abstentions (recorded, not
    required). Required for `paired`: every committed cell has a distinct arm id and no slice rule, and per horizon every committed
    cell has the identical empty-forecast set."""
    cells, horizons, problems = {}, {}, []
    for prepared in stable:
        for name, cell in prepared["cells"].items():
            if not isinstance(cell, dict) or cell.get("status") != "committed":
                continue
            arm = cell.get("arm_id")
            if not isinstance(arm, str) or arm in cells:
                problems.append(f"cell {name}: missing or duplicate arm id {arm!r}")
                continue
            if cell.get("slice_rule") is not None:
                problems.append(f"{arm}: a stable cell carries a slice rule")
            ids = empty_forecast_ids(cell)
            abstentions = sorted(m["event_id"] for m in cell["rows"] if m.get("input_status", "available") != "available")
            horizon = str(cell["role"]["horizon_seconds"])
            cells[arm] = {"horizon_seconds": int(horizon), "empty_forecast_ids": ids, "empty_forecast": len(ids),
                          "input_abstentions": len(abstentions), "empty_forecast_equals_input_abstentions": ids == abstentions}
            horizons.setdefault(horizon, {}).setdefault(tuple(ids), []).append(arm)
    unpaired = sorted(h for h, sets in horizons.items() if len(sets) != 1)
    if unpaired:
        problems.append(f"empty-forecast event sets differ between the committed cells of horizon(s) {unpaired}")
    summary = {h: {"committed_cells": sum(len(arms) for arms in sets.values()), "distinct_empty_forecast_sets": len(sets),
                   "empty_forecast_per_set": sorted(len(ids) for ids in sets)} for h, sets in sorted(horizons.items())}
    return {"rule": RULE, "cells": cells, "horizons": summary, "problems": problems, "paired": bool(cells) and not problems}


def freeze_expected(check):
    """Fix the label-free empty-forecast sets the scoring wrapper must use. Once per run; a second, different freeze refuses."""
    need(check.get("paired") is True, f"the label-free pre-check did not pass: {check.get('problems')}")
    expected = {arm: frozenset(entry["empty_forecast_ids"]) for arm, entry in check["cells"].items()}
    need(not EXPECTED or EXPECTED == expected, "the label-free empty-forecast record is fixed once per run")
    EXPECTED.clear()
    EXPECTED.update(expected)
    return len(expected)


# ------------------------------------------------------------------------------------------------------------ scoring wrapper

def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _calls(node):
    """Dotted names of every call inside a function node (m.original.per_event_rows -> 'm.original.per_event_rows')."""
    names = []
    for call in ast.walk(node):
        if not isinstance(call, ast.Call):
            continue
        parts, target = [], call.func
        while isinstance(target, ast.Attribute):
            parts.append(target.attr)
            target = target.value
        if isinstance(target, ast.Name):
            parts.append(target.id)
            names.append(".".join(reversed(parts)))
    return names


def _function(path, name):
    tree = ast.parse(Path(path).read_text())
    return next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)


def check_shape(consumer):
    """Pinned bytes and the call sites this patch relies on: evaluate reaches scoring only through `persistence` and `m.score_cell`,
    and each of them reaches per_event_rows exactly once, after reading its labels with labels_for; per_event_rows' `predicted`
    and its full-target Jaccard are the lines forecast_set mirrors."""
    membership = consumer.m
    need(_sha(consumer.__file__) == CONSUMER_SHA, "stable consumer.py differs from its pinned hash")
    need(_sha(membership.__file__) == MEMBERSHIP_SHA, "stable reviewed_membership.py differs from its pinned hash")
    need(_sha(membership.original.__file__) == CUSTODIAN_EVAL_SHA, "forecast_custodian_eval.py differs from its pinned hash")
    evaluate = _calls(_function(consumer.__file__, "evaluate"))
    need(evaluate.count("persistence") == 1 and evaluate.count("m.score_cell") == 1
         and not any(c.endswith(("per_event_rows", "score_membership", "_jaccard")) for c in evaluate),
         "stable evaluate shape changed")
    persistence = _calls(_function(consumer.__file__, "persistence"))
    need(persistence.count("m.original.per_event_rows") == 1 and persistence.count("m.labels_for") == 1,
         "stable persistence shape changed")
    score_cell = _calls(_function(membership.__file__, "score_cell"))
    need(score_cell.count("original.per_event_rows") == 1 and score_cell.count("labels_for") == 1,
         "stable score_cell shape changed")
    source = Path(membership.original.__file__).read_text()
    segment = ast.get_source_segment(source, _function(membership.original.__file__, "per_event_rows"))
    need(segment.count('predicted = set(map(int, row["predicted_asns"]))') == 1 and segment.count("predicted = set()") == 1
         and segment.count('"jaccard": _jaccard(truth, predicted)') == 1, "per_event_rows shape changed")


def _restricted(cell, evidence, table, drop):
    """The cell and its label table without the excluded events (shallow copies; nothing shared is mutated)."""
    horizon = evidence["label_horizon"][str(cell["role"]["horizon_seconds"])]
    horizons = dict(table["horizons"])
    horizons[horizon] = {eid: label for eid, label in table["horizons"][horizon].items() if eid not in drop}
    restricted_table = dict(table)
    restricted_table["horizons"] = horizons
    restricted_cell = dict(cell)
    restricted_cell["rows"] = [r for r in cell["rows"] if r["event_id"] not in drop]
    restricted_cell["predictions"] = [p for p in cell["predictions"] if p["event_id"] not in drop]
    restricted_cell["inputs"] = {eid: value for eid, value in cell["inputs"].items() if eid not in drop}
    return restricted_cell, restricted_table


def _wrap(function, labels_for, kind):
    def scored(cell, evidence, table, **kwargs):
        if not isinstance(cell, dict) or cell.get("status") != "committed":
            return function(cell, evidence, table, **kwargs)
        arm = cell["arm_id"]
        need(arm in EXPECTED, f"{arm}: no label-free empty-forecast record (the pre-label check did not run for this cell)")
        empty = set(empty_forecast_ids(cell))
        need(empty == EXPECTED[arm], f"{arm}: the cell's empty-forecast events differ from the label-free pre-check")
        labels = labels_for(cell, evidence, table)            # pinned: the very labels the pinned scorer reads
        excluded = sorted(eid for eid in empty
                          if labels[eid].get("target_status") == "scorable" and not set(map(int, labels[eid]["target_asns"])))
        if excluded:
            drop = set(excluded)
            restricted_cell, restricted_table = _restricted(cell, evidence, table, drop)
            report = function(restricted_cell, evidence, restricted_table, **kwargs)
            need(report.get("status") == "scored" and not drop & {r["event_id"] for r in report["rows"]},
                 f"{arm}: an excluded event was scored")
            report["reference_events"] = len(labels)
            report["input_status_counts"] = dict(Counter(m["input_status"] for m in cell["rows"]))
        else:
            report = function(cell, evidence, table, **kwargs)
        censored = sum(1 for m in cell["rows"] if labels[m["event_id"]].get("target_status") == "censored")
        need(report.get("status") == "scored" and report["scorable_events"] == len(report["rows"])
             and report["censored_events"] == censored
             and report["reference_events"] == report["scorable_events"] + censored + len(excluded),
             f"{arm}: reference/scorable/censored/not-scorable accounting does not add up")
        statuses = {m["event_id"]: m["input_status"] for m in cell["rows"]}
        report[FIELD] = {"rule": RULE, "count": len(excluded), "event_ids": excluded,
                         "input_status_counts": dict(Counter(statuses[eid] for eid in excluded))}
        RECORDS.append({"arm_id": arm, "path": kind, "horizon_seconds": cell["role"]["horizon_seconds"], "count": len(excluded),
                        "event_ids": excluded, "reference_events": report["reference_events"],
                        "scorable_events": report["scorable_events"], "censored_events": report["censored_events"]})
        return report

    setattr(scored, MARK, True)
    scored.__wrapped__ = function
    return scored


def install(consumer):
    """Wrap the stable consumer's two scoring entry points (its own `persistence`, its private m's `score_cell`). Idempotent."""
    check_shape(consumer)
    membership = consumer.m
    if not getattr(consumer.persistence, MARK, False):
        consumer.persistence = _wrap(consumer.persistence, membership.labels_for, "persistence")
    if not getattr(membership.score_cell, MARK, False):
        membership.score_cell = _wrap(membership.score_cell, membership.labels_for, "score_cell")
    return consumer


def installed(consumer):
    return getattr(consumer.persistence, MARK, False) is True and getattr(consumer.m.score_cell, MARK, False) is True
