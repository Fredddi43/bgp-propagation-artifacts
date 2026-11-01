#!/usr/bin/env python3
"""SAGE with history minus persistence on the prespecified issue-time slice, R1 and R2 (revision analysis, review
round 5, Opus A-R2 / DA #2 / NEW-5).

The slice (sections/app-protocol.tex, tab:recipe): early growth, the number of members first available in
(delta/2, delta], is at least 12 at 30 s or 22 at 60 s; the cut was chosen on the 2025 training split only. Slice
Jaccard uses its own decision threshold, calibrated on validation slice events (the record field
``two_threshold_jaccard``; a committed baseline decision keeps its own set, so its slice Jaccard is ``jaccard``, exactly
as in bgbench.forecast_custodian_eval). Persistence forecasts the seed set and needs no threshold; its Jaccard is
``jaccard_persist`` in R1 and s / (s + R) in R2 (s = |seed_asns|, R = new_members; the identity holds on every R1 record
and is checked there by paper_set_errors_r2.r1_seed_counts).

Steps, in order; the script stops on any failed check before writing:
1. Load R1 and R2 with the loaders of scripts/paper_set_errors_r2.py (R1 per-event files checked against the released
   report's per_event_sha256; R2 arm identities against the released primary report), extended by the slice fields.
2. Slice membership: the recorded in_issue_time_slice flag must equal the frozen rule (early_growth >= 12 / 22) on every
   learned record, every arm and training seed must agree, and the slice sizes must be the published 966 / 502 (R1) and
   372 / 211 (R2).
3. Reproduce every published slice-Jaccard contrast (R1: C1-C4 at 30/60 s; R2: C1-C4 at 30/60 s, C5 and C6 at 60 s):
   difference and interval to 1e-12, events and blocks exactly, with the released blocks (incident-day blocks over the
   whole cohort, restricted to slice events).
4. New: arm minus persistence on the slice, for SAGE with history (the requested contrast), online history (mean size
   rule), and the frozen 2025 SAGE (R2, 60 s), with the same bootstrap (training seeds then incident-day blocks,
   10,000 repetitions, seed 1701; bgbench.forecast_ranking.paired_bootstrap). Also given, labelled as secondary: SAGE
   with its full-target threshold (``jaccard``) on the slice events, and the share of slice events on which the arm's
   slice Jaccard equals persistence's (an upper bound on "adds nothing", as in set_errors_r2.json).

Ordinary 95 % intervals, unadjusted p-values, descriptive. Not a prespecified contrast (the prespecified slice family
holds C1-C6 only). No model is retrained, no prediction regenerated, no label file read.

Usage (repo root):
    .venv/bin/python -B scripts/paper_slice_vs_persistence.py \
        --r1-report .agents/operations/r1-v11-posteval-20261024/evidence/released/report.json \
        --r1-per-event <local copy of results/per_event> \
        --r1-arm-spec .agents/operations/r1-arm-spec-20261020/arm-spec.json \
        --r1-manifest-30 .agents/operations/r1-v11-posteval-20261024/evidence/released/retrospective-2025-v6-d30.json \
        --r1-manifest-60 .agents/operations/r1-v11-posteval-20261024/evidence/released/retrospective-2025-v6-d60.json \
        --r2-scores <local copy of primary-scores.json> \
        --r2-report docs/paper/r2-report-20261030/primary.json \
        --out-json paper/generated/slice_vs_persistence.json --out-tex paper/generated/slice_vs_persistence.tex
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from bgbench.forecast_analysis import incident_day_blocks  # noqa: E402
from bgbench.forecast_ranking import paired_bootstrap  # noqa: E402
import paper_month_boundary as mb  # noqa: E402  (hash helper, require)
import paper_set_errors_r2 as se2  # noqa: E402  (loaders and seed-count identities)

REPS = 10_000
SEED = 1701
HORIZONS = (30, 60)
SLICE_CUT = {30: 12, 60: 22}  # sections/app-protocol.tex tab:recipe, "Slice"
PUBLISHED_SLICE_EVENTS = {"R1": {30: 966, 60: 502}, "R2": {30: 372, 60: 211}}
SLICE_FIELDS = ("in_issue_time_slice", "two_threshold_jaccard", "issue_time_variables", "decision_rule")
CONTRASTS = {"C1": ("sage_on", "none_on"), "C2": ("sage_on", "online_history"), "C3": ("sage_on", "sage_off"),
             "C4": ("none_on", "none_off"), "C5": ("frozen_sage_on", "online_history"),
             "C6": ("frozen_sage_on", "sage_on")}
VS_PERSISTENCE = ("sage_on", "online_history", "frozen_sage_on")
NAME = {"sage_on": "SAGE, history", "online_history": "Online history (mean)", "frozen_sage_on": "SAGE, frozen 2025"}
require = mb.require

# the loaders keep only their declared fields; add the slice fields (module globals read at call time)
se2.R1_FIELDS = tuple(dict.fromkeys(se2.R1_FIELDS + SLICE_FIELDS))
se2.R2_FIELDS = tuple(dict.fromkeys(se2.R2_FIELDS + SLICE_FIELDS))


def slice_value(r):
    """bgbench.forecast_custodian_eval.compute_families.slice_decisions, record by record."""
    if r.get("two_threshold_jaccard") is not None:
        return r["two_threshold_jaccard"]
    if r.get("decision_rule") == "committed_baseline_decision":
        return r["jaccard"]
    raise SystemExit("STOP: a learned record without a validation-calibrated slice decision")


def slice_mask(period, arms, delta):
    cut = SLICE_CUT[delta]
    masks = set()
    for name, by_delta in arms.items():
        for seed in by_delta.get(delta, []):
            mask = tuple(r["issue_time_variables"]["early_growth"] >= cut for r in seed)
            flags = [r.get("in_issue_time_slice") for r in seed]
            require(all(f is None or f == m for f, m in zip(flags, mask)),
                    f"{period} {name}@{delta}: recorded slice flag differs from the frozen rule (early_growth >= {cut})")
            if name in ("sage_on", "sage_off", "none_on", "none_off", "frozen_sage_on"):
                require(all(f is not None for f in flags), f"{period} {name}@{delta}: learned record without slice flag")
            masks.add(mask)
    require(len(masks) == 1, f"{period}@{delta}: arms disagree on slice membership")
    inside = np.array(next(iter(masks)), dtype=bool)
    require(int(inside.sum()) == PUBLISHED_SLICE_EVENTS[period][delta],
            f"{period}@{delta}: {int(inside.sum())} slice events, published {PUBLISHED_SLICE_EVENTS[period][delta]}")
    return inside


def matrix(seeds, inside, value=slice_value):
    return np.array([[value(r) for r in seed] for seed in seeds], dtype=float)[:, inside]


def keep(res):
    return {k: res[k] for k in ("difference", "ci95", "p_value", "events", "blocks", "training_seeds")}


def period_results(period, arms, rows, published, repetitions, seed):
    out = {}
    for d in HORIZONS:
        s, R = (se2.r1_seed_counts if period == "R1" else se2.r2_seed_counts)(arms, d)
        inside = slice_mask(period, arms, d)
        blocks = incident_day_blocks(rows[d])
        sblocks = [b for b, k in zip(blocks, inside) if k]
        jp_all = s / (s + R)
        if period == "R1":
            rec = np.array([r["jaccard_persist"] for r in arms["sage_on"][d][0]], dtype=float)
            require(np.abs(rec - jp_all).max() < 1e-12, f"R1@{d}: jaccard_persist != s/(s+R)")
        persist = np.atleast_2d(jp_all[inside])
        entry = {"slice_events": int(inside.sum()), "all_events": len(rows[d]), "slice_blocks": len(set(sblocks)),
                 "slice_cut_early_growth": SLICE_CUT[d],
                 "slice_no_growth_events": int((R[inside] == 0).sum()),
                 "slice_mean_seeds": float(s[inside].mean()), "slice_mean_new_members": float(R[inside].mean()),
                 "slice_median_new_members": float(np.median(R[inside])),
                 "persistence_slice_jaccard": float(persist.mean())}
        # 3. reproduce every published slice contrast
        rep = {}
        for cid, (left, right) in CONTRASTS.items():
            key = f"{cid}@{d}"
            if key not in published:
                continue
            pub = published[key]
            require(pub["left"] == left and pub["right"] == right, f"{period} {key}: published arms {pub['left']}, {pub['right']}")
            got = paired_bootstrap(matrix(arms[left][d], inside), matrix(arms[right][d], inside), sblocks,
                                   repetitions=repetitions, seed=seed)
            require(abs(got["difference"] - pub["difference"]) < 1e-12
                    and np.allclose(got["ci95"], pub["ci95"], atol=1e-12, rtol=0)
                    and got["events"] == pub["events"] and got["blocks"] == pub["blocks"],
                    f"{period} slice {key}: got {got['difference']:.12f} {got['ci95']} ({got['events']}, {got['blocks']}), "
                    f"published {pub['difference']:.12f} {pub['ci95']} ({pub['events']}, {pub['blocks']})")
            rep[key] = {"left": left, "right": right, "difference": pub["difference"], "ci95": pub["ci95"],
                        "events": pub["events"], "blocks": pub["blocks"], "reproduced_exactly": True}
            print(f"{period} slice {key} reproduced: {got['difference']:+.6f} [{got['ci95'][0]:+.6f}, {got['ci95'][1]:+.6f}]",
                  flush=True)
        require(f"C2@{d}" in rep, f"{period}: C2@{d} not reproduced")
        entry["published_slice_contrasts_reproduced"] = rep
        # 4. arm minus persistence on the slice
        arms_out = {}
        for arm in VS_PERSISTENCE:
            if d not in arms.get(arm, {}):
                continue
            left = matrix(arms[arm][d], inside)
            res = keep(paired_bootstrap(left, persist, sblocks, repetitions=repetitions, seed=seed))
            same = np.abs(left - persist) < 1e-12
            a = {"slice_jaccard": se2.seed_summary(left.mean(axis=1)), "minus_persistence": res,
                 "equals_persistence_share": se2.seed_summary(same.mean(axis=1)),
                 "equals_persistence_share_growth_events": se2.seed_summary(same[:, R[inside] > 0].mean(axis=1))}
            if arm in ("sage_on", "frozen_sage_on"):
                full_thr = matrix(arms[arm][d], inside, value=lambda r: r["jaccard"])
                a["full_target_threshold_on_slice"] = {
                    "slice_jaccard": se2.seed_summary(full_thr.mean(axis=1)),
                    "minus_persistence": keep(paired_bootstrap(full_thr, persist, sblocks, repetitions=repetitions,
                                                               seed=seed))}
            arms_out[arm] = a
            print(f"{period}@{d} {arm:15s} slice J {a['slice_jaccard']['mean']:.4f}  persistence {persist.mean():.4f}  "
                  f"minus persistence {res['difference']:+.4f} [{res['ci95'][0]:+.4f}, {res['ci95'][1]:+.4f}] "
                  f"p={res['p_value']:.4f}  J==Jp {a['equals_persistence_share']['mean']:.3f}", flush=True)
        # consistency: SAGE - persistence minus (history - persistence) equals the published C2 slice difference
        if "online_history" in arms_out:
            c2 = arms_out["sage_on"]["minus_persistence"]["difference"] - arms_out["online_history"]["minus_persistence"]["difference"]
            require(abs(c2 - rep[f"C2@{d}"]["difference"]) < 1e-12, f"{period}@{d}: arm-minus-persistence does not add up to C2")
        entry["arms"] = arms_out
        out[str(d)] = entry
    return out


def published_slice(report, period):
    fam = (report["analysis_ranking_v1_c1_c4"] if period == "R1" else report)["families"]["slice_jaccard"]["contrasts"]
    return fam


def signed(x, digits=3):
    return f"{x:+.{digits}f}".replace("-", "$-$")


def write_tex(path, res):
    lines = [
        "% Generated by scripts/paper_slice_vs_persistence.py; do not edit by hand.",
        "% Prespecified issue-time slice (early growth >= 12 at 30 s, >= 22 at 60 s). Slice Jaccard with the slice threshold",
        "% calibrated on validation slice events; persistence forecasts the seed set. Paired difference to persistence over",
        "% slice events, mean over five training seeds, ordinary 95% interval (training seeds then incident-day blocks,",
        "% 10,000 repetitions, seed 1701). Revision analysis, not a prespecified contrast; unadjusted.",
        "% J - persistence has four decimals, or six to eight where every value of the row is below 0.001 in magnitude.",
        "\\begin{tabular}{@{}llrlrl@{}}",
        "\\toprule",
        "Period & $\\Delta$ & Slice events & Forecast & $J$ & $J -$ persistence \\\\",
        "\\midrule",
    ]
    for period in ("R1", "R2"):
        for d in HORIZONS:
            e = res[period][str(d)]
            lead = f"{period} & {d}\\,s & {e['slice_events']}"
            lines.append(f"{lead} & Persistence & {e['persistence_slice_jaccard']:.3f} & -- \\\\")
            for arm in VS_PERSISTENCE:
                if arm not in e["arms"]:
                    continue
                a = e["arms"][arm]
                mp = a["minus_persistence"]
                lines.append(f" & & & {NAME[arm]} & {a['slice_jaccard']['mean']:.3f} & "
                             f"{se2.small_interval(mp['difference'], mp['ci95'])} \\\\")
            if not (period == "R2" and d == 60):
                lines.append("\\midrule" if d == 60 else "\\cmidrule(l){2-6}")
    lines += ["\\bottomrule", "\\end{tabular}", ""]
    Path(path).write_text("\n".join(lines))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ("r1-report", "r1-per-event", "r1-arm-spec", "r1-manifest-30", "r1-manifest-60", "r2-scores",
                 "r2-report", "out-json", "out-tex"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--repetitions", type=int, default=REPS)
    p.add_argument("--seed", type=int, default=SEED)
    args = p.parse_args()
    res, prov = {}, {}
    arms, rows, report, prov["R1"] = se2.load_r1(args)
    res["R1"] = period_results("R1", arms, rows, published_slice(report, "R1"), args.repetitions, args.seed)
    del arms
    arms, rows, report, prov["R2"] = se2.load_r2(args)
    res["R2"] = period_results("R2", arms, rows, published_slice(report, "R2"), args.repetitions, args.seed)
    del arms
    out = {
        "kind": "slice_vs_persistence_revision_analysis", "confirmatory": False, "replaces_published_values": False,
        "prespecified": "no: the slice and its threshold are prespecified, this contrast (arm minus persistence) is not",
        "definitions": {
            "slice": "early_growth >= 12 (30 s) or >= 22 (60 s), issue_time_variables of the record; recorded "
                     "in_issue_time_slice checked against the rule",
            "slice_jaccard": "two_threshold_jaccard (slice threshold calibrated on validation slice events); a committed "
                             "baseline decision uses its own set (jaccard), as bgbench.forecast_custodian_eval",
            "persistence": "seed set; R1 jaccard_persist, R2 s/(s+R) from seed_asns and new_members (identity checked on "
                           "every R1 record; assumed for R2 from the target definition, as in set_errors_r2.json)",
            "full_target_threshold_on_slice": "secondary: the arm's full-target-threshold Jaccard (jaccard) on the slice "
                                              "events",
            "equals_persistence_share": "share of slice events with |J - J_persist| < 1e-12 (upper bound on adding "
                                        "nothing)",
            "interval": f"paired_bootstrap, training seeds then incident-day blocks (blocks of the whole cohort restricted "
                        f"to slice events, as the released evaluator), {args.repetitions} repetitions, rng seed "
                        f"{args.seed}; ordinary 95 %, p unadjusted"},
        "reproduced": "every published slice-Jaccard contrast (R1 C1-C4, R2 C1-C6) to 1e-12, with events and blocks",
        "provenance": prov, "results": res, "source_sha256": mb.sha(__file__)}
    Path(args.out_json).write_text(json.dumps(out, indent=1) + "\n")
    write_tex(args.out_tex, res)
    print("wrote", args.out_json, args.out_tex)


if __name__ == "__main__":
    main()
