#!/usr/bin/env python3
"""Set-error accounting of the R1 and R2 set forecasts (revision analysis, review round 3, Codex analysis item 3).

For each evaluation and horizon, over all scored events (not only the AP-eligible ones), and for the arms
SAGE with history (``sage_on``), the frozen 2025 SAGE (``frozen_sage_on``, R2 at 60 s only), online history with the
mean-size rule (``online_history``) and with the median-size rule (``history_median``), and persistence (the seed set):

* ``added_mean``              mean number of added (non-seed) ASes per event, |predicted - seeds| = new_tp + new_fp;
* ``no_growth``               events without new members (no AS joins after issue time) and, on those, the false
                              additions: mean added per such event, total, and share of such events with any addition;
* ``adds_nothing_share``      share of events whose prediction equals the seed set (empty_new_prediction); for a learned
                              arm this is the persistence fallback;
* ``jaccard``                 absolute full-target Jaccard of the committed set (seeds included) against the target;
* ``minus_persistence``       (R1) paired Jaccard difference to persistence, with the published interval method.

Learned arms are averaged over their five training seeds (statistic per seed, then the mean; the per-seed range is
kept in the JSON). Field definitions are those of bgbench.forecast_retrospective_scoring.score_membership
(new_tp, new_fp, no_growth, empty_new_prediction, jaccard, jaccard_persist).

Availability. The released R1 per-event files carry every field above. The released R2 primary-scores.json carries,
per arm record, only average_precision, coverage_ceiling, decision_rule, eligible, event_id, in_issue_time_slice,
input_status, issue_time_variables, jaccard, metric_version, new_members, precision_at, ranking_status, recall_at,
seed_asns and two_threshold_jaccard: there is no new_tp/new_fp (or predicted set), no empty_new_prediction and no
jaccard_persist (or target set). For R2 only the absolute Jaccard and the number of events without new members are
computed; added counts, false additions, the fallback share and persistence's Jaccard are reported as unavailable.

Checks: R1 files against the released report's per_event_sha256; R2 arm identities against the released primary
report. The arm Jaccard means and the published full-target Jaccard contrasts (C2, and C5 for the frozen arm) and the
published mean/median history Jaccard must be reproduced, else the script stops. No model is retrained, no prediction
regenerated, no label read. Interval for minus_persistence: training seeds then incident-day blocks, 10,000
repetitions, seed 1701 (bgbench.forecast_ranking.paired_bootstrap), ordinary 95 %, descriptive.

Usage (repo root):
    .venv/bin/python -B scripts/paper_set_errors.py \
        --r1-report .agents/operations/r1-v11-posteval-20261024/evidence/released/report.json \
        --r1-per-event <local copy of results/per_event> \
        --r1-arm-spec .agents/operations/r1-arm-spec-20261020/arm-spec.json \
        --r1-manifest-30 .agents/operations/r1-v11-posteval-20261024/evidence/released/retrospective-2025-v6-d30.json \
        --r1-manifest-60 .agents/operations/r1-v11-posteval-20261024/evidence/released/retrospective-2025-v6-d60.json \
        --r2-scores <local copy of primary-scores.json> \
        --r2-report docs/paper/r2-report-20261030/primary.json \
        --out-json paper/generated/set_errors.json --out-tex paper/generated/set_errors.tex
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
import paper_month_boundary as mb  # noqa: E402  (hash helper, released-report constants, formatting)

REPS = 10_000
SEED = 1701
HORIZONS = (30, 60)
R1_ARMS = ("sage_on", "online_history", "history_median")
R2_ARMS = ("sage_on", "frozen_sage_on", "online_history", "history_median")
ROW_ORDER = ("sage_on", "frozen_sage_on", "online_history", "history_median", "persistence")
NAME = {"sage_on": "SAGE, history", "frozen_sage_on": "SAGE, frozen 2025", "online_history": "Online history (mean)",
        "history_median": "Online history (median)", "persistence": "Persistence"}
R1_FIELDS = ("event_id", "new_tp", "new_fp", "new_fn", "new_members", "no_growth", "empty_new_prediction", "jaccard",
             "jaccard_persist", "eligible")
R2_PRESENT = ("average_precision", "coverage_ceiling", "decision_rule", "eligible", "event_id", "in_issue_time_slice",
              "input_status", "issue_time_variables", "jaccard", "metric_version", "new_members", "precision_at",
              "ranking_status", "recall_at", "seed_asns", "two_threshold_jaccard")
R2_MISSING = {"added_mean": ["new_tp", "new_fp", "predicted_asns"],
              "false_additions_on_no_growth": ["new_fp", "predicted_asns"],
              "adds_nothing_share": ["empty_new_prediction", "predicted_asns"],
              "persistence_jaccard": ["jaccard_persist", "target_asns"]}
require = mb.require


def seed_summary(values):
    v = np.asarray(values, dtype=float)
    return {"mean": float(v.mean()), "per_seed": v.tolist(), "min": float(v.min()), "max": float(v.max())}


def r1_stats(seeds):
    """Set-error statistics per training seed (each seed: list of per-event records, aligned)."""
    per = {k: [] for k in ("added_mean", "added_mean_growth", "no_growth_added_mean", "no_growth_false_total",
                           "no_growth_any_share", "adds_nothing_share", "jaccard", "persistence_jaccard")}
    for rows in seeds:
        added = np.array([r["new_tp"] + r["new_fp"] for r in rows], dtype=float)
        nog = np.array([r["no_growth"] for r in rows], dtype=bool)
        empty = np.array([r["empty_new_prediction"] for r in rows], dtype=bool)
        jac = np.array([r["jaccard"] for r in rows], dtype=float)
        per_j = np.array([r["jaccard_persist"] for r in rows], dtype=float)
        require(np.isfinite(jac).all() and np.isfinite(per_j).all(), "Undefined Jaccard in R1")
        require(((added == 0) == empty).all(), "empty_new_prediction disagrees with new_tp + new_fp")
        require((nog == np.array([r["new_members"] == 0 for r in rows])).all(), "no_growth disagrees with new_members")
        require(all(r["new_tp"] + r["new_fn"] == r["new_members"] for r in rows), "new_tp + new_fn != new_members")
        require(all(r["new_tp"] == 0 for r, g in zip(rows, nog) if g), "true positives on an event without growth")
        per["added_mean"].append(added.mean())
        per["added_mean_growth"].append(added[~nog].mean())
        per["no_growth_added_mean"].append(added[nog].mean())
        per["no_growth_false_total"].append(added[nog].sum())
        per["no_growth_any_share"].append((added[nog] > 0).mean())
        per["adds_nothing_share"].append(empty.mean())
        per["jaccard"].append(jac.mean())
        per["persistence_jaccard"].append(per_j.mean())
    first = seeds[0]
    nog = [r["no_growth"] for r in first]
    return {"events": len(first), "no_growth_events": int(sum(nog)),
            "eligible_events": int(sum(r["eligible"] for r in first)),
            **{k: seed_summary(v) for k, v in per.items()}}


def load_r1(args):
    require(mb.sha(args.r1_report) == mb.R1_REPORT_SHA, "R1 report is not the released one")
    report = json.loads(Path(args.r1_report).read_text())
    spec = json.loads(Path(args.r1_arm_spec).read_text())
    require(spec["kind"] == "frozen_evaluation_arm_spec" and spec["population"] == "retrospective_r1", "Bad arm spec")
    rows, arms, files = {}, {a: {} for a in R1_ARMS}, {}
    for delta, manifest in ((30, args.r1_manifest_30), (60, args.r1_manifest_60)):
        m = json.loads(Path(manifest).read_text())
        require(m["delta_s"] == delta, f"Manifest {manifest} is not the {delta} s manifest")
        rows[delta] = [{"event_id": e["event_id"], "onset": e["onset"], "incident_id": e["incident_id"]}
                       for e in m["events"] if e["split"] == "test"]
        order = [r["event_id"] for r in rows[delta]]
        for arm in R1_ARMS:
            arms[arm][delta] = []
            for cell in spec["arms"][arm][str(delta)]:
                path = Path(args.r1_per_event) / (cell.replace("/", "__", 1) + ".json")
                digest = mb.sha(path)
                require(report["per_event_sha256"].get(cell) == digest, f"{cell}: differs from the released hash")
                files[cell] = digest
                by_id = {r["event_id"]: {k: r[k] for k in R1_FIELDS} for r in json.loads(path.read_text())}
                require(sorted(by_id) == sorted(order), f"{cell} does not cover the R1 cohort exactly")
                arms[arm][delta].append([by_id[e] for e in order])
    analysis = report["analysis_ranking_v1_c1_c4"]
    published = {d: {"C2": analysis["families"]["full_target_jaccard"]["contrasts"][f"C2@{d}"]["difference"],
                     "online_history": analysis["history_median_vs_mean_jaccard"]["horizons"][str(d)]["mean_extent_jaccard"],
                     "history_median": analysis["history_median_vs_mean_jaccard"]["horizons"][str(d)]["median_extent_jaccard"]}
                 for d in HORIZONS}
    return arms, rows, published, {"report_sha256": mb.R1_REPORT_SHA, "per_event_sha256": files,
                                   "arm_spec_sha256": mb.sha(args.r1_arm_spec)}


def load_r2(args):
    scores = json.loads(Path(args.r2_scores).read_text())
    report = json.loads(Path(args.r2_report).read_text())
    require(scores["kind"] == "newperiod_primary_computed_scores_v1", "Not the R2 primary computed scores")
    require(report["population"] == "new_period", "Not the R2 primary report")
    present = set()
    for arm in R2_ARMS:
        require(scores["identities"][arm] == report["arms"][arm], f"R2 {arm}: identities differ from the report")
        for d in scores["arms"][arm]:
            for s in scores["arms"][arm][d]:
                require([r["event_id"] for r in s] == [r["event_id"] for r in scores["rows"][d]], f"R2 {arm}@{d} misaligned")
                for r in s:
                    present |= set(r)
    require(present == set(R2_PRESENT), f"R2 record fields changed: {sorted(present ^ set(R2_PRESENT))}")
    fam = report["families"]["full_target_jaccard"]["contrasts"]
    hist = report["history_median_vs_mean_jaccard"]["horizons"]
    published = {d: {"C2": fam[f"C2@{d}"]["difference"], "online_history": hist[str(d)]["mean_extent_jaccard"],
                     "history_median": hist[str(d)]["median_extent_jaccard"]} for d in HORIZONS}
    c5 = fam["C5@60"]
    require(c5["left"] == "frozen_sage_on" and c5["right"] == "online_history", f"C5@60 is not frozen - history: {c5}")
    published[60]["C5"] = c5["difference"]
    return scores, published, {"primary_scores_sha256": mb.sha(args.r2_scores),
                               "primary_report_sha256": mb.sha(args.r2_report),
                               "evaluation_window": report["evaluation_window"]}


def close(a, b, what):
    require(abs(a - b) < 1e-12, f"{what}: got {a:.12f}, published {b:.12f}")


def r1(args, repetitions, seed):
    arms, rows, published, provenance = load_r1(args)
    out = {}
    for d in HORIZONS:
        entry = {}
        for arm in R1_ARMS:
            entry[arm] = r1_stats(arms[arm][d])
        # persistence: the seed set; jaccard_persist is the same in every file (same seeds, same target)
        ref = [r["jaccard_persist"] for r in arms["sage_on"][d][0]]
        for arm in R1_ARMS:
            for s in arms[arm][d]:
                require([r["jaccard_persist"] for r in s] == ref, f"R1 {arm}@{d}: persistence Jaccard differs")
        n = len(ref)
        no_growth = entry["sage_on"]["no_growth_events"]
        entry["persistence"] = {"events": n, "no_growth_events": no_growth,
                                "added_mean": seed_summary([0.0]), "added_mean_growth": seed_summary([0.0]),
                                "no_growth_added_mean": seed_summary([0.0]), "no_growth_false_total": seed_summary([0.0]),
                                "no_growth_any_share": seed_summary([0.0]), "adds_nothing_share": seed_summary([1.0]),
                                "jaccard": seed_summary([float(np.mean(ref))])}
        # reproduction of the published Jaccard values
        close(entry["sage_on"]["jaccard"]["mean"] - entry["online_history"]["jaccard"]["mean"], published[d]["C2"],
              f"R1 C2@{d} full-target Jaccard")
        close(entry["online_history"]["jaccard"]["mean"], published[d]["online_history"], f"R1 mean history @{d}")
        close(entry["history_median"]["jaccard"]["mean"], published[d]["history_median"], f"R1 median history @{d}")
        entry["published_reproduced"] = {"full_target_jaccard_C2": published[d]["C2"],
                                         "online_history_jaccard": published[d]["online_history"],
                                         "history_median_jaccard": published[d]["history_median"]}
        # learned / history minus persistence, published interval method over all scored events
        blocks = incident_day_blocks(rows[d])
        persist = np.atleast_2d(np.array(ref, dtype=float))
        for arm in R1_ARMS:
            left = np.array([[r["jaccard"] for r in s] for s in arms[arm][d]], dtype=float)
            res = paired_bootstrap(left, persist, blocks, repetitions=repetitions, seed=seed)
            entry[arm]["minus_persistence"] = {k: res[k] for k in ("difference", "ci95", "p_value", "events", "blocks",
                                                                   "training_seeds")}
        out[str(d)] = entry
        for arm in ROW_ORDER:
            if arm in entry:
                e = entry[arm]
                mp = e.get("minus_persistence")
                print(f"R1@{d} {arm:15s} added {e['added_mean']['mean']:8.2f}  no-growth any {e['no_growth_any_share']['mean']:.3f} "
                      f"(mean {e['no_growth_added_mean']['mean']:.2f})  adds-nothing {e['adds_nothing_share']['mean']:.3f}  "
                      f"J {e['jaccard']['mean']:.4f}" + (f"  -persist {mp['difference']:+.4f} [{mp['ci95'][0]:+.4f}, {mp['ci95'][1]:+.4f}]"
                                                       if mp else ""), flush=True)
    return out, provenance


def r2(args):
    scores, published, provenance = load_r2(args)
    out = {}
    for d in HORIZONS:
        entry = {}
        for arm in R2_ARMS:
            seeds = scores["arms"][arm].get(str(d))
            if seeds is None:
                continue
            jac = [float(np.mean([r["jaccard"] for r in s])) for s in seeds]
            require(all(np.isfinite(jac)), f"R2 {arm}@{d}: undefined Jaccard")
            first = seeds[0]
            entry[arm] = {"events": len(first), "no_growth_events": int(sum(r["new_members"] == 0 for r in first)),
                          "eligible_events": int(sum(r["eligible"] for r in first)),
                          "abstentions": int(sum(r["input_status"] != "available" for r in first)),
                          "jaccard": seed_summary(jac), "unavailable": sorted(R2_MISSING)}
        close(entry["sage_on"]["jaccard"]["mean"] - entry["online_history"]["jaccard"]["mean"], published[d]["C2"],
              f"R2 C2@{d} full-target Jaccard")
        close(entry["online_history"]["jaccard"]["mean"], published[d]["online_history"], f"R2 mean history @{d}")
        close(entry["history_median"]["jaccard"]["mean"], published[d]["history_median"], f"R2 median history @{d}")
        if "frozen_sage_on" in entry:
            close(entry["frozen_sage_on"]["jaccard"]["mean"] - entry["online_history"]["jaccard"]["mean"],
                  published[d]["C5"], f"R2 C5@{d} full-target Jaccard")
        entry["published_reproduced"] = {f"full_target_jaccard_{k}" if k in ("C2", "C5") else f"{k}_jaccard": v
                                         for k, v in published[d].items()}
        entry["persistence"] = {"unavailable": ["jaccard"], "reason": "no jaccard_persist (or target set) in R2 records"}
        out[str(d)] = entry
        for arm in R2_ARMS:
            if arm in entry:
                print(f"R2@{d} {arm:15s} J {entry[arm]['jaccard']['mean']:.4f}  no-growth events "
                      f"{entry[arm]['no_growth_events']}/{entry[arm]['events']}", flush=True)
    return out, provenance


def num(x, digits):
    return f"{x:.{digits}f}"


def write_tex(path, res):
    dash = "--"
    lines = [
        "% Generated by scripts/paper_set_errors.py; do not edit by hand.",
        "% All scored events. Added: mean number of non-seed ASes added per event. No-growth events: events without new",
        "% members; Any: share of them with at least one (false) addition; Mean: false additions per such event.",
        "% Adds none: share of events whose forecast equals the seed set (persistence fallback for a learned arm).",
        "% J: absolute full-target Jaccard. Learned arms: mean over five training seeds. R1 only: the R2 records carry no",
        "% added-set counts (their absolute Jaccard is in set_errors_r2.tex; this JSON keeps the R2 entries).",
        "% In parentheses under each horizon: scored events / events without new members.",
        "\\begin{tabular}{@{}lllrrrrr@{}}",
        "\\toprule",
        " & & & & \\multicolumn{2}{c}{No-growth events} & & \\\\",
        "\\cmidrule(lr){5-6}",
        "Period & $\\Delta$ & Forecast & Added & Any & Mean & Adds none & $J$ \\\\",
        "\\midrule",
    ]
    def thousands(n):
        return f"{n:,}".replace(",", "{,}")

    for period in ("R1",):          # the R2 rows would be all "--" except J, which set_errors_r2.tex prints
        for d in HORIZONS:
            entry = res[period][str(d)]
            arms = [a for a in ROW_ORDER if a in entry and "jaccard" in entry[a]]
            # first column of each block: period and horizon, then (events / events without new members)
            leads = [f"{period} & {d}\\,s",
                     f" & ({thousands(entry['sage_on']['events'])}/{thousands(entry['sage_on']['no_growth_events'])})"]
            for i, arm in enumerate(arms):
                e = entry[arm]
                lead = leads[i] if i < len(leads) else " & "
                if "added_mean" in e:
                    cells = [num(e["added_mean"]["mean"], 2), num(e["no_growth_any_share"]["mean"], 3),
                             num(e["no_growth_added_mean"]["mean"], 2), num(e["adds_nothing_share"]["mean"], 3)]
                else:
                    cells = [dash] * 4
                lines.append(f"{lead} & {NAME[arm]} & " + " & ".join(cells) + f" & {num(e['jaccard']['mean'], 3)} \\\\")
            if d == HORIZONS[0]:
                lines.append("\\cmidrule(l){2-8}")
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
    res["R1"], prov["R1"] = r1(args, args.repetitions, args.seed)
    res["R2"], prov["R2"] = r2(args)
    out = {"kind": "set_error_accounting_revision_analysis", "confirmatory": False, "replaces_published_values": False,
           "population": "all scored events (AP-ineligible events without new members included)",
           "definitions": {
               "added": "|predicted - seeds| = new_tp + new_fp (bgbench.forecast_retrospective_scoring)",
               "no_growth": "no AS joins after issue time (no_growth; equals new_members == 0)",
               "false_additions_on_no_growth": "every addition on a no-growth event is false (new_tp = 0 there)",
               "adds_nothing": "empty_new_prediction: the committed set equals the seed set",
               "jaccard": "full-target Jaccard of the committed set (seeds included) against the target set",
               "persistence": "the seed set; jaccard_persist; adds nothing by construction",
               "seed_aggregation": "statistic per training seed, then mean over the five seeds",
               "minus_persistence_interval": "paired_bootstrap, training seeds then incident-day blocks over all "
                                             f"scored events, {args.repetitions} repetitions, rng seed {args.seed}"},
           "r2_record_fields": list(R2_PRESENT), "r2_missing_fields": R2_MISSING,
           "r1_frozen_arm": "not applicable: the R1 SAGE is itself the 2025 model; the frozen arm exists only in R2 (60 s)",
           "provenance": prov, "results": res, "source_sha256": mb.sha(__file__)}
    Path(args.out_json).write_text(json.dumps(out, indent=1) + "\n")
    write_tex(args.out_tex, res)
    print("wrote", args.out_json, args.out_tex)


if __name__ == "__main__":
    main()
