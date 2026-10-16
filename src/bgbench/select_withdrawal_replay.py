"""Sprint 3 step 3/4: the withdrawal-wave replay set from the identifier-v1 candidates on n_wd (`bgbench identify --signals n_wd`).
Every candidate window is replayed (50 in 2024 at z ≥ 8, ≥ 3 collectors). Manifest: event_id, kind=withdrawal, t0 (window
start), burst_end, peak_vps, split."""
from __future__ import annotations

import polars as pl

from . import config


def run(year: int = 2024, run_tag: str = "z8_m3_c2_log_n_wd") -> dict:
    ident = config.DATA_ROOT / "identifier" / f"{year}-01-01_{year}-12-31"
    if not ident.exists():   # partial year (e.g. 2026 Jan–Aug): the identify run is named by its actual end date
        cands = sorted((config.DATA_ROOT / "identifier").glob(f"{year}-01-01_{year}-*"))
        if cands:
            ident = cands[-1]
    c = pl.read_csv(ident / run_tag / "candidates.csv",
                    try_parse_dates=True)
    c = c.with_columns(pl.col("start").cast(pl.Datetime("us", "UTC")), pl.col("end").cast(pl.Datetime("us", "UTC")))
    sel = c.with_columns(
        event_id=pl.col("start").dt.strftime("%Y%m%dT%H%M%S") + pl.lit("_wd"), kind=pl.lit("withdrawal"),
        t0=pl.col("start"), burst_end=pl.col("end"),
        split=pl.when(pl.col("start").dt.month() <= config.SPLIT_MONTH).then(pl.lit("train")).otherwise(pl.lit("test")),
        reason=pl.lit("all_candidates"), labelled=pl.lit(False),
    ).sort("t0")
    out_dir = config.DATA_ROOT / "inventory" / str(year); out_dir.mkdir(parents=True, exist_ok=True)
    sel.write_parquet(out_dir / "withdrawal_replay_selection.parquet")
    man = out_dir / "withdrawal_replay_manifest.tsv"
    sel.select("event_id", "kind", pl.col("t0").dt.strftime("%Y-%m-%dT%H:%M:%S").alias("t0"),
               pl.col("burst_end").dt.strftime("%Y-%m-%dT%H:%M:%S").alias("burst_end"), "peak_vps", "split", "reason").write_csv(man, separator="\t")
    return {"selected": sel.height, "train": int((sel["split"] == "train").sum()), "test": int((sel["split"] == "test").sum()), "manifest": str(man)}
