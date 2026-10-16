"""Hijack vs its recovery, paired on the full recovery replay set: each recovery event (eventset/<year>_recovery) is joined to its
hijack (recovery_replay_selection.parquet: hijack_id) in the origin-change event set. Per pair: persistence Jaccard 30 s → 2 h,
time to 90 % of the 2-h extent (coarse grid), reach, duration. Reports paired differences with bootstrap CIs and the share of pairs
where the recovery is slower. Writes eventset/<year>_recovery/pairs.parquet and pairs_summary.json. usage: recovery_pairs_full.py <year>"""
from __future__ import annotations

import json

import numpy as np
import polars as pl

from bgbench import config

import argparse
_ap = argparse.ArgumentParser()
_ap.add_argument("year", type=int)
_ap.add_argument("--only-reason", default=None, help="keep pairs whose hijack has this selection reason (events.parquet column reason)")
_ap.add_argument("--exclude-reason", default=None, help="drop pairs whose hijack has this selection reason, e.g. rpki_invalid_sample")
_ap.add_argument("--suffix", default="", help="write <output><suffix> instead of the default files")

_a = _ap.parse_args()
year = _a.year
SUF = _a.suffix


def _hijack_filter(df, col="hijack_id"):
    """Restrict to hijacks of one selection population via the reason column of eventset/<year>/events.parquet."""
    if not (_a.only_reason or _a.exclude_reason):
        return df
    rs = pl.read_parquet(config.DATA_ROOT / "eventset" / str(year) / "events.parquet").select(pl.col("event_id").alias(col), "reason")
    df = df.join(rs, on=col, how="left")
    if _a.only_reason:
        df = df.filter(pl.col("reason") == _a.only_reason)
    if _a.exclude_reason:
        df = df.filter(pl.col("reason") != _a.exclude_reason)
    return df.drop("reason")
GRID = [("set_d30s", 30), ("set_d1m", 60), ("set_d5m", 300), ("set_d15m", 900), ("set_T60m", 3600), ("set_final_2h", 7200)]


def load(tag: str) -> pl.DataFrame:
    e = pl.read_parquet(config.DATA_ROOT / "eventset" / (f"{year}_{tag}" if tag else str(year)) / "events.parquet").filter(pl.col("error").is_null())
    rows = []
    for r in e.select("event_id", "asns_final_2h", "duration_min", *[c for c, _ in GRID]).iter_rows(named=True):
        fin = set(r["set_final_2h"] or [])
        t90 = 7200
        for col, s in GRID:
            if fin and len(set(r[col] or []) & fin) >= 0.9 * len(fin):
                t90 = s; break
        a = set(r["set_d30s"] or [])
        rows.append({"event_id": r["event_id"], "reach": r["asns_final_2h"], "duration_min": r["duration_min"], "t90_s": t90, "j30": len(a & fin) / len(a | fin) if (a | fin) else 1.0})
    return pl.DataFrame(rows)


hij = load("").rename({c: f"h_{c}" for c in ("reach", "duration_min", "t90_s", "j30")}).rename({"event_id": "hijack_id"})
rec = load("recovery").rename({c: f"r_{c}" for c in ("reach", "duration_min", "t90_s", "j30")})
sel = pl.read_parquet(config.DATA_ROOT / "inventory" / str(year) / "recovery_replay_selection.parquet").select("event_id", "hijack_id", "gap_s", "split")
pairs = _hijack_filter(sel.join(rec, on="event_id").join(hij, on="hijack_id"))
pairs.write_parquet(config.DATA_ROOT / "eventset" / f"{year}_recovery" / f"pairs{SUF}.parquet")
rng = np.random.default_rng(0)


def ci(x):
    x = np.asarray(x, dtype=float)
    if len(x) < 20:
        return None
    b = [np.mean(rng.choice(x, size=len(x))) for _ in range(1000)]
    return [round(float(np.percentile(b, 2.5)), 4), round(float(np.percentile(b, 97.5)), 4)]


out = {"year": year, "pairs": pairs.height, "gap_s_p50": float(pairs["gap_s"].median()),
       "hijack": {"j30_mean": round(float(pairs["h_j30"].mean()), 4), "t90_s_p50": float(pairs["h_t90_s"].median()), "t90_gt_5min_frac": round(float((pairs["h_t90_s"] > 300).mean()), 4), "reach_p50": float(pairs["h_reach"].median())},
       "recovery": {"j30_mean": round(float(pairs["r_j30"].mean()), 4), "t90_s_p50": float(pairs["r_t90_s"].median()), "t90_gt_5min_frac": round(float((pairs["r_t90_s"] > 300).mean()), 4), "reach_p50": float(pairs["r_reach"].median())},
       "paired_j30_diff_recovery_minus_hijack": {"mean": round(float((pairs["r_j30"] - pairs["h_j30"]).mean()), 4), "ci95": ci(pairs["r_j30"] - pairs["h_j30"])},
       "recovery_slower_t90_frac": round(float((pairs["r_t90_s"] > pairs["h_t90_s"]).mean()), 4), "recovery_lower_j30_frac": round(float((pairs["r_j30"] < pairs["h_j30"]).mean()), 4),
       "recovery_reach_over_hijack_reach_p50": round(float((pairs["r_reach"] / pairs["h_reach"].clip(1)).median()), 3)}
for lo, hi, lab in ((0, 60, "gap<1min"), (60, 900, "gap 1-15min"), (900, 86400, "gap>15min")):
    g = pairs.filter((pl.col("gap_s") >= lo) & (pl.col("gap_s") < hi))
    if g.height >= 20:
        out[f"by_{lab}"] = {"pairs": g.height, "hijack_j30": round(float(g["h_j30"].mean()), 4), "recovery_j30": round(float(g["r_j30"].mean()), 4), "hijack_t90_p50": float(g["h_t90_s"].median()), "recovery_t90_p50": float(g["r_t90_s"].median())}
print(json.dumps(out, indent=1))
(config.DATA_ROOT / "eventset" / f"{year}_recovery" / f"pairs_summary{SUF}.json").write_text(json.dumps(out, indent=1))
