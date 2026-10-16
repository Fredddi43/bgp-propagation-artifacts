"""Hijack vs its recovery, paired on the full recovery replay set: each recovery event (eventset/<year>_recovery) is joined to its
hijack (recovery_replay_selection.parquet: hijack_id) in the origin-change event set. Per pair: persistence Jaccard 30 s → 2 h,
time to 90 % of the 2-h extent (continuous replay timestamps), reach, duration. Reports paired differences with bootstrap CIs and the share of pairs
where the recovery is slower. Writes eventset/<year>_recovery/pairs.parquet and pairs_summary.json. usage: recovery_pairs_full.py <year>"""
from __future__ import annotations

import json

import polars as pl

from bgbench import config
from bgbench.paired_analysis import add_pair_arguments, read_pair_inputs, filter_hijack_population, pair_events, unique_payload, link_components, clustered_mean_ci

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
def load(tag: str) -> pl.DataFrame:
    e = (recovery_table if tag else hijack_table)
    rows = []
    for r in e.select("event_id", "duration_min", "t90_s", "set_d30s", "set_final_2h", *(["t0_obs"] if "t0_obs" in e.columns else [])).iter_rows(named=True):
        fin, early = set(r["set_final_2h"] or []), set(r["set_d30s"] or [])
        rows.append({"event_id": r["event_id"], "reach": len(fin), "duration_min": r["duration_min"],
                     "t90_s": r["t90_s"] if fin else None, "t0_obs": r.get("t0_obs"),
                     "j30": len(early & fin) / len(early | fin) if (early | fin) else 0.0})
    return unique_payload(pl.DataFrame(rows))


hij = load("").rename({c: f"h_{c}" for c in ("reach", "duration_min", "t90_s", "j30", "t0_obs")}).rename({"event_id": "hijack_id"})
rec = load("recovery").rename({c: f"r_{c}" for c in ("reach", "duration_min", "t90_s", "j30", "t0_obs")})
sel = pl.read_parquet(selection_file).select("event_id", "hijack_id", "gap_s", "split")
pairs = _hijack_filter(pair_events(sel, rec, hij))
if _a.require_matched_definition:
    if pairs["h_t0_obs"].null_count() or pairs["r_t0_obs"].null_count():
        raise ValueError("Matched primary pairs require observed onsets")
    pairs = pairs.with_columns(observed_gap_s=(
        pl.col("r_t0_obs").str.to_datetime(time_zone="UTC") - pl.col("h_t0_obs").str.to_datetime(time_zone="UTC")
    ).dt.total_microseconds() / 1e6)
    if pairs.filter(pl.col("observed_gap_s") < 0).height:
        raise ValueError("Observed recovery precedes its paired observed hijack")
groups = link_components(pairs)
pairs = pairs.with_columns(pl.Series("bootstrap_component", groups))
pairs.write_parquet(output_dir / f"pairs{SUF}.parquet")


def ci(x):
    return clustered_mean_ci(x, groups)


out = {"year": year, "pairs": pairs.height, "only_reason": _a.only_reason, "exclude_reason": _a.exclude_reason,
       "j30_definition": "intersection/union, empty union scores zero", "unique_recoveries": pairs["event_id"].n_unique(),
       "unique_hijacks": pairs["hijack_id"].n_unique(), "bootstrap_components": len(set(groups)),
       "ci_method": "1000 connected-event cluster bootstrap resamples, seed 0; link-weighted mean",
       "t90_definition": "continuous first-arrival 90% quantile; undefined for empty final set",
       "timing_comparable_pairs": pairs.filter(pl.col("h_t90_s").is_not_null() & pl.col("r_t90_s").is_not_null()).height,
       "hijack_t90_observed": pairs["h_t90_s"].drop_nulls().len(), "recovery_t90_observed": pairs["r_t90_s"].drop_nulls().len(),
       "zero_hijack_reach": (pairs["h_reach"] == 0).sum(), "zero_recovery_reach": (pairs["r_reach"] == 0).sum(), "gap_s_p50": float(pairs["gap_s"].median()),
       "hijack": {"j30_mean": round(float(pairs["h_j30"].mean()), 4), "t90_s_p50": float(pairs["h_t90_s"].median()), "t90_gt_5min_frac": round(float((pairs["h_t90_s"] > 300).mean()), 4), "reach_p50": float(pairs["h_reach"].median())},
       "recovery": {"j30_mean": round(float(pairs["r_j30"].mean()), 4), "t90_s_p50": float(pairs["r_t90_s"].median()), "t90_gt_5min_frac": round(float((pairs["r_t90_s"] > 300).mean()), 4), "reach_p50": float(pairs["r_reach"].median())},
       "paired_j30_diff_recovery_minus_hijack": {"mean": round(float((pairs["r_j30"] - pairs["h_j30"]).mean()), 4), "ci95": ci(pairs["r_j30"] - pairs["h_j30"])},
       "recovery_slower_t90_frac": round(float((pairs["r_t90_s"] > pairs["h_t90_s"]).mean()), 4), "recovery_lower_j30_frac": round(float((pairs["r_j30"] < pairs["h_j30"]).mean()), 4),
       "recovery_reach_over_hijack_reach_p50": round(float((pairs.filter(pl.col("h_reach") > 0)["r_reach"] / pairs.filter(pl.col("h_reach") > 0)["h_reach"]).median()), 3)}
for lo, hi, lab in ((0, 60, "gap<1min"), (60, 900, "gap 1-15min"), (900, 86400, "gap>15min")):
    g = pairs.filter((pl.col("gap_s") >= lo) & (pl.col("gap_s") < hi))
    if g.height >= 20:
        out[f"by_{lab}"] = {"pairs": g.height, "hijack_j30": round(float(g["h_j30"].mean()), 4), "recovery_j30": round(float(g["r_j30"].mean()), 4), "hijack_t90_p50": float(g["h_t90_s"].median()), "recovery_t90_p50": float(g["r_t90_s"].median())}
out["chronologically_unmatched_links"] = _a.chronology_exclusions
out["chronologically_unmatched_count"] = len(_a.chronology_exclusions)
out["pair_population"] = {"require_valid_hijack": _a.require_valid_hijack,
                          "require_matched_definition": _a.require_matched_definition,
                          "hijack_events": str(_a.hijack_events) if _a.hijack_events else None,
                          "recovery_events": str(_a.recovery_events) if _a.recovery_events else None}
print(json.dumps(out, indent=1))
(output_dir / f"pairs_summary{SUF}.json").write_text(json.dumps(out, indent=1))
