#!/usr/bin/env python3
"""R2 set errors derived from the retained per-event records, and absolute P@10 per arm in R1 and R2.

Revision analysis, review round 4 (Opus NEW-3/NEW-5, Codex W2 and "Additional results recoverable from retained scores").
It extends paper/generated/set_errors.json, which left the R2 persistence Jaccard and the R2 false additions blank.

Derivations (stated per quantity in the JSON, ``derivations``):

* The 2-h target set accumulates and holds the seeds (sections/03-data.tex), so for every event with s seeds and R new
  members, |target| = s + R and the persistence Jaccard is J_persist = s / (s + R). R2 records carry ``seed_asns`` (s)
  and ``new_members`` (R). In R1 the identity is checked on every record: s = true_size - new_members (learned-arm
  files) and jaccard_persist * true_size = s, which holds if and only if the seeds lie inside the target.
* Every committed set holds all seeds (bgbench.forecast_retrospective_scoring.score_membership: a baseline decision must
  retain every seed, a learned decision is seeds | selected). On an event without new members (R = 0) every addition is
  false, and J = s / (s + FP), so FP = s (1/J - 1). In R1 this is checked against the recorded ``new_fp`` of every
  no-growth record of every arm and seed; in R2 the derived FP must be an integer (within 1e-6) on every no-growth record.
* On an event with new members, J = (s + TP) / (s + R + FP) does not separate TP and FP, so added counts and the
  adds-nothing share over all events stay unavailable for R2 (they need the forecast set). An arm that adds nothing has
  J = J_persist exactly; the share of events with J == J_persist is therefore an upper bound on the adds-nothing share.
  The R1 records give both values, which shows how tight the bound is.
* ``gap_share_no_growth``: the share of the mean Jaccard gap persistence - arm that falls on events without new members,
  sum_no-growth (J_persist - J) / sum_all (J_persist - J), from the seed-averaged per-event values; only for arms whose
  gap is large (history arms).
* Absolute ranking levels: event-macro means over eligible events of AP, P@5/10/20/50 and the coverage ceiling (share of
  new members among the candidates), per training seed, then the mean over seeds; persistence ranks nothing.

Reproduction checks (the script stops on any mismatch, before writing): R1 per-event files against the released
report's per_event_sha256; R2 arm identities against the released primary report; every published P@10 contrast
(R1: C1-C4 at 30/60 s; R2: C1-C4 at 30/60 s, C5 and C6 at 60 s) through the released evaluator
(bgbench.forecast_ranking.ranking_contrast, metric precision_at, budget 10) to 1e-12 in difference and interval; absolute
mean AP of every arm and seed against the reports' stratification_by_new_members (event-weighted); the published
full-target Jaccard values (C2, C5, mean and median history); and the R1 values of paper/generated/set_errors.json
(persistence Jaccard, no-growth false additions, arm minus persistence with its interval) through the derived route.

Intervals: training seeds then incident-day blocks over all scored events (Jaccard) or eligible events (P@10),
10,000 repetitions, seed 1701 (bgbench.forecast_ranking.paired_bootstrap), ordinary 95 %, descriptive, unadjusted.
No model is retrained, no prediction regenerated, no label file read.

Usage (repo root):
    .venv/bin/python -B scripts/paper_set_errors_r2.py \
        --r1-report .agents/operations/r1-v11-posteval-20261024/evidence/released/report.json \
        --r1-per-event <local copy of results/per_event> \
        --r1-arm-spec .agents/operations/r1-arm-spec-20261020/arm-spec.json \
        --r1-manifest-30 .agents/operations/r1-v11-posteval-20261024/evidence/released/retrospective-2025-v6-d30.json \
        --r1-manifest-60 .agents/operations/r1-v11-posteval-20261024/evidence/released/retrospective-2025-v6-d60.json \
        --r2-scores <local copy of primary-scores.json> \
        --r2-report docs/paper/r2-report-20261030/primary.json \
        --set-errors-json paper/generated/set_errors.json \
        --out-json paper/generated/set_errors_r2.json --out-tex paper/generated/set_errors_r2.tex
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
from bgbench.forecast_ranking import paired_bootstrap, ranking_contrast  # noqa: E402
import paper_month_boundary as mb  # noqa: E402  (hash helper, released-report constant, formatting)

REPS = 10_000
SEED = 1701
HORIZONS = (30, 60)
BUDGETS = ("5", "10", "20", "50")
R1_ARMS = ("sage_on", "sage_off", "none_on", "none_off", "online_history", "history_median", "online_history_native")
R2_ARMS = R1_ARMS + ("frozen_sage_on",)
TABLE_ARMS = ("persistence", "sage_on", "frozen_sage_on", "online_history", "history_median", "online_history_native")
HISTORY_ARMS = ("online_history", "history_median", "online_history_native")
NAME = {"persistence": "Persistence", "sage_on": "SAGE, history", "frozen_sage_on": "SAGE, frozen 2025",
        "online_history": "Online history (mean)", "history_median": "Online history (median)",
        "online_history_native": "Online history, native", "sage_off": "SAGE, no history",
        "none_on": "No MP, history", "none_off": "No MP, no history"}
R1_FIELDS = ("event_id", "eligible", "average_precision", "precision_at", "coverage_ceiling", "new_members", "jaccard",
             "jaccard_persist", "new_tp", "new_fp", "no_growth", "empty_new_prediction", "true_size")
R2_FIELDS = ("event_id", "eligible", "average_precision", "precision_at", "coverage_ceiling", "new_members", "jaccard",
             "input_status", "issue_time_variables", "seed_asns")
require = mb.require


def seed_summary(values):
    v = np.asarray(values, dtype=float)
    return {"mean": float(v.mean()), "per_seed": v.tolist(), "min": float(v.min()), "max": float(v.max())}


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
                by_id = {r["event_id"]: {k: r.get(k) for k in R1_FIELDS} for r in json.loads(path.read_text())}
                require(sorted(by_id) == sorted(order), f"{cell} does not cover the R1 cohort exactly")
                arms[arm][delta].append([by_id[e] for e in order])
    return arms, rows, report, {"report_sha256": mb.R1_REPORT_SHA, "per_event_sha256": files,
                                "arm_spec_sha256": mb.sha(args.r1_arm_spec),
                                "manifest_30_sha256": mb.sha(args.r1_manifest_30),
                                "manifest_60_sha256": mb.sha(args.r1_manifest_60)}


def load_r2(args):
    scores = json.loads(Path(args.r2_scores).read_text())
    report = json.loads(Path(args.r2_report).read_text())
    require(scores["kind"] == "newperiod_primary_computed_scores_v1", "Not the R2 primary computed scores")
    require(report["population"] == "new_period", "Not the R2 primary report")
    rows = {d: scores["rows"][str(d)] for d in HORIZONS}
    arms = {}
    for arm in R2_ARMS:
        require(scores["identities"][arm] == report["arms"][arm], f"R2 {arm}: identities differ from the report")
        arms[arm] = {}
        for d in HORIZONS:
            seeds = scores["arms"][arm].get(str(d))
            if seeds is None:
                continue
            arms[arm][d] = []
            for s in seeds:
                require([r["event_id"] for r in s] == [r["event_id"] for r in rows[d]], f"R2 {arm}@{d} misaligned")
                arms[arm][d].append([{k: r.get(k) for k in R2_FIELDS} for r in s])
    return arms, rows, report, {"primary_scores_sha256": mb.sha(args.r2_scores),
                                "primary_report_sha256": mb.sha(args.r2_report),
                                "evaluation_window": report["evaluation_window"]}


# ----------------------------------------------------------------------------- per-event seeds and new members

def r1_seed_counts(arms, delta):
    """s per event from the learned-arm records, with the seed-subset identity checked on every record."""
    s_ref, r_ref = None, None
    for arm in ("sage_on", "sage_off", "none_on", "none_off"):
        for seed in arms[arm][delta]:
            t = np.array([r["true_size"] for r in seed], dtype=float)
            R = np.array([r["new_members"] for r in seed], dtype=float)
            jp = np.array([r["jaccard_persist"] for r in seed], dtype=float)
            s = t - R
            require((s >= 1).all(), f"R1@{delta} {arm}: an event without seeds")
            require(np.abs(jp * t - s).max() < 1e-9, f"R1@{delta} {arm}: seeds not inside the target (J_persist*|T| != s)")
            if s_ref is None:
                s_ref, r_ref = s, R
            require((s == s_ref).all() and (R == r_ref).all(), f"R1@{delta}: seed or new-member counts differ by arm")
    for arm in HISTORY_ARMS:
        for seed in arms[arm][delta]:
            require((np.array([r["new_members"] for r in seed]) == r_ref).all(), f"R1@{delta} {arm}: new members differ")
            jp = np.array([r["jaccard_persist"] for r in seed], dtype=float)
            require(np.abs(jp - s_ref / (s_ref + r_ref)).max() < 1e-12, f"R1@{delta} {arm}: J_persist identity fails")
    return s_ref, r_ref


def r2_seed_counts(arms, delta):
    """s per event from seed_asns, identical across arms and training seeds, and equal to seeds_at_issue."""
    ref_seeds, ref_r = None, None
    for arm in R2_ARMS:
        for seed in arms[arm].get(delta, []):
            seeds = [tuple(sorted(set(r["seed_asns"]))) for r in seed]
            R = [r["new_members"] for r in seed]
            require(all(len(set(r["seed_asns"])) == len(r["seed_asns"]) for r in seed), f"R2 {arm}@{delta}: duplicate seed")
            require(all(r["issue_time_variables"]["seeds_at_issue"] == len(x) for r, x in zip(seed, seeds)),
                    f"R2 {arm}@{delta}: seeds_at_issue differs from seed_asns")
            if ref_seeds is None:
                ref_seeds, ref_r = seeds, R
            require(seeds == ref_seeds and R == ref_r, f"R2 {arm}@{delta}: seeds or new members differ between arms")
    s = np.array([len(x) for x in ref_seeds], dtype=float)
    require((s >= 1).all(), f"R2@{delta}: an event without seeds")
    return s, np.array(ref_r, dtype=float)


# ----------------------------------------------------------------------------- set errors

def set_stats(period, arm, seeds, s, R, delta):
    """Derived set-error statistics per training seed (records aligned with s and R)."""
    nog = R == 0
    jp = s / (s + R)
    out = {k: [] for k in ("jaccard", "no_growth_any_share", "no_growth_false_mean", "no_growth_false_total",
                           "jaccard_equals_persistence_share", "jaccard_equals_persistence_share_growth")}
    direct = {k: [] for k in ("no_growth_false_mean", "adds_nothing_share")}
    for seed in seeds:
        j = np.array([r["jaccard"] for r in seed], dtype=float)
        require(np.isfinite(j).all() and (j > 0).all() and (j <= 1 + 1e-12).all(), f"{period} {arm}@{delta}: bad Jaccard")
        fp = s[nog] * (1 / j[nog] - 1)
        require(np.abs(fp - np.rint(fp)).max(initial=0) < 1e-6, f"{period} {arm}@{delta}: non-integer derived FP")
        fp = np.rint(fp)
        if period == "R1":
            rec = np.array([r["new_fp"] for r, g in zip(seed, nog) if g], dtype=float)
            require((rec == fp).all(), f"R1 {arm}@{delta}: derived no-growth FP differs from the recorded new_fp")
            require(all(r["no_growth"] == g for r, g in zip(seed, nog)), f"R1 {arm}@{delta}: no_growth flag differs")
            direct["no_growth_false_mean"].append(rec.mean())
            direct["adds_nothing_share"].append(np.mean([r["empty_new_prediction"] for r in seed]))
        same = np.abs(j - jp) < 1e-12
        out["jaccard"].append(j.mean())
        out["no_growth_any_share"].append((fp > 0).mean())
        out["no_growth_false_mean"].append(fp.mean())
        out["no_growth_false_total"].append(fp.sum())
        out["jaccard_equals_persistence_share"].append(same.mean())
        out["jaccard_equals_persistence_share_growth"].append(same[~nog].mean())
    result = {k: seed_summary(v) for k, v in out.items()}
    if period == "R1":
        result["recorded"] = {k: seed_summary(v) for k, v in direct.items()}
        # the upper bound must hold seed by seed
        require(all(a <= b + 1e-12 for a, b in zip(direct["adds_nothing_share"], out["jaccard_equals_persistence_share"])),
                f"R1 {arm}@{delta}: J == J_persist share below the adds-nothing share")
    return result


def gap_share(seeds, s, R):
    jp = s / (s + R)
    j = np.mean([[r["jaccard"] for r in seed] for seed in seeds], axis=0)
    gap = jp - j
    return {"mean_gap": float(gap.mean()), "no_growth_share_of_gap": float(gap[R == 0].sum() / gap.sum()),
            "growth_share_of_gap": float(gap[R > 0].sum() / gap.sum())}


def minus_persistence(seeds, s, R, rows, repetitions, seed):
    left = np.array([[r["jaccard"] for r in x] for x in seeds], dtype=float)
    persist = np.atleast_2d(s / (s + R))
    res = paired_bootstrap(left, persist, incident_day_blocks(rows), repetitions=repetitions, seed=seed)
    return {k: res[k] for k in ("difference", "ci95", "p_value", "events", "blocks", "training_seeds")}


# ----------------------------------------------------------------------------- ranking levels

def ranking_levels(seeds):
    elig = np.array([r["eligible"] for r in seeds[0]])
    for x in seeds:
        require((np.array([r["eligible"] for r in x]) == elig).all(), "Training seeds disagree on eligibility")
    out = {"eligible_events": int(elig.sum())}
    out["average_precision"] = seed_summary([np.mean([r["average_precision"] for r, e in zip(x, elig) if e])
                                             for x in seeds])
    out["coverage_ceiling"] = seed_summary([np.mean([r["coverage_ceiling"] for r, e in zip(x, elig) if e])
                                            for x in seeds])
    out["precision_at"] = {b: seed_summary([np.mean([r["precision_at"][b] for r, e in zip(x, elig) if e])
                                            for x in seeds]) for b in BUDGETS}
    return out


def check_strata_ap(period, arm, delta, seeds, strat):
    """Absolute mean AP of each seed equals the report's event-weighted stratum means."""
    per_seed = strat[arm][str(delta)]
    require(len(per_seed) == len(seeds), f"{period} {arm}@{delta}: stratification seed count differs")
    for x, st in zip(seeds, per_seed):
        n = sum(v["events"] for v in st["strata"].values())
        ap = sum(v["events"] * v["mean_average_precision"] for v in st["strata"].values()) / n
        mine = np.mean([r["average_precision"] for r in x if r["eligible"]])
        require(n == sum(r["eligible"] for r in x) and abs(ap - mine) < 1e-12,
                f"{period} {arm}@{delta}: absolute AP {mine:.12f} differs from the report strata {ap:.12f}")


def p10_contrast(left, right, rows, repetitions, seed):
    res = ranking_contrast(left, right, rows, metric="precision_at", budget=10, repetitions=repetitions, seed=seed)
    return {k: res[k] for k in ("difference", "ci95", "p_value", "eligible_events", "blocks", "training_seeds")}


def same(a, b, what):
    require(abs(a["difference"] - b["difference"]) < 1e-12 and np.allclose(a["ci95"], b["ci95"], atol=1e-12, rtol=0),
            f"{what}: got {a['difference']:.12f} {a['ci95']}, reference {b['difference']:.12f} {b['ci95']}")


# ----------------------------------------------------------------------------- period driver

def period_results(period, arms, rows, report, set_errors_ref, repetitions, seed):
    analysis = report["analysis_ranking_v1_c1_c4"] if period == "R1" else report
    fam = analysis["families"]
    strat = analysis["stratification_by_new_members"]
    hist = analysis["history_median_vs_mean_jaccard"]["horizons"]
    out = {}
    for d in HORIZONS:
        present = [a for a in arms if d in arms[a]]
        s, R = (r1_seed_counts if period == "R1" else r2_seed_counts)(arms, d)
        entry = {"events": len(s), "no_growth_events": int((R == 0).sum()), "eligible_events": int((R > 0).sum()),
                 "persistence": {"jaccard": float(np.mean(s / (s + R))), "mean_seeds": float(s.mean()),
                                 "ranks_nothing": True}}
        if period == "R1":
            entry["persistence"]["recorded_jaccard_persist"] = float(np.mean([r["jaccard_persist"]
                                                                              for r in arms["sage_on"][d][0]]))
        arms_out = {}
        for arm in present:
            seeds = arms[arm][d]
            e = {"training_seeds": len(seeds), "set": set_stats(period, arm, seeds, s, R, d),
                 "ranking": ranking_levels(seeds)}
            require(e["ranking"]["eligible_events"] == entry["eligible_events"], f"{period} {arm}@{d}: eligible count")
            check_strata_ap(period, arm, d, seeds, strat)
            e["set"]["minus_persistence"] = minus_persistence(seeds, s, R, rows[d], repetitions, seed)
            if arm in HISTORY_ARMS:
                e["set"]["gap_decomposition"] = gap_share(seeds, s, R)
            arms_out[arm] = e
        entry["arms"] = arms_out

        # --- reproduction of published values
        jac = {a: arms_out[a]["set"]["jaccard"]["mean"] for a in arms_out}
        c2 = fam["full_target_jaccard"]["contrasts"][f"C2@{d}"]["difference"]
        require(abs(jac["sage_on"] - jac["online_history"] - c2) < 1e-12, f"{period} C2@{d} full-target Jaccard")
        require(abs(jac["online_history"] - hist[str(d)]["mean_extent_jaccard"]) < 1e-12, f"{period} mean history J @{d}")
        require(abs(jac["history_median"] - hist[str(d)]["median_extent_jaccard"]) < 1e-12, f"{period} median J @{d}")
        if "frozen_sage_on" in arms_out:
            c5 = fam["full_target_jaccard"]["contrasts"]["C5@60"]
            require(c5["left"] == "frozen_sage_on" and c5["right"] == "online_history"
                    and abs(jac["frozen_sage_on"] - jac["online_history"] - c5["difference"]) < 1e-12, "R2 C5@60 Jaccard")
        p10 = {}
        for key, c in fam["p_at_10"]["contrasts"].items():
            if not key.endswith(f"@{d}"):
                continue
            mine = p10_contrast(arms[c["left"]][d], arms[c["right"]][d], rows[d], repetitions, seed)
            same(mine, c, f"{period} P@10 {key}")
            require(mine["eligible_events"] == c["eligible_events"], f"{period} P@10 {key}: eligible events")
            lv = {a: arms_out[a]["ranking"]["precision_at"]["10"]["mean"] for a in (c["left"], c["right"])}
            require(abs(lv[c["left"]] - lv[c["right"]] - c["difference"]) < 1e-12, f"{period} P@10 {key}: levels")
            p10[key] = {"left": c["left"], "right": c["right"], "difference": c["difference"], "ci95": c["ci95"],
                        "reproduced_exactly": True}
        entry["published_p_at_10_contrasts"] = p10
        # descriptive P@10 contrasts of the native arm (not in a published family)
        entry["p_at_10_native_contrasts"] = {
            "online_history_native_minus_online_history": p10_contrast(
                arms["online_history_native"][d], arms["online_history"][d], rows[d], repetitions, seed),
            "sage_on_minus_online_history_native": p10_contrast(
                arms["sage_on"][d], arms["online_history_native"][d], rows[d], repetitions, seed)}
        if period == "R1":
            ref = set_errors_ref["results"]["R1"][str(d)]
            require(abs(entry["persistence"]["jaccard"] - ref["persistence"]["jaccard"]["mean"]) < 1e-12,
                    f"R1@{d}: derived persistence Jaccard differs from set_errors.json")
            for a in ("sage_on", "online_history", "history_median"):
                st = arms_out[a]["set"]
                same(st["minus_persistence"], ref[a]["minus_persistence"], f"R1 {a}@{d} minus persistence")
                for k in ("no_growth_any_share", "no_growth_false_total"):
                    require(abs(st[k]["mean"] - ref[a][k]["mean"]) < 1e-9, f"R1 {a}@{d}: {k} differs from set_errors")
                require(abs(st["no_growth_false_mean"]["mean"] - ref[a]["no_growth_added_mean"]["mean"]) < 1e-9,
                        f"R1 {a}@{d}: no-growth false additions differ from set_errors.json")
                require(abs(st["recorded"]["adds_nothing_share"]["mean"] - ref[a]["adds_nothing_share"]["mean"]) < 1e-12,
                        f"R1 {a}@{d}: adds-nothing share differs from set_errors.json")
            entry["set_errors_json_reproduced"] = True
        out[str(d)] = entry
        for a in TABLE_ARMS:
            if a in arms_out:
                e = arms_out[a]
                mp = e["set"]["minus_persistence"]
                print(f"{period}@{d} {a:22s} P@10 {e['ranking']['precision_at']['10']['mean']:.4f}  "
                      f"cov {e['ranking']['coverage_ceiling']['mean']:.4f}  J {e['set']['jaccard']['mean']:.4f}  "
                      f"-persist {mp['difference']:+.5f} [{mp['ci95'][0]:+.5f}, {mp['ci95'][1]:+.5f}]  "
                      f"no-growth any {e['set']['no_growth_any_share']['mean']:.4f} "
                      f"mean {e['set']['no_growth_false_mean']['mean']:.3f}  "
                      f"J==Jp {e['set']['jaccard_equals_persistence_share']['mean']:.4f}", flush=True)
        print(f"{period}@{d} persistence J {entry['persistence']['jaccard']:.6f}  no-growth "
              f"{entry['no_growth_events']}/{entry['events']}", flush=True)
    return out


# ----------------------------------------------------------------------------- LaTeX

def small_interval(diff, ci):
    """Four decimals if any value reaches 0.001 in magnitude, else the fewest of 6, 7, 8 at which no nonzero value
    rounds to zero (the learned arms), so no entry reads as a signed zero."""
    values = (diff, *ci)
    if max(map(abs, values)) >= 0.001:
        digits = 4
    else:
        digits = next((d for d in (6, 7) if all(x == 0 or round(abs(x), d) > 0 for x in values)), 8)

    def s(x):
        return f"{x:+.{digits}f}".replace("-", "$-$")
    return f"{s(diff)} [{s(ci[0])}, {s(ci[1])}]"


PANEL_A_ARMS = ("sage_on", "online_history", "history_median", "persistence")   # rows of set_errors.tex (R1 only)


def write_tex(path, res):
    dash = "--"
    lines = [
        "% Generated by scripts/paper_set_errors_r2.py; do not edit by hand.",
        "% All scored events for the set columns, eligible events for P@10. P@10: absolute precision at ten (new members",
        "% among the first ten ranked candidates / 10), mean over five training seeds for learned arms. J: full-target",
        "% Jaccard. J - persistence: paired difference with an ordinary 95% interval (training seeds, then incident-day",
        "% blocks; 10,000 repetitions, seed 1701). No-growth events (no new members): Any, share with at least one false",
        "% addition; Mean, false additions per such event. R2 persistence and false additions are derived from seed_asns,",
        "% new_members and jaccard (J_persist = s/(s+R); FP = s(1/J-1) without growth); R1 values are recorded ones.",
        "% In parentheses: scored events / events without new members / eligible events.",
        "% J - persistence has four decimals, or six to eight where every value of the row is below 0.001 in magnitude.",
        "\\begin{tabular}{@{}lllrrlrr@{}}",
        "\\toprule",
        " & & & & & & \\multicolumn{2}{c}{No-growth events} \\\\",
        "\\cmidrule(l){7-8}",
        "Period & $\\Delta$ & Forecast & P@10 & $J$ & $J -$ persistence & Any & Mean \\\\",
        "\\midrule",
    ]

    def thousands(n):
        return f"{n:,}".replace(",", "{,}")

    for period in ("R1", "R2"):
        for d in HORIZONS:
            entry = res[period][str(d)]
            leads = [f"{period} & {d}\\,s",
                     f" & ({thousands(entry['events'])}/{thousands(entry['no_growth_events'])}/"
                     f"{thousands(entry['eligible_events'])})"]
            i = 0
            for arm in TABLE_ARMS:
                in_panel_a = period == "R1" and arm in PANEL_A_ARMS   # panel A prints these R1 values already
                if arm == "persistence" and in_panel_a:
                    continue                                       # nothing left to print
                if arm == "persistence":
                    cells = [dash, dash if in_panel_a else f"{entry['persistence']['jaccard']:.3f}", dash,
                             dash if in_panel_a else "0", dash if in_panel_a else "0"]
                elif arm in entry["arms"]:
                    e = entry["arms"][arm]
                    mp = e["set"]["minus_persistence"]
                    cells = [f"{e['ranking']['precision_at']['10']['mean']:.3f}",
                             dash if in_panel_a else f"{e['set']['jaccard']['mean']:.3f}",
                             small_interval(mp["difference"], mp["ci95"]),
                             dash if in_panel_a else f"{e['set']['no_growth_any_share']['mean']:.3f}",
                             dash if in_panel_a else f"{e['set']['no_growth_false_mean']['mean']:.2f}"]
                else:
                    continue
                lead = leads[i] if i < len(leads) else " & "
                i += 1
                lines.append(f"{lead} & {NAME[arm]} & " + " & ".join(cells) + " \\\\")
            if d == HORIZONS[0]:
                lines.append("\\cmidrule(l){2-8}")
        if period == "R1":
            lines.append("\\midrule")
    lines += ["\\bottomrule", "\\end{tabular}", ""]
    Path(path).write_text("\n".join(lines))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ("r1-report", "r1-per-event", "r1-arm-spec", "r1-manifest-30", "r1-manifest-60", "r2-scores",
                 "r2-report", "set-errors-json", "out-json", "out-tex"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--repetitions", type=int, default=REPS)
    p.add_argument("--seed", type=int, default=SEED)
    args = p.parse_args()
    ref = json.loads(Path(args.set_errors_json).read_text())
    require(ref["kind"] == "set_error_accounting_revision_analysis", "Not set_errors.json")
    res, prov = {}, {}
    arms, rows, report, prov["R1"] = load_r1(args)
    res["R1"] = period_results("R1", arms, rows, report, ref, args.repetitions, args.seed)
    del arms
    arms, rows, report, prov["R2"] = load_r2(args)
    res["R2"] = period_results("R2", arms, rows, report, ref, args.repetitions, args.seed)
    del arms
    out = {
        "kind": "set_errors_r2_and_absolute_p_at_10_revision_analysis", "confirmatory": False,
        "replaces_published_values": False, "extends": "paper/generated/set_errors.json (R2 rows left blank there)",
        "derivations": {
            "seed_count_s": "R2: |seed_asns| of the record (identical across arms and training seeds, equal to "
                            "issue_time_variables.seeds_at_issue). R1: true_size - new_members of the learned-arm records.",
            "seeds_inside_target": "The 2-h target accumulates and holds the seeds (sections/03-data.tex). Checked on every "
                                   "R1 record: jaccard_persist * true_size == true_size - new_members, which holds iff the "
                                   "seeds lie inside the target. R2 records carry no target size; the identity is "
                                   "assumed from the definition, and the integer check below and the J == J_persist "
                                   "share of the learned arms are consistent with it.",
            "persistence_jaccard": "J_persist = s / (s + R), R = new_members. Equals the recorded jaccard_persist on every "
                                   "R1 record.",
            "no_growth_false_additions": "On an event with R = 0 every committed set holds all seeds and every addition is "
                                         "false, so J = s / (s + FP) and FP = s (1/J - 1). Equals the recorded new_fp on "
                                         "every R1 no-growth record of every arm and seed; integer within 1e-6 on every "
                                         "R2 no-growth record.",
            "jaccard_equals_persistence_share": "Share of events with |J - J_persist| < 1e-12. An arm that adds nothing has "
                                                "J = J_persist, so this is an upper bound on the adds-nothing share over "
                                                "all events (equality can also occur when TP (s + R) = s FP). R1 gives the "
                                                "recorded adds-nothing share next to it.",
            "gap_decomposition": "sum over no-growth events of (J_persist - J) / sum over all events, J averaged over "
                                 "training seeds per event; history arms only.",
            "minus_persistence": "paired_bootstrap of the arm's per-event Jaccard against J_persist over all scored "
                                 "events, training seeds then incident-day blocks.",
            "ranking_levels": "event-macro mean over eligible events per training seed, then the mean over seeds; "
                              "precision_at budgets 5/10/20/50 and coverage_ceiling from the records.",
            "p_at_10_native_contrasts": "descriptive paired P@10 contrasts that include the native arm (not part of a "
                                        "published family), ranking_contrast with metric precision_at, budget 10."},
        "unavailable_for_r2": {
            "added_count_all_events": "needs the forecast set or new_tp/new_fp; on events with growth, J does not "
                                      "separate true from false additions",
            "adds_nothing_share_all_events": "same reason; only the upper bound jaccard_equals_persistence_share is given",
            "false_additions_on_growth_events": "same reason"},
        "intervals": {"repetitions": args.repetitions, "rng_seed": args.seed, "kind": "ordinary 95 % percentile",
                      "p_values": "unadjusted, descriptive only"},
        "reproduced": ["every published P@10 contrast (difference and interval) of R1 and R2",
                       "absolute AP of every arm and training seed against stratification_by_new_members",
                       "published full-target Jaccard C2 (both periods), C5@60 (R2), mean and median history Jaccard",
                       "R1 persistence Jaccard, no-growth false additions, adds-nothing share and arm-minus-persistence "
                       "intervals of paper/generated/set_errors.json"],
        "reference_set_errors_json_sha256": mb.sha(args.set_errors_json),
        "provenance": prov, "results": res, "source_sha256": mb.sha(__file__)}
    Path(args.out_json).write_text(json.dumps(out, indent=1) + "\n")
    write_tex(args.out_tex, res)
    print("wrote", args.out_json, args.out_tex)


if __name__ == "__main__":
    main()
