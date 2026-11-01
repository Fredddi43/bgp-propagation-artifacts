#!/usr/bin/env python3
"""Recompute the R1 ranking metrics from the rank sidecar and compare them with the released per-event files.

The sidecar (``cells.parquet``, ``events.parquet``, ``sets.parquet``; see its README) holds, for every
retained R1 cell and every event it scored, the evaluator's tie groups that contain new members: start
position, size and number of new members of each group, plus the number of ranked candidates, the
number of new members, the ranking status and the event's target and input-seen AS sets.

For each (cell, event) the checker rebuilds the evaluator's ranking up to the order inside tie groups,
which the metric does not depend on (``bgbench.forecast_ranking``: every metric is the expectation over
random orders within tie groups), and recomputes the metrics with the released evaluator:

  ``entry`` (default)  calls ``event_ranking_metrics`` itself, unchanged, on a synthetic ranking with the
                       same tie structure: candidates 1..ranked, one score per group, the first r slots of
                       a group with r new members are new members, the unranked new members are extra
                       target ASes outside the candidates.
  ``groups``           calls the evaluator's ``expected_average_precision`` / ``expected_hits_at`` on the
                       group sizes directly (faster; same arithmetic).

Every ranking field present in a released row (average_precision, precision_at, recall_at, coverage_ceiling,
new_members, new_members_ranked, ranked, eligible, ranking_status, metric_version) must equal the recomputed
value exactly. Every per-event file is also hashed against the digest in the released R1 report, and every
sidecar row's new-member count against its target and input-seen sets. Cells the sidecar lists as not built
(their committed forecast is no longer on disk) are reported by name as gaps, not compared.

  python -I -B scripts/r1_rank_sidecar_check.py --sidecar DIR --per-event DIR --report report.json \
      [--mode entry|groups] [--workers N] [--src DIR_WITH_bgbench] [--out result.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import resource
import sys
import time
from multiprocessing import get_context
from pathlib import Path

FORECAST_RANKING_SHA256 = "4cea491ad7665b3ca57c4b07b2376b41643452dbe44734f7781b49540d840c97"  # R1 source manifest
FIELDS = {"average_precision": "average_precision", "precision_at": "precision_at", "recall_at": "recall_at",
          "coverage_ceiling": "coverage_ceiling", "new_members": "new_members",
          "new_members_ranked": "new_members_ranked", "ranked": "ranked", "eligible": "eligible",
          "ranking_status": "status", "metric_version": "metric_version"}
ROOT = Path(__file__).resolve().parents[1]
_STATE = {}


def file_sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_ranking(src=None):
    sys.path.insert(0, str(Path(src) if src else ROOT / "src"))
    from bgbench import forecast_ranking as fr
    return fr


def init(sidecar, per_event, mode, src=None):
    import numpy as np
    import polars as pl
    _STATE.update(np=np, pl=pl, fr=load_ranking(src), sidecar=Path(sidecar), per_event=Path(per_event), mode=mode)


def expand(np, ranked, starts, sizes, relevant):
    """Group sizes and new-member counts over the whole ranking (r = 0 filler groups between)."""
    full_sizes, full_relevant, position = [], [], 0
    for s, n, r in zip(starts, sizes, relevant):
        if not (s >= position and 1 <= r <= n):
            raise ValueError("invalid sidecar group")
        if s > position:
            full_sizes.append(s - position)
            full_relevant.append(0)
        full_sizes.append(n)
        full_relevant.append(r)
        position = s + n
    if position > ranked:
        raise ValueError("sidecar groups beyond the ranking")
    if ranked > position:
        full_sizes.append(ranked - position)
        full_relevant.append(0)
    return np.asarray(full_sizes, dtype=np.int64), np.asarray(full_relevant, dtype=np.int64)


def recompute(status, total, ranked, starts, sizes, relevant):
    np, fr = _STATE["np"], _STATE["fr"]
    full_sizes, full_relevant = expand(np, ranked, starts, sizes, relevant)
    ranked_new = int(full_relevant.sum())
    if ranked_new > total:
        raise ValueError("more ranked new members than new members")
    if _STATE["mode"] == "entry":
        unranked = np.arange(ranked + 1, ranked + 1 + total - ranked_new, dtype=np.int64)
        if status in fr.ABSTENTION_STATUSES:
            if ranked:
                raise ValueError("abstention with a ranking")
            return fr.event_ranking_metrics([], [], unranked.tolist(), [], status=status)
        group_of_slot = np.repeat(np.arange(len(full_sizes), dtype=np.int64), full_sizes)
        scores = -group_of_slot.astype(np.float64)  # one score per group, descending in rank order
        firsts = np.cumsum(full_sizes) - full_sizes
        new_slots = np.concatenate([np.arange(f, f + r, dtype=np.int64) for f, r in zip(firsts, full_relevant) if r]
                                   or [np.zeros(0, np.int64)])
        target = np.concatenate([new_slots + 1, unranked])
        return fr.event_ranking_metrics(np.arange(1, ranked + 1, dtype=np.int64), scores, target, [], status=status)
    # mode "groups": the evaluator's metric functions on the group sizes
    result = {"status": status, "new_members": total, "ranked": ranked, "new_members_ranked": ranked_new,
              "eligible": total > 0, "coverage_ceiling": float(full_relevant.sum() / total) if total else None,
              "metric_version": fr.METRIC_VERSION}
    if not total:
        result.update(average_precision=None, precision_at={str(b): None for b in fr.BUDGETS},
                      recall_at={str(b): None for b in fr.BUDGETS})
        return result
    result["average_precision"] = fr.expected_average_precision(full_sizes, full_relevant, total)
    hits = {b: fr.expected_hits_at(full_sizes, full_relevant, b) for b in fr.BUDGETS}
    result["precision_at"] = {str(b): hits[b] / b for b in hits}
    result["recall_at"] = {str(b): hits[b] / total for b in hits}
    return result


def check_cell(job):
    """One cell: its released rows against the sidecar rows of the cell whose ranking it carries."""
    pl = _STATE["pl"]
    started = time.time()
    raw = (_STATE["per_event"] / job["per_event_file"]).read_bytes()
    rows = json.loads(raw)
    ranking_rows = [r for r in rows if any(k in r for k in FIELDS)]
    out = {"cell_id": job["cell_id"], "rows": len(rows), "ranking_rows": len(ranking_rows), "fields": 0,
           "mismatches": [], "mismatch_count": 0,
           "file_digest_ok": None if job["skip_digest"] else hashlib.sha256(raw).hexdigest() == job["per_event_sha256"]}
    del raw
    if job["ranking_rows"] != len(ranking_rows) or (job["events"] is not None and job["events"] != len(rows)):
        out["mismatches"].append({"cell": "row counts differ from cells.parquet"})
        out["mismatch_count"] += 1
    out["eligible"] = sum(r.get("eligible") is True for r in ranking_rows)
    out["gap"] = bool(ranking_rows) and str(job.get("verification") or "").startswith("not_built")
    if not ranking_rows or out["gap"]:  # no ranking metric, or a named gap (committed forecast not on disk)
        out["seconds"] = time.time() - started
        return out
    side = (pl.scan_parquet(_STATE["sidecar"] / "events.parquet")
            .filter(pl.col("cell_index") == job["rank_rows_from"]).collect())
    by_event = {}
    for event_id, status, total, ranked, starts, sizes, relevant in side.select(
            "event_id", "status", "new_members", "ranked", "starts", "sizes", "relevant").iter_rows():
        by_event[event_id] = (status, total, ranked, starts, sizes, relevant)
    del side
    if set(by_event) != {r["event_id"] for r in ranking_rows}:
        out["mismatches"].append({"cell": "sidecar events differ from the released rows"})
        out["mismatch_count"] += 1
        return out
    for row in ranking_rows:
        status, total, ranked, starts, sizes, relevant = by_event[row["event_id"]]
        try:
            result = recompute(status, total, ranked, starts, sizes, relevant)
        except ValueError as error:
            out["mismatch_count"] += 1
            if len(out["mismatches"]) < 20:
                out["mismatches"].append({"event_id": row["event_id"], "error": str(error)})
            continue
        for field, key in FIELDS.items():
            if field not in row:
                continue
            out["fields"] += 1
            if row[field] != result[key] or type(row[field]) is not type(result[key]) and not (
                    isinstance(row[field], float) and isinstance(result[key], float)):
                out["mismatch_count"] += 1
                if len(out["mismatches"]) < 20:
                    out["mismatches"].append({"event_id": row["event_id"], "field": field,
                                              "released": row[field], "recomputed": result[key]})
    out["seconds"] = time.time() - started
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sidecar", required=True, help="directory with cells/events/sets.parquet and MANIFEST.json")
    parser.add_argument("--per-event", required=True, help="released R1 per_event directory")
    parser.add_argument("--report", required=True, help="released R1 report.json (per_event_sha256)")
    parser.add_argument("--mode", choices=("entry", "groups"), default="entry")
    parser.add_argument("--workers", type=int, default=max(1, min(8, (os.cpu_count() or 2) // 2)))
    parser.add_argument("--skip-file-digests", action="store_true", help="do not re-hash the per-event files")
    parser.add_argument("--src", help="directory holding bgbench/ (default: this repository's src/)")
    parser.add_argument("--out", help="write the result JSON here")
    args = parser.parse_args()
    started = time.time()
    import numpy as np  # noqa: F401
    import polars as pl
    sidecar, per_event = Path(args.sidecar), Path(args.per_event)
    problems = []
    ranking_source = Path(args.src or ROOT / "src") / "bgbench" / "forecast_ranking.py"
    if file_sha(ranking_source) != FORECAST_RANKING_SHA256:
        problems.append("src/bgbench/forecast_ranking.py differs from the R1 evaluator's pinned bytes")
    manifest = json.loads((sidecar / "MANIFEST.json").read_text())
    for name, entry in manifest["files"].items():
        if file_sha(sidecar / name) != entry["sha256"]:
            problems.append(f"{name} differs from the sidecar MANIFEST")
    report_raw = Path(args.report).read_bytes()
    report = json.loads(report_raw)
    digests = report["per_event_sha256"]
    cells = pl.read_parquet(sidecar / "cells.parquet")
    if set(cells["cell_id"]) != set(digests):
        problems.append("sidecar cells differ from the report's per-event files")
    jobs = cells.to_dicts()
    for job in jobs:
        if job["per_event_sha256"] != digests.get(job["cell_id"]):
            problems.append(f"{job['cell_id']}: sidecar names another per-event digest than the report")
    # R = |target - input_seen| of each row's set, and the set belongs to the row's event (vectorised).
    sets = pl.scan_parquet(sidecar / "sets.parquet").select(
        "set_id", pl.col("event_id").alias("set_event_id"),
        pl.col("target_asns").list.set_difference("input_seen_asns").list.len().alias("set_new_members"))
    set_check = (pl.scan_parquet(sidecar / "events.parquet").select("cell_index", "event_id", "new_members", "set_id")
                 .join(sets, on="set_id", how="left")
                 .select(pl.len().alias("rows"),
                         ((pl.col("set_new_members") != pl.col("new_members")).fill_null(True)
                          | (pl.col("set_event_id") != pl.col("event_id")).fill_null(True)).sum().alias("bad"))
                 .collect().row(0, named=True))
    for job in jobs:
        job["skip_digest"] = args.skip_file_digests
    # Spawned workers: polars must not be used across fork (its thread pool deadlocks in forked children).
    with get_context("spawn").Pool(args.workers, initializer=init, initargs=(sidecar, per_event, args.mode, args.src)) as pool:
        order = sorted(jobs, key=lambda j: -j["ranking_rows"])  # largest cells first for balance
        results = list(pool.imap_unordered(check_cell, order, chunksize=1))
    file_digest_mismatches = sorted(r["cell_id"] for r in results if r["file_digest_ok"] is False)
    checked = [r for r in results if r["ranking_rows"] and not r["gap"]]
    gaps = [r for r in results if r["gap"]]
    totals = {"cells": len(results), "ranking_cells_checked": len(checked),
              "ranking_rows_checked": sum(r["ranking_rows"] for r in checked),
              "eligible_rows_checked": sum(r["eligible"] for r in checked),
              "gap_cells": len(gaps), "gap_ranking_rows": sum(r["ranking_rows"] for r in gaps),
              "gap_eligible_rows": sum(r["eligible"] for r in gaps),
              "cells_without_ranking_metrics": sum(r["ranking_rows"] == 0 for r in results),
              "rows": sum(r["rows"] for r in results), "fields_compared": sum(r["fields"] for r in results),
              "mismatches": sum(r["mismatch_count"] for r in results),
              "sidecar_rows_checked_against_sets": set_check["rows"],
              "new_member_set_mismatches": set_check["bad"],
              "per_event_files_hashed": sum(r["file_digest_ok"] is not None for r in results),
              "per_event_file_digest_mismatches": len(file_digest_mismatches),
              "alias_cells": int(cells["alias_of"].is_not_null().sum())}
    self_usage = resource.getrusage(resource.RUSAGE_SELF)
    child_usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    summary = {"kind": "r1_rank_sidecar_check_v1", "mode": args.mode, "workers": args.workers,
               "passed": not problems and not file_digest_mismatches and totals["mismatches"] == 0
               and totals["new_member_set_mismatches"] == 0,
               "complete": not gaps, "gap_cells": sorted(r["cell_id"] for r in gaps),
               "totals": totals, "problems": problems, "file_digest_mismatches": file_digest_mismatches[:20],
               "mismatching_cells": [{k: r[k] for k in ("cell_id", "mismatch_count", "mismatches")}
                                     for r in results if r["mismatch_count"]][:20],
               "report_sha256": hashlib.sha256(report_raw).hexdigest(),
               "sidecar_manifest": manifest["files"],
               "wall_seconds": round(time.time() - started, 1),
               "cpu_seconds": round(self_usage.ru_utime + self_usage.ru_stime + child_usage.ru_utime
                                    + child_usage.ru_stime, 1),
               "peak_rss_parent_bytes": self_usage.ru_maxrss * 1024,
               "peak_rss_largest_worker_bytes": child_usage.ru_maxrss * 1024,
               "python": sys.version.split()[0], "numpy": np.__version__, "polars": pl.__version__}
    text = json.dumps(summary, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(text + "\n")
    print(text)
    raise SystemExit(0 if summary["passed"] else 1)


if __name__ == "__main__":
    main()
