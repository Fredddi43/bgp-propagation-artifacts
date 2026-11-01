#!/usr/bin/env python3
"""Month-boundary subsets under leaker resampling (revision analysis, review round 4, Opus A1).

The month-boundary analysis (scripts/paper_month_boundary.py) removes the events whose identifier date is the first
(``no_day1``) or the first to third (``no_day1_3``) of a month and redraws the C2 and native intervals with the published
method, training seeds then incident-day blocks. The actor analysis (scripts/paper_actor_bootstrap.py) redraws the
intervals on all eligible events with the leaker AS as a resampling unit. This script combines the two: on each
month-boundary subset it redraws the C2 and native intervals with

* ``day_blocks``    training seeds, then incident-day blocks rebuilt from the kept events (bgbench.forecast_ranking.
                    paired_bootstrap and bgbench.forecast_analysis.incident_day_blocks, called unchanged); this is the
                    month-boundary interval and must reproduce paper/generated/month_boundary.json exactly;
* ``leaker_blocks`` training seeds, then whole leaker ASes (paired_bootstrap with the leaker as the block label);
* ``leaker_x_day``  training seeds, then leakers and incident days drawn independently, each event weighted by the
                    product of its leaker's and its day's multiplicities (paper_actor_bootstrap.two_way_bootstrap,
                    called unchanged).

Contrasts: C2 (SAGE with history minus online history, shared candidates) and native (SAGE with history minus online
history on its native candidates), R1 and R2, 30 s and 60 s. Statistic: event-macro mean AP difference over the kept
eligible events, then the training-seed mean (unchanged). 10,000 repetitions, numpy default_rng(1701), ordinary 95 %
percentile intervals, unadjusted descriptive p-values. The ``all`` population must reproduce the published report
(difference, interval, events, blocks) and paper/generated/actor_bootstrap.json (leaker and leaker x day intervals)
exactly; the subsets' day-block results must reproduce paper/generated/month_boundary.json exactly. Otherwise the script
stops before writing anything.

Inputs: those of paper_month_boundary.py (loaders and hash checks reused unchanged), plus the two generated JSON files
named above as reproduction references. No model is retrained, no prediction regenerated, no label read and no published
number changed.

Usage (repo root):
    .venv/bin/python -B scripts/paper_month_boundary_actor.py \
        --r1-report .agents/operations/r1-v11-posteval-20261024/evidence/released/report.json \
        --r1-per-event <local copy of results/per_event> \
        --r1-arm-spec .agents/operations/r1-arm-spec-20261020/arm-spec.json \
        --r1-manifest-30 .agents/operations/r1-v11-posteval-20261024/evidence/released/retrospective-2025-v6-d30.json \
        --r1-manifest-60 .agents/operations/r1-v11-posteval-20261024/evidence/released/retrospective-2025-v6-d60.json \
        --r1-events data/corrected-release-20261016/eventset/2025_leak/events.parquet \
        --r2-scores <local copy of primary-scores.json> \
        --r2-report docs/paper/r2-report-20261030/primary.json \
        --month-boundary-json paper/generated/month_boundary.json \
        --actor-bootstrap-json paper/generated/actor_bootstrap.json \
        --out-json paper/generated/month_boundary_actor.json --out-tex paper/generated/month_boundary_actor.tex
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
import paper_actor_bootstrap as ab  # noqa: E402  (leaker parse, two-way bootstrap, R1 leaker check)
import paper_month_boundary as mb  # noqa: E402  (released loaders, hash checks, subsets, formatting)

REPS = 10_000
SEED = 1701
HORIZONS = (30, 60)
CONTRASTS = ab.CONTRASTS          # C2 and native
SUBSETS = mb.SUBSETS              # all, no_day1, no_day1_3
require = mb.require
FIELDS = ("difference", "ci95", "p_value")


def same(a, b):
    return abs(a["difference"] - b["difference"]) < 1e-12 and np.allclose(a["ci95"], b["ci95"], atol=1e-12, rtol=0)


def evaluate(period, arms, rows, published, mb_ref, ab_ref, repetitions, seed):
    out = {}
    for delta in HORIZONS:
        for cid, (left_arm, right_arm) in CONTRASTS.items():
            key = f"{cid}@{delta}"
            a_seeds, b_seeds = arms[left_arm][delta], arms[right_arm][delta]
            left = np.array([[e["average_precision"] for e in s] for s in a_seeds], dtype=float)
            right = np.array([[e["average_precision"] for e in s] for s in b_seeds], dtype=float)
            masks = [np.array([e["eligible"] for e in s]) for s in list(a_seeds) + list(b_seeds)]
            require(all((m == masks[0]).all() for m in masks), f"{period} {key}: arms disagree on the eligible cohort")
            entry = {"left": left_arm, "right": right_arm, "horizon_seconds": delta}
            for name, days_out in SUBSETS.items():
                keep = masks[0] & np.array([mb.id_day(r["event_id"]) not in days_out for r in rows[delta]])
                kept = [r for r, k in zip(rows[delta], keep) if k]
                leakers = [ab.leaker(r["event_id"]) for r in kept]
                days = incident_day_blocks(kept)
                day = paired_bootstrap(left[:, keep], right[:, keep], days, repetitions=repetitions, seed=seed)
                act = paired_bootstrap(left[:, keep], right[:, keep], leakers, repetitions=repetitions, seed=seed)
                two = ab.two_way_bootstrap(left[:, keep], right[:, keep], leakers, days, repetitions=repetitions,
                                           seed=seed)
                require(abs(act["difference"] - day["difference"]) < 1e-15
                        and abs(two["difference"] - day["difference"]) < 1e-15, f"{period} {key} {name}: point moved")
                # reproduction: month-boundary day-block interval on every subset
                ref = mb_ref[period]["contrasts"][key][name]
                require(same(day, ref) and int(keep.sum()) == ref["eligible_events"] and day["blocks"] == ref["blocks"],
                        f"{period} {key} {name}: day-block result differs from month_boundary.json: "
                        f"{day['difference']:.6f} {day['ci95']} vs {ref['difference']:.6f} {ref['ci95']}")
                if name == "all":
                    pub = published[key]
                    require(round(day["difference"], 4) == round(pub["difference"], 4)
                            and [round(x, 4) for x in day["ci95"]] == [round(x, 4) for x in pub["ci95"]]
                            and int(keep.sum()) == pub["eligible_events"] and day["blocks"] == pub["blocks"],
                            f"{period} {key}: does not reproduce the published value")
                    aref = ab_ref[period]["contrasts"][key]
                    require(same(act, aref["leaker_blocks"]) and same(two, aref["leaker_x_day"]),
                            f"{period} {key}: leaker intervals differ from actor_bootstrap.json")
                entry[name] = {
                    "eligible_events": int(keep.sum()), "excluded_identifier_days": sorted(days_out),
                    "day_blocks": {**{k: day[k] for k in FIELDS}, "blocks": day["blocks"]},
                    "leaker_blocks": {**{k: act[k] for k in FIELDS}, "blocks": act["blocks"]},
                    "leaker_x_day": {**{k: two[k] for k in FIELDS}, "leakers": two["leakers"], "days": two["days"],
                                     "degenerate_repetitions": two["degenerate_repetitions"]},
                    "training_seeds": day["training_seeds"],
                    "zero_inside": {k: bool(v["ci95"][0] <= 0 <= v["ci95"][1])
                                    for k, v in (("day_blocks", day), ("leaker_blocks", act), ("leaker_x_day", two))},
                }
                print(f"{period} {key} {name:9s}: {day['difference']:+.4f} n={int(keep.sum())}  "
                      f"day [{day['ci95'][0]:+.4f}, {day['ci95'][1]:+.4f}]  "
                      f"leaker [{act['ci95'][0]:+.4f}, {act['ci95'][1]:+.4f}]  "
                      f"leaker x day [{two['ci95'][0]:+.4f}, {two['ci95'][1]:+.4f}]", flush=True)
            entry["reproduced"] = {"published_all": True, "month_boundary_day_blocks_all_subsets": True,
                                   "actor_bootstrap_all": True}
            out[key] = entry
    return out


def write_tex(path, results):
    lines = [
        "% Generated by scripts/paper_month_boundary_actor.py; do not edit by hand.",
        "% Paired AP difference over the kept eligible events, mean over five training seeds; ordinary 95% percentile",
        "% intervals, training seeds resampled first, 10,000 repetitions, seed 1701. No d1: events whose identifier date is",
        "% the first of a month removed; no d1--3: first to third removed. The day-block intervals of the same subsets are in",
        "% month_boundary.tex (not repeated here). Leaker: whole leaker ASes. Leaker x day: leakers and days drawn",
        "% independently (pigeonhole). n: kept eligible events.",
        "\\begin{tabular}{@{}lllrrll@{}}",
        "\\toprule",
        "Period & Contrast & Subset & $n$ & Diff. & Leaker blocks & Leaker $\\times$ day \\\\",
        "\\midrule",
    ]
    for period in ("R1", "R2"):
        first = True
        for delta in HORIZONS:
            for cid in CONTRASTS:
                e = results[period][f"{cid}@{delta}"]
                name = {"native": "Native"}.get(cid, cid) + f"@{delta}\\,s"
                for i, sub in enumerate(("no_day1", "no_day1_3")):
                    s = e[sub]
                    lead = period if first else ""
                    first = False
                    label = {"no_day1": "No d1", "no_day1_3": "No d1--3"}[sub]
                    n = f"{s['eligible_events']:,}".replace(",", "{,}")
                    lines.append(f"{lead} & {name if i == 0 else ''} & {label} & {n} & "
                                 f"{mb.signed(s['day_blocks']['difference'])} & "
                                 f"{mb.interval(s['leaker_blocks']['ci95'])} & {mb.interval(s['leaker_x_day']['ci95'])} \\\\")
        if period == "R1":
            lines.append("\\midrule")
    lines += ["\\bottomrule", "\\end{tabular}", ""]
    Path(path).write_text("\n".join(lines))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ("r1-report", "r1-per-event", "r1-arm-spec", "r1-manifest-30", "r1-manifest-60", "r1-events",
                 "r2-scores", "r2-report", "month-boundary-json", "actor-bootstrap-json", "out-json", "out-tex"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--repetitions", type=int, default=REPS)
    p.add_argument("--seed", type=int, default=SEED)
    args = p.parse_args()
    mb_ref = json.loads(Path(args.month_boundary_json).read_text())
    ab_ref = json.loads(Path(args.actor_bootstrap_json).read_text())
    require(mb_ref["kind"] == "month_boundary_sensitivity_revision_analysis", "Not month_boundary.json")
    require(ab_ref["kind"] == "actor_block_bootstrap_revision_analysis", "Not actor_bootstrap.json")
    require(mb_ref["method"]["repetitions"] == args.repetitions == ab_ref["method"]["repetitions"]
            and mb_ref["method"]["rng_seed"] == args.seed == ab_ref["method"]["rng_seed"], "Reference RNG settings differ")

    out = {"kind": "month_boundary_actor_bootstrap_revision_analysis", "confirmatory": False,
           "replaces_published_values": False,
           "method": {"statistic": "event_macro_mean_AP_difference_then_training_seed_mean (unchanged)",
                      "subsets": {k: sorted(v) for k, v in SUBSETS.items()},
                      "day_definition": "day of month of the identifier time, event_id[6:8] (UTC), as month_boundary",
                      "intervals": {
                          "day_blocks": "training seeds, then incident-day blocks rebuilt from the kept eligible events "
                                        "(the month-boundary interval)",
                          "leaker_blocks": "training seeds, then whole leaker ASes (paired_bootstrap, leaker as block)",
                          "leaker_x_day": "training seeds, then leakers and incident days drawn independently; event "
                                          "weight = leaker multiplicity x day multiplicity (two_way_bootstrap)"},
                      "repetitions": args.repetitions, "rng_seed": args.seed,
                      "leaker": "a of the leak event, parsed from event_id '<t0>_leak_<a>'; R1 checked against the 2025 "
                                "event table", "p_values": "unadjusted, descriptive only"},
           "contrasts": {k: {"left": v[0], "right": v[1]} for k, v in CONTRASTS.items()},
           "references": {"month_boundary_json_sha256": mb.sha(args.month_boundary_json),
                          "actor_bootstrap_json_sha256": mb.sha(args.actor_bootstrap_json)},
           "source_sha256": mb.sha(__file__)}
    results = {}
    for period, loader in (("R1", mb.load_r1), ("R2", mb.load_r2)):
        arms, rows, published, provenance = loader(args)
        if period == "R1":
            provenance["leaker_check"] = ab.check_r1_leakers(args.r1_events, rows)
        results[period] = evaluate(period, arms, rows, published, mb_ref, ab_ref, args.repetitions, args.seed)
        out[period] = {"provenance": provenance, "contrasts": results[period]}
        del arms
    Path(args.out_json).write_text(json.dumps(out, indent=1) + "\n")
    write_tex(args.out_tex, results)
    print("wrote", args.out_json, args.out_tex)


if __name__ == "__main__":
    main()
