"""Build first-return-path recovery measurements from daily origin-change tables.

This deliberately measures paths on recorded bad-to-good transitions, conditional
on within-day announcement history. It does not reconstruct withdrawal/RIB state
or claim complete Internet recovery. Every expected collector-day must exist.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime as dt
import json
from pathlib import Path

import polars as pl

from bgbench import config
from bgbench.eventset import run
from bgbench.recovery import write_first_return_measurement

COLLECTORS = ["rrc25", "rrc00", "rrc12", "rrc01", "route-views3", "rrc03", "route-views2", "rrc20", "rrc15", "route-views.linx"]
SCHEMA = {"ts": pl.Datetime("us", "UTC"), "collector": pl.String,
          "peer_ip": pl.String, "peer_asn": pl.UInt32, "prefix": pl.String,
          "prev_origin": pl.UInt32, "new_origin": pl.UInt32, "as_path": pl.String}


def rebuild(year: int, source: Path, workers: int):
    selection = pl.read_parquet(config.DATA_ROOT / "inventory" / str(year) / "recovery_replay_selection.parquet")
    recoveries = selection.select("event_id", "prefix", "new_origin", "prev_origin", "first_ts").unique().with_columns(kind=pl.lit("recovery"))
    origins = pl.read_parquet(config.DATA_ROOT / "inventory" / str(year) / "replay_selection.parquet")
    pairs = selection.select(pl.col("hijack_id").alias("event_id"), "prefix",
                             pl.col("prev_origin").alias("new_origin"), pl.col("new_origin").alias("prev_origin")).unique()
    hijacks = pairs.join(origins.select("event_id", "first_ts"), on="event_id", how="inner", validate="m:1").with_columns(kind=pl.lit("hijack"))
    if hijacks.height != pairs.height:
        raise ValueError("selected hijack absent from origin selection")
    events = pl.concat([recoveries, hijacks.select(recoveries.columns)], how="vertical_relaxed").sort("first_ts")
    # An event may play different roles in different links: use an internal key,
    # while retaining ordinary event_id in each separately written payload table.
    events = events.with_columns(measurement_id=pl.col("kind") + pl.lit(":") + pl.col("event_id"))
    if events["measurement_id"].n_unique() != events.height:
        raise ValueError("conflicting transition event definition")
    daily = {}
    coverage = {}
    for event in events.iter_rows(named=True):
        first = event["first_ts"]
        last = first + dt.timedelta(hours=3)
        days = sorted({first.date(), last.date()})
        coverage[event["measurement_id"]] = {"recovery_expected_source_files": len(days) * len(COLLECTORS),
                                      "recovery_missing_source_files": 0,
                                      "recovery_source_window_crosses_midnight": len(days) > 1}
        for day in days:
            daily.setdefault(day.isoformat(), []).append(event)
    rows = {}
    source_manifest = []

    def read_day(collector, day, selected):
        file = source / collector / f"{day}.origin_changes.parquet"
        if not file.exists():
            return None, {"collector": collector, "day": day, "exists": False,
                          "events": [event["measurement_id"] for event in selected]}
        definitions = pl.DataFrame(selected).with_columns(pl.col("new_origin", "prev_origin").cast(pl.UInt32))
        data = (pl.scan_parquet(file).filter(pl.col("prefix").is_in(definitions["prefix"].unique().to_list()))
                .with_columns(pl.col("collector").cast(pl.String)).collect())
        matched = data.join(definitions, on=["prefix", "new_origin", "prev_origin"], how="inner")
        matched = matched.filter((pl.col("ts") >= pl.col("first_ts"))
                                 & (pl.col("ts") <= pl.col("first_ts") + pl.duration(hours=3)))
        return matched, {"collector": collector, "day": day, "exists": True,
                         "bytes": file.stat().st_size, "matched_transitions": matched.height}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(read_day, collector, day, selected)
                   for day, selected in sorted(daily.items()) for collector in COLLECTORS]
        for index, future in enumerate(as_completed(futures), 1):
            matched, meta = future.result()
            source_manifest.append(meta)
            if matched is None:
                for event_id in meta["events"]:
                    coverage[event_id]["recovery_missing_source_files"] += 1
            elif matched.height:
                for key, subset in matched.partition_by("measurement_id", as_dict=True).items():
                    rows.setdefault(key[0], []).append(subset.select(list(SCHEMA)))
            if index % 250 == 0:
                print(json.dumps({"year": year, "source_files_scanned": index, "total": len(futures)}), flush=True)
    summaries = []
    def write_one(event):
        parts = rows.get(event["measurement_id"], [])
        changes = pl.concat(parts, how="vertical_relaxed") if parts else pl.DataFrame(schema=SCHEMA)
        root = config.DATA_ROOT / f"events_replay_{event['kind']}_first_transition"
        summary = write_first_return_measurement(event, changes, root / event["event_id"], coverage[event["measurement_id"]])
        summary["measurement_id"] = event["measurement_id"]
        return summary
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for index, summary in enumerate(pool.map(write_one, events.iter_rows(named=True)), 1):
            summaries.append({"measurement_id": summary["measurement_id"], "event_id": summary["event_id"], "error": summary.get("error"), **coverage[summary["measurement_id"]]})
            if index % 500 == 0:
                print(json.dumps({"year": year, "payloads_written": index, "total": events.height}), flush=True)
    for kind in ("recovery", "hijack"):
        output = config.DATA_ROOT / "eventset" / f"{year}_{kind}_first_transition"
        output.mkdir(parents=True, exist_ok=True)
        (output / "transition_source_manifest.json").write_text(json.dumps(source_manifest, indent=1))
        (output / "transition_coverage.json").write_text(json.dumps([s for s in summaries if s["measurement_id"].startswith(kind + ":")], indent=1))
        root = config.DATA_ROOT / f"events_replay_{kind}_first_transition"
        result = run(year, "recovery" if kind == "recovery" else "", replay_root=root, output_dir=output)
        print(json.dumps({"kind": kind, **result}, default=str), flush=True)



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("year", type=int)
    parser.add_argument("--source", type=Path, required=True, help="original prefix_events directory")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    rebuild(args.year, args.source, args.workers)
