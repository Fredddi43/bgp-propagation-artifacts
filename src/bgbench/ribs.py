"""RIB snapshots: parse one RIS bview / RouteViews rib per collector at a chosen instant into compact
(peer, prefix, as_path, origin) Parquet — the pre-t₀ path state ADR-0012's path-loss membership needs.
⚠️ RIS bview lands exactly at 00/08/16 UTC = beacon announcement instants; never use it for beacons."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pyarrow.parquet as pq

from . import config
from .broker import search
from .fetch import fetch_all
from .parse import parse_file


def nearest_rib_before(collector: str, at: dt.datetime):
    """Latest RIB dump with ts_start <= at (searches back up to 26 h)."""
    items = search(collector, at - dt.timedelta(hours=26), at + dt.timedelta(seconds=1), "rib")
    items = [i for i in items if i.ts_start <= at]
    return items[-1] if items else None


def ingest_rib(
    collector: str, at: dt.datetime, out_dir: Path | None = None, workers: int = 4
) -> dict:
    item = nearest_rib_before(collector, at)
    if item is None:
        return {"collector": collector, "at": at.isoformat(), "error": "no RIB found in broker"}
    out_dir = out_dir or (config.RIB_DIR / collector)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{item.ts_start:%Y-%m-%dT%H%M}.parquet"
    if out.exists():
        return {
            "collector": collector,
            "rib_ts": item.ts_start.isoformat(),
            "path": str(out),
            "skipped": True,
        }
    shm = config.shm_dir() / "ribs" / collector
    try:
        res = fetch_all([item], shm, workers=workers)
        if not res or not res[0].path:
            return {
                "collector": collector,
                "rib_ts": item.ts_start.isoformat(),
                "error": res[0].error if res else "fetch failed",
            }
        tbl, n = parse_file(str(res[0].path), collector)
    finally:
        config.release_shm(shm)
    slim = tbl.select(["ts", "peer_ip", "peer_asn", "prefix", "as_path", "origin_asn", "collector"])
    pq.write_table(slim, out, compression="zstd", compression_level=3)
    return {
        "collector": collector,
        "rib_ts": item.ts_start.isoformat(),
        "rows": n,
        "bytes_raw": res[0].size,
        "path": str(out),
    }
