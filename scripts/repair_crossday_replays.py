"""Targeted legacy cross-midnight replay repair in isolated output directories.

prepare writes a collector/day array plan, prioritizing the cited graph cohorts.
worker downloads only the archive blocks intersecting those event windows.
merge requires every planned slice, then emits repaired measurements separately.
Existing release inputs and symlinked replay roots are never written.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import json
import re
from pathlib import Path

import polars as pl

from bgbench import config
from bgbench.broker import search
from bgbench.fetch import fetch_all
from bgbench.parse import parse_day
from bgbench.replay import PASS_COLLECTORS
from bgbench.replay_day import ROW_COLS, _leak_regex, load_manifest, merge_event, merge_withdrawal


def intervals_union(intervals):
    result = []
    for lo, hi in sorted(intervals):
        if result and lo <= result[-1][1]:
            result[-1][1] = max(result[-1][1], hi)
        else:
            result.append([lo, hi])
    return result


def block_intervals(intervals, collector):
    step = 300 if collector.startswith("rrc") else 900
    rounded = [(int(lo.timestamp()) // step * step,
                (int(hi.timestamp()) // step + 1) * step) for lo, hi in intervals]
    return intervals_union(rounded), step


def prepare(output: Path):
    priority = set()
    for year in (2023, 2024, 2025):
        for file in (config.DATA_ROOT / "tgn" / f"{year}_leak200" / "d30s").glob("*.pt"):
            priority.add(file.stem.split("@vp=")[0])
    events, grouped = {}, defaultdict(list)
    for year in range(2022, 2027):
        for tag in ("", "leak", "withdrawal"):
            file = config.DATA_ROOT / "inventory" / str(year) / (f"{tag}_replay_manifest.tsv" if tag else "replay_manifest.tsv")
            if not file.exists():
                continue
            manifest = load_manifest(file).unique("event_id")
            for row in manifest.iter_rows(named=True):
                if row["w_start"].date() == row["w_end"].date():
                    continue
                key = f"{tag or 'origin'}:{row['event_id']}"
                row.update(year=year, tag=tag, key=key, priority=row["event_id"] in priority, tasks=[])
                events[key] = row
                # Withdrawal prefix discovery needs its entire burst, including
                # both dates. Keep it in a single collector/event worker.
                if tag == "withdrawal":
                    grouped[("withdrawal", row["event_id"])].append(key)
                else:
                    day = row["w_start"].date()
                    while day <= row["w_end"].date():
                        grouped[("day", day.isoformat())].append(key)
                        day += dt.timedelta(days=1)
    tasks = []
    for (kind, label), keys in grouped.items():
        if kind == "day":
            start = dt.datetime.fromisoformat(label).replace(tzinfo=dt.UTC)
            end = start + dt.timedelta(days=1)
            windows = [(max(events[key]["w_start"], start), min(events[key]["w_end"], end)) for key in keys]
        else:
            windows = [(events[keys[0]]["w_start"], events[keys[0]]["w_end"])]
        for collector in PASS_COLLECTORS:
            blocks, step = block_intervals(windows, collector)
            tasks.append({"collector": collector, "label": label, "events": keys,
                          "priority": any(events[key]["priority"] for key in keys),
                          "intervals": blocks, "step": step,
                          "expected_blocks": sum((hi-lo)//step for lo, hi in blocks)})
    tasks.sort(key=lambda task: (not task["priority"], task["label"], task["collector"]))
    for index, task in enumerate(tasks):
        task["index"] = index
        for key in task["events"]:
            events[key]["tasks"].append(index)
    plan = {"events": events, "tasks": tasks}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, default=str))
    summary = {"events": len(events), "tasks": len(tasks), "blocks": sum(t["expected_blocks"] for t in tasks),
               "priority_events": sum(e["priority"] for e in events.values()),
               "priority_tasks": sum(t["priority"] for t in tasks),
               "priority_blocks": sum(t["expected_blocks"] for t in tasks if t["priority"])}
    output.with_suffix(".summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary), flush=True)


def _event(value):
    row = dict(value)
    for column in ("t0", "w_start", "w_end", "burst_end"):
        if row.get(column):
            row[column] = dt.datetime.fromisoformat(row[column])
    return row


def no_downloaded_archives_report(index, expected, items, results, missing_index, failed):
    """An indexed archive outage is terminal evidence, not a parser failure."""
    if not expected or (not missing_index and not failed):
        raise ValueError("No downloaded archives without an explained coverage gap")
    return {"task": index, "status": "archive_gaps", "expected_blocks": len(expected),
            "indexed_blocks": len(items), "fetched_blocks": 0,
            "missing_index_timestamps": sorted(missing_index), "failed": failed,
            "bytes": 0, "parse": {"files": 0, "elems": 0, "parts": 0, "engine": "not_run_no_archives"},
            "archives": [{"url": result.item.url, "transport_url": result.transport_url or result.item.url, "size": result.size, "error": result.error,
                          "ts_start": int(result.item.ts_start.timestamp()),
                          "ts_end": int(result.item.ts_end.timestamp())} for result in results]}


def worker(plan_file: Path, index: int, output: Path, procs: int, downloads: int):
    plan = json.loads(plan_file.read_text())
    task = plan["tasks"][index]
    marker = output / "tasks" / f"{index}.json"
    if marker.exists() and json.loads(marker.read_text()).get("status") == "complete":
        return
    marker.parent.mkdir(parents=True, exist_ok=True)
    items = {}
    expected = set()
    for lo, hi in task["intervals"]:
        expected.update(range(lo, hi, task["step"]))
        for item in search(task["collector"], dt.datetime.fromtimestamp(lo, dt.UTC), dt.datetime.fromtimestamp(hi, dt.UTC)):
            items[item.url] = item
    missing_index = sorted(expected - {int(item.ts_start.timestamp()) for item in items.values()})
    scratch = config.shm_dir() / "crossday-repair" / str(index)
    try:
        results = fetch_all(list(items.values()), scratch / "raw", workers=downloads)
        failed = [{"url": result.item.url, "error": result.error, "ts_start": int(result.item.ts_start.timestamp()), "ts_end": int(result.item.ts_end.timestamp())} for result in results if not result.path]
        transient = [row for row in failed if row["error"] != "404"]
        if transient:
            raise RuntimeError(f"transient archive failures: {transient[:3]}")
        paths = [result.path for result in results if result.path]
        if not paths:
            report = no_downloaded_archives_report(index, expected, items, results, missing_index, failed)
            temporary_marker = marker.with_suffix(".tmp")
            temporary_marker.write_text(json.dumps(report, indent=1))
            temporary_marker.replace(marker)
            print(json.dumps(report), flush=True)
            return
        stats = parse_day(paths, task["collector"], scratch / "parsed", procs=procs, delete_raw=True)
        parts = list((scratch / "parsed").glob("part-*.parquet"))
        if not parts:
            raise RuntimeError("no parsed archive records")
        base = pl.scan_parquet(parts).with_columns(pl.col("collector").cast(pl.String))
        definitions = [_event(plan["events"][key]) for key in task["events"]]
        announcements = base.filter((pl.col("elem_type") == "A") & pl.col("as_path").is_not_null())
        prefixes = sorted({event["prefix"] for event in definitions if event["tag"] == ""})
        patterns = sorted({_leak_regex(int(event["a"]), event["sources"]) for event in definitions if event["tag"] == "leak"})
        origins = announcements.filter(pl.col("prefix").is_in(prefixes)).select(ROW_COLS).collect(engine="streaming") if prefixes else None
        leaks = announcements.filter(pl.col("as_path").str.contains("|".join(patterns))).select(ROW_COLS).collect(engine="streaming") if patterns else None
        for key in task["events"]:
            event = _event(plan["events"][key])
            window = base.filter((pl.col("ts") >= pl.lit(event["w_start"])) & (pl.col("ts") <= pl.lit(event["w_end"])))
            if event["tag"] == "withdrawal":
                burst_end = (event.get("burst_end") or event["t0"]) + dt.timedelta(minutes=5)
                prefixes = (window.filter((pl.col("elem_type") == "W") & (pl.col("ts") >= pl.lit(event["t0"])) & (pl.col("ts") <= pl.lit(burst_end)))
                            .group_by("prefix").agg(n=pl.col("peer_ip").n_unique()).filter(pl.col("n") >= 3).select("prefix").collect()["prefix"])
                rows = window.filter(pl.col("prefix").is_in(prefixes.to_list())).select("elem_type", *ROW_COLS).collect(engine="streaming")
            else:
                subset = leaks if event["tag"] == "leak" else origins
                window = subset.filter((pl.col("ts") >= pl.lit(event["w_start"])) & (pl.col("ts") <= pl.lit(event["w_end"])))
                if event["tag"] == "leak":
                    window = window.filter(pl.col("as_path").str.contains(_leak_regex(int(event["a"]), event["sources"])))
                else:
                    window = window.filter(pl.col("prefix") == event["prefix"])
                rows = window.select(ROW_COLS)
            folder = output / "parts" / (event["tag"] or "origin") / event["event_id"]
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / f"{task['collector']}__{index}.parquet"
            temporary = target.with_suffix(".tmp")
            rows.write_parquet(temporary, compression="zstd")
            temporary.replace(target)
        report = {"task": index, "status": "complete" if not missing_index and not failed else "archive_gaps",
                  "expected_blocks": len(expected), "indexed_blocks": len(items), "fetched_blocks": len(paths),
                  "missing_index_timestamps": missing_index, "failed": failed,
                  "bytes": sum(result.size for result in results), "parse": stats,
                  "archives": [{"url": result.item.url, "transport_url": result.transport_url or result.item.url, "size": result.size, "error": result.error, "ts_start": int(result.item.ts_start.timestamp()), "ts_end": int(result.item.ts_end.timestamp())} for result in results]}
        temporary_marker = marker.with_suffix(".tmp")
        temporary_marker.write_text(json.dumps(report, indent=1))
        temporary_marker.replace(marker)
        print(json.dumps({key: value for key, value in report.items() if key not in ("archives", "parse")}), flush=True)
    finally:
        config.release_shm(scratch)


def selected_events(plan, years=None, tags=None):
    tags = {"" if tag == "origin" else tag for tag in tags} if tags else None
    return [event for event in plan["events"].values() if (not years or int(event["year"]) in years) and (tags is None or event["tag"] in tags)]


def report_path(output: Path, name: str, report_stem: str | None):
    return output / (name + ("-" + report_stem if report_stem else "") + ".json")


def archive_start(row):
    value = row.get("ts_start")
    if value is not None:
        return int(value) if isinstance(value, (int, float)) else int(dt.datetime.fromisoformat(value).timestamp())
    match = re.search(r"(?:updates|bview)\.(\d{8})\.(\d{4})", row.get("url", ""))
    if match:
        return int(dt.datetime.strptime("".join(match.groups()), "%Y%m%d%H%M").replace(tzinfo=dt.UTC).timestamp())
    return None


def event_task_coverage(event, task, report):
    """A collector-day gap excludes only event windows intersecting that block."""
    status = report.get("status", "pending")
    if status != "archive_gaps":
        return status, []
    gaps = set(report.get("missing_index_timestamps", []))
    for failure in report.get("failed", []):
        start = archive_start(failure)
        if start is None:
            return "archive_gaps", ["unresolved_failed_archive_timestamp"]
        gaps.add(start)
    if not gaps:
        return "archive_gaps", ["unspecified_archive_gap"]
    lo, hi = event["w_start"].timestamp(), event["w_end"].timestamp()
    relevant = sorted(start for start in gaps if start <= hi and start + task["step"] > lo)
    return ("archive_gaps" if relevant else "complete"), relevant


def merge(plan_file: Path, output: Path, priority_only: bool, workers: int = 8, exclude_incomplete: bool = False, years=None, tags=None, report_stem=None):
    plan = json.loads(plan_file.read_text())
    selected = [_event(value) for value in selected_events(plan, years, tags) if not priority_only or value["priority"]]
    task_ids = sorted({index for event in selected for index in event["tasks"]})
    def read_status(index):
        file = output / "tasks" / f"{index}.json"
        try:
            status = json.loads(file.read_text()) if file.exists() else {"status": "pending"}
        except json.JSONDecodeError:
            status = {"status": "pending"}  # An older worker may still be writing its marker.
        return index, status
    with ThreadPoolExecutor(max_workers=workers * 2) as pool:
        statuses = dict(pool.map(read_status, task_ids))
    def one(event):
        row = {"event_id": event["event_id"], "year": event["year"], "tag": event["tag"]}
        coverage = {index: event_task_coverage(event, plan["tasks"][index], statuses[index]) for index in event["tasks"]}
        event_statuses = [value[0] for value in coverage.values()]
        if "pending" in event_statuses:
            return {**row, "status": "pending"}
        parts = output / "parts" / (event["tag"] or "origin")
        merged = output / "events" / (event["tag"] or "origin")
        summary_file = merged / event["event_id"] / "summary.json"
        if any(status != "complete" for status in event_statuses):
            if exclude_incomplete:
                summary_file.parent.mkdir(parents=True, exist_ok=True)
                summary_file.write_text(json.dumps({"event_id": event["event_id"], "error": "incomplete_crossday_archive_coverage",
                                                   "measurement_source_task_statuses": sorted(set(event_statuses)),
                                                   "measurement_missing_archive_blocks": {str(index): gaps for index, (status, gaps) in coverage.items() if gaps}}, indent=1))
                return {**row, "status": "excluded", "reason": "incomplete_crossday_archive_coverage"}
            return {**row, "status": "archive_gaps"}
        if summary_file.exists():
            existing = json.loads(summary_file.read_text())
            if existing.get("crossday_repair_complete") and not existing.get("error"):
                return {**row, "status": "merged", "resumed": True}
        if event["tag"] == "withdrawal":
            result = merge_withdrawal(event["event_id"], event["t0"], event.get("burst_end"),
                                      parts_root_override=parts, merged_root_override=merged)
        else:
            leak = (int(event["a"]), event["sources"], event.get("upstreams") or "") if event["tag"] == "leak" else None
            result = merge_event(event["event_id"], event.get("prefix"), event.get("new_origin"), event["t0"],
                                 tag=event["tag"], leak=leak, parts_root_override=parts, merged_root_override=merged)
        result["crossday_repair_complete"] = True
        result["measurement_repair_source_tasks"] = event["tasks"]
        summary_file.write_text(json.dumps(result, indent=1, default=str))
        return {**row, "status": "excluded" if result.get("error") else "merged", "reason": result.get("error")}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(one, selected))
    report_path(output, "merge-priority" if priority_only else "merge", report_stem).write_text(json.dumps(rows, indent=1))
    print(json.dumps({"events": len(rows), "merged": sum(row["status"] == "merged" for row in rows),
                      "excluded": sum(row["status"] == "excluded" for row in rows),
                      "pending": sum(row["status"] == "pending" for row in rows)}), flush=True)


def compare(plan_file: Path, output: Path, years=None, tags=None, report_stem=None):
    """Reviewable input-change manifest before any overlay/table publication."""
    from bgbench.eventset import build_table
    plan = json.loads(plan_file.read_text())
    groups = {(int(event["year"]), event["tag"]) for event in selected_events(plan, years, tags)}
    changes = []
    for year, tag in sorted(groups):
        root = output / "events" / (tag or "origin")
        if not root.exists():
            continue
        repaired = build_table(year, tag, replay_root=root)
        if repaired.is_empty():
            continue
        destination = config.DATA_ROOT / "eventset" / (f"{year}_{tag}" if tag else str(year))
        baseline = destination / "events.before-crossday-repair.parquet"
        current = pl.read_parquet(baseline if baseline.exists() else destination / "events.parquet")
        old = {row["event_id"]: row for row in current.iter_rows(named=True)}
        for new in repaired.iter_rows(named=True):
            before = old[new["event_id"]]
            sets = {}
            for key in sorted(column for column in set(before) | set(new) if column.startswith("set_")):
                prior, after = set(before.get(key) or []), set(new.get(key) or [])
                sets[key] = {"old_n": len(prior), "new_n": len(after), "added": sorted(after-prior), "removed": sorted(prior-after)}
            changes.append({"year": year, "tag": tag, "event_id": new["event_id"], "raw_source_rebuilt": True,
                            "old_t0_obs": before.get("t0_obs"), "new_t0_obs": new.get("t0_obs"),
                            "old_error": before.get("error"), "new_error": new.get("error"),
                            "old_t90_s": before.get("t90_s"), "new_t90_s": new.get("t90_s"),
                            "old_anomalous_msgs": before.get("anomalous_msgs"), "new_anomalous_msgs": new.get("anomalous_msgs"),
                            "sets": sets})
    report_path(output, "input-changes", report_stem).write_text(json.dumps(changes, indent=1, default=str))
    print(json.dumps({"events": len(changes), "changed_onset": sum(row["old_t0_obs"] != row["new_t0_obs"] for row in changes),
                      "changed_target": sum(bool(row["sets"].get("set_final_2h", {}).get("added")) or bool(row["sets"].get("set_final_2h", {}).get("removed")) for row in changes)}), flush=True)


def patch_measurements(current: pl.DataFrame, repaired: pl.DataFrame) -> pl.DataFrame:
    # Replace measured quantities only. Preserve eligibility/classification,
    # split, catalogue labels and any annotations already attached downstream.
    exact = {"error", "observation_lag_s", "anomalous_msgs", "t90_s", "t0_obs", "trigger_lag_s",
             "sessions_carrying", "sessions_switched", "collectors_seeing", "leaked_prefixes", "wave_prefixes"}
    measured = sorted({column for column in [*current.columns, *repaired.columns] if column in exact or column.startswith(("set_", "asns_", "vp_", "measurement_"))})
    missing = [pl.lit(None, dtype=current.schema[column]).alias(column) for column in measured if column not in repaired.columns]
    repaired = repaired.with_columns(missing)
    patch = repaired.select("event_id", *measured).with_columns(__repair_found=pl.lit(True))
    combined = current.join(patch, on="event_id", how="left", suffix="__repaired", validate="1:1")
    replacements = [pl.when(pl.col("__repair_found").fill_null(False)).then(pl.col(column + "__repaired")).otherwise(pl.col(column)).alias(column)
                    for column in measured if column in current.columns]
    combined = combined.with_columns(replacements).drop("__repair_found", *[column + "__repaired" for column in measured if column in current.columns])
    # A newly introduced scalar column otherwise exists only on repaired rows
    # after the left join. Counts are redundant with sets: materialize them for
    # the complete selected population, including untouched rows.
    combined = combined.with_columns([
        pl.col(column).list.len().alias("asns_" + column[4:])
        for column in combined.columns if column.startswith("set_")
    ])
    if combined.height != current.height or combined["event_id"].n_unique() != combined.height:
        raise ValueError("repair changed the selected event population unexpectedly")
    return combined


def publish(plan_file: Path, output: Path, years=None, tags=None, report_stem=None):
    from bgbench.eventset import build_table, run
    plan = json.loads(plan_file.read_text())
    grouped_ids = {}
    for event in selected_events(plan, years, tags):
        grouped_ids.setdefault((int(event["year"]), event["tag"]), set()).add(event["event_id"])
    def publish_group(group):
        year, tag = group
        root = output / "events" / (tag or "origin")
        if not root.exists():
            return None
        repaired = build_table(year, tag, replay_root=root, event_ids=grouped_ids[group])
        if repaired.is_empty():
            return None
        destination = config.DATA_ROOT / "eventset" / (f"{year}_{tag}" if tag else str(year))
        baseline_file = destination / "events.before-crossday-repair.parquet"
        if not baseline_file.exists():
            import shutil
            shutil.copy2(destination / "events.parquet", baseline_file)
        current = pl.read_parquet(destination / "events.parquet")
        combined = patch_measurements(current, repaired)
        run(year, tag, table_override=combined)
        return {"year": year, "tag": tag, "repaired_events": repaired.height,
                "event_ids": repaired["event_id"].to_list()}
    # Each year/family writes its own directory. Keep deterministic report order
    # while rebuilding these independent tables concurrently on the batch host.
    with ThreadPoolExecutor(max_workers=5) as pool:
        reports = [report for report in pool.map(publish_group, sorted(grouped_ids)) if report is not None]
    report_path(output, "published", report_stem).write_text(json.dumps(reports, indent=1))
    print(json.dumps(reports), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "worker", "merge", "compare", "publish"])
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--task-index", type=int)
    parser.add_argument("--procs", type=int, default=4)
    parser.add_argument("--downloads", type=int, default=4)
    parser.add_argument("--priority-only", action="store_true")
    parser.add_argument("--merge-workers", type=int, default=8)
    parser.add_argument("--exclude-incomplete", action="store_true")
    parser.add_argument("--years", nargs="+", type=int)
    parser.add_argument("--tags", nargs="+")
    parser.add_argument("--report-stem")
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.plan)
    elif args.action == "worker":
        worker(args.plan, args.task_index, args.output, args.procs, args.downloads)
    elif args.action == "merge":
        merge(args.plan, args.output, args.priority_only, args.merge_workers, args.exclude_incomplete, args.years, args.tags, args.report_stem)
    elif args.action == "compare":
        compare(args.plan, args.output, args.years, args.tags, args.report_stem)
    else:
        publish(args.plan, args.output, args.years, args.tags, args.report_stem)
