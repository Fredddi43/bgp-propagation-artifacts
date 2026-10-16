"""Prefix-level persistence floor (ADR-0005 "which prefixes"): for each replayed leak event, the set of leaked prefixes observed by
Δ vs by 2 h (from anomalous.parquet), Jaccard per event, on the test split; also the still-growing share and the prefix count
p50/p90. usage: prefix_floor.py <year>"""
from __future__ import annotations

import datetime as dt
import json
import sys

import polars as pl

from bgbench import config
from bgbench.replay_day import roots

year = int(sys.argv[1])
E = config.DATA_ROOT / "eventset" / f"{year}_leak"
ev = pl.read_parquet(E / "events.parquet").filter(pl.col("error").is_null()).select("event_id", "split", "t0_obs", "asns_final_2h")
root = roots("leak")[1]
DELTAS = {"d30s": 30, "d1m": 60, "d5m": 300, "d15m": 900}
rows = []
for r in ev.iter_rows(named=True):
    f = root / r["event_id"] / "anomalous.parquet"
    if not f.exists():
        continue
    a = pl.read_parquet(f, columns=["prefix", "ts"])
    if a["ts"].dtype.time_zone:
        a = a.with_columns(pl.col("ts").dt.replace_time_zone(None))
    t0 = dt.datetime.fromisoformat(r["t0_obs"]).replace(tzinfo=None)
    fin = set(a.filter(pl.col("ts") <= t0 + dt.timedelta(hours=2))["prefix"].to_list())
    if not fin:
        continue
    row = {"event_id": r["event_id"], "split": r["split"], "prefixes_2h": len(fin), "asns_2h": r["asns_final_2h"]}
    for k, s in DELTAS.items():
        cur = set(a.filter(pl.col("ts") <= t0 + dt.timedelta(seconds=s))["prefix"].to_list())
        row[f"j_{k}"] = len(cur & fin) / len(cur | fin); row[f"grow_{k}"] = len(fin) > len(cur)
    rows.append(row)
d = pl.DataFrame(rows); d.write_parquet(E / "prefix_floor.parquet")
t = d.filter(pl.col("split") == "test")
out = {"year": year, "events": d.height, "test": t.height, "prefixes_2h_p50_p90": [float(d["prefixes_2h"].quantile(q)) for q in (0.5, 0.9)],
       "persistence_prefix_jaccard_test": {k: round(float(t[f"j_{k}"].mean()), 4) for k in DELTAS}, "still_growing_prefixes": {k: round(float(d[f"grow_{k}"].mean()), 4) for k in DELTAS}}
big = d.filter(pl.col("asns_2h") >= 200); tb = big.filter(pl.col("split") == "test")
if tb.height:
    out["large_leaks_ge200"] = {"events": big.height, "test": tb.height, "prefixes_2h_p50": float(big["prefixes_2h"].median()), "persistence_prefix_jaccard_test": {k: round(float(tb[f"j_{k}"].mean()), 4) for k in DELTAS}}
multi = d.filter(pl.col("prefixes_2h") >= 10); tm = multi.filter(pl.col("split") == "test")
if tm.height:
    out["multi_prefix_ge10"] = {"events": multi.height, "test": tm.height, "persistence_prefix_jaccard_test": {k: round(float(tm[f"j_{k}"].mean()), 4) for k in DELTAS}}
print(json.dumps(out, indent=1)); (E / "prefix_floor_summary.json").write_text(json.dumps(out, indent=1))
