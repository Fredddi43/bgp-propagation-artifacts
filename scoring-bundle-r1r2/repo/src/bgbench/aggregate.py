"""Per-collector per-minute signals (ADR-0013 inputs), computed from the hourly Parquet parts."""

from __future__ import annotations

from pathlib import Path

import polars as pl


def minute_signals(day_dir: Path) -> pl.DataFrame:
    lf = pl.scan_parquet(str(day_dir / "part-*.parquet"))
    return (
        lf.with_columns(minute=pl.col("ts").dt.truncate("1m"))
        .group_by("collector", "minute")
        .agg(
            n_ann=(pl.col("elem_type") == "A").sum().cast(pl.UInt32),
            n_wd=(pl.col("elem_type") == "W").sum().cast(pl.UInt32),
            n_prefixes=pl.col("prefix").n_unique().cast(pl.UInt32),
            n_peers=pl.col("peer_ip").n_unique().cast(pl.UInt16),
            n_origins=pl.col("origin_asn").drop_nulls().n_unique().cast(pl.UInt32),
            n_paths=pl.col("as_path").drop_nulls().n_unique().cast(pl.UInt32),
        )
        .sort("collector", "minute")
        .collect()
    )
