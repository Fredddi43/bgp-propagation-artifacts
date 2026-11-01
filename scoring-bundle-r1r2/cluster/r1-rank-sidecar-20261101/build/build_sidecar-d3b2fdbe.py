#!/usr/bin/env python3
"""Build the R1 rank sidecar by replaying the original R1 scoring tasks with the pinned evaluator.

The R1 evaluation (r1-release-parallel-v11-20261024) scored every non-alias committed cell in a
64-lane Slurm array. Each lane read a task envelope (task-NNNN.json: the cell, its scoring context and
the parent-verified metadata buffers), the cell's prediction bytes, and its bound label files, and ran
the pinned driver's scorer. The envelopes are still on disk. This script runs the same scorer on the
same bytes, with one addition: ``bgbench.forecast_retrospective_scoring.event_ranking_metrics`` is
wrapped. The wrapper returns the unchanged function's result, and additionally records, from the
evaluator's own helpers ``_clean_ranking`` and ``_tie_groups`` on the same arguments, the tie groups
of the evaluator's ranking that contain new members.

Per cell it then requires that
  * the replayed per-event rows, serialised exactly as the R1 worker did, hash to the digest in the
    released R1 report (``per_event_sha256``), i.e. the replay reproduces the released file byte for
    byte;
  * every captured call maps to exactly one released row, and the row's ranking fields equal the
    result of the call;
  * the metrics recomputed from the captured groups alone equal the result of the call.
Only then are the cell's sidecar rows written (one parquet per cell, atomically, plus a done record),
so a rerun skips finished cells.

  replay --lane N        cells of topology lane N (default: $SLURM_ARRAY_TASK_ID)
  replay --cells A,B     named cells (dry run)
  merge                  combine the per-cell files into sidecar/{cells,events,sets}.parquet

Run with the project venv: python -I -B build_sidecar.py ... (cwd /tmp).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import resource
import sys
import time
from pathlib import Path

FROOT = Path("<FORECAST_ROOT>")
V11 = FROOT / "r1-release-parallel-v11-20261024"
ARRAY = V11 / "control-v1" / "scoring-array"
TOPOLOGY_SHA256 = "27c8424f1c5e0971cf506f7c52cbf78f0dc0f1f5c97316110bbd59f743fdb54b"  # execution-spec scoring_topology
REPORT = V11 / "control-v1" / "results" / "report.json"
REPORT_SHA256 = "049c7a9c433de1f4d03c4b5a3f7194316fc991f2c56e41ec64aac5c05b96339d"
SEAL = FROOT / "occurrence-final-v1/custody/r1-access/r1-seal-134d74fb72dd8d4940adb52bb0bdc11d0f7948cfad0560324275d711a219f887.json"
SEAL_SHA256 = "1cad501a3fab90abc3f2eb8cd0f2ffd29f193c435e77c4ded27bc447d41e2b5c"
OUT = FROOT / "r1-rank-sidecar-20261101"
WORK = OUT / "work"
RANKING_FIELDS = {  # released row key -> event_ranking_metrics result key
    "average_precision": "average_precision", "precision_at": "precision_at", "recall_at": "recall_at",
    "new_members": "new_members", "eligible": "eligible", "ranked": "ranked",
    "new_members_ranked": "new_members_ranked", "coverage_ceiling": "coverage_ceiling",
    "metric_version": "metric_version", "ranking_status": "status"}


def need(ok, message):
    if not ok:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def file_sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_checked(path, expected):
    raw = Path(path).read_bytes()
    need(digest(raw) == expected, f"digest differs: {path}")
    return raw


SCRIPT_SHA256 = file_sha(__file__)  # the bytes this process runs, fixed at start


def safe_name(cell_id):
    return cell_id.replace("/", "__")


def maxrss_bytes():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024


# --------------------------------------------------------------------------- pinned evaluator

class Pinned:
    """The R1 driver and bgbench modules from the pinned R1 source tree, imported from source only."""

    def __init__(self, topology):
        source = topology["source"]
        for path, expected in source.items():
            need(file_sha(path) == expected, f"pinned source changed: {path}")
        pinned = set(source)

        def source_only_imports(event, args):  # as parallel_scoring.initialize: never a cached .pyc
            if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
                path = os.fsdecode(args[0])
                if path.endswith(".pyc"):
                    try:
                        original = importlib.util.source_from_cache(path)
                    except ValueError:
                        original = path[:-1]
                    if original in pinned:
                        raise FileNotFoundError("pinned imports require verified source bytes")
        sys.addaudithook(source_only_imports)
        driver_path = topology["driver_path"]
        root = Path(driver_path).resolve().parents[1]
        sys.path[:0] = [str(root / "src"), str(root / "scripts")]
        sys.dont_write_bytecode = True
        spec = importlib.util.spec_from_file_location("r1_scoring_pinned_driver", driver_path)
        self.driver = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.driver)
        import numpy as np
        import parallel_scoring as ps
        from bgbench import forecast_ranking as fr
        from bgbench import forecast_retrospective_scoring as frs
        from bgbench import forecast_train
        for module in (fr, frs, forecast_train, ps):
            need(str(Path(module.__file__).resolve()) in pinned, f"module outside the pinned source: {module.__file__}")
        self.np, self.ps, self.fr, self.frs = np, ps, fr, frs
        # Same exact one-partition memo the R1 workers installed (a cache; identical results).
        self.memo = self.driver.PartitionMemo(forecast_train.load_partition)
        forecast_train.load_partition = self.memo
        self.calls = []
        self._install()

    def _install(self):
        np, fr, frs = self.np, self.fr, self.frs
        original = frs.event_ranking_metrics
        need(original is fr.event_ranking_metrics, "scorer does not use forecast_ranking.event_ranking_metrics")
        calls = self.calls

        def capturing(candidate_asns, scores, target, input_seen, *, budgets=fr.BUDGETS, status="available"):
            for value in (candidate_asns, scores, target, input_seen):
                need(isinstance(value, (list, tuple, set, frozenset, np.ndarray)), "non-reiterable ranking input")
            result = original(candidate_asns, scores, target, input_seen, budgets=budgets, status=status)
            need(tuple(int(b) for b in budgets) == tuple(fr.BUDGETS), "non-default budgets")
            target_set = set(map(int, target))
            seen_set = set(map(int, input_seen))
            new = np.fromiter((int(a) for a in target_set - seen_set), dtype=np.int64)
            if status in fr.ABSTENTION_STATUSES:
                asns, values = np.zeros(0, np.int64), np.zeros(0)
            else:
                asns, values = fr._clean_ranking(candidate_asns, scores, input_seen)
            sizes, relevant = fr._tie_groups(asns, values, new)
            starts = np.cumsum(sizes) - sizes
            keep = relevant > 0
            capture = {"status": status, "new_members": int(len(new)), "ranked": int(len(asns)),
                       "starts": starts[keep].astype(np.int64), "sizes": sizes[keep].astype(np.int64),
                       "relevant": relevant[keep].astype(np.int64),
                       "target": sorted(target_set), "input_seen": sorted(seen_set),
                       "result": result, "event_id": None}
            self.self_check(capture)
            calls.append(capture)
            return result

        def tagging(function):
            def wrapper(*args, **kwargs):
                start = len(calls)
                rows = function(*args, **kwargs)
                made = calls[start:]
                need(len(made) == len(rows), f"{function.__name__}: calls and rows differ")
                for capture, row in zip(made, rows):
                    need(capture["event_id"] is None, "call already assigned")
                    capture["event_id"] = row["event_id"]
                return rows
            wrapper.__name__ = function.__name__
            return wrapper

        frs.event_ranking_metrics = capturing
        frs.score_membership = tagging(frs.score_membership)
        frs.score_panel = tagging(frs.score_panel)

    def expand(self, capture):
        """Full (sizes, relevant) arrays: the captured groups plus r=0 filler groups for the gaps."""
        np = self.np
        sizes, relevant, position = [], [], 0
        for s, n, r in zip(capture["starts"].tolist(), capture["sizes"].tolist(), capture["relevant"].tolist()):
            need(s >= position and 1 <= r <= n, "invalid captured group")
            if s > position:
                sizes.append(s - position)
                relevant.append(0)
            sizes.append(n)
            relevant.append(r)
            position = s + n
        need(position <= capture["ranked"], "groups beyond the ranking")
        if capture["ranked"] > position:
            sizes.append(capture["ranked"] - position)
            relevant.append(0)
        return np.asarray(sizes, dtype=np.int64), np.asarray(relevant, dtype=np.int64)

    def self_check(self, capture):
        """The metrics follow from the captured groups alone (evaluator helpers, unchanged)."""
        fr, result = self.fr, capture["result"]
        sizes, relevant = self.expand(capture)
        total = capture["new_members"]
        need(result["new_members"] == total and result["ranked"] == capture["ranked"]
             and result["new_members_ranked"] == int(relevant.sum()) and result["status"] == capture["status"],
             "captured counts differ")
        if total:
            need(fr.expected_average_precision(sizes, relevant, total) == result["average_precision"], "AP differs")
            for b in fr.BUDGETS:
                hits = fr.expected_hits_at(sizes, relevant, b)
                need(hits / b == result["precision_at"][str(b)] and hits / total == result["recall_at"][str(b)],
                     "P@k/recall@k differs")
            need(float(relevant.sum() / total) == result["coverage_ceiling"], "coverage differs")
        else:
            need(result["average_precision"] is None and result["coverage_ceiling"] is None, "ineligible differs")


# --------------------------------------------------------------------------- replay

def load_anchors():
    topology = json.loads(read_checked(ARRAY / "topology.json", TOPOLOGY_SHA256))
    activation = json.loads((ARRAY / "activation.json").read_bytes())
    need(activation["topology_sha256"] == TOPOLOGY_SHA256, "activation names another topology")
    tasks = json.loads(read_checked(ARRAY / "tasks-ready.json", activation["tasks_sha256"]))
    need(tasks["topology_sha256"] == TOPOLOGY_SHA256 and tasks["labels_opened"] is False, "tasks-ready differs")
    report = json.loads(read_checked(REPORT, REPORT_SHA256))
    return topology, tasks, report


def lane_of(topology):
    return {key: (index, position) for index, keys in enumerate(topology["lanes"])
            for position, key in enumerate(keys)}


SOURCE_EVENTS = FROOT / "occurrence-final-v1/development-data/eventset/2025_leak/events.parquet"
SOURCE_EVENTS_SHA256 = "2862855d49683b464d3d4b9bd9679cec22c7cec4365ff4be7e19dd33638840f8"  # manifests' source_receipts
PER_EVENT = V11 / "control-v1" / "results" / "per_event"
CROSS_FIELDS = ("jaccard", "jaccard_persist", "precision", "recall", "size_ratio", "true_size", "new_true_size",
                "candidate_target_coverage", "true_outside_candidates", "candidate_jaccard",
                "candidate_jaccard_persist", "new_tp", "new_fp", "new_fn", "new_precision", "new_recall", "new_f1",
                "no_growth", "empty_new_prediction")
_TARGETS = {}


def source_targets():
    """event_id -> 2-h target AS set (set_final_2h) of the hash-pinned source event table of the R1 manifests."""
    if not _TARGETS:
        import polars as pl
        raw = read_checked(SOURCE_EVENTS, SOURCE_EVENTS_SHA256)
        import io
        table = pl.read_parquet(io.BytesIO(raw)).select("event_id", "set_final_2h")
        for event_id, target in table.iter_rows():
            need(event_id not in _TARGETS, "duplicate event in the source table")
            _TARGETS[event_id] = None if target is None else frozenset(map(int, target))
    return _TARGETS


def finite_or_none(value):
    import math
    return None if isinstance(value, float) and not math.isfinite(value) else value


def direct_cell(pinned, cell, context, payload, released):
    """Fallback when the cell's label tensors are gone: the scorer's own ranking call, targets from the source table.

    Mirrors score_membership (forecast_retrospective_scoring.py lines 69-125) and score_panel (lines 259-267) for the
    event_ranking_metrics call; for membership rows also the target-dependent decision fields (membership_metrics,
    new_tp/new_fp/new_fn, ...), which the released rows carry and which pin the target set further.
    """
    np, frs = pinned.np, pinned.frs
    from bgbench.graph_metrics import membership_metrics
    targets = source_targets()
    side = context["side"]
    calls = pinned.calls
    released_by_id = {r["event_id"]: r for r in released}
    cross = 0
    if "h3_context" in side:
        from bgbench.forecast_panel_scoring import aligned_rows
        state = side["h3_context"]
        aligned = aligned_rows(state["arm"], state["family"], state["rows"], payload, state["binding"],
                               cell["predictions_sha256"], temporal_monotone=state["temporal_monotone"],
                               horizon_seconds=state["horizon"])
        original = {r["event_id"]: r for r in payload}
        for row in aligned:
            truth = targets[row["event_id"]]
            need(truth is not None, "event without a source target")
            available = row["forecast_available"]
            forecast = original[row["event_id"]] if available else {}
            scores = forecast.get("ranking_scores", forecast.get("probabilities", []))
            frs.event_ranking_metrics(row["candidate_asns"], scores, set(truth), set(map(int, row["input_seed_asns"])),
                                      status="available" if available else "no_input")
            calls[-1]["event_id"] = row["event_id"]
        return cross
    predictions = {r["event_id"]: r for r in payload}
    need(len(predictions) == len(payload) and set(predictions) == set(side["event_ids"]), "prediction population differs")
    for event_id in side["event_ids"]:
        row = predictions[event_id]
        truth = targets[event_id]
        need(truth is not None, "event without a source target")
        truth = set(truth)
        seeds = set(row["seed_asns"])
        frs.event_ranking_metrics(row["candidate_asns"], frs.ranking_scores(row), truth, seeds,
                                  status=row.get("status", "available"))
        calls[-1]["event_id"] = event_id
        # Target-dependent decision fields, computed as score_membership does.
        if "ranking_scores" in row:
            predicted = set(map(int, row["predicted_asns"]))
            union = truth | predicted
            expected = {"jaccard": len(truth & predicted) / len(union) if union else float("nan"),
                        "jaccard_persist": len(truth & seeds) / len(truth | seeds) if truth | seeds else float("nan")}
        else:
            selected = np.asarray(row["probabilities"]) >= row["threshold"]
            event = {"asn": np.asarray(row["candidate_asns"]), "target_asns": np.asarray(sorted(truth), dtype=np.int64),
                     "seed_asns": np.asarray(sorted(seeds), dtype=np.int64)}
            expected = membership_metrics(event, selected)
            predicted = seeds | set(np.asarray(row["candidate_asns"])[selected].tolist())
            need(predicted == set(row["predicted_asns"]), "committed decision differs from probabilities/threshold")
        new_true, new_pred = truth - seeds, predicted - seeds
        tp = len(new_true & new_pred)
        expected.update(new_tp=tp, new_fp=len(new_pred - truth), new_fn=len(new_true - new_pred),
                        new_precision=tp / len(new_pred) if new_pred else None,
                        new_recall=tp / len(new_true) if new_true else None,
                        new_f1=2 * tp / (len(new_pred) + len(new_true)) if new_pred or new_true else None,
                        no_growth=not new_true, empty_new_prediction=not new_pred)
        out = released_by_id[event_id]
        for field in CROSS_FIELDS:
            if field in out:
                need(out[field] == finite_or_none(expected[field]), f"{event_id}: {field} differs (target set)")
                cross += 1
    return cross


def released_rows(report, key):
    raw = read_checked(PER_EVENT / f"{safe_name(key)}.json", report["per_event_sha256"][key])
    return json.loads(raw)


def replay_cell(pinned, topology, tasks, report, key):
    started = time.time()
    np, ps, driver = pinned.np, pinned.ps, pinned.driver
    ref = tasks["tasks"][key]
    task = json.loads(read_checked(ref["path"], ref["sha256"]))
    metadata = task["metadata"]
    cell, context = metadata["cell"], metadata["context"]
    need(cell == topology["cells"][key] and cell["cell_id"] == key, "task cell differs from topology")
    prediction = task["prediction"]
    need(prediction["path"] == cell["predictions_path"] and prediction["sha256"] == cell["predictions_sha256"],
         "task prediction differs")
    missing = sorted(p for p in [*metadata["data_paths"], *metadata["labels"], prediction["path"]]
                     if not os.path.exists(p))
    if missing and cell["payload"] in driver.NPZ_PAYLOADS:  # curve/count cells carry no ranking metric
        released = released_rows(report, key)
        need(not any(k in r for r in released for k in RANKING_FIELDS), f"{key}: curve cell with ranking fields")
        record = {"cell_id": key, "format": cell["format"], "scorer_path": "curve", "role": cell["role"],
                  "verification": "not_rebuilt_inputs_missing", "missing_inputs": len(missing),
                  "missing_examples": missing[:3], "predictions_sha256": cell["predictions_sha256"],
                  "per_event_sha256_reproduced": None, "rows": len(released), "ranking_rows": 0, "eligible": 0,
                  "groups": 0, "new_members_ranked": 0, "files": None}
        write_done(key, record)
        return record
    if not os.path.exists(prediction["path"]):  # a ranking cell whose committed forecast is gone: a named gap
        released = released_rows(report, key)
        ranking = [r for r in released if any(k in r for k in RANKING_FIELDS)]
        record = {"cell_id": key, "format": cell["format"], "role": cell["role"],
                  "scorer_path": "panel" if "h3_context" in context["side"] else "membership",
                  "verification": "not_built_committed_forecast_missing", "missing_inputs": len(missing),
                  "missing_examples": missing[:3], "predictions_path": cell["predictions_path"],
                  "predictions_sha256": cell["predictions_sha256"], "per_event_sha256_reproduced": None,
                  "rows": len(released), "ranking_rows": len(ranking),
                  "eligible": sum(r.get("eligible") is True for r in ranking), "groups": 0,
                  "new_members_ranked": None, "files": None}
        write_done(key, record)
        return record
    raw = read_checked(prediction["path"], prediction["sha256"])
    import base64
    buffers = {path: base64.b64decode(value, validate=True) for path, value in task["buffers"].items()}
    del task
    reads = ps.ScoringReads(buffers, metadata["labels"], metadata["max_file_bytes"])
    context["reads"] = reads
    payload = driver.decode_validated(cell, raw, {key: raw}, context["side"], context["r1_event_ids"], reads)
    pinned.calls.clear()
    cross = 0
    if missing:  # label tensors gone: direct path, verified against the released rows field by field
        need(cell["payload"] not in driver.NPZ_PAYLOADS and "stable_context" not in context["side"],
             f"{key}: no fallback for this scorer")
        rows = released_rows(report, key)
        cross = direct_cell(pinned, cell, context, payload, rows)
        reproduced, verification = None, "direct_fields_exact"
    else:
        rows = driver.SCORERS[cell["format"]]["score"](cell, payload, raw, context)
        # The R1 worker's serialisation (parallel_scoring.worker_task); the parent re-dumped the same bytes.
        result_bytes = (json.dumps(rows, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
        reproduced = digest(result_bytes)
        need(reproduced == report["per_event_sha256"][key], f"{key}: replay does not reproduce the released file")
        del result_bytes
        verification = "replay_byte_exact"
    by_id = {row["event_id"]: row for row in rows}
    need(len(by_id) == len(rows) and sorted(by_id) == sorted(context["side"]["event_ids"]), "population differs")
    calls = pinned.calls
    pending = [c for c in calls if c["event_id"] is None]
    if pending:  # score_stable's own calls: persistence rows (in payload order), then certified abstentions
        need(cell["format"] == "stable_prediction_index_v1", "unassigned ranking calls")
        state = context["side"]["stable_context"]
        order = []
        if state["arm"] == "persistence":
            order += [r["event_id"] for r in payload if r["stable_input_status"] == "stable_input"]
        order += [r["event_id"] for r in payload if r["stable_input_status"] == "certified_no_stable_input"]
        need(len(order) == len(pending), "stable call order differs")
        for capture, event_id in zip(pending, order):
            capture["event_id"] = event_id
    captured = {c["event_id"]: c for c in calls}
    need(len(captured) == len(calls), "two calls for one event")
    ranking_rows = [row for row in rows if any(k in row for k in RANKING_FIELDS)]
    need(set(captured) == {row["event_id"] for row in ranking_rows}, "calls and ranking rows differ")
    need(not calls or len(ranking_rows) == len(rows), "ranking fields on a subset of rows")
    compared = 0
    for row in ranking_rows:
        result = captured[row["event_id"]]["result"]
        for field, source in RANKING_FIELDS.items():
            if field in row:
                need(row[field] == result[source], f"{key} {row['event_id']}: {field} differs from its call")
                compared += 1
    # Per-cell sidecar rows.
    import polars as pl
    events = sorted(captured)
    sets, set_keys = {}, []
    for event_id in events:
        c = captured[event_id]
        doc = json.dumps([event_id, c["target"], c["input_seen"]], separators=(",", ":")).encode()
        set_key = digest(doc)
        set_keys.append(set_key)
        sets.setdefault(set_key, (event_id, c["target"], c["input_seen"]))
    frame = pl.DataFrame({
        "event_id": events,
        "status": [captured[e]["status"] for e in events],
        "new_members": pl.Series([captured[e]["new_members"] for e in events], dtype=pl.Int32),
        "ranked": pl.Series([captured[e]["ranked"] for e in events], dtype=pl.Int32),
        "set_key": set_keys,
        "starts": pl.Series([captured[e]["starts"].tolist() for e in events], dtype=pl.List(pl.Int32)),
        "sizes": pl.Series([captured[e]["sizes"].tolist() for e in events], dtype=pl.List(pl.Int32)),
        "relevant": pl.Series([captured[e]["relevant"].tolist() for e in events], dtype=pl.List(pl.Int32)),
    }, schema_overrides={"event_id": pl.String, "status": pl.String, "set_key": pl.String})
    set_frame = pl.DataFrame({
        "set_key": list(sets),
        "event_id": [v[0] for v in sets.values()],
        "target_asns": pl.Series([v[1] for v in sets.values()], dtype=pl.List(pl.Int64)),
        "input_seen_asns": pl.Series([v[2] for v in sets.values()], dtype=pl.List(pl.Int64)),
    }, schema_overrides={"set_key": pl.String, "event_id": pl.String})
    name = safe_name(key)
    written = {}
    for kind, data in (("events", frame), ("sets", set_frame)):
        path = WORK / kind / f"{name}.parquet"
        temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
        data.write_parquet(temporary, compression="zstd", compression_level=9, statistics=True)
        os.replace(temporary, path)
        written[kind] = {"path": str(path), "sha256": file_sha(path), "rows": data.height}
    side = context["side"]
    kind = ("curve" if not calls else "stable" if "stable_context" in side
            else "panel" if "h3_context" in side else "membership")
    record = {"cell_id": key, "format": cell["format"], "scorer_path": kind, "role": cell["role"],
              "predictions_path": cell["predictions_path"], "predictions_sha256": cell["predictions_sha256"],
              "task": ref, "verification": verification, "per_event_sha256_reproduced": reproduced,
              "missing_inputs": len(missing), "missing_examples": missing[:3],
              "target_source": ({"path": str(SOURCE_EVENTS), "sha256": SOURCE_EVENTS_SHA256, "column": "set_final_2h"}
                                if verification == "direct_fields_exact" else "cell label partition (replay)"),
              "cross_fields_compared": cross,
              "rows": len(rows), "ranking_rows": len(ranking_rows), "fields_compared": compared,
              "eligible": int(sum(bool(captured[e]["result"]["eligible"]) for e in events)),
              "groups": int(sum(len(captured[e]["starts"]) for e in events)),
              "new_members_ranked": int(sum(int(captured[e]["relevant"].sum()) for e in events)),
              "label_files_read": metadata["labels"], "data_paths": len(metadata["data_paths"]),
              "files": written, "seconds": round(time.time() - started, 3),
              "process_maxrss_bytes": maxrss_bytes(), "memo_loads": pinned.memo.loads,
              "memo_hits": pinned.memo.hits, "host": os.uname().nodename,
              "slurm_job": os.environ.get("SLURM_JOB_ID"), "slurm_array_task": os.environ.get("SLURM_ARRAY_TASK_ID")}
    write_done(key, record)
    pinned.calls.clear()
    return record


def write_done(key, record):
    record["build_script_sha256"] = SCRIPT_SHA256
    done = WORK / "done" / f"{safe_name(key)}.json"
    temporary = done.with_name(done.name + f".tmp-{os.getpid()}")
    temporary.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, done)


def replay(args):
    for sub in ("events", "sets", "done", "logs"):
        (WORK / sub).mkdir(parents=True, exist_ok=True)
    topology, tasks, report = load_anchors()
    if args.cells:
        keys = args.cells.split(",")
    else:
        lane = int(args.lane if args.lane is not None else os.environ["SLURM_ARRAY_TASK_ID"])
        keys = topology["lanes"][lane]
    need(all(k in topology["cells"] for k in keys), "unknown cell")
    todo = [k for k in keys if not (WORK / "done" / f"{safe_name(k)}.json").exists()]
    print(json.dumps({"cells": len(keys), "todo": len(todo), "host": os.uname().nodename}), flush=True)
    if not todo:
        return
    pinned = Pinned(topology)
    failures = 0
    (WORK / "failed").mkdir(exist_ok=True)
    for key in todo:
        try:
            record = replay_cell(pinned, topology, tasks, report, key)
        except Exception as error:  # record and continue with the lane; the cell has no done record
            import traceback
            failures += 1
            pinned.calls.clear()
            (WORK / "failed" / f"{safe_name(key)}.json").write_text(json.dumps(
                {"cell_id": key, "error": f"{type(error).__name__}: {error}"[:2000],
                 "traceback": traceback.format_exc()[-4000:], "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                 "slurm_job": os.environ.get("SLURM_JOB_ID")}, indent=2) + "\n")
            print(json.dumps({"cell_id": key, "failed": f"{type(error).__name__}: {error}"[:500]}), flush=True)
            continue
        print(json.dumps({k: record.get(k) for k in ("cell_id", "scorer_path", "verification", "rows", "ranking_rows",
                                                     "groups", "fields_compared", "cross_fields_compared", "seconds",
                                                     "process_maxrss_bytes")}), flush=True)
    if failures:
        raise SystemExit(f"{failures} cell(s) failed; see {WORK / 'failed'}")


# --------------------------------------------------------------------------- merge

def merge(args):
    import polars as pl
    topology, tasks, report = load_anchors()
    seal = json.loads(read_checked(SEAL, SEAL_SHA256))
    committed = [c for c in seal["cells"] if c["status"] == "committed"]
    need({c["cell_id"] for c in committed} == set(report["per_event_sha256"]), "seal and report differ")
    done = {}
    for cell in committed:
        if cell.get("alias_of"):
            continue
        path = WORK / "done" / f"{safe_name(cell['cell_id'])}.json"
        need(path.exists(), f"cell not replayed: {cell['cell_id']}")
        done[cell["cell_id"]] = json.loads(path.read_text())
    need(set(done) == set(topology["cells"]), "replayed cells differ from the topology")
    final = OUT / "sidecar"
    final.mkdir(parents=True, exist_ok=True)
    cell_rows, frames, set_frames = [], [], []
    order = sorted(c["cell_id"] for c in committed)
    index = {cell_id: i for i, cell_id in enumerate(order)}
    by_id = {c["cell_id"]: c for c in committed}
    for cell_id in order:
        cell = by_id[cell_id]
        parent = cell.get("alias_of")
        record = done[parent or cell_id]
        cell_rows.append({
            "cell_index": index[cell_id], "cell_id": cell_id, "format": cell["format"],
            "scorer_path": record["scorer_path"], "alias_of": parent,
            "rank_rows_from": index[parent] if parent else index[cell_id],
            "role_json": json.dumps(cell["role"], sort_keys=True),
            "predictions_sha256": cell["predictions_sha256"], "commitment_sha256": cell.get("commitment_sha256"),
            "per_event_file": safe_name(cell_id) + ".json", "per_event_sha256": report["per_event_sha256"][cell_id],
            "verification": record["verification"],
            "replay_reproduced_per_event_sha256": record["per_event_sha256_reproduced"],
            "events": record["rows"], "ranking_rows": record["ranking_rows"], "eligible": record["eligible"],
            "groups": record["groups"], "new_members_ranked": record["new_members_ranked"],
            "fields_verified_at_build": record.get("fields_compared", 0),
            "cross_fields_verified_at_build": record.get("cross_fields_compared", 0)})
        if parent or record["files"] is None:
            continue
        frame = pl.read_parquet(record["files"]["events"]["path"])
        need(file_sha(record["files"]["events"]["path"]) == record["files"]["events"]["sha256"], "events file changed")
        frames.append(frame.with_columns(pl.lit(index[cell_id], dtype=pl.Int16).alias("cell_index")))
        need(file_sha(record["files"]["sets"]["path"]) == record["files"]["sets"]["sha256"], "sets file changed")
        set_frames.append(pl.read_parquet(record["files"]["sets"]["path"]))
    cells = pl.DataFrame(cell_rows).with_columns(pl.col("cell_index").cast(pl.Int16),
                                                  pl.col("rank_rows_from").cast(pl.Int16))
    sets = pl.concat(set_frames).unique(subset="set_key", keep="first", maintain_order=True)
    sets = sets.sort(["event_id", "set_key"]).with_row_index("set_id").with_columns(pl.col("set_id").cast(pl.Int32))
    events = pl.concat(frames).join(sets.select("set_key", "set_id"), on="set_key", how="left")
    need(events["set_id"].null_count() == 0, "event without its set")
    events = events.select("cell_index", "event_id", "status", "new_members", "ranked", "set_id",
                           "starts", "sizes", "relevant").sort(["cell_index", "event_id"])
    outputs = {"cells.parquet": cells, "events.parquet": events, "sets.parquet": sets.drop("set_key")}
    manifest = {"kind": "r1_rank_sidecar_v1", "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "report_sha256": REPORT_SHA256, "seal_sha256": SEAL_SHA256, "topology_sha256": TOPOLOGY_SHA256,
                "ledger_sha256": report["ledger_sha256"], "spec_sha256": report["spec_sha256"],
                "forecast_ranking_sha256": topology["source"][next(p for p in topology["source"]
                                                                   if p.endswith("src/bgbench/forecast_ranking.py"))],
                "source_event_table": {"path": str(SOURCE_EVENTS), "sha256": SOURCE_EVENTS_SHA256},
                "build_script_sha256": sorted({r.get("build_script_sha256") for r in done.values()}),
                "verification_counts": {v: sum(row["verification"] == v for row in cell_rows)
                                        for v in sorted({row["verification"] for row in cell_rows})},
                "files": {}}
    for name, frame in outputs.items():
        path = final / name
        temporary = path.with_name(path.name + ".tmp")
        frame.write_parquet(temporary, compression="zstd", compression_level=19, statistics=True,
                            row_group_size=1 << 17)
        os.replace(temporary, path)
        manifest["files"][name] = {"sha256": file_sha(path), "bytes": path.stat().st_size, "rows": frame.height}
    (final / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("replay")
    p.add_argument("--lane", type=int)
    p.add_argument("--cells")
    commands.add_parser("merge")
    args = parser.parse_args()
    {"replay": replay, "merge": merge}[args.command](args)


if __name__ == "__main__":
    main()
