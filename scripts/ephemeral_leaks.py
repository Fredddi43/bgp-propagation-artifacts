"""ADR-0008 §6: ephemeral-leak false-positive analysis. Split the replayed leak events by identifier duration (< 1 min, 1–10 min,
> 10 min) and report per class: share, share labelled by Radar (the only external confirmation we have), 2-h extent, persistence
floor at 30 s (test), still-growing share, leaked prefixes. usage: ephemeral_leaks.py <year>"""
from __future__ import annotations

import json
import sys

import polars as pl

from bgbench import config

year = int(sys.argv[1])
E = config.DATA_ROOT / "eventset" / f"{year}_leak"
ev = pl.read_parquet(E / "events.parquet").filter(pl.col("error").is_null())
ev = ev.with_columns(pl.when(pl.col("duration_min") < 1).then(pl.lit("<1 min")).when(pl.col("duration_min") <= 10).then(pl.lit("1-10 min")).otherwise(pl.lit(">10 min")).alias("dur"),
                     pl.struct(["set_d30s", "set_final_2h"]).map_elements(lambda s: (len(set(s["set_d30s"] or []) & set(s["set_final_2h"] or [])) / len(set(s["set_d30s"] or []) | set(s["set_final_2h"] or []))) if (s["set_d30s"] or s["set_final_2h"]) else 1.0, return_dtype=pl.Float64).alias("j30"),
                     (pl.col("set_final_2h").list.len().fill_null(0) > pl.col("set_d30s").list.len().fill_null(0)).alias("growing30"))
out = {"year": year, "events": ev.height, "by_duration": {}}
for (dcls,), g in ev.group_by("dur"):
    t = g.filter(pl.col("split") == "test")
    out["by_duration"][dcls] = {"n": g.height, "share": round(g.height / ev.height, 4), "radar_labelled_share": round(float(g["labelled"].mean()), 4),
                                "asns_final_2h_p50": float(g["asns_final_2h"].median()), "asns_final_2h_p90": float(g["asns_final_2h"].quantile(0.9)),
                                "leaked_prefixes_p50": float(g["leaked_prefixes"].median()) if "leaked_prefixes" in g.columns else None,
                                "collectors_seeing_p50": float(g["collectors_seeing"].median()),
                                "persist_j30_test_mean": round(float(t["j30"].mean()), 4) if t.height else None, "n_test": t.height,
                                "growing_at_30s_frac": round(float(g["growing30"].mean()), 4)}
print(json.dumps(out, indent=1)); (E / "ephemeral_summary.json").write_text(json.dumps(out, indent=1))
