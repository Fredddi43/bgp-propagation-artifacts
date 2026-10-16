"""Test-split persistence floor J(set_Δ, set_2h) by selection reason and RPKI validity of the new origin, for one year.
Used to compare the label-free RPKI-invalid stratum (reason rpki_invalid_sample) with the stratified sample and the
Radar/GRIP-labelled stratum, e.g. 2022 vs the like-for-like 2024 control (docs/results/2026-09-15-extension-2022-2026.md).
usage: floor_by_stratum.py <year> [--split test|train|all]  → prints a markdown table"""
from __future__ import annotations

import argparse

import polars as pl

from bgbench import config

ap = argparse.ArgumentParser()
ap.add_argument("year", type=int)
ap.add_argument("--split", default="test")
ap.add_argument("--later-valid", action="store_true", help="split invalid events by whether the origin becomes ROA-valid within 7/30 days "
                "(eventset/<year>/later_validity.parquet from later_validity.py)")
a = ap.parse_args()
E = config.DATA_ROOT / "eventset" / str(a.year)

ev = pl.read_parquet(E / "events.parquet").filter(pl.col("error").is_null())
if a.split != "all":
    ev = ev.filter(pl.col("split") == a.split)
ev = ev.join(pl.read_parquet(E / "rpki_validity.parquet").select("event_id", "validity"), on="event_id", how="left")
ev = ev.with_columns(pl.when(pl.col("reason") == "rpki_invalid_sample").then(pl.lit("invalid sample"))
                     .when(pl.col("reason") == "stratified").then(pl.lit("stratified")).otherwise(pl.lit("labelled")).alias("stratum"))
if a.later_valid:
    lv = pl.read_parquet(E / "later_validity.parquet").select("event_id", "later_valid")
    ev = ev.join(lv, on="event_id", how="left").with_columns(
        pl.when(pl.col("validity") != "invalid").then(pl.col("validity"))
        .when(pl.col("later_valid") == True).then(pl.lit("invalid, ROA-valid within 30 d"))
        .otherwise(pl.lit("invalid, stays invalid")).alias("validity"))


def jac(a: str, b: str) -> pl.Expr:
    inter = pl.col(a).list.set_intersection(pl.col(b)).list.len()
    union = pl.col(a).list.set_union(pl.col(b)).list.len().clip(1)
    return (inter / union).alias(a.replace("set_", "J_"))


ev = ev.with_columns(*[jac(c, "set_final_2h") for c in ("set_d30s", "set_d1m", "set_d5m", "set_d15m")],
                     pl.col("set_final_2h").list.len().alias("extent"))
tab = (ev.group_by("stratum", "validity").agg(n=pl.len(), J30s=pl.col("J_d30s").mean(), J1m=pl.col("J_d1m").mean(),
                                                J5m=pl.col("J_d5m").mean(), J15m=pl.col("J_d15m").mean(), extent_p50=pl.col("extent").median())
       .sort("stratum", "validity"))
print(f"year {a.year}, split {a.split}, {ev.height} events\n")
print("| stratum | class | n | J 30 s | 1 min | 5 min | 15 min | extent p50 |\n|---|---|---|---|---|---|---|---|")
for r in tab.iter_rows(named=True):
    print(f"| {r['stratum']} | {r['validity']} | {r['n']:,} | {r['J30s']:.3f} | {r['J1m']:.3f} | {r['J5m']:.3f} | {r['J15m']:.3f} | {r['extent_p50']:.0f} |")
