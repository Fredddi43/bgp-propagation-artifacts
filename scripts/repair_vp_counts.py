"""Recompute retained VP horizon counts from timestamped replay observations.

AS sets have already been aligned by repair_extent_counts.py. Only rows whose
observation and identifier origins differ need this migration. Source replay
files remain untouched; table replacement is atomic.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import json
import os
from pathlib import Path

import polars as pl

from bgbench import config
from bgbench.extent import TARGETS_S


def counts(item: tuple[Path, dict]) -> dict:
    root, row = item
    folder = root / row["event_id"]
    if (folder / "vp_first.parquet").exists():
        vp = pl.read_parquet(folder / "vp_first.parquet")
    elif (folder / "vp_changes.parquet").exists():
        vp = pl.read_parquet(folder / "vp_changes.parquet", columns=["collector", "peer_ip", "change_ts"])
        vp = vp.group_by("collector", "peer_ip").agg(first=pl.col("change_ts").min())
    else:
        vp = pl.read_parquet(folder / "anomalous.parquet", columns=["collector", "peer_ip", "ts"])
        vp = vp.group_by("collector", "peer_ip").agg(first=pl.col("ts").min())
    t0 = dt.datetime.fromisoformat(row["t0_obs"])
    return {"event_id": row["event_id"], **{
        "vp_" + name: vp.filter(pl.col("first") <= t0 + dt.timedelta(seconds=seconds)).height
        for name, seconds in TARGETS_S.items()}}


def main() -> None:
    report = []
    for path in sorted((config.DATA_ROOT / "eventset").glob("*/events.parquet")):
        if "recovery" in path.parent.name:
            continue
        tag = path.parent.name.partition("_")[2]
        root = config.DATA_ROOT / ("events_replay" + ("_" + tag if tag else ""))
        table = pl.read_parquet(path)
        needed = table.filter(pl.col("error").is_null() & (pl.col("observation_lag_s") != 0)).drop_nulls("t0_obs")
        with ThreadPoolExecutor(max_workers=12) as pool:
            fixes = list(pool.map(counts, ((root, row) for row in needed.select("event_id", "t0_obs").to_dicts())))
        changed = {}
        if fixes:
            patch = pl.DataFrame(fixes)
            joined = table.join(patch, on="event_id", how="left", suffix="_fixed", validate="1:1")
            for name in TARGETS_S:
                column = "vp_" + name
                changed[column] = joined.filter(pl.col(column + "_fixed").is_not_null() & (pl.col(column) != pl.col(column + "_fixed"))).height
                joined = joined.with_columns(pl.coalesce(column + "_fixed", column).alias(column)).drop(column + "_fixed")
            temp = path.with_suffix(".tmp.parquet")
            joined.write_parquet(temp, compression="zstd")
            os.replace(temp, path)
            summary_path = path.parent / "summary.json"
            if summary_path.exists():
                summary = json.loads(summary_path.read_text())
                ok = joined.filter(pl.col("error").is_null()).drop_nulls("vp_final_2h")
                if ok.height:
                    summary["vp_final_p50_p90"] = [float(ok["vp_final_2h"].quantile(q)) for q in (0.5, 0.9)]
                summary["vp_count_definition"] = "sessions_first_observed_by_onset_plus_horizon"
                summary_path.write_text(json.dumps(summary, indent=1) + "\n")
        record = {"table": path.parent.name, "rows_recomputed": len(fixes), "changed": changed}
        report.append(record)
        print(json.dumps(record), flush=True)
    (config.WORK_ROOT.parent / "vp-migration.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
