"""Who switches back? For each hijack → recovery pair, compare the recovery's 2-h set R (ASes seen switching to the legitimate
origin) with the hijack's 2-h set H (ASes seen carrying the invalid route): |R ∩ H| / |R| is the share of recoverers that had
carried the hijack; |R − H| / |R| the share that never carried it (they had lost or re-routed the prefix and re-learn it at
recovery). Also H − R: hijack carriers never seen switching back within 2 h. usage: recovery_overlap.py <year>"""
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
E = config.DATA_ROOT / "eventset"
rec = pl.read_parquet(E / f"{year}_recovery" / "events.parquet").filter(pl.col("error").is_null()).select("event_id", "set_final_2h")
hij = pl.read_parquet(E / str(year) / "events.parquet").filter(pl.col("error").is_null()).select(pl.col("event_id").alias("hijack_id"), pl.col("set_final_2h").alias("h_set"))
sel = pl.read_parquet(config.DATA_ROOT / "inventory" / str(year) / "recovery_replay_selection.parquet").select("event_id", "hijack_id", "gap_s")
p = _hijack_filter(sel.join(rec, on="event_id").join(hij, on="hijack_id"))
rows = []
for r in p.iter_rows(named=True):
    R, H = set(r["set_final_2h"] or []), set(r["h_set"] or [])
    if not R:
        continue
    rows.append({"in_both": len(R & H) / len(R), "only_recovery": len(R - H) / len(R), "hijack_not_recovered": (len(H - R) / len(H)) if H else None, "r": len(R), "h": len(H), "gap_s": r["gap_s"]})
d = pl.DataFrame(rows)
out = {"year": year, "pairs": d.height, "recoverers_that_carried_hijack_mean": round(float(d["in_both"].mean()), 4), "recoverers_never_carried_hijack_mean": round(float(d["only_recovery"].mean()), 4),
       "recoverers_never_carried_hijack_p50": round(float(d["only_recovery"].median()), 4), "hijack_carriers_not_seen_recovering_mean": round(float(d["hijack_not_recovered"].drop_nulls().mean()), 4),
       "recovery_set_over_hijack_set_p50": round(float((d["r"] / d["h"].clip(1)).median()), 3)}
for lo, hi, lab in ((0, 60, "gap<1min"), (60, 900, "gap 1-15min"), (900, 86400, "gap>15min")):
    g = d.filter((pl.col("gap_s") >= lo) & (pl.col("gap_s") < hi))
    if g.height >= 20:
        out[f"by_{lab}"] = {"pairs": g.height, "recoverers_never_carried_hijack_mean": round(float(g["only_recovery"].mean()), 4), "recovery_over_hijack_p50": round(float((g["r"] / g["h"].clip(1)).median()), 3)}
print(json.dumps(out, indent=1))
(E / f"{year}_recovery" / f"overlap_summary{SUF}.json").write_text(json.dumps(out, indent=1))
