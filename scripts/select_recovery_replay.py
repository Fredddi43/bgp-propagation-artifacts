"""Recovery replay set: for every replayed origin-change event whose new origin is RPKI-invalid and displaced a valid origin
(the textbook hijack), the counterpart event in the inventory that puts the previous origin back (B→A on the same prefix
within 24 h). Writes inventory/<year>/recovery_replay_selection.parquet (same columns as replay_selection.parquet, reason =
"recovery") and recovery_replay_manifest.tsv for replay-by-day under tag "recovery". usage: select_recovery_replay.py <year>"""
from __future__ import annotations

import sys

import polars as pl

from bgbench import config

year = int(sys.argv[1])
INV = config.DATA_ROOT / "inventory" / str(year)
sel = pl.read_parquet(INV / "replay_selection.parquet")
val = pl.read_parquet(config.DATA_ROOT / "eventset" / str(year) / "rpki_validity.parquet").filter((pl.col("validity") == "invalid") & (pl.col("prev_validity") == "valid"))
hij = sel.join(val.select("event_id"), on="event_id", how="semi").with_columns(
    pl.col("prev_origins").cast(pl.Utf8).str.extract(r"(\d+)", 1).cast(pl.UInt32, strict=False).alias("prev_origin")).filter(pl.col("prev_origin").is_not_null())
inv = pl.read_parquet(INV / "events_ranked.parquet").with_columns(
    pl.col("prev_origins").cast(pl.Utf8).str.extract(r"(\d+)", 1).cast(pl.UInt32, strict=False).alias("prev_origin"),
    (pl.col("first_ts").dt.strftime("%Y%m%dT%H%M%S") + "_" + pl.col("prefix").str.replace("/", "-") + "_" + pl.col("new_origin").cast(pl.Utf8)).alias("event_id"))
# counterpart: same prefix, new_origin == hijack's prev_origin, prev_origin == hijack's new_origin, 0 < gap ≤ 24 h; earliest one
cand = hij.select("prefix", pl.col("new_origin").alias("h_new"), pl.col("prev_origin").alias("h_prev"), pl.col("first_ts").alias("h_ts"), pl.col("event_id").alias("hijack_id"), pl.col("split").alias("h_split")).join(
    inv.select("prefix", "new_origin", "prev_origin", "first_ts", "event_id", "max_collectors", "max_peers", "duration_min", "labelled", "flip_back", "plen", "month", "score"), on="prefix", how="inner")
cand = cand.filter((pl.col("new_origin") == pl.col("h_prev")) & (pl.col("prev_origin") == pl.col("h_new")) & (pl.col("first_ts") > pl.col("h_ts")) & ((pl.col("first_ts") - pl.col("h_ts")).dt.total_seconds() <= 86400))
rec = cand.sort("first_ts").unique("hijack_id", keep="first")
vis = pl.when(pl.col("max_collectors") <= 1).then(pl.lit("1")).when(pl.col("max_collectors") <= 4).then(pl.lit("2-4")).when(pl.col("max_collectors") <= 7).then(pl.lit("5-7")).otherwise(pl.lit("8-10"))
dur = pl.when(pl.col("duration_min") <= 5).then(pl.lit("5")).when(pl.col("duration_min") <= 15).then(pl.lit("10-15")).when(pl.col("duration_min") <= 60).then(pl.lit("20-60")).otherwise(pl.lit(">60"))
out = rec.select("event_id", "prefix", "new_origin", "prev_origin", "first_ts", "max_collectors", "max_peers", "duration_min", "labelled", "flip_back", "plen", "month", "score", "hijack_id",
                 pl.col("h_split").alias("split"), (pl.col("first_ts") - pl.col("h_ts")).dt.total_seconds().alias("gap_s")).with_columns(
    reason=pl.lit("recovery"), vis_bucket=vis, dur_bucket=dur)
out.write_parquet(INV / "recovery_replay_selection.parquet")
out.select("event_id", "prefix", "new_origin", pl.col("first_ts").dt.replace_time_zone(None).dt.strftime("%Y-%m-%dT%H:%M:%S").alias("t0"), "split", "reason").write_csv(INV / "recovery_replay_manifest.tsv", separator="\t")
print({"year": year, "hijacks_invalid_displacing_valid": hij.height, "recoveries_found": out.height, "gap_s_p50": float(out["gap_s"].median()) if out.height else None,
       "already_replayed": out.join(sel.select("event_id"), on="event_id", how="semi").height, "train": int((out["split"] == "train").sum()), "test": int((out["split"] == "test").sum())})
