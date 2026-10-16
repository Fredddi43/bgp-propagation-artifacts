"""Reconstruct the leaked prefix set of every Cloudflare Radar leak we can match, from our own replay (the public API
withholds prefixes; the hijack feed has them). For each Radar leak (leaker = leak_seg[1], window [min_ts, max_ts]) find
our leak events with the same leaker whose t₀ is within ±10 min, read the anomalous announcements of the replayed
event, and take their prefixes. Output: labels/<year>/cloudflare_leaks_prefixes_reconstructed.parquet and an agreement
summary (our count vs Radar's prefix_count). usage: label_leak_prefixes.py <year>"""
from __future__ import annotations

import json
import re
import sys

import polars as pl

from bgbench import config
from bgbench.labels import load_cf_leaks
from bgbench.replay_day import roots

year = int(sys.argv[1])
LB = config.DATA_ROOT / "labels" / f"{year}-01-01_{year + 1}-01-01"
lk = load_cf_leaks(LB)
if lk is None:
    print("no Radar leak labels for", year); sys.exit(0)
leaker = []
for v in lk["leak_seg"].to_list():
    seg = re.sub(r"[\[\]\" ]", "", v).split(",")
    leaker.append(int(seg[1]) if len(seg) >= 2 and seg[1] else 0)
lk = lk.with_columns(pl.Series("leaker", leaker, dtype=pl.UInt32), pl.col("prefix_count").cast(pl.Int64), pl.col("peer_count").cast(pl.Int64),
                     pl.col("min_ts").dt.replace_time_zone(None), pl.col("max_ts").cast(pl.Utf8).str.to_datetime(time_zone="UTC", strict=False).dt.replace_time_zone(None))
sel = pl.read_parquet(config.DATA_ROOT / "inventory" / str(year) / "leak_replay_selection.parquet").select("event_id", pl.col("a").cast(pl.UInt32), "t0")
if sel["t0"].dtype.time_zone:
    sel = sel.with_columns(pl.col("t0").dt.replace_time_zone(None))
root = roots("leak")[1]
rows = []
j = lk.join(sel, left_on="leaker", right_on="a", how="inner").filter((pl.col("t0") - pl.col("min_ts")).dt.total_seconds().abs() <= 600)
for r in j.iter_rows(named=True):
    d = root / r["event_id"]
    if not (d / "anomalous.parquet").exists():
        continue
    pf = pl.read_parquet(d / "anomalous.parquet", columns=["prefix", "ts"])
    if pf["ts"].dtype.time_zone:
        pf = pf.with_columns(pl.col("ts").dt.replace_time_zone(None))
    pf = pf.filter((pl.col("ts") >= pl.lit(r["min_ts"]) - pl.duration(minutes=10)) & (pl.col("ts") <= pl.lit(r["max_ts"] or r["min_ts"]) + pl.duration(minutes=10)))
    prefixes = sorted(pf["prefix"].unique().to_list())
    rows.append({"radar_id": r["id"], "leaker": int(r["leaker"]), "event_id": r["event_id"], "radar_prefix_count": r["prefix_count"], "radar_peer_count": r["peer_count"],
                 "our_prefix_count": len(prefixes), "prefixes": json.dumps(prefixes)})
out = pl.DataFrame(rows).unique("radar_id", keep="first") if rows else pl.DataFrame()
out.write_parquet(LB / "cloudflare_leaks_prefixes_reconstructed.parquet")
if out.height:
    ratio = (out["our_prefix_count"] / out["radar_prefix_count"].clip(1))
    summ = {"radar_leaks": lk.height, "matched_to_our_events": out.height, "exact_count_match": int((out["our_prefix_count"] == out["radar_prefix_count"]).sum()),
            "our_ge_radar": int((out["our_prefix_count"] >= out["radar_prefix_count"]).sum()), "ratio_p10_p50_p90": [round(float(ratio.quantile(q)), 3) for q in (0.1, 0.5, 0.9)],
            "radar_prefix_count_p50": float(out["radar_prefix_count"].median()), "our_prefix_count_p50": float(out["our_prefix_count"].median())}
    print(json.dumps(summ, indent=1)); (LB / "cloudflare_leaks_prefixes_reconstructed.json").write_text(json.dumps(summ, indent=1))
else:
    print("no matches")
