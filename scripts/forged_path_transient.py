"""Second pass over forged_path_candidates.parquet: a legitimate new adjacency persists, a forged one does not. For each candidate
edge (a, origin) first seen on day d, check whether it appears in any collector's new_edges table on days d+2 … d+8; candidates that
do not are *transient*. Re-summarises counts, monthly series and origin validity for the transient subset and writes
forged_path_candidates_transient.{parquet,json}. usage: forged_path_transient.py <year>"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict

import polars as pl

from bgbench import config

year = int(sys.argv[1])
COLL = ["rrc25", "rrc00", "rrc12", "rrc01", "route-views3", "rrc03", "route-views2", "rrc20", "rrc15", "route-views.linx"]
PE = config.DATA_ROOT / "prefix_events"
out_dir = config.DATA_ROOT / "inventory" / str(year)
c = pl.read_parquet(out_dir / "forged_path_candidates.parquet")
if c.is_empty():
    print("no candidates"); sys.exit(0)
edges = set(zip(c["a"].to_list(), c["origin"].to_list()))
# days on which each candidate edge is seen anywhere
seen_days: dict[tuple, set] = defaultdict(set)
days = sorted(set(c["day"].to_list()))
d_first, d_last = dt.date.fromisoformat(days[0]), dt.date.fromisoformat(days[-1]) + dt.timedelta(days=8)
day = d_first
while day <= d_last:
    ds = day.isoformat()
    for col in COLL:
        f = PE / col / f"{ds}.new_edges.parquet"
        if not f.exists():
            continue
        e = pl.read_parquet(f, columns=["a", "b"])
        for ab in zip(e["a"].cast(pl.Int64).to_list(), e["b"].cast(pl.Int64).to_list()):
            if ab in edges:
                seen_days[ab].add(ds)
    day += dt.timedelta(days=1)
flags = []
for d0, a, o in zip(c["day"].to_list(), c["a"].to_list(), c["origin"].to_list()):
    dd = dt.date.fromisoformat(d0)
    later = {(dd + dt.timedelta(days=k)).isoformat() for k in range(2, 9)}
    flags.append(not (seen_days.get((a, o), set()) & later))
c = c.with_columns(pl.Series("transient", flags))
t = c.filter(pl.col("transient"))
c.write_parquet(out_dir / "forged_path_candidates_transient.parquet")
summ = {"year": year, "candidates": c.height, "transient": t.height, "transient_share": round(t.height / c.height, 4),
        "transient_distinct_origins": int(t["origin"].n_unique()),
        "transient_by_month": {m: n for m, n in t.with_columns(pl.col("day").str.slice(0, 7).alias("m")).group_by("m").len().sort("m").iter_rows()},
        "transient_origin_validity": {v: n for v, n in t.group_by("origin_validity").len().iter_rows()},
        "all_origin_validity": {v: n for v, n in c.group_by("origin_validity").len().iter_rows()},
        "transient_collectors_p50": float(t["collectors"].median()) if t.height else None,
        "transient_ge3_collectors": int((t["collectors"] >= 3).sum()),
        "sample_transient": t.sort("msgs", descending=True).head(15).to_dicts()}
print(json.dumps(summ, indent=1, default=str)); (out_dir / "forged_path_candidates_transient.json").write_text(json.dumps(summ, indent=1, default=str))
