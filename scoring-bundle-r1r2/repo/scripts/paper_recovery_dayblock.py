#!/usr/bin/env python3
"""Day-block intervals for the matched outward/return recovery results (revision analysis, review round 2, W5/REQ-6).

The recovery section reports, per year, the paired difference of the 30-s persistence floor (return minus outward,
link-weighted mean over matched links) and the median ratio of return to outward extent, with intervals that resample
connected components of shared events (1,000 draws, seed 0). Almost every component is one link, so those intervals
treat links as nearly independent. This script recomputes the same point estimates from the retained per-link tables of
the corrected release and adds intervals that resample whole UTC days instead.

Resampling unit ("day block"): the UTC day of the outward identifier (first 8 characters of hijack_id). Days that are
joined by a connected component of shared events (a return event shared by links whose outward identifiers fall on
different days) are merged into one unit, so links that share an event are always drawn together. Statistics:

* mean paired difference J30(R) - J30(O), the ratio of resampled sums (link-weighted, as published);
* median of |R| / |O| over links with |O| > 0 (exact weighted median of the resampled multiset).

Both are computed for all links and for the identifier-gap strata < 1 min, 1-15 min and > 15 min (gap_s in [0, 60),
[60, 900), [900, 86400)); a stratum is resampled within its own links. Percentile 95 % intervals, 10,000 draws, numpy
default_rng(1701), a fresh generator per year, stratum and statistic. For comparison the component bootstrap is also run
with the same 10,000 draws and seed, and the published component intervals (1,000 draws, seed 0) are reproduced
exactly before anything else (scripts/paper_measurement_checks.py; docs/paper/corrected-recovery-2026-10-16.json).
No published number is changed; this is a revision analysis beside the published table.

Usage (repo root):
    .venv/bin/python -B scripts/paper_recovery_dayblock.py data/corrected-release-20261016 \
        --out-json paper/generated/recovery_dayblock.json --out-tex paper/generated/recovery_dayblock.tex
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import polars as pl

YEARS = range(2022, 2027)
DRAWS, SEED = 10_000, 1701
PUB_DRAWS, PUB_SEED = 1000, 0
GAPS = (("lt1min", 0, 60, r"$<1$\,min"), ("1to15min", 60, 900, r"1--15\,min"), ("gt15min", 900, 86400, r"$\geq 15$\,min"))
GAP_JSON = {"lt1min": "gap<1min", "1to15min": "gap 1-15min", "gt15min": "gap>15min"}
REPO = Path(__file__).resolve().parents[1]
# Published point estimates of generated/recovery_summary_rows.tex (3 decimals), checked before any analysis.
PUBLISHED_ALL = {2022: -0.005, 2023: -0.052, 2024: -0.080, 2025: -0.161, 2026: -0.049}
PUBLISHED_GT15 = {2022: 0.132, 2023: 0.100, 2024: 0.034, 2025: 0.092, 2026: 0.062}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise SystemExit(f"STOP: {message}")


def percentile(draws):
    return [float(x) for x in np.percentile(np.asarray(draws, dtype=float), [2.5, 97.5])]


# ---- the published component bootstrap, copied unchanged from scripts/paper_measurement_checks.py -----------------
def published_cluster_draws(values, groups, stat, rng):
    _, index = np.unique(groups, return_inverse=True)
    order = np.argsort(index, kind="stable")
    starts = np.searchsorted(index[order], np.arange(index.max() + 1))
    ends = np.append(starts[1:], len(order))
    members = [order[s:e] for s, e in zip(starts, ends)]
    n = len(members)
    out = []
    for _ in range(PUB_DRAWS):
        pick = rng.integers(0, n, size=n)
        out.append(stat(values[np.concatenate([members[i] for i in pick])]))
    return out


def published_mean_ci(values, groups, rng):
    values, groups = np.asarray(values, float), np.asarray(groups)
    _, index = np.unique(groups, return_inverse=True)
    n = index.max() + 1
    totals, counts = np.bincount(index, weights=values, minlength=n), np.bincount(index, minlength=n)
    draws = []
    for _ in range(PUB_DRAWS):
        pick = rng.integers(0, n, size=n)
        draws.append(totals[pick].sum() / counts[pick].sum())
    return percentile(draws)


# ---- block bootstrap used for the new intervals --------------------------------------------------------------------
def block_mean_draws(values, unit, rng, draws=DRAWS):
    n = unit.max() + 1
    totals, counts = np.bincount(unit, weights=values, minlength=n), np.bincount(unit, minlength=n)
    out = np.empty(draws)
    for i in range(draws):
        pick = rng.integers(0, n, size=n)
        out[i] = totals[pick].sum() / counts[pick].sum()
    return out


def weighted_median(sorted_values, weights):
    """Median of the multiset that repeats sorted_values[i] weights[i] times (np.median convention)."""
    cw = np.cumsum(weights)
    total = int(cw[-1])
    k = total // 2
    upper = sorted_values[np.searchsorted(cw, k, side="right")]
    if total % 2:
        return float(upper)
    return float((sorted_values[np.searchsorted(cw, k - 1, side="right")] + upper) / 2)


def block_median_draws(values, unit, rng, draws=DRAWS):
    n = unit.max() + 1
    order = np.argsort(values, kind="stable")
    v, u = values[order], unit[order]
    out = np.empty(draws)
    for i in range(draws):
        pick = rng.integers(0, n, size=n)
        out[i] = weighted_median(v, np.bincount(pick, minlength=n)[u])
    return out


def self_test():
    rng = np.random.default_rng(7)
    for _ in range(200):
        values = rng.integers(0, 20, size=rng.integers(1, 40)).astype(float) / 3
        unit = rng.integers(0, 6, size=len(values))
        unit = np.unique(unit, return_inverse=True)[1]
        n = unit.max() + 1
        pick = rng.integers(0, n, size=n)
        expanded = np.concatenate([values[unit == j] for j in pick])
        order = np.argsort(values, kind="stable")
        require(abs(weighted_median(values[order], np.bincount(pick, minlength=n)[unit[order]]) - np.median(expanded))
                < 1e-12, "weighted median self-test failed")


def merged_day_units(days, components):
    """Union of UTC days and shared-event components: returns dense unit ids and merge statistics."""
    parent = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for d, c in zip(days, components):
        a, b = find(("d", d)), find(("c", c))
        if a != b:
            parent[max(a, b)] = min(a, b)
    roots = [find(("d", d)) for d in days]
    unit = np.unique(np.array([f"{r[0]}:{r[1]}" for r in roots]), return_inverse=True)[1]
    return unit, {"utc_days": len(set(days)), "units": int(unit.max() + 1),
                  "days_merged_into_multi_day_units": len(set(days)) - int(unit.max() + 1)}


def summary(point, comp, day):
    return {"point": point, "component_ci95_10k": comp, "dayblock_ci95_10k": day}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("data", type=Path)
    ap.add_argument("--out-json", type=Path, required=True)
    ap.add_argument("--out-tex", type=Path, required=True)
    args = ap.parse_args()
    self_test()
    recovery = json.loads((REPO / "docs/paper/corrected-recovery-2026-10-16.json").read_text())
    facts = json.loads((REPO / "paper/generated/measurement-checks-facts.json").read_text())["years"]
    out = {"kind": "recovery_dayblock_revision_analysis", "replaces_published_values": False,
           "method": {"unit": "UTC day of the outward identifier (hijack_id[:8]), days joined by a shared-event "
                              "component merged into one unit",
                      "statistics": {"mean_diff": "link-weighted mean of r_j30 - h_j30 (ratio of resampled sums)",
                                     "median_ratio": "median of r_reach / h_reach over links with h_reach > 0",
                                     "largest_day": "post hoc: the raw UTC day (hijack_id[:8]) with most links, its mean_diff, "
                                                    "and mean_diff without it (descriptive, no interval)"},
                      "draws": DRAWS, "seed": SEED, "interval": "percentile 95 %",
                      "rng": "fresh numpy default_rng(1701) per year, stratum and statistic",
                      "published_component_bootstrap": {"draws": PUB_DRAWS, "seed": PUB_SEED,
                                                        "reproduced_before_analysis": True},
                      "gap_strata_s": {k: [lo, hi] for k, lo, hi, _ in GAPS}},
           "inputs_sha256": {}, "source_sha256": sha(Path(__file__)), "years": {}}
    for year in YEARS:
        suffix = "" if year == 2022 else "_labelled"
        rel = f"eventset/{year}_recovery_first_transition/pairs{suffix}.parquet"
        digest = sha(args.data / rel)
        require(recovery["inputs_sha256"].get(rel) == digest, f"{rel}: hash differs from the paper's recorded input")
        out["inputs_sha256"][rel] = digest
        pairs = pl.read_parquet(args.data / rel)
        ref = recovery["years"][str(year)]["pairs"]
        require(pairs.height == ref["pairs"], f"{year}: link count differs")
        require(pairs["hijack_id"].str.contains(r"^\d{8}T\d{6}_").all(), f"{year}: unexpected outward identifier")
        diff = (pairs["r_j30"] - pairs["h_j30"]).to_numpy()
        comp = pairs["bootstrap_component"].to_numpy()

        # 1. reproduce the published values exactly
        pooled = float(diff.mean())
        require(round(pooled, 4) == ref["paired_j30_diff_recovery_minus_hijack"]["mean"]
                and round(pooled, 3) == PUBLISHED_ALL[year], f"{year}: pooled difference not reproduced")
        pub_ci = [round(x, 4) for x in published_mean_ci(diff, comp, np.random.default_rng(PUB_SEED))]
        require(pub_ci == ref["paired_j30_diff_recovery_minus_hijack"]["ci95"], f"{year}: pooled component CI")
        frame = pairs.filter(pl.col("h_reach") > 0)
        ratio_all = (frame["r_reach"] / frame["h_reach"]).to_numpy()
        require(round(float(np.median(ratio_all)), 3) == ref["recovery_reach_over_hijack_reach_p50"],
                f"{year}: pooled median extent ratio not reproduced")
        rng_pub = np.random.default_rng(PUB_SEED)  # the published strata share one generator per year, in this order
        published_strata = {}
        for key, lo, hi, _ in GAPS:
            g = pairs.filter((pl.col("gap_s") >= lo) & (pl.col("gap_s") < hi))
            gf = g.filter(pl.col("h_reach") > 0)
            d = (g["r_j30"] - g["h_j30"]).to_numpy()
            r = (gf["r_reach"] / gf["h_reach"]).to_numpy()
            dci = published_mean_ci(d, g["bootstrap_component"].to_numpy(), rng_pub)
            rci = percentile(published_cluster_draws(r, gf["bootstrap_component"].to_numpy(), np.median, rng_pub))
            pub = facts[str(year)]["recovery_by_gap"][key]
            require(g.height == pub["links"] and abs(float(d.mean()) - pub["paired_diff_mean"]) < 1e-9
                    and np.allclose(dci, pub["paired_diff_ci95"], atol=1e-9, rtol=0)
                    and abs(float(np.median(r)) - pub["extent_ratio_p50"]) < 1e-9
                    and np.allclose(rci, pub["extent_ratio_p50_ci95"], atol=1e-9, rtol=0),
                    f"{year} {key}: published stratum values not reproduced")
            published_strata[key] = {"paired_diff_ci95": dci, "extent_ratio_p50_ci95": rci,
                                     "paired_diff_mean": float(d.mean())}
        require(round(published_strata["gt15min"]["paired_diff_mean"], 3) == PUBLISHED_GT15[year],
                f"{year}: gap > 15 min difference not reproduced")

        # 2. new intervals
        days = pairs["hijack_id"].str.slice(0, 8).to_list()
        year_out = {"links": pairs.height, "components": int(len(np.unique(comp)))}
        populations = [("all", pairs)] + [(key, pairs.filter((pl.col("gap_s") >= lo) & (pl.col("gap_s") < hi)))
                                          for key, lo, hi, _ in GAPS]
        for key, g in populations:
            d = (g["r_j30"] - g["h_j30"]).to_numpy()
            gcomp = g["bootstrap_component"].to_numpy()
            gunit, merge = merged_day_units(g["hijack_id"].str.slice(0, 8).to_list(), gcomp.tolist())
            cunit = np.unique(gcomp, return_inverse=True)[1]
            gf_mask = (g["h_reach"] > 0).to_numpy()
            r = (g["r_reach"] / g["h_reach"]).to_numpy()[gf_mask]
            entry = {
                "links": g.height, "links_with_outward_extent": int(gf_mask.sum()), **merge,
                "max_links_per_unit": int(np.bincount(gunit).max()),
                "mean_diff": summary(float(d.mean()),
                                     percentile(block_mean_draws(d, cunit, np.random.default_rng(SEED))),
                                     percentile(block_mean_draws(d, gunit, np.random.default_rng(SEED)))),
                "median_ratio": summary(float(np.median(r)),
                                        percentile(block_median_draws(r, cunit[gf_mask], np.random.default_rng(SEED))),
                                        percentile(block_median_draws(r, gunit[gf_mask], np.random.default_rng(SEED)))),
            }
            # post hoc leave-largest-day-out check (review round 3 NEW-8): the raw UTC day with most links; ties go to the
            # earliest day (np.unique sorts); descriptive, no interval
            gday = np.asarray(g["hijack_id"].str.slice(0, 8).to_list())
            days_u, days_n = np.unique(gday, return_counts=True)
            keep = gday != days_u[np.argmax(days_n)]
            entry["largest_day"] = {"day": str(days_u[np.argmax(days_n)]), "links": int(days_n.max()),
                                    "mean_diff": float(d[~keep].mean()), "links_without": int(keep.sum()),
                                    "mean_diff_without": float(d[keep].mean()) if keep.any() else None}
            if key == "all":
                entry["mean_diff"]["published_component_ci95"] = ref["paired_j30_diff_recovery_minus_hijack"]["ci95"]
                entry["median_ratio"]["published_component_ci95"] = None  # the pooled ratio is published without one
            else:
                entry["mean_diff"]["published_component_ci95"] = published_strata[key]["paired_diff_ci95"]
                entry["median_ratio"]["published_component_ci95"] = published_strata[key]["extent_ratio_p50_ci95"]
            for stat in ("mean_diff", "median_ratio"):
                lo_, hi_ = entry[stat]["dayblock_ci95_10k"]
                ref_value = 0.0 if stat == "mean_diff" else 1.0
                entry[stat]["dayblock_excludes_" + ("zero" if stat == "mean_diff" else "one")] = bool(
                    lo_ > ref_value or hi_ < ref_value)
            year_out[key] = entry
            print(f"{year} {key:9s} links={g.height:5d} units={merge['units']:3d} "
                  f"dJ {entry['mean_diff']['point']:+.3f} comp {np.round(entry['mean_diff']['component_ci95_10k'], 3)} "
                  f"day {np.round(entry['mean_diff']['dayblock_ci95_10k'], 3)} | ratio {entry['median_ratio']['point']:.3f} "
                  f"day {np.round(entry['median_ratio']['dayblock_ci95_10k'], 3)}", flush=True)
        out["years"][str(year)] = year_out
    args.out_json.write_text(json.dumps(out, indent=1) + "\n")
    write_tex(args.out_tex, out)
    print("wrote", args.out_json, args.out_tex)


def write_tex(path, out):
    years = [str(y) for y in YEARS]

    def row(label, cells):
        return label + " & " + " & ".join(cells) + " \\\\\n"

    def ci(c, digits):
        if c is None:
            return "--"
        return f"[{c[0]:+.{digits}f}, {c[1]:+.{digits}f}]".replace("-", "$-$") if digits == 3 else \
            f"[{c[0]:.{digits}f}, {c[1]:.{digits}f}]"

    t = ["% Generated by scripts/paper_recovery_dayblock.py; do not edit by hand.",
         "% component CI: the published connected-component bootstrap (1,000 draws, seed 0), reproduced exactly; the",
         "% pooled extent ratio is published without an interval, so its row shows the component bootstrap with",
         "% 10,000 draws, seed 1701 (marked *). day-block CI: UTC days of the outward identifier, days joined by a",
         "% shared-event component merged, 10,000 draws, seed 1701. Percentile 95 % intervals.",
         "\\begin{tabular}{lrrrrr}", "\\toprule", " & " + " & ".join(years) + " \\\\", "\\midrule"]
    body = row("day units (all links)", [str(out["years"][y]["all"]["units"]) for y in years])
    body += row("max.\\ links per unit", [f"{out['years'][y]['all']['max_links_per_unit']:,}" for y in years])
    for key, label in (("all", "all links"), ("lt1min", r"identifier gap $<1$\,min"),
                       ("1to15min", r"identifier gap 1--15\,min"), ("gt15min", r"identifier gap $\geq 15$\,min")):
        body += "\\midrule\n" + f"\\multicolumn{{6}}{{l}}{{\\emph{{{label}}}}} \\\\\n"
        e = [out["years"][y][key] for y in years]
        body += row("paired $\\Delta\\Jac$", [f"${x['mean_diff']['point']:+.3f}$" for x in e])
        body += row("\\quad component CI", [ci(x["mean_diff"]["published_component_ci95"], 3) for x in e])
        body += row("\\quad day-block CI", [ci(x["mean_diff"]["dayblock_ci95_10k"], 3) for x in e])
        body += row("extent $R/O$, p50", [f"{x['median_ratio']['point']:.2f}" for x in e])
        body += row("\\quad component CI" + ("*" if key == "all" else ""),
                    [ci(x["median_ratio"]["published_component_ci95"] or x["median_ratio"]["component_ci95_10k"], 2)
                     for x in e])
        body += row("\\quad day-block CI", [ci(x["median_ratio"]["dayblock_ci95_10k"], 2) for x in e])
    t.append(body.rstrip("\n"))
    t += ["\\bottomrule", "\\end{tabular}", ""]
    Path(path).write_text("\n".join(t))


if __name__ == "__main__":
    main()
