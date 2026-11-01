"""ADR-0017: choose the replay set from the ranked inventory."""
from __future__ import annotations

import polars as pl

from . import config

VIS = [("2-4", 2, 4), ("5-7", 5, 7), ("8-10", 8, 99)]
DUR = [("5", 0, 5), ("10-15", 6, 15), (">15", 16, 10**9)]


def select(year: int, per_cell: int = 110, label_peers: int = 10, seed: int = 20240904) -> pl.DataFrame:
    ev = pl.read_parquet(config.DATA_ROOT / "inventory" / str(year) / "events_ranked.parquet")
    ev = ev.with_columns(
        vis_bucket=pl.when(pl.col("max_collectors") <= 4).then(pl.lit("2-4")).when(pl.col("max_collectors") <= 7).then(pl.lit("5-7")).otherwise(pl.lit("8-10")),
        dur_bucket=pl.when(pl.col("duration_min") <= 5).then(pl.lit("5")).when(pl.col("duration_min") <= 15).then(pl.lit("10-15")).otherwise(pl.lit(">15")),
        split=pl.when(pl.col("first_ts").dt.month() <= config.SPLIT_MONTH).then(pl.lit("train")).otherwise(pl.lit("test")),
        event_id=pl.concat_str([pl.col("first_ts").dt.strftime("%Y%m%dT%H%M%S"), pl.lit("_"), pl.col("prefix").str.replace_all("[/:]", "-"), pl.lit("_"), pl.col("new_origin").cast(pl.String)]),
    )
    strat = (ev.with_columns(r=pl.int_range(pl.len()).shuffle(seed=seed).over("vis_bucket", "dur_bucket", "flip_back"))
               .filter(pl.col("r") < per_cell).drop("r").with_columns(reason=pl.lit("stratified")))
    lab = (ev.filter(pl.col("labelled") & (pl.col("lab_peers") >= label_peers))
             .with_columns(reason=pl.lit("labelled")))
    sel = pl.concat([strat, lab], how="diagonal_relaxed").unique(["prefix", "new_origin", "first_ts"], keep="first")
    return sel.sort("first_ts")


def run(year: int = 2024, per_cell: int = 110, label_peers: int = 10) -> dict:
    sel = select(year, per_cell, label_peers)
    out = config.DATA_ROOT / "inventory" / str(year) / "replay_selection.parquet"
    sel.write_parquet(out)
    cells = sel.filter(pl.col("reason") == "stratified").group_by("vis_bucket", "dur_bucket", "flip_back").len().sort("vis_bucket", "dur_bucket", "flip_back")
    return {"selected": sel.height, "stratified": int((sel["reason"] == "stratified").sum()), "labelled": int((sel["reason"] == "labelled").sum()),
            "train": int((sel["split"] == "train").sum()), "test": int((sel["split"] == "test").sum()),
            "cells": cells.to_dicts(), "out": str(out)}
