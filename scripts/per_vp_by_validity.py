"""Per-collector persistence floors split by RPKI validity class (the reframing's per-VP claim, ADR-0004: never pooled).
Recomputes the per-event, per-collector Jaccard of the Δ set against the collector's own 2-h set from membership.parquet (as
eventset.per_vp_and_duration does), joins eventset/<year>/rpki_validity.parquet, and reports mean J at 30 s and 1 min per
collector × class on the test split with the per-class spread across collectors. usage: per_vp_by_validity.py <year>"""
from __future__ import annotations

import datetime as dt
import json

import polars as pl

from bgbench import config
from bgbench.replay_day import roots

import argparse
_ap = argparse.ArgumentParser(); _ap.add_argument("year", type=int)
_ap.add_argument("--exclude-reason", default=None, help="drop events with this selection reason, e.g. rpki_invalid_sample (paper population)")
_ap.add_argument("--suffix", default="", help="output file suffix")
_a = _ap.parse_args(); year = _a.year; SUF = _a.suffix
E = config.DATA_ROOT / "eventset" / str(year)
_, root = roots("")
val = pl.read_parquet(E / "rpki_validity.parquet").select("event_id", "validity")
tbl = pl.read_parquet(E / "events.parquet").filter(pl.col("error").is_null() & (pl.col("split") == "test"))
if _a.exclude_reason:
    tbl = tbl.filter(pl.col("reason") != _a.exclude_reason)
tbl = tbl.select("event_id", "t0_obs").join(val, on="event_id")
rows = []
for k, r in enumerate(tbl.iter_rows(named=True)):
    mf = root / r["event_id"] / "membership.parquet"
    if not mf.exists():
        continue
    t0 = dt.datetime.fromisoformat(r["t0_obs"])
    mem = pl.read_parquet(mf, columns=["collector", "asn", "first_seen"])
    for c, g in mem.group_by("collector"):
        fin = set(g.filter(pl.col("first_seen") <= pl.lit(t0 + dt.timedelta(hours=2)))["asn"].to_list())
        if not fin:
            continue
        for dk, ds in (("d30s", 30), ("d1m", 60)):
            s = set(g.filter(pl.col("first_seen") <= pl.lit(t0 + dt.timedelta(seconds=ds)))["asn"].to_list())
            rows.append({"event_id": r["event_id"], "validity": r["validity"], "collector": c[0], "delta": dk, "jaccard": len(s & fin) / len(s | fin)})
    if k % 1000 == 0:
        print(k, "events", flush=True)
pv = pl.DataFrame(rows)
per = pv.group_by("validity", "collector", "delta").agg(n=pl.len(), jaccard_mean=pl.col("jaccard").mean().round(3)).sort("delta", "validity", "collector")
spread = per.group_by("validity", "delta").agg(collectors=pl.len(), min=pl.col("jaccard_mean").min(), max=pl.col("jaccard_mean").max(), std=pl.col("jaccard_mean").std().round(3)).sort("delta", "validity")
# does the class ordering hold at every collector?
order_ok = {}
for (dk,), g in per.filter(pl.col("delta") == "d30s").group_by("delta"):
    ok = 0; tot = 0
    for (c,), h in g.group_by("collector"):
        m = {v: j for v, j in zip(h["validity"].to_list(), h["jaccard_mean"].to_list())}
        if all(x in m for x in ("invalid", "unknown", "valid")):
            tot += 1; ok += int(m["invalid"] > m["unknown"] > m["valid"])
    order_ok[dk] = {"collectors_with_all_classes": tot, "invalid>unknown>valid": ok}
per.write_csv(E / f"persistence_per_vp_by_validity_test{SUF}.csv")
out = {"year": year, "events": int(pv["event_id"].n_unique()), "per_vp_by_validity": per.to_dicts(), "spread": spread.to_dicts(), "ordering_at_30s": order_ok}
print(json.dumps(out, indent=1, default=str)); (E / f"per_vp_by_validity{SUF}.json").write_text(json.dumps(out, indent=1, default=str))
