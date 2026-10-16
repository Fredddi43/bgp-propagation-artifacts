"""Fill redundant early AS counts only after the frozen non-graph runs finish.

Keep original inputs and a narrow reconstruction sidecar. Independent verification
must approve the resulting bridge before it is accepted by the release gate.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil
import time

import polars as pl


COLUMNS = [f"asns_{h}" for h in ("d30s", "d1m", "d5m", "d15m")]
TABLES = ("2023_leak", "2024_leak", "2025_leak", "2024", "2024_withdrawal")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def content_sha256(table: pl.DataFrame) -> str:
    return hashlib.sha256(table.sort("event_id").select(sorted(table.columns)).write_json().encode()).hexdigest()


def filled_counts(table: pl.DataFrame):
    if table["event_id"].n_unique() != table.height:
        raise ValueError("Event identifiers must be unique")
    changed = {}
    expressions = []
    for column in COLUMNS:
        if column not in table.columns:
            raise ValueError(f"Expected existing redundant column {column}")
        source = "set_" + column.removeprefix("asns_")
        invalid = table.filter(pl.col(column).is_not_null() & (
            pl.col(source).is_null() | (pl.col(column) != pl.col(source).list.len())))
        if invalid.height:
            raise ValueError(f"Existing non-null {column} disagrees with its set: {invalid['event_id'].to_list()[:5]}")
        if table.filter(pl.col("error").is_null() & pl.col(source).is_null()).height:
            raise ValueError(f"Usable event has missing {source}")
        needs_fill = pl.col("error").is_null() & pl.col(column).is_null()
        changed[column] = sorted(table.filter(needs_fill)["event_id"].to_list())
        dtype = table.schema[column] if table.schema[column] != pl.Null else pl.Int64
        expressions.append(pl.when(needs_fill).then(pl.col(source).list.len()).otherwise(pl.col(column)).cast(dtype).alias(column))
    return table.with_columns(expressions), changed


def atomic_json(path: Path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=1))
    temporary.replace(path)


def run(root: Path, wait: bool = False):
    marker = root / "nongraph-final-complete.json"
    while not marker.exists():
        if not wait:
            raise RuntimeError("All non-graph tasks must finish before input mutation")
        time.sleep(30)
    completion = json.loads(marker.read_text())
    plan = json.loads((root / "nongraph-plan.json").read_text())
    if completion["tasks"] != len(plan) or completion["plan_sha256"] != sha256(root / "nongraph-plan.json"):
        raise RuntimeError("Non-graph completion does not match the frozen plan")
    expected = [root / "nongraph-final" / str(t["year"]) / f"{t['index']:03d}_{t['kind']}" / "complete.json" for t in plan]
    if not all(p.exists() for p in expected):
        raise RuntimeError("Missing non-graph completion records")
    gate_sha = sha256(marker)
    reports = []
    for name in TABLES:
        relative = Path("eventset") / name / "events.parquet"
        source = root / "data" / relative
        backup = root / "source-before-derived-count-fill" / relative
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            original_sha = sha256(source)
            temporary = backup.with_suffix(".tmp")
            shutil.copy2(source, temporary)
            if sha256(temporary) != original_sha or sha256(source) != original_sha:
                raise RuntimeError("Source changed while preserving original input")
            temporary.replace(backup)
        before = pl.read_parquet(backup)
        after, changed = filled_counts(before)
        current = pl.read_parquet(source)
        before_content = content_sha256(before)
        after_content = content_sha256(after)
        if content_sha256(current) not in (before_content, after_content):
            raise RuntimeError(f"Concurrent or unrelated mutation in {relative}")
        sidecar_relative = Path("verification/derived-count-fill") / f"{name}.parquet"
        sidecar = root / "data" / sidecar_relative
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        before.select("event_id", *COLUMNS).write_parquet(sidecar)
        if content_sha256(current) != after_content:
            temporary = source.with_suffix(".derived-count-fill.tmp")
            after.write_parquet(temporary)
            temporary.replace(source)
        reports.append({
            "path": relative.as_posix(), "before_path": str(backup.relative_to(root)),
            "before_sha256": sha256(backup), "before_content_sha256": before_content,
            "after_sha256": sha256(source), "after_content_sha256": after_content,
            "before_counts_path": sidecar_relative.as_posix(), "before_counts_sha256": sha256(sidecar),
            "before_counts_content_sha256": content_sha256(before.select("event_id", *COLUMNS)),
            "before_columns": before.columns, "rows": before.height, "columns": COLUMNS,
            "changed_event_ids_by_column": changed,
        })
        atomic_json(root / "derived-count-fill-progress.json", {"tables": reports})
    if sha256(marker) != gate_sha:
        raise RuntimeError("Non-graph completion marker changed during migration")
    report = {"schema_version": 1, "transformation": "fill_missing_early_asn_counts_from_sets_v1",
              "source_completion_marker": marker.name, "source_completion_marker_sha256": gate_sha,
              "finished_utc": dt.datetime.now(dt.UTC).isoformat(), "tables": reports}
    atomic_json(root / "derived-count-fill-bridge.json", report)
    print(json.dumps({"finished": True, "tables": len(reports), "changed_counts": {
        row["path"]: {key: len(ids) for key, ids in row["changed_event_ids_by_column"].items()} for row in reports}}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_root", type=Path)
    parser.add_argument("--wait", action="store_true")
    args = parser.parse_args()
    run(args.run_root, args.wait)
