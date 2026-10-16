"""Are the ASes that switch back without having carried the hijack the ROV enforcers? For each hijack → recovery pair: R = recovery
2-h set, H = hijack 2-h set. RoVista enforcing share (ratio ≥ 0.5 at nearest date ≤ t₀) among R − H (switched back, never carried the
invalid), R ∩ H (carried it, switched back) and H − R (carried it, not seen switching back). usage: recovery_rov.py <year>"""
from __future__ import annotations

import bisect
import json

import polars as pl

from bgbench import config

import argparse
_ap = argparse.ArgumentParser()
_ap.add_argument("year", type=int)
_ap.add_argument("--only-reason", default=None, help="keep pairs whose hijack has this selection reason (events.parquet column reason)")
_ap.add_argument("--exclude-reason", default=None, help="drop pairs whose hijack has this selection reason, e.g. rpki_invalid_sample")
_ap.add_argument("--suffix", default="", help="write <output><suffix> instead of the default files")
_ap.add_argument("--freeze-date", default=None, help="YYYY-MM-DD: ignore RoVista measurements after this date (RoVista regime change mid-2025)")
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
rov = pl.read_parquet(config.DATA_ROOT / "rpki" / "rovista" / "as_rov_series.parquet").with_columns(pl.col("date").cast(pl.Utf8)).sort("asn", "date")
if _a.freeze_date:
    rov = rov.filter(pl.col("date") <= _a.freeze_date)
series = {int(a[0]): (g["date"].to_list(), g["ratio"].to_list()) for a, g in rov.group_by("asn", maintain_order=True)}


def enforcing(asn: int, day: str):
    s = series.get(asn)
    if not s:
        return None
    i = max(bisect.bisect_right(s[0], day) - 1, 0)
    return s[1][i] >= 0.5


rec = pl.read_parquet(E / f"{year}_recovery" / "events.parquet").filter(pl.col("error").is_null()).select("event_id", "set_final_2h")
hij = pl.read_parquet(E / str(year) / "events.parquet").filter(pl.col("error").is_null()).select(pl.col("event_id").alias("hijack_id"), pl.col("set_final_2h").alias("h_set"))
sel = pl.read_parquet(config.DATA_ROOT / "inventory" / str(year) / "recovery_replay_selection.parquet").select("event_id", "hijack_id")
p = _hijack_filter(sel.join(rec, on="event_id").join(hij, on="hijack_id"))
acc = {k: [0, 0] for k in ("R-H", "R&H", "H-R")}
for r in p.iter_rows(named=True):
    day = f"{r['event_id'][:4]}-{r['event_id'][4:6]}-{r['event_id'][6:8]}"
    R, H = set(r["set_final_2h"] or []), set(r["h_set"] or [])
    for k, S in (("R-H", R - H), ("R&H", R & H), ("H-R", H - R)):
        for a in S:
            e = enforcing(int(a), day)
            if e is not None:
                acc[k][0] += 1; acc[k][1] += int(e)
out = {"year": year, "pairs": p.height, "rovista_ases": len(series), "freeze_date": _a.freeze_date, "only_reason": _a.only_reason, "exclude_reason": _a.exclude_reason,
       "enforcing_share": {k: {"measured": n, "enforcing": e, "share": round(e / n, 4) if n else None} for k, (n, e) in acc.items()}}
print(json.dumps(out, indent=1))
(E / f"{year}_recovery" / f"rov_summary{SUF}.json").write_text(json.dumps(out, indent=1))
