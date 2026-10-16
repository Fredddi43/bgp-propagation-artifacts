"""Hijack-out vs recovery-back, paired. An origin change A→B on prefix p at t₁ followed by B→A on the same prefix within 24 h is a
hijack (or misconfiguration) and its recovery. For each pair, compare how the two propagate: reach at 2 h, persistence Jaccard
30 s → 2 h, time to 90 % of the 2-h extent (coarse: first grid point among 30 s, 1, 5, 15, 60 min whose set reaches ≥ 90 % of
the final set), duration — split by the RPKI validity of the hijack's new origin (invalid-displacing-valid = textbook hijack).
usage: hijack_recovery_pairs.py <year>  → eventset/<year>/hijack_recovery_pairs.{parquet,json}"""
from __future__ import annotations

import json
import sys

import polars as pl

from bgbench import config

year = int(sys.argv[1])
E = config.DATA_ROOT / "eventset" / str(year)
ev = pl.read_parquet(E / "events.parquet").filter(pl.col("error").is_null())
man = pl.read_csv(config.DATA_ROOT / "inventory" / str(year) / "replay_manifest.tsv", separator="\t").select(
    "event_id", "prefix", pl.col("new_origin").cast(pl.Int64), pl.col("t0").str.to_datetime(strict=False))
inv = pl.read_parquet(config.DATA_ROOT / "inventory" / str(year) / "events_ranked.parquet").with_columns(
    (pl.col("first_ts").dt.strftime("%Y%m%dT%H%M%S") + "_" + pl.col("prefix").str.replace("/", "-") + "_" + pl.col("new_origin").cast(pl.Utf8)).alias("event_id"),
    pl.col("prev_origins").cast(pl.Utf8).str.extract(r"(\d+)", 1).cast(pl.Int64, strict=False).alias("prev_origin")).select("event_id", "prev_origin").unique("event_id")
val = pl.read_parquet(E / "rpki_validity.parquet").select("event_id", "validity", "prev_validity")
ev = ev.join(man, on="event_id").join(inv, on="event_id", how="left").join(val, on="event_id", how="left")

GRID = [("set_d30s", 30), ("set_d1m", 60), ("set_d5m", 300), ("set_d15m", 900), ("set_T60m", 3600), ("set_final_2h", 7200)]


def t90(row) -> int:
    fin = set(row["set_final_2h"] or [])
    if not fin:
        return 0
    for col, s in GRID:
        if len(set(row[col] or []) & fin) >= 0.9 * len(fin):
            return s
    return 7200


def j30(row) -> float:
    a, b = set(row["set_d30s"] or []), set(row["set_final_2h"] or [])
    return len(a & b) / len(a | b) if (a | b) else 1.0


rows = ev.select("event_id", "prefix", "new_origin", "prev_origin", "t0", "validity", "prev_validity", "asns_final_2h", "duration_min", "labelled",
                 *[c for c, _ in GRID]).to_dicts()
for r in rows:
    r["t90_s"] = t90(r); r["j30"] = j30(r)
by_prefix: dict[str, list] = {}
for r in rows:
    by_prefix.setdefault(r["prefix"], []).append(r)
pairs = []
for p, lst in by_prefix.items():
    lst.sort(key=lambda r: r["t0"])
    for i, h in enumerate(lst):
        if h["prev_origin"] is None:
            continue
        for rec in lst[i + 1:]:
            dt_s = (rec["t0"] - h["t0"]).total_seconds()
            if dt_s > 86400:
                break
            if rec["new_origin"] == h["prev_origin"] and rec["prev_origin"] == h["new_origin"]:
                pairs.append({"prefix": p, "hijack_id": h["event_id"], "recovery_id": rec["event_id"], "gap_s": dt_s, "hijack_validity": h["validity"], "hijack_prev_validity": h["prev_validity"],
                              "h_reach": h["asns_final_2h"], "r_reach": rec["asns_final_2h"], "h_j30": h["j30"], "r_j30": rec["j30"], "h_t90": h["t90_s"], "r_t90": rec["t90_s"],
                              "h_dur": h["duration_min"], "r_dur": rec["duration_min"], "h_labelled": h["labelled"], "r_labelled": rec["labelled"]})
                break
pf = pl.DataFrame(pairs)
pf.write_parquet(E / "hijack_recovery_pairs.parquet")
summ = {"year": year, "events": len(rows), "pairs": pf.height, "by_hijack_validity": {}}
if pf.height:
    for (v,), g in pf.group_by("hijack_validity"):
        summ["by_hijack_validity"][v] = {
            "pairs": g.height, "gap_s_p50": float(g["gap_s"].median()),
            "hijack": {"reach_p50": float(g["h_reach"].median()), "j30_mean": round(float(g["h_j30"].mean()), 4), "t90_s_p50": float(g["h_t90"].median()), "t90_gt_5min_frac": round(float((g["h_t90"] > 300).mean()), 4), "labelled": round(float(g["h_labelled"].mean()), 3)},
            "recovery": {"reach_p50": float(g["r_reach"].median()), "j30_mean": round(float(g["r_j30"].mean()), 4), "t90_s_p50": float(g["r_t90"].median()), "t90_gt_5min_frac": round(float((g["r_t90"] > 300).mean()), 4), "labelled": round(float(g["r_labelled"].mean()), 3)},
            "recovery_slower_frac": round(float((g["r_t90"] > g["h_t90"]).mean()), 4), "recovery_j30_lower_frac": round(float((g["r_j30"] < g["h_j30"]).mean()), 4)}
print(json.dumps(summ, indent=1))
(E / "hijack_recovery_pairs.json").write_text(json.dumps(summ, indent=1))
