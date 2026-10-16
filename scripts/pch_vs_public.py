"""What does an IXP-side vantage set add? For each 2024 leak event replayed both at the ten public collectors (eventset/<year>_leak)
and at the 17 PCH DE-CIX collectors (eventset/<year>_leakpch): the 2-h AS sets from each side, their overlap, the ASes only PCH
sees, only the public collectors see, and the persistence floor at 30 s on the PCH side. usage: pch_vs_public.py <year> [public_tag pch_tag]  (default leak leakpch; origin family: "" pchorigin)"""
from __future__ import annotations

import json
import sys

import numpy as np
import polars as pl

from bgbench import config

year = int(sys.argv[1])
pub_tag = sys.argv[2] if len(sys.argv) > 2 else "leak"; pch_tag = sys.argv[3] if len(sys.argv) > 3 else "leakpch"
E = config.DATA_ROOT / "eventset"
pub = pl.read_parquet(E / (f"{year}_{pub_tag}" if pub_tag else str(year)) / "events.parquet").filter(pl.col("error").is_null()).select("event_id", "split", pl.col("set_d30s").alias("p30"), pl.col("set_final_2h").alias("pfin"), pl.col("collectors_seeing").alias("p_coll"))
pch = pl.read_parquet(E / f"{year}_{pch_tag}" / "events.parquet").filter(pl.col("error").is_null()).select("event_id", pl.col("set_d30s").alias("x30"), pl.col("set_final_2h").alias("xfin"), pl.col("collectors_seeing").alias("x_coll"))
j = pub.join(pch, on="event_id", how="inner")
rows = []
for r in j.iter_rows(named=True):
    P, X = set(r["pfin"] or []), set(r["xfin"] or [])
    if not P and not X:
        continue
    p30, x30 = set(r["p30"] or []), set(r["x30"] or [])
    rows.append({"event_id": r["event_id"], "split": r["split"], "pub": len(P), "pch": len(X), "both": len(P & X), "only_pch": len(X - P), "only_pub": len(P - X),
                 "union": len(P | X), "pch_seen": bool(X), "p_coll": r["p_coll"], "x_coll": r["x_coll"],
                 "j30_pub": len(p30 & P) / len(p30 | P) if (p30 | P) else None, "j30_pch": len(x30 & X) / len(x30 | X) if (x30 | X) else None,
                 "j30_union": len((p30 | x30) & (P | X)) / len((p30 | x30) | (P | X)) if (P | X) else None})
d = pl.DataFrame(rows)
seen = d.filter(pl.col("pch_seen"))
out = {"year": year, "events_in_both_sets": d.height, "events_seen_at_pch": seen.height, "share_seen_at_pch": round(seen.height / d.height, 4) if d.height else None,
       "pch_collectors_seeing_p50": float(seen["x_coll"].median()) if seen.height else None,
       "extent_pub_p50": float(d["pub"].median()), "extent_pch_p50": float(seen["pch"].median()) if seen.height else None,
       "ases_only_pch_p50": float(seen["only_pch"].median()) if seen.height else None, "ases_only_pch_share_of_union_mean": round(float((seen["only_pch"] / seen["union"]).mean()), 4) if seen.height else None,
       "ases_only_pub_share_of_union_mean": round(float((seen["only_pub"] / seen["union"]).mean()), 4) if seen.height else None,
       "union_over_pub_p50": round(float((seen["union"] / seen["pub"].clip(1)).median()), 3) if seen.height else None,
       "persistence_j30_test": {"public": round(float(d.filter(pl.col("split") == "test")["j30_pub"].drop_nulls().mean()), 4),
                                "pch": round(float(seen.filter(pl.col("split") == "test")["j30_pch"].drop_nulls().mean()), 4) if seen.height else None,
                                "union": round(float(seen.filter(pl.col("split") == "test")["j30_union"].drop_nulls().mean()), 4) if seen.height else None}}
big = seen.filter(pl.col("pub") >= 200)
if big.height:
    out["large_leaks_ge200"] = {"events": big.height, "ases_only_pch_p50": float(big["only_pch"].median()), "union_over_pub_p50": round(float((big["union"] / big["pub"]).median()), 3),
                                "persistence_j30_public": round(float(big["j30_pub"].drop_nulls().mean()), 4), "persistence_j30_union": round(float(big["j30_union"].drop_nulls().mean()), 4)}
vf = E / str(year) / "rpki_validity.parquet"
if not pub_tag and vf.exists():
    v = pl.read_parquet(vf).select("event_id", "validity")
    dv = d.join(v, on="event_id")
    out["by_validity"] = {}
    for (val,), g in dv.group_by("validity"):
        gs = g.filter(pl.col("pch_seen"))
        out["by_validity"][val] = {"events": g.height, "share_seen_at_pch": round(gs.height / g.height, 4), "extent_pub_p50": float(g["pub"].median()),
                                   "extent_pch_p50": float(gs["pch"].median()) if gs.height else None, "pch_over_pub_p50": round(float((gs["pch"] / gs["pub"].clip(1)).median()), 3) if gs.height else None}
print(json.dumps(out, indent=1))
d.write_parquet(E / f"{year}_{pch_tag}" / "pch_vs_public.parquet"); (E / f"{year}_{pch_tag}" / "pch_vs_public.json").write_text(json.dumps(out, indent=1))
