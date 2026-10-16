"""Compare observed AS-path membership in paired hijack (H) and return (R) sets.
R−H means an AS was absent from the observed hijack paths, not proof that it never
carried the hijack or had neither route. Empty R pairs are counted but excluded
from fractions with |R| in the denominator. usage: recovery_overlap.py <year>
"""
from __future__ import annotations

import json

import polars as pl

from bgbench import config
from bgbench.paired_analysis import add_pair_arguments, read_pair_inputs, filter_hijack_population, pair_events, unique_payload

import argparse
_ap = argparse.ArgumentParser()
_ap.add_argument("year", type=int)
_ap.add_argument("--only-reason", default=None, help="keep pairs whose hijack has this selection reason (events.parquet column reason)")
_ap.add_argument("--exclude-reason", default=None, help="drop pairs whose hijack has this selection reason, e.g. rpki_invalid_sample")
_ap.add_argument("--suffix", default="", help="write <output><suffix> instead of the default files")

add_pair_arguments(_ap)
_a = _ap.parse_args()
year = _a.year
SUF = _a.suffix
hijack_table, recovery_table, output_dir, selection_file = read_pair_inputs(_a, year)


def _hijack_filter(df, col="hijack_id"):
    return filter_hijack_population(df, _a, year, col)
E = config.DATA_ROOT / "eventset"
rec = recovery_table.select("event_id", "set_final_2h")
hij = hijack_table.select(pl.col("event_id").alias("hijack_id"), pl.col("set_final_2h").alias("h_set"))
sel = pl.read_parquet(selection_file).select("event_id", "hijack_id", "gap_s")
p = _hijack_filter(pair_events(sel, rec, hij))
rows = []
for r in p.iter_rows(named=True):
    R, H = set(r["set_final_2h"] or []), set(r["h_set"] or [])
    if not R:
        continue
    rows.append({"in_both": len(R & H) / len(R), "only_recovery": len(R - H) / len(R), "hijack_not_recovered": (len(H - R) / len(H)) if H else None, "r": len(R), "h": len(H), "gap_s": r["gap_s"]})
d = pl.DataFrame(rows)
out = {"year": year, "pairs": d.height, "selected_pairs": p.height, "zero_recovery_reach_pairs": p.height - d.height,
       "interpretation": "observed AS-path overlap; absence does not establish an AS routing state", "recoverers_that_carried_hijack_mean": round(float(d["in_both"].mean()), 4), "recoverers_never_carried_hijack_mean": round(float(d["only_recovery"].mean()), 4),
       "recoverers_never_carried_hijack_p50": round(float(d["only_recovery"].median()), 4), "hijack_carriers_not_seen_recovering_mean": round(float(d["hijack_not_recovered"].drop_nulls().mean()), 4),
       "recovery_set_over_hijack_set_p50": round(float((d.filter(pl.col("h") > 0)["r"] / d.filter(pl.col("h") > 0)["h"]).median()), 3)}
for lo, hi, lab in ((0, 60, "gap<1min"), (60, 900, "gap 1-15min"), (900, 86400, "gap>15min")):
    g = d.filter((pl.col("gap_s") >= lo) & (pl.col("gap_s") < hi))
    if g.height >= 20:
        out[f"by_{lab}"] = {"pairs": g.height, "recoverers_never_carried_hijack_mean": round(float(g["only_recovery"].mean()), 4), "recovery_over_hijack_p50": round(float((g.filter(pl.col("h") > 0)["r"] / g.filter(pl.col("h") > 0)["h"]).median()), 3)}
out["chronologically_unmatched_links"] = _a.chronology_exclusions
out["chronologically_unmatched_count"] = len(_a.chronology_exclusions)
out["pair_population"] = {"require_valid_hijack": _a.require_valid_hijack,
                          "require_matched_definition": _a.require_matched_definition,
                          "hijack_events": str(_a.hijack_events) if _a.hijack_events else None,
                          "recovery_events": str(_a.recovery_events) if _a.recovery_events else None}
print(json.dumps(out, indent=1))
(output_dir / f"overlap_summary{SUF}.json").write_text(json.dumps(out, indent=1))
