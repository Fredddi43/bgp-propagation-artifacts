"""Robustness checks for the measurement sections (paper sections 5 and 6), camera-ready revision of 2026-10-30.

Reads only the finalized corrected release (data/corrected-release-20261016, the same files that
paper_propagation_tables.py, paper_recovery_tables.py and paper_frontier_tables.py read). Before any analysis it
checks every input against the SHA-256 recorded in the paper's own source files, and it reproduces the published
pooled values from the per-event and per-link tables. Any mismatch stops the script.

Analyses (all deterministic; bootstrap seed 0, 1,000 draws, percentile 95 % intervals):
  recovery_by_gap   outward (O) / return (R) links split by identifier gap (<1 min, 1-15 min, >15 min, the strata
                    of recovery_overlap.py): mean J30 of O and R, paired difference R - O with a component bootstrap
                    (the connected-event clusters of the paired analysis), t90 medians, share of returns with the
                    larger t90, median extent ratio |R|/|O| with a component bootstrap.
  frontier_diff     difference of mean frontier log-odds between RPKI classes (invalid - valid, invalid - unknown,
                    label-free invalid stratum - valid / unknown), two-sample event bootstrap.
  floor_bins        persistence floor J(S30s, S2h) by class within bins of two-hour extent |S2h| and of identifier
                    duration, catalogue population, test split, 2024 and 2025.
  floor_dayblock    day-block bootstrap intervals for the floors of the paper's Table 1 and for the year-to-year
                    changes of the pooled floor (UTC days of the event identifier are the resampling blocks).
  visibility        stratified sample without catalogue labels, restricted to the visibility rule of the label-free
                    invalid stratum (>= 10 peers and >= 3 collectors): floor by class, test split.

usage: python -B scripts/paper_measurement_checks.py data/corrected-release-20261016 paper/generated
writes <out>/measurement-checks-facts.json, recovery_gap.tex, floor_bins.tex, frontier_diff.tex, floor_dayblock.tex
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import polars as pl

YEARS = range(2022, 2027)
SEED, DRAWS = 0, 1000
GAPS = (("lt1min", 0, 60, r"$<1$\,min"), ("1to15min", 60, 900, r"1--15\,min"), ("gt15min", 900, 86400, r"$\geq 15$\,min"))
GAP_JSON = {"lt1min": "gap<1min", "1to15min": "gap 1-15min", "gt15min": "gap>15min"}
EXTENT_BINS = ((1, 50, "1--50"), (51, 100, "51--100"), (101, 200, "101--200"), (201, 10**9, r"$>200$"))
DURATION_BINS = ((0, 5, r"5\,min"), (6, 15, r"10--15\,min"), (16, 10**9, r"$>15$\,min"))
CLASSES = ("invalid", "unknown", "valid")
REPO = Path(__file__).resolve().parents[1]
BOUND = {  # source file of the paper -> its recorded input hashes
    "docs/paper/corrected-recovery-2026-10-16.json": "inputs_sha256",
    "paper/generated/propagation-facts.json": "inputs_sha256",
    "paper/generated/frontier_facts.json": "inputs_sha256",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def percentile(draws) -> list[float]:
    return [float(x) for x in np.percentile(np.asarray(draws, dtype=float), [2.5, 97.5])]


def cluster_draws(values: np.ndarray, groups: np.ndarray, stat, rng) -> list[float]:
    """Resample whole clusters with replacement; stat receives the concatenated values."""
    _, index = np.unique(groups, return_inverse=True)
    order = np.argsort(index, kind="stable")
    starts = np.searchsorted(index[order], np.arange(index.max() + 1))
    ends = np.append(starts[1:], len(order))
    members = [order[s:e] for s, e in zip(starts, ends)]
    n = len(members)
    out = []
    for _ in range(DRAWS):
        pick = rng.integers(0, n, size=n)
        out.append(stat(values[np.concatenate([members[i] for i in pick])]))
    return out


def mean_ci_clusters(values, groups, rng):
    values, groups = np.asarray(values, float), np.asarray(groups)
    _, index = np.unique(groups, return_inverse=True)
    n = index.max() + 1
    totals, counts = np.bincount(index, weights=values, minlength=n), np.bincount(index, minlength=n)
    draws = []
    for _ in range(DRAWS):
        pick = rng.integers(0, n, size=n)
        draws.append(totals[pick].sum() / counts[pick].sum())
    return percentile(draws)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("data", type=Path)
    ap.add_argument("out", type=Path)
    args = ap.parse_args()
    inputs: dict[str, str] = {}
    checks: list[str] = []

    bound = {}
    for source, key in BOUND.items():
        for rel, digest in json.loads((REPO / source).read_text())[key].items():
            bound[rel] = digest

    def read(rel: str, must_be_bound: bool = True):
        path = args.data / rel
        digest = sha(path)
        if rel in bound:
            if bound[rel] != digest:
                raise SystemExit(f"hash mismatch against the paper's source files: {rel}")
        elif must_be_bound:
            raise SystemExit(f"input not bound by any paper source file: {rel}")
        inputs[rel] = digest
        return pl.read_parquet(path) if path.suffix == ".parquet" else json.loads(path.read_text())

    recovery_json = json.loads((REPO / "docs/paper/corrected-recovery-2026-10-16.json").read_text())["years"]
    prop_json = json.loads((REPO / "paper/generated/propagation-facts.json").read_text())["years"]
    frontier_json = json.loads((REPO / "paper/generated/frontier_facts.json").read_text())["years"]
    facts = {"method": {"seed": SEED, "draws": DRAWS, "interval": "percentile 95 %",
                        "gap_strata_s": [[lo, hi] for _, lo, hi, _ in GAPS],
                        "extent_bins": [[lo, hi] for lo, hi, _ in EXTENT_BINS],
                        "duration_bins_min": [[lo, hi] for lo, hi, _ in DURATION_BINS],
                        "visibility_rule": "max_peers >= 10 and max_collectors >= 3 (select_validity_stratum.py)"},
             "years": {}}

    # ---------------------------------------------------------------- recovery by identifier gap
    for year in YEARS:
        rng = np.random.default_rng(SEED)
        suffix = "" if year == 2022 else "_labelled"
        pairs = read(f"eventset/{year}_recovery_first_transition/pairs{suffix}.parquet")
        ref = recovery_json[str(year)]
        assert pairs.height == ref["pairs"]["pairs"]
        assert pairs["bootstrap_component"].n_unique() == ref["pairs"]["bootstrap_components"]
        diff = (pairs["r_j30"] - pairs["h_j30"]).to_numpy()
        groups = pairs["bootstrap_component"].to_numpy()
        pooled_mean = float(diff.mean())
        assert round(pooled_mean, 4) == ref["pairs"]["paired_j30_diff_recovery_minus_hijack"]["mean"]
        pooled_ci = [round(x, 4) for x in mean_ci_clusters(diff, groups, np.random.default_rng(SEED))]
        assert pooled_ci == ref["pairs"]["paired_j30_diff_recovery_minus_hijack"]["ci95"], (pooled_ci, year)
        checks.append(f"{year} recovery: pooled paired difference and its component-bootstrap interval reproduced")
        strata, weighted = {}, 0.0
        for key, lo, hi, _ in GAPS:
            g = pairs.filter((pl.col("gap_s") >= lo) & (pl.col("gap_s") < hi))
            jr = ref["pairs"]["by_" + GAP_JSON[key]]
            assert g.height == jr["pairs"]
            assert round(g["h_j30"].mean(), 4) == jr["hijack_j30"] and round(g["r_j30"].mean(), 4) == jr["recovery_j30"]
            assert g["h_t90_s"].median() == jr["hijack_t90_p50"] and g["r_t90_s"].median() == jr["recovery_t90_p50"]
            ratio_frame = g.filter(pl.col("h_reach") > 0)
            ratio = (ratio_frame["r_reach"] / ratio_frame["h_reach"]).to_numpy()
            assert round(float(np.median(ratio)), 3) == ref["overlap"]["by_" + GAP_JSON[key]]["recovery_over_hijack_p50"]
            d = (g["r_j30"] - g["h_j30"]).to_numpy()
            weighted += d.sum()
            strata[key] = {
                "links": g.height, "share_of_links": g.height / pairs.height,
                "outward_j30_mean": float(g["h_j30"].mean()), "return_j30_mean": float(g["r_j30"].mean()),
                "paired_diff_mean": float(d.mean()),
                "paired_diff_ci95": mean_ci_clusters(d, g["bootstrap_component"].to_numpy(), rng),
                "outward_t90_s_p50": float(g["h_t90_s"].median()), "return_t90_s_p50": float(g["r_t90_s"].median()),
                "return_slower_share": float((g["r_t90_s"] > g["h_t90_s"]).mean()),
                "extent_ratio_p50": float(np.median(ratio)),
                "extent_ratio_p50_ci95": percentile(cluster_draws(ratio, ratio_frame["bootstrap_component"].to_numpy(),
                                                                  np.median, rng)),
            }
        assert sum(s["links"] for s in strata.values()) == pairs.height
        assert abs(weighted / pairs.height - pooled_mean) < 1e-12
        checks.append(f"{year} recovery: gap strata reproduce the published by_gap values and the pooled mean")
        facts["years"].setdefault(str(year), {})["recovery_by_gap"] = {
            "pooled": {"links": pairs.height, "paired_diff_mean": pooled_mean, "paired_diff_ci95": pooled_ci}, **strata}

    # ---------------------------------------------------------------- frontier differences between classes
    for year in YEARS:
        rng = np.random.default_rng(SEED)
        main_suffix = "" if year == 2022 else "_labelled" + ("_frozen2505" if year >= 2025 else "")
        main = read(f"eventset/{year}/rov_frontier{main_suffix}.parquet", must_be_bound=False)
        odds = {}
        for cls in CLASSES:
            x = main.filter((pl.col("validity") == cls) & pl.col("log_odds").is_not_null())["log_odds"].to_numpy()
            ref = frontier_json[str(year)]["paper"]["by_validity"][cls]
            assert len(x) == ref["events_with_both_measured"] and round(float(x.mean()), 3) == ref["log_odds_frontier_vs_carriers_mean"]
            odds[cls] = x
        if year >= 2023:
            s_suffix = "_stratum" + ("_frozen2505" if year >= 2025 else "")
            stratum = read(f"eventset/{year}/rov_frontier{s_suffix}.parquet", must_be_bound=False)
            x = stratum.filter((pl.col("validity") == "invalid") & pl.col("log_odds").is_not_null())["log_odds"].to_numpy()
            ref = frontier_json[str(year)]["invalid_stratum"]["by_validity"]["invalid"]
            assert len(x) == ref["events_with_both_measured"] and round(float(x.mean()), 3) == ref["log_odds_frontier_vs_carriers_mean"]
            odds["invalid_stratum"] = x
        checks.append(f"{year} frontier: per-event log-odds reproduce the published class means and counts")
        out = {}
        for a, b in (("invalid", "valid"), ("invalid", "unknown"), ("invalid_stratum", "valid"), ("invalid_stratum", "unknown")):
            if a not in odds:
                continue
            xa, xb = odds[a], odds[b]
            draws = [rng.choice(xa, size=len(xa)).mean() - rng.choice(xb, size=len(xb)).mean() for _ in range(DRAWS)]
            out[f"{a}_minus_{b}"] = {"diff": float(xa.mean() - xb.mean()), "ci95": percentile(draws)}
        facts["years"][str(year)]["frontier_diff"] = out

    # ---------------------------------------------------------------- floors: bins, day blocks, visibility
    def scored(year):
        e = read(f"eventset/{year}/events.parquet").filter(pl.col("error").is_null())
        v = read(f"eventset/{year}/rpki_validity.parquet").select("event_id", "validity")
        e = e.join(v, on="event_id", how="left", validate="1:1")
        return e.with_columns(
            pl.col("set_final_2h").list.len().alias("extent"),
            (pl.col("set_d30s").list.set_intersection("set_final_2h").list.len()
             / pl.col("set_d30s").list.set_union("set_final_2h").list.len().clip(1)).alias("J"),
            pl.col("event_id").str.slice(0, 8).alias("day"))

    def dayblock(frame, rng):
        """Event-weighted mean of J over the test split; resample UTC days."""
        agg = frame.group_by("day").agg(pl.col("J").sum().alias("s"), pl.len().alias("n")).sort("day")  # fixed order: seeded draws repeat
        s, n = agg["s"].to_numpy(), agg["n"].to_numpy()
        draws = []
        for _ in range(DRAWS):
            pick = rng.integers(0, len(s), size=len(s))
            draws.append(s[pick].sum() / n[pick].sum())
        return float(frame["J"].mean()), draws

    # cumulative sets: S_delta is a subset of S_2h, so J(S_delta, S_2h) = |S_delta| / |S_2h| (0 for an empty S_2h)
    subset = {}
    for year in YEARS:
        for tag in ("", "_leak"):
            frame = read(f"eventset/{year}{tag}/events.parquet").filter(pl.col("error").is_null())
            for h in ("d30s", "d1m", "d5m", "d15m"):
                assert (frame["set_" + h].list.set_difference(frame["set_final_2h"]).list.len() == 0).all(), (year, tag, h)
            subset[f"{year}{tag or '_origin'}"] = frame.height
    facts["cumulative_subset_check"] = {"usable_events_checked": subset, "horizons": ["d30s", "d1m", "d5m", "d15m"],
                                        "result": "set_delta subset of set_final_2h for every usable event"}
    checks.append("cumulative sets: every usable origin-change and leak event has set_delta within set_final_2h")

    pooled_draws = {}
    for year in YEARS:
        rng = np.random.default_rng(SEED)
        e = scored(year)
        test = e.filter(pl.col("split") == "test")
        paper = test.filter(pl.col("reason") != "rpki_invalid_sample")
        ref = prop_json[str(year)]
        assert abs(paper["J"].mean() - ref["paper"]["floors"]["d30s"]) < 1e-12
        for cls in CLASSES:
            assert abs(paper.filter(pl.col("validity") == cls)["J"].mean() - ref["paper"]["validity"][cls]["floors"]["d30s"]) < 1e-12
        checks.append(f"{year} floors: per-event J reproduces the published catalogue-population floors")
        cells = {"all": paper, **{c: paper.filter(pl.col("validity") == c) for c in CLASSES},
                 "stratified": test.filter(pl.col("reason") == "stratified"),
                 "invalid_stratum": test.filter(pl.col("reason") == "rpki_invalid_sample")}
        block = {}
        for name, frame in cells.items():
            if frame.height == 0:
                continue
            m, draws = dayblock(frame, rng)
            block[name] = {"mean": m, "ci95": percentile(draws), "test_events": frame.height, "days": frame["day"].n_unique()}
            if name == "all":
                pooled_draws[year] = (m, np.asarray(draws))
        # class differences with joint day resampling (classes share days, so they are resampled together)
        per_day = paper.group_by("day", "validity").agg(pl.col("J").sum().alias("s"), pl.len().alias("n"))
        days = sorted(paper["day"].unique().to_list())
        pos = {d: i for i, d in enumerate(days)}
        sums = {c: np.zeros(len(days)) for c in CLASSES}
        counts = {c: np.zeros(len(days)) for c in CLASSES}
        for d, c, s, n in per_day.iter_rows():
            sums[c][pos[d]], counts[c][pos[d]] = s, n
        diffs = {"invalid_minus_unknown": ("invalid", "unknown"), "unknown_minus_valid": ("unknown", "valid"),
                 "invalid_minus_valid": ("invalid", "valid")}
        draws = {k: [] for k in diffs}
        for _ in range(DRAWS):
            pick = rng.integers(0, len(days), size=len(days))
            means = {c: sums[c][pick].sum() / max(counts[c][pick].sum(), 1) for c in CLASSES}
            for k, (a, b) in diffs.items():
                draws[k].append(means[a] - means[b])
        block["class_differences"] = {k: {"diff": block[a]["mean"] - block[b]["mean"], "ci95": percentile(draws[k])}
                                      for k, (a, b) in diffs.items()}
        facts["years"][str(year)]["floor_dayblock"] = block

        # visibility-matched comparison inside the stratified sample, without catalogue labels
        vis = test.filter((pl.col("reason") == "stratified") & ~pl.col("labelled")
                          & (pl.col("max_peers") >= 10) & (pl.col("max_collectors") >= 3))
        facts["years"][str(year)]["visibility_matched"] = {
            **{c: {"floor": (float(vis.filter(pl.col("validity") == c)["J"].mean())
                             if vis.filter(pl.col("validity") == c).height else None),
                   "test_events": vis.filter(pl.col("validity") == c).height,
                   "extent_p50": (float(vis.filter(pl.col("validity") == c)["extent"].median())
                                  if vis.filter(pl.col("validity") == c).height else None)} for c in CLASSES},
            "label_free_invalid_stratum": {"floor": float(cells["invalid_stratum"]["J"].mean()) if cells["invalid_stratum"].height else None,
                                           "test_events": cells["invalid_stratum"].height}}

        if year in (2024, 2025):
            bins = {}
            for kind, column, edges in (("extent", "extent", EXTENT_BINS), ("duration", "duration_min", DURATION_BINS)):
                bins[kind] = []
                for lo, hi, label in edges:
                    sub = paper.filter((pl.col(column) >= lo) & (pl.col(column) <= hi))
                    labelled = sub.filter(pl.col("labelled"))
                    bins[kind].append({"bin": [lo, hi], "label": label, **{
                        c: {"floor": float(sub.filter(pl.col("validity") == c)["J"].mean()) if sub.filter(pl.col("validity") == c).height else None,
                            "test_events": sub.filter(pl.col("validity") == c).height,
                            "share_of_class_test_events": sub.filter(pl.col("validity") == c).height / paper.filter(pl.col("validity") == c).height,
                            "radar_labelled_floor": float(labelled.filter(pl.col("validity") == c)["J"].mean()) if labelled.filter(pl.col("validity") == c).height else None,
                            "radar_labelled_test_events": labelled.filter(pl.col("validity") == c).height} for c in CLASSES}})
            facts["years"][str(year)]["floor_bins"] = bins

    changes = {}
    for a, b in ((2023, 2024), (2024, 2025), (2025, 2026)):
        (ma, da), (mb, db) = pooled_draws[a], pooled_draws[b]
        changes[f"{a}_to_{b}"] = {"diff": mb - ma, "ci95": percentile(db - da)}
    facts["pooled_floor_changes"] = changes

    # ---------------------------------------------------------------- ranges quoted in the prose
    y = facts["years"]
    def span(values): return [min(values), max(values)]
    gap = {g: [y[str(k)]["recovery_by_gap"][g] for k in YEARS] for g, *_ in GAPS}
    fr = [y[str(k)]["frontier_diff"] for k in YEARS]
    vm = [y[str(k)]["visibility_matched"] for k in YEARS]
    summary = {
        "recovery": {
            "share_lt1min": span([x["share_of_links"] for x in gap["lt1min"]]),
            "share_gt15min": span([x["share_of_links"] for x in gap["gt15min"]]),
            "diff_lt1min": span([x["paired_diff_mean"] for x in gap["lt1min"]]),
            "diff_lt1min_all_ci_below_zero": all(x["paired_diff_ci95"][1] < 0 for x in gap["lt1min"]),
            "return_slower_lt1min": span([x["return_slower_share"] for x in gap["lt1min"]]),
            "extent_ratio_lt1min": span([x["extent_ratio_p50"] for x in gap["lt1min"]]),
            "diff_1to15min": span([x["paired_diff_mean"] for x in gap["1to15min"]]),
            "diff_gt15min": span([x["paired_diff_mean"] for x in gap["gt15min"]]),
            "diff_gt15min_all_ci_above_zero": all(x["paired_diff_ci95"][0] > 0 for x in gap["gt15min"]),
            "outward_t90_gt15min": span([x["outward_t90_s_p50"] for x in gap["gt15min"]]),
            "return_t90_gt15min": span([x["return_t90_s_p50"] for x in gap["gt15min"]]),
            "return_t90_shorter_gt15min_every_year": all(x["return_t90_s_p50"] < x["outward_t90_s_p50"] for x in gap["gt15min"]),
            "return_slower_gt15min": span([x["return_slower_share"] for x in gap["gt15min"]]),
            "extent_ratio_gt15min": span([x["extent_ratio_p50"] for x in gap["gt15min"]]),
        },
        "frontier": {
            "invalid_minus_valid": span([x["invalid_minus_valid"]["diff"] for x in fr]),
            "invalid_minus_unknown": span([x["invalid_minus_unknown"]["diff"] for x in fr]),
            "all_paper_ci_above_zero": all(x[k]["ci95"][0] > 0 for x in fr for k in ("invalid_minus_valid", "invalid_minus_unknown")),
            "stratum_minus_valid": span([x["invalid_stratum_minus_valid"]["diff"] for x in fr if "invalid_stratum_minus_valid" in x]),
            "stratum_minus_unknown": span([x["invalid_stratum_minus_unknown"]["diff"] for x in fr if "invalid_stratum_minus_unknown" in x]),
            "all_stratum_ci_above_zero": all(x[k]["ci95"][0] > 0 for x in fr for k in ("invalid_stratum_minus_valid", "invalid_stratum_minus_unknown") if k in x),
        },
        "visibility_matched": {
            "unknown_floor": span([x["unknown"]["floor"] for x in vm]), "unknown_test_events": span([x["unknown"]["test_events"] for x in vm]),
            "valid_floor": span([x["valid"]["floor"] for x in vm]), "valid_test_events": span([x["valid"]["test_events"] for x in vm]),
            "invalid_floor": span([x["invalid"]["floor"] for x in vm]), "invalid_test_events": span([x["invalid"]["test_events"] for x in vm]),
            "label_free_stratum_floor": span([x["label_free_invalid_stratum"]["floor"] for x in vm]),
            "unknown_and_valid_below_stratum_every_year": all(max(x["unknown"]["floor"], x["valid"]["floor"]) < x["label_free_invalid_stratum"]["floor"] for x in vm),
        },
        "floor_bins": {str(k): {
            "invalid_above_unknown_extent_le200": all(b["invalid"]["floor"] > b["unknown"]["floor"] for b in y[str(k)]["floor_bins"]["extent"][:3]),
            "invalid_above_unknown_duration_le15": all(b["invalid"]["floor"] > b["unknown"]["floor"] for b in y[str(k)]["floor_bins"]["duration"][:2]),
            "valid_lowest_every_bin": all(b["valid"]["floor"] < min(b["invalid"]["floor"], b["unknown"]["floor"])
                                          for kind in ("extent", "duration") for b in y[str(k)]["floor_bins"][kind]),
            "radar_labelled_invalid_above_unknown_extent_le200": all(b["invalid"]["radar_labelled_floor"] > b["unknown"]["radar_labelled_floor"] for b in y[str(k)]["floor_bins"]["extent"][:3]),
            "radar_labelled_invalid_above_unknown_duration_le15": all(b["invalid"]["radar_labelled_floor"] > b["unknown"]["radar_labelled_floor"] for b in y[str(k)]["floor_bins"]["duration"][:2]),
            "radar_labelled_invalid_below_unknown_extent_gt200": y[str(k)]["floor_bins"]["extent"][3]["invalid"]["radar_labelled_floor"] < y[str(k)]["floor_bins"]["extent"][3]["unknown"]["radar_labelled_floor"],
            "share_of_invalid_test_events_extent_le200": sum(b["invalid"]["share_of_class_test_events"] for b in y[str(k)]["floor_bins"]["extent"][:3]),
            "share_of_invalid_test_events_duration_le15": sum(b["invalid"]["share_of_class_test_events"] for b in y[str(k)]["floor_bins"]["duration"][:2]),
            "extent_gt200": {c: y[str(k)]["floor_bins"]["extent"][3][c] for c in CLASSES},
            "duration_gt15": {c: y[str(k)]["floor_bins"]["duration"][2][c] for c in CLASSES},
        } for k in (2024, 2025)},
        "dayblock": {
            "class_differences_all_ci_exclude_zero": {k: [str(yr) for yr in YEARS if y[str(yr)]["floor_dayblock"]["class_differences"][k]["ci95"][0] > 0]
                                                     for k in ("invalid_minus_unknown", "unknown_minus_valid", "invalid_minus_valid")},
        },
    }
    facts["summary"] = summary
    facts["provenance"] = {
        "generator": "scripts/paper_measurement_checks.py",
        "command": "PYTHONPATH=src .venv/bin/python -I -B scripts/paper_measurement_checks.py data/corrected-release-20261016 paper/generated",
        "data_root": "corrected release of 2026-10-16 (data/corrected-release-20261016, git-ignored local copy of the released data)",
        "binding": "events, rpki_validity and pairs files must match the SHA-256 listed in docs/paper/corrected-recovery-2026-10-16.json "
                   "or paper/generated/propagation-facts.json; the per-event rov_frontier parquet files are not listed there and are "
                   "bound by reproducing the published class means and event counts of paper/generated/frontier_facts.json",
        "not_computed": "ROV shares by identifier-gap stratum: the RoVista series (rpki/rovista/as_rov_series.parquet) is not in the "
                        "local release copy"}
    facts["checks"] = checks
    facts["inputs_sha256"] = inputs

    # ---------------------------------------------------------------- tables
    def row(label, values):
        return label + " & " + " & ".join(values) + r" \\" + "\n"

    def f2(x): return "--" if x is None else f"{x:.2f}"
    def ci(c): return f"[${c[0]:+.2f}$, ${c[1]:+.2f}$]"
    def sgn(x): return f"${x:+.3f}$"
    head = "\\begin{tabular}{lrrrrr}\n\\toprule\n" + row("", map(str, YEARS)) + "\\midrule\n"
    t = head
    y = facts["years"]
    t += row(r"links, $<1$ / 1--15 / $\geq 15$\,min (\%)", [" / ".join(f"{100*y[str(k)]['recovery_by_gap'][g]['share_of_links']:.0f}" for g, *_ in GAPS) for k in YEARS])
    for g, _, _, label in GAPS:
        t += r"\midrule" + "\n" + r"\multicolumn{6}{l}{\emph{identifier gap " + label + r"}} \\" + "\n"
        r = [y[str(k)]["recovery_by_gap"][g] for k in YEARS]
        t += row("links", [f"{x['links']:,}" for x in r])
        t += row(r"$\Jac_{30}$, $O$ / $R$", [f"{x['outward_j30_mean']:.2f} / {x['return_j30_mean']:.2f}" for x in r])
        t += row(r"paired $\Delta\Jac$", [sgn(x["paired_diff_mean"]) for x in r])
        t += row(r"\quad 95\,\% CI", [ci(x["paired_diff_ci95"]) for x in r])
        t += row(r"$t_{90}$ p50 (s), $O$ / $R$", [f"{x['outward_t90_s_p50']:.0f} / {x['return_t90_s_p50']:.0f}" for x in r])
        t += row("return slower", [f"{100*x['return_slower_share']:.0f}" + r"\,\%" for x in r])
        t += row(r"extent $R/O$, p50", [f"{x['extent_ratio_p50']:.2f}" for x in r])
        t += row(r"\quad 95\,\% CI", [f"[{x['extent_ratio_p50_ci95'][0]:.2f}, {x['extent_ratio_p50_ci95'][1]:.2f}]" for x in r])
    (args.out / "recovery_gap.tex").write_text("% Generated by scripts/paper_measurement_checks.py\n" + t + "\\bottomrule\n\\end{tabular}\n")

    # rows of the body summary table (tab:recovery-summary): pooled values as published, plus two gap columns
    t = ""
    for k in YEARS:
        p, o, r = recovery_json[str(k)]["pairs"], recovery_json[str(k)]["overlap"], recovery_json[str(k)]["rov"]
        d, g = p["paired_j30_diff_recovery_minus_hijack"], y[str(k)]["recovery_by_gap"]
        share = r["enforcing_share"]
        t += row(str(k), [f"{p['pairs']:,}", f"{100*g['lt1min']['share_of_links']:.0f}" + r"\,\%",
                          f"${d['mean']:+.3f}$ " + ci(d["ci95"]),
                          f"${g['gt15min']['paired_diff_mean']:+.3f}$ " + ci(g["gt15min"]["paired_diff_ci95"]),
                          f"{p['hijack']['t90_s_p50']:.1f} / {p['recovery']['t90_s_p50']:.1f}",
                          f"{100*p['recovery_slower_t90_frac']:.1f}" + r"\,\%",
                          f"{p['recovery_reach_over_hijack_reach_p50']:.2f}" + r"$\times$",
                          f"{100*o['recoverers_never_carried_hijack_mean']:.1f}" + r"\,\%",
                          f"{share['R-H']['share']:.2f} / {share['R&H']['share']:.2f}"])
    (args.out / "recovery_summary_rows.tex").write_text("% Generated by scripts/paper_measurement_checks.py (rows of tab:recovery-summary)\n" + t)

    t = "\\begin{tabular}{lrrrr}\n\\toprule\n" + row("year", ["invalid $-$ valid", "invalid $-$ unknown", "stratum $-$ valid", "stratum $-$ unknown"]) + "\\midrule\n"
    for k in YEARS:
        d = y[str(k)]["frontier_diff"]
        cell = lambda key: "--" if key not in d else f"${d[key]['diff']:+.2f}$ " + ci(d[key]["ci95"])
        t += row(str(k), [cell("invalid_minus_valid"), cell("invalid_minus_unknown"),
                          cell("invalid_stratum_minus_valid"), cell("invalid_stratum_minus_unknown")])
    (args.out / "frontier_diff.tex").write_text("% Generated by scripts/paper_measurement_checks.py\n" + t + "\\bottomrule\n\\end{tabular}\n")

    t = "\\begin{tabular}{llrrrrrr}\n\\toprule\n" + row(" & bin", [r"\multicolumn{3}{c}{2024: invalid / unknown / valid}", r"\multicolumn{3}{c}{2025: invalid / unknown / valid}"]).replace(" & \\multicolumn{3}{c}{2025", " & \\multicolumn{3}{c}{2025") + "\\midrule\n"
    for kind, title in (("extent", r"extent at 2\,h (ASes)"), ("duration", "identifier duration")):
        for i in range(len(y["2024"]["floor_bins"][kind])):
            cells = []
            for k in (2024, 2025):
                b = y[str(k)]["floor_bins"][kind][i]
                cells += [f"{f2(b[c]['floor'])} ({b[c]['test_events']:,})" for c in CLASSES]
            t += row((title if i == 0 else "") + " & " + y["2024"]["floor_bins"][kind][i]["label"], cells)
        if kind == "extent":
            t += "\\midrule\n"
    (args.out / "floor_bins.tex").write_text("% Generated by scripts/paper_measurement_checks.py\n" + t + "\\bottomrule\n\\end{tabular}\n")

    t = head
    for name, label in (("all", "all events"), ("invalid", r"\quad invalid"), ("unknown", r"\quad unknown"), ("valid", r"\quad valid"),
                        ("stratified", "stratified sample"), ("invalid_stratum", "label-free invalid")):
        t += row(label, ["--" if name not in y[str(k)]["floor_dayblock"] else
                         f"{y[str(k)]['floor_dayblock'][name]['ci95'][0]:.2f}--{y[str(k)]['floor_dayblock'][name]['ci95'][1]:.2f}" for k in YEARS])
    t += row("test days", [f"{y[str(k)]['floor_dayblock']['all']['days']}" for k in YEARS])
    t += r"\midrule" + "\n" + r"\multicolumn{6}{l}{\emph{difference between classes, same day blocks}} \\" + "\n"
    for key, label in (("invalid_minus_unknown", "invalid $-$ unknown"), ("unknown_minus_valid", "unknown $-$ valid")):
        t += row(label, [f"${y[str(k)]['floor_dayblock']['class_differences'][key]['diff']:+.2f}$" for k in YEARS])
        t += row(r"\quad 95\,\% CI", [ci(y[str(k)]["floor_dayblock"]["class_differences"][key]["ci95"]) for k in YEARS])
    t += r"\midrule" + "\n" + row(r"all events, change from previous year", ["--"] + [
        "--" if f"{k-1}_to_{k}" not in changes else f"${changes[f'{k-1}_to_{k}']['diff']:+.2f}$ " + ci(changes[f"{k-1}_to_{k}"]["ci95"])
        for k in list(YEARS)[1:]])
    (args.out / "floor_dayblock.tex").write_text("% Generated by scripts/paper_measurement_checks.py\n" + t + "\\bottomrule\n\\end{tabular}\n")
    def tidy(o):  # 10 decimals: removes last-bit noise of parallel float sums, so reruns are byte-identical
        if isinstance(o, float): return round(o, 10)
        if isinstance(o, dict): return {k: tidy(v) for k, v in o.items()}
        if isinstance(o, list): return [tidy(v) for v in o]
        return o
    (args.out / "measurement-checks-facts.json").write_text(json.dumps(tidy(facts), indent=1, sort_keys=False) + "\n")
    print("\n".join(checks))


if __name__ == "__main__":
    main()
