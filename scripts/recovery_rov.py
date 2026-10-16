"""ROV enforcement among observed paired AS-path sets R−H, R∩H and H−R.
Membership is not evidence of an AS's unobserved routing state. RoVista uses only
the latest measurement at or before the event date; missing history is unknown.
usage: recovery_rov.py <year>
"""
from __future__ import annotations

import json

import polars as pl

from bgbench import config
from bgbench.rov_history import ratio_at
from bgbench.paired_analysis import add_pair_arguments, read_pair_inputs, filter_hijack_population, pair_events, unique_payload

import argparse
_ap = argparse.ArgumentParser()
_ap.add_argument("year", type=int)
_ap.add_argument("--only-reason", default=None, help="keep pairs whose hijack has this selection reason (events.parquet column reason)")
_ap.add_argument("--exclude-reason", default=None, help="drop pairs whose hijack has this selection reason, e.g. rpki_invalid_sample")
_ap.add_argument("--suffix", default="", help="write <output><suffix> instead of the default files")
_ap.add_argument("--freeze-date", default=None, help="YYYY-MM-DD: ignore RoVista measurements after this date (RoVista regime change mid-2025)")
add_pair_arguments(_ap)
_a = _ap.parse_args()
year = _a.year
SUF = _a.suffix
hijack_table, recovery_table, output_dir, selection_file = read_pair_inputs(_a, year)


def _hijack_filter(df, col="hijack_id"):
    return filter_hijack_population(df, _a, year, col)
E = config.DATA_ROOT / "eventset"
rov = pl.read_parquet(config.DATA_ROOT / "rpki" / "rovista" / "as_rov_series.parquet").with_columns(pl.col("date").cast(pl.Utf8)).sort("asn", "date")
if _a.freeze_date:
    rov = rov.filter(pl.col("date") <= _a.freeze_date)
series = {int(a[0]): (g["date"].to_list(), g["ratio"].to_list()) for a, g in rov.group_by("asn", maintain_order=True)}


def enforcing(asn: int, day: str):
    ratio = ratio_at(series, asn, day)
    return None if ratio is None else ratio >= 0.5


rec = recovery_table.select("event_id", "set_final_2h")
hij = hijack_table.select(pl.col("event_id").alias("hijack_id"), pl.col("set_final_2h").alias("h_set"))
sel = pl.read_parquet(selection_file).select("event_id", "hijack_id")
p = _hijack_filter(pair_events(sel, rec, hij))
acc = {k: [0, 0, 0, 0] for k in ("R-H", "R&H", "H-R")}
for r in p.iter_rows(named=True):
    day = f"{r['event_id'][:4]}-{r['event_id'][4:6]}-{r['event_id'][6:8]}"
    R, H = set(r["set_final_2h"] or []), set(r["h_set"] or [])
    for k, S in (("R-H", R - H), ("R&H", R & H), ("H-R", H - R)):
        for a in S:
            e = enforcing(int(a), day)
            acc[k][2] += 1
            acc[k][3] += int(int(a) in series and series[int(a)][0][0] > day)
            if e is not None:
                acc[k][0] += 1; acc[k][1] += int(e)
out = {"year": year, "pairs": p.height, "rovista_ases": len(series), "freeze_date": _a.freeze_date, "only_reason": _a.only_reason, "exclude_reason": _a.exclude_reason,
       "lookup_policy": "latest measurement at or before event date; missing history is unknown",
       "enforcing_share": {k: {"total_as_pair_observations": total, "measured": n, "unknown": total - n, "future_only_excluded": future, "coverage": round(n / total, 4) if total else None, "enforcing": e, "share": round(e / n, 4) if n else None} for k, (n, e, total, future) in acc.items()}}
out["chronologically_unmatched_links"] = _a.chronology_exclusions
out["chronologically_unmatched_count"] = len(_a.chronology_exclusions)
out["pair_population"] = {"require_valid_hijack": _a.require_valid_hijack,
                          "require_matched_definition": _a.require_matched_definition,
                          "hijack_events": str(_a.hijack_events) if _a.hijack_events else None,
                          "recovery_events": str(_a.recovery_events) if _a.recovery_events else None}
print(json.dumps(out, indent=1))
(output_dir / f"rov_summary{SUF}.json").write_text(json.dumps(out, indent=1))
