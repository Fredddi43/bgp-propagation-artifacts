"""Re-merge retained recovery announcements in parallel, then rebuild event tables.

Run with BGBENCH_DATA_ROOT pointing to an isolated copy of inventory/eventset and
an output events_replay_recovery directory. The parts directory may be read-only.
POLARS_MAX_THREADS=2 python scripts/rebuild_recovery.py 2025 --workers 8
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime as dt
import json

import polars as pl

from bgbench import config
from bgbench.eventset import run
from bgbench.replay_day import merge_event, roots


def rebuild(year: int, workers: int = 8) -> dict:
    selection = pl.read_parquet(config.DATA_ROOT / "inventory" / str(year) / "recovery_replay_selection.parquet")
    events = selection.select("event_id", "prefix", "new_origin", "prev_origin", "first_ts").unique()
    if events["event_id"].n_unique() != events.height:
        raise ValueError("conflicting recovery event definition")
    events = events.sort("first_ts")
    parts, _ = roots("recovery")
    coverage = []
    for event in events.iter_rows(named=True):
        t0 = event["first_ts"]
        expected = sorted({(t0 - dt.timedelta(hours=1)).date().isoformat(),
                           (t0 + dt.timedelta(hours=3)).date().isoformat()})
        files = list((parts / event["event_id"]).glob("*.parquet"))
        legacy = any("__" not in f.stem for f in files)
        if len(expected) > 1 and legacy:
            coverage.append({"event_id": event["event_id"], "expected_dates": expected,
                             "issue": "legacy collector-only files cannot establish multi-day coverage"})
    output = config.DATA_ROOT / "eventset" / f"{year}_recovery"
    output.mkdir(parents=True, exist_ok=True)
    (output / "legacy_multiday_coverage.json").write_text(json.dumps(coverage, indent=2))

    def one(e):
        return merge_event(e["event_id"], e["prefix"], int(e["new_origin"]), e["first_ts"],
                           tag="recovery", recovery_prev_origin=int(e["prev_origin"]))

    errors = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(one, e): e["event_id"] for e in events.iter_rows(named=True)}
        for index, future in enumerate(as_completed(futures), 1):
            try:
                result = future.result()
                if result.get("error"):
                    errors.append({"event_id": futures[future], "error": result["error"]})
            except Exception as exc:
                raise RuntimeError(f"recovery merge failed: {futures[future]}") from exc
            if index % 250 == 0:
                print(json.dumps({"year": year, "merged": index, "total": events.height, "errors": len(errors)}), flush=True)
    (output / "rebuild_errors.json").write_text(json.dumps(errors, indent=2))
    result = run(year, "recovery")
    result["legacy_multiday_coverage_events"] = len(coverage)
    print(json.dumps(result, default=str), flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("year", type=int)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    rebuild(args.year, args.workers)
