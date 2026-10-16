"""MRT → Parquet with pybgpkit-parser (Rust). One collector-day → hourly Parquet parts."""

from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from .schema import ARROW_SCHEMA, FIELDS


def _batch_to_table(rows: list[tuple], collector: str) -> pa.Table:
    """Convert one iter_tuple_batches batch (list of tuples in FIELDS order) to an Arrow table."""
    cols = list(zip(*rows))  # 11 tuples of length n
    n = len(rows)
    origins = cols[6]
    arrays = {
        "ts": pa.array([int(t * 1_000_000) for t in cols[0]], pa.timestamp("us", tz="UTC")),
        "elem_type": pa.array(cols[1], pa.string()).dictionary_encode(),
        "peer_ip": pa.array(cols[2], pa.large_string()),
        "peer_asn": pa.array(cols[3], pa.uint32()),
        "prefix": pa.array(cols[4], pa.large_string()),
        "as_path": pa.array(cols[5], pa.large_string()),
        "origin_asn": pa.array([o[0] if o and len(o) == 1 else None for o in origins], pa.uint32()),
        "origin_asns": pa.array(origins, pa.list_(pa.uint32())),
        "next_hop": pa.array(cols[7], pa.large_string()),
        "communities": pa.array(cols[8], pa.list_(pa.large_string())),
        "aggr_asn": pa.array(cols[9], pa.uint32()),
        "aggr_ip": pa.array(cols[10], pa.large_string()),
        "collector": pa.array([collector] * n, pa.string()).dictionary_encode(),
    }
    return pa.table(arrays).cast(ARROW_SCHEMA)


def parse_file(path: str, collector: str, batch_size: int = 50_000) -> tuple[pa.Table, int]:
    """Parse one MRT file into an Arrow table, converting batch-by-batch so peak memory is one batch
    of Python objects plus the compact Arrow output. Returns (table, n_elems)."""
    from pybgpkit_parser import Parser  # imported here so worker processes load the Rust ext

    tables, n = [], 0
    for batch in Parser(path).iter_tuple_batches(FIELDS, batch_size=batch_size):
        if not batch:
            continue
        tables.append(_batch_to_table(batch, collector))
        n += len(batch)
    if n == 0:
        return ARROW_SCHEMA.empty_table(), 0
    # no combine_chunks(): >2 GB of string offsets in one chunk overflows pyarrow 32-bit offsets on big RIBs
    return pa.concat_tables(tables), n


def _parse_hour(paths: list[str], collector: str, out: str, side_dir: str | None = None, rel_path: str | None = None) -> int:
    """Worker task: parse one hour's files, concat, sort by ts, write one zstd Parquet part, and — when side_dir is
    given — the hour's side tables (issue #27) from the same in-memory table. Returns n elems."""
    tables, n = [], 0
    for p in paths:
        tbl, k = parse_file(p, collector)
        if k:
            tables.append(tbl)
        n += k
    if n:
        tbl = pa.concat_tables(tables).sort_by("ts")
        del tables
        pq.write_table(tbl, out, compression="zstd", compression_level=3, use_dictionary=True, write_statistics=True)
        if side_dir:
            _side_tables_from_arrow(tbl, side_dir, Path(out).stem.split("-")[1], rel_path)
    return n


def _side_tables_from_arrow(tbl: pa.Table, side_dir: str, hour: str, rel_path: str | None = None) -> None:
    import polars as pl

    from .prefix_events import hour_side_tables

    df = pl.from_arrow(tbl).with_columns(pl.col("collector").cast(pl.String))
    hour_side_tables(df, Path(side_dir), hour, Path(rel_path) if rel_path else None)


def _side_tables_from_parquet(part: str, side_dir: str, rel_path: str | None = None) -> None:
    """Rust-engine variant: read the finished hourly part back (one hour, RAM-speed) and compute its side tables."""
    import polars as pl

    from .prefix_events import hour_side_tables

    hour = Path(part).stem.split("-")[1]
    hour_side_tables(pl.read_parquet(part).with_columns(pl.col("collector").cast(pl.String)), Path(side_dir), hour,
                     Path(rel_path) if rel_path else None)


def _hour_of(filename: str) -> str:
    # RIS/RouteViews: updates.20240615.1355.gz / updates.20240615.1345.bz2 -> "13"
    # PCH: route-collector.<site>.pch.net-mrt-bgp-updates-2024-06-27-18-05.gz -> "18"
    import re

    m = re.search(r"-(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})\.gz$", filename)
    if m:
        return m.group(4)
    stem = filename.split(".")
    return stem[2][:2]


def _pool(procs: int):
    """Worker pool: *spawned* processes (polars/rayon thread pools must not be forked) with a small polars thread
    budget each, since `procs` workers already fill the job's cores."""
    import multiprocessing as mp

    os.environ.setdefault("POLARS_MAX_THREADS", "2")
    return ProcessPoolExecutor(max_workers=procs, mp_context=mp.get_context("spawn"))


import os
import subprocess

RUST_BIN = os.environ.get(
    "BGBENCH_PARSE_BIN",
    os.environ.get("BGBENCH_RUST_BIN") or "rust/bgbench-parse/target/release/bgbench-parse",
)


def rust_available() -> bool:
    """Rust writer is the default engine since 2026-09-05 (#25: parity on every column, 2.1× the Python engine per
    core, 5 GB instead of 17 GB peak per job). BGBENCH_PARSE_ENGINE=python forces the pybgpkit path."""
    return os.environ.get("BGBENCH_PARSE_ENGINE", "rust") == "rust" and os.path.exists(RUST_BIN)


def _rust_hour(paths: list[str], collector: str, out: Path) -> int:
    """Run the Rust writer for one hour's files; returns element count parsed from its stderr summary."""
    r = subprocess.run(
        [RUST_BIN, "--collector", collector, "--out", str(out), *paths],
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0:
        raise RuntimeError(f"bgbench-parse failed ({r.returncode}): {r.stderr[-800:]}")
    try:
        return int(r.stderr.strip().split()[0])
    except (ValueError, IndexError):
        return -1


def parse_day(
    files: list[Path], collector: str, out_dir: Path, procs: int = 8, delete_raw: bool = True,
    side_dir: Path | None = None, rel_path: Path | None = None,
) -> dict:
    """Parse all files of one collector-day into out_dir/part-HH.parquet (zstd). Returns stats.
    Engine: the Rust writer (issue #25) only when BGBENCH_PARSE_ENGINE=rust and the binary exists; else Python.
    side_dir: when given, each hour's side tables (prefix_events.hour_side_tables) are written there too (#27)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    by_hour: dict[str, list[Path]] = defaultdict(list)
    for f in files:
        by_hour[_hour_of(f.name)].append(f)
    stats = {
        "files": len(files),
        "elems": 0,
        "parts": 0,
        "per_hour": {},
        "engine": "rust" if rust_available() else "python",
    }
    if not files:                       # archive gap: nothing to parse (ingest-day then writes an empty manifest)
        return stats
    if rust_available():
        from concurrent.futures import ThreadPoolExecutor

        hours = sorted(by_hour)
        # memory-aware concurrency: the Rust writer holds a whole hour (arenas + Arrow copy ≈ 25× the gzipped input) and
        # the side-table workers explode an hour's paths; storms like rrc03 2023-02-08 (8 GB gz/day) OOM'd a 187 GB job
        # at 8 concurrent hours. Budget = job memory minus what /dev/shm already holds (raw files, transient Parquet).
        hour_gz = max(sum(p.stat().st_size for p in by_hour[h]) for h in hours)
        # ≈ 100× the gzipped hour: rrc03 2023-02-08 (8 GB gz/day, ~50 M elements/hour) OOM'd at 187 GB with 25× and at
        # 125 GB with 60× (3 concurrent hours) — the storm hours need ~25 GB each
        per_hour_mb = max(200.0, 100.0 * hour_gz / 1e6)
        budget_mb = float(os.environ.get("SLURM_MEM_PER_NODE", os.environ.get("BGBENCH_MEM_MB", "64000")))
        shm_mb = sum(p.stat().st_size for p in files) / 1e6 * 1.8       # raw + the Parquet that will replace it in RAM
        rust_workers = int(max(1, min(procs, (0.75 * budget_mb - shm_mb) // per_hour_mb)))
        side_workers = 1 if per_hour_mb > 8000 else int(max(1, min(max(1, procs // 4), rust_workers // 2)))
        stats["rust_workers"] = rust_workers; stats["side_workers"] = side_workers; stats["per_hour_mb_est"] = round(per_hour_mb)
        with ThreadPoolExecutor(max_workers=rust_workers) as ex, _pool(side_workers) as px:
            futs = {
                h: ex.submit(
                    _rust_hour,
                    [str(p) for p in sorted(by_hour[h])],
                    collector,
                    out_dir / f"part-{h}.parquet",
                )
                for h in hours
            }
            side_futs = []
            for h in hours:
                n = futs[h].result()
                stats["per_hour"][h] = n
                stats["elems"] += max(n, 0)
                stats["parts"] += 1
                if side_dir is not None and n != 0:
                    side_futs.append(px.submit(_side_tables_from_parquet, str(out_dir / f"part-{h}.parquet"), str(side_dir),
                                               str(rel_path) if rel_path else None))
                if delete_raw:
                    for p in by_hour[h]:
                        p.unlink(missing_ok=True)
            for f in side_futs:
                f.result()
        return stats
    # Python engine: one task per hour in a worker process — parse the hour's files, concat, sort, write —
    # so the main process never serialises the heavy concat/sort/write while workers idle (measured: single-
    # process parse ≈ 96k elems/s but the old main-process hourly write dropped the job to ≈ 25k/s/core).
    hours = sorted(by_hour)
    with _pool(procs) as ex:
        futs = {h: ex.submit(_parse_hour, [str(p) for p in sorted(by_hour[h])], collector,
                             str(out_dir / f"part-{h}.parquet"), str(side_dir) if side_dir is not None else None,
                             str(rel_path) if rel_path else None)
                for h in hours}
        for h in hours:
            n = futs[h].result()
            stats["per_hour"][h] = n
            stats["elems"] += n
            if n:
                stats["parts"] += 1
            if delete_raw:
                for p in by_hour[h]:
                    p.unlink(missing_ok=True)
    return stats
