#!/usr/bin/env python3
"""Month-boundary sensitivity of the R1 and R2 forecast contrasts (revision analysis, review round 2, W4/REQ-2).

The leak identifier tests path-triple novelty per calendar month, so a recurring triple looks new on the first day of
every month. This script re-evaluates the existing paired AP contrasts of the released R1 report and of the released R2
primary result on three populations of eligible events:

* ``all``      every eligible event (must reproduce the published difference and interval exactly);
* ``no_day1``  events whose identifier date (the YYYYMMDD prefix of event_id) is not the 1st of a month;
* ``no_day1_3`` events whose identifier date is not the 1st, 2nd or 3rd of a month.

The identifier date is the one behind the paper's "1,174 of 8,412 leaks start on the first day of a month"; the
replay ``onset`` field can fall an hour earlier (one-hour look-back) and is used only for the resampling blocks, exactly
as in the released evaluators.

Statistic and interval are those of the released evaluators, called unchanged (bgbench.forecast_ranking.paired_bootstrap
and bgbench.forecast_analysis.incident_day_blocks): event-macro mean AP difference over eligible events, averaged over
the five training seeds (a single-run baseline is broadcast); percentile interval from resampling training seeds and
then whole incident-day blocks (each incident assigned to the UTC day of its first onset among the analysed events),
10,000 repetitions, numpy default_rng(1701). For a subset the blocks are rebuilt from the kept events. Intervals are
ordinary 95 % intervals, not simultaneous; p-values are unadjusted and descriptive. No model is retrained, no
prediction is regenerated and no published number is changed: this is a revision analysis beside the sealed results.

Inputs (all read-only):
* R1: the released report (SHA-256 049c7a9c...) and its per-event score files, fetched read-only from
  <CLUSTER_STORAGE>/.../r1-release-parallel-v11-20261024/control-v1/results/per_event/ (each file is checked against the report's
  per_event_sha256); the frozen arm spec; the R1 cohort manifests (event_id, onset, incident_id);
  the 2025 leak event table of the corrected release (selection reason: Radar match vs volume).
* R2: primary-scores.json of the released R2 primary result, fetched read-only from
  <CLUSTER_STORAGE>/.../data-custodian/single-R2-v1/arms/000/attempt/, and the released primary.json.

Usage (repo root):
    .venv/bin/python -B scripts/paper_month_boundary.py \
        --r1-report .agents/operations/r1-v11-posteval-20261024/evidence/released/report.json \
        --r1-per-event <local copy of results/per_event> \
        --r1-arm-spec .agents/operations/r1-arm-spec-20261020/arm-spec.json \
        --r1-manifest-30 .agents/operations/r1-v11-posteval-20261024/evidence/released/retrospective-2025-v6-d30.json \
        --r1-manifest-60 .agents/operations/r1-v11-posteval-20261024/evidence/released/retrospective-2025-v6-d60.json \
        --r1-events data/corrected-release-20261016/eventset/2025_leak/events.parquet \
        --r2-scores <local copy of primary-scores.json> \
        --r2-report docs/paper/r2-report-20261030/primary.json \
        --out-json paper/generated/month_boundary.json --out-tex paper/generated/month_boundary.tex
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from bgbench.forecast_analysis import incident_day_blocks  # noqa: E402
from bgbench.forecast_ranking import paired_bootstrap, ranking_contrast  # noqa: E402

REPS = 10_000
SEED = 1701
R1_REPORT_SHA = "049c7a9c433de1f4d03c4b5a3f7194316fc991f2c56e41ec64aac5c05b96339d"
CONTRASTS = {"C1": ("sage_on", "none_on"), "C2": ("sage_on", "online_history"), "C3": ("sage_on", "sage_off"),
             "C4": ("none_on", "none_off"), "native": ("sage_on", "online_history_native")}
LABEL = {"C1": "C1 (SAGE $-$ no MP, history on)", "C2": "C2 (SAGE $-$ online history, shared)",
         "C3": "C3 (SAGE: history on $-$ off)", "C4": "C4 (no MP: history on $-$ off)",
         "native": "Native (SAGE $-$ online history, native)"}
HORIZONS = (30, 60)
SUBSETS = {"all": set(), "no_day1": {1}, "no_day1_3": {1, 2, 3}}
ARMS = sorted({a for pair in CONTRASTS.values() for a in pair})


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def require(condition, message):
    if not condition:
        raise SystemExit(f"STOP: {message}")


def id_day(event_id):
    """Day of month of the identifier time (event_id starts with YYYYMMDDTHHMMSS)."""
    require(len(event_id) > 15 and event_id[8] == "T" and event_id[:8].isdigit(), f"Unexpected event_id {event_id}")
    return int(event_id[6:8])


def slim(rows):
    return [{"event_id": r["event_id"], "eligible": bool(r["eligible"]), "average_precision": r["average_precision"]}
            for r in rows]


def subset_contrast(left_seeds, right_seeds, rows, exclude_days, repetitions, seed):
    """ranking_contrast restricted to eligible events whose identifier day is not in ``exclude_days``."""
    left = np.array([[e["average_precision"] for e in s] for s in left_seeds], dtype=float)
    right = np.array([[e["average_precision"] for e in s] for s in right_seeds], dtype=float)
    masks = [np.array([e["eligible"] for e in s]) for s in list(left_seeds) + list(right_seeds)]
    require(all((m == masks[0]).all() for m in masks), "Arms or seeds disagree on the eligible cohort")
    keep = masks[0] & np.array([id_day(r["event_id"]) not in exclude_days for r in rows])
    kept = [r for r, k in zip(rows, keep) if k]
    result = paired_bootstrap(left[:, keep], right[:, keep], incident_day_blocks(kept),
                              repetitions=repetitions, seed=seed)
    result.update(eligible_events=int(keep.sum()), left_mean=float(left[:, keep].mean(axis=1).mean()),
                  right_mean=float(right[:, keep].mean(axis=1).mean()))
    return result


def evaluate(period, arms, rows, published, repetitions, seed, check_full_evaluator=True):
    out = {}
    for delta in HORIZONS:
        for cid, (left, right) in CONTRASTS.items():
            key = f"{cid}@{delta}"
            a, b = arms[left][delta], arms[right][delta]
            entry = {"left": left, "right": right, "horizon_seconds": delta}
            for name, days in SUBSETS.items():
                res = subset_contrast(a, b, rows[delta], days, repetitions, seed)
                entry[name] = {k: res[k] for k in ("difference", "ci95", "p_value", "eligible_events", "blocks",
                                                   "training_seeds", "left_mean", "right_mean")}
            pub = published[key]
            got = entry["all"]
            if check_full_evaluator:
                # The released evaluator itself, on the same inputs, must give the same numbers.
                ref = ranking_contrast(a, b, rows[delta], metric="average_precision", repetitions=repetitions, seed=seed)
                require(abs(ref["difference"] - got["difference"]) < 1e-12
                        and np.allclose(ref["ci95"], got["ci95"], atol=1e-12, rtol=0),
                        f"{period} {key}: subset path differs from ranking_contrast")
            ok = (round(got["difference"], 4) == round(pub["difference"], 4)
                  and [round(x, 4) for x in got["ci95"]] == [round(x, 4) for x in pub["ci95"]]
                  and got["eligible_events"] == pub["eligible_events"] and got["blocks"] == pub["blocks"])
            require(ok, f"{period} {key} does not reproduce the published value: got {got['difference']:.6f} "
                        f"{got['ci95']} ({got['eligible_events']} events, {got['blocks']} blocks), published "
                        f"{pub['difference']:.6f} {pub['ci95']} ({pub['eligible_events']}, {pub['blocks']})")
            entry["published"] = {k: pub[k] for k in ("difference", "ci95", "eligible_events", "blocks")}
            entry["reproduced_exactly"] = bool(abs(got["difference"] - pub["difference"]) < 1e-12
                                               and np.allclose(got["ci95"], pub["ci95"], atol=1e-12, rtol=0))
            out[key] = entry
            print(f"{period} {key}: " + "  ".join(
                f"{n} {entry[n]['difference']:+.4f} [{entry[n]['ci95'][0]:+.4f}, {entry[n]['ci95'][1]:+.4f}] "
                f"n={entry[n]['eligible_events']}" for n in SUBSETS), flush=True)
    return out


def day_class(day):
    return "day1" if day == 1 else "day2_3" if day <= 3 else "day4plus"


def composition(rows, eligible, reason=None):
    """Counts of events (all and eligible) by identifier-day class, optionally by selection reason."""
    out = {}
    for delta in HORIZONS:
        elig = eligible[delta]
        c = {"events": Counter(), "eligible": Counter()}
        for r, e in zip(rows[delta], elig):
            cls = day_class(id_day(r["event_id"]))
            keys = [cls] + ([f"{reason[r['event_id']]}/{cls}", reason[r["event_id"]]] if reason else [])
            for k in keys:
                c["events"][k] += 1
                if e:
                    c["eligible"][k] += 1
        out[str(delta)] = {
            "events": len(rows[delta]), "eligible_events": int(sum(elig)),
            "by_identifier_day": {k: {"events": c["events"][k], "eligible": c["eligible"][k]}
                                  for k in ("day1", "day2_3", "day4plus")},
            "onset_field_day1_events": sum(r["onset"][8:10] == "01" for r in rows[delta]),
        }
        if reason:
            out[str(delta)]["by_selection"] = {
                f"{s}/{cls}": {"events": c["events"][f"{s}/{cls}"], "eligible": c["eligible"][f"{s}/{cls}"]}
                for s in sorted(set(reason.values())) for cls in ("day1", "day2_3", "day4plus")}
            out[str(delta)]["by_selection"].update(
                {s: {"events": c["events"][s], "eligible": c["eligible"][s]} for s in sorted(set(reason.values()))})
    return out


def load_r1(args):
    require(sha(args.r1_report) == R1_REPORT_SHA, "R1 report is not the released one")
    report = json.loads(Path(args.r1_report).read_text())
    per_event_sha = report["per_event_sha256"]
    spec = json.loads(Path(args.r1_arm_spec).read_text())
    require(spec["kind"] == "frozen_evaluation_arm_spec" and spec["population"] == "retrospective_r1", "Bad arm spec")
    rows, arms, files = {}, {a: {} for a in ARMS}, {}
    for delta, manifest in ((30, args.r1_manifest_30), (60, args.r1_manifest_60)):
        m = json.loads(Path(manifest).read_text())
        require(m["delta_s"] == delta, f"Manifest {manifest} is not the {delta} s manifest")
        rows[delta] = [{"event_id": e["event_id"], "onset": e["onset"], "incident_id": e["incident_id"]}
                       for e in m["events"] if e["split"] == "test"]
        order = [r["event_id"] for r in rows[delta]]
        for arm in ARMS:
            arms[arm][delta] = []
            for cell in spec["arms"][arm][str(delta)]:
                path = Path(args.r1_per_event) / (cell.replace("/", "__", 1) + ".json")
                digest = sha(path)
                require(per_event_sha.get(cell) == digest, f"{cell}: per-event file differs from the released hash")
                files[cell] = digest
                by_id = {r["event_id"]: r for r in slim(json.loads(path.read_text()))}
                require(sorted(by_id) == sorted(order), f"{cell} does not cover the R1 cohort exactly")
                arms[arm][delta].append([by_id[e] for e in order])
    published = {}
    fam = report["analysis_ranking_v1_c1_c4"]["families"]
    for delta in HORIZONS:
        for cid in ("C1", "C2", "C3", "C4"):
            published[f"{cid}@{delta}"] = fam["primary_ap"]["contrasts"][f"{cid}@{delta}"]
        published[f"native@{delta}"] = fam["whole_system_ap"]["contrasts"][f"C2-native@{delta}"]
    return arms, rows, published, {"report_sha256": R1_REPORT_SHA, "per_event_sha256": files,
                                   "arm_spec_sha256": sha(args.r1_arm_spec),
                                   "manifest_30_sha256": sha(args.r1_manifest_30),
                                   "manifest_60_sha256": sha(args.r1_manifest_60)}


def load_r2(args):
    scores = json.loads(Path(args.r2_scores).read_text())
    report = json.loads(Path(args.r2_report).read_text())
    require(scores["kind"] == "newperiod_primary_computed_scores_v1", "Not the R2 primary computed scores")
    require(report["population"] == "new_period", "Not the R2 primary report")
    for arm in ARMS:
        require(scores["identities"][arm] == report["arms"][arm], f"R2 {arm}: identities differ from the report")
    rows = {d: scores["rows"][str(d)] for d in HORIZONS}
    arms = {a: {d: [slim(s) for s in scores["arms"][a][str(d)]] for d in HORIZONS} for a in ARMS}
    for a in ARMS:
        for d in HORIZONS:
            for s in arms[a][d]:
                require([r["event_id"] for r in s] == [r["event_id"] for r in rows[d]], f"R2 {a}@{d} misaligned")
    fam = report["families"]
    published = {}
    for delta in HORIZONS:
        for cid in ("C1", "C2", "C3", "C4"):
            published[f"{cid}@{delta}"] = fam["primary_ap"]["contrasts"][f"{cid}@{delta}"]
        published[f"native@{delta}"] = fam["whole_system_ap"]["contrasts"][f"C2-native@{delta}"]
    return arms, rows, published, {"primary_scores_sha256": sha(args.r2_scores), "primary_report_sha256":
                                   sha(args.r2_report), "evaluation_window": report["evaluation_window"]}


def signed(x):
    return f"{x:+.4f}".replace("-", "$-$")


def interval(ci):
    return f"[{signed(ci[0])}, {signed(ci[1])}]"


def write_tex(path, results, comp):
    lines = [
        "% Generated by scripts/paper_month_boundary.py; do not edit by hand.",
        "\\begin{table*}",
        "\\caption{Month-boundary sensitivity of the AP contrasts (revision analysis). Paired difference over eligible "
        "events, mean over five training seeds, with ordinary 95\\,\\% intervals from resampling training seeds and "
        "UTC-day blocks, each incident in the day of its first onset (10{,}000 repetitions, seed 1701). \\emph{All}: the published values. \\emph{No d1}: "
        "events whose identifier date is the first of a month removed; \\emph{no d1--3}: first to third removed. "
        "\\emph{Native}: SAGE with history minus native history (online history on its native candidates). "
        "The intervals are unadjusted and descriptive. "
        "Last rows: eligible events.}",
        "\\label{tab:month-boundary}",
        "\\scriptsize",
        "\\setlength{\\tabcolsep}{3pt}",
        "\\begin{tabular}{@{}lllllll@{}}",
        "\\toprule",
        " & \\multicolumn{3}{c}{R1 (Sep--Dec 2025)} & \\multicolumn{3}{c}{R2 (1 Sep--16 Oct 2026)} \\\\",
        "\\cmidrule(lr){2-4}\\cmidrule(l){5-7}",
        "Contrast & All & No d1 & No d1--3 & All & No d1 & No d1--3 \\\\",
        "\\midrule",
    ]
    for delta in HORIZONS:
        for cid in CONTRASTS:
            key = f"{cid}@{delta}"
            name = {"native": "Native"}.get(cid, cid) + f"@{delta}\\,s"
            entries = [results[p][key][s] for p in ("R1", "R2") for s in SUBSETS]
            # two lines per contrast (difference, then interval) so the six columns fit the text width
            lines.append(name + " & " + " & ".join(signed(e["difference"]) for e in entries) + " \\\\")
            lines.append(" & " + " & ".join(interval(e["ci95"]) for e in entries) + " \\\\[2pt]")
        counts = [comp[p][str(delta)][s] for p in ("R1", "R2") for s in ("all", "no_day1", "no_day1_3")]
        lines.append(f"Eligible events, {delta}\\,s & " + " & ".join(f"{n:,}".replace(",", "{,}") for n in counts) + " \\\\")
        if delta == 30:
            lines.append("\\midrule")
    lines += ["\\bottomrule", "\\end{tabular}", "\\end{table*}", ""]
    Path(path).write_text("\n".join(lines))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ("r1-report", "r1-per-event", "r1-arm-spec", "r1-manifest-30", "r1-manifest-60", "r1-events",
                 "r2-scores", "r2-report", "out-json", "out-tex"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--repetitions", type=int, default=REPS)
    p.add_argument("--seed", type=int, default=SEED)
    args = p.parse_args()

    import polars as pl
    events = pl.read_parquet(args.r1_events, columns=["event_id", "reason", "labelled"])
    require(set(events["reason"].unique().to_list()) <= {"labelled", "top"}, "Unexpected selection reasons")
    reason = {e: ("radar_match" if r == "labelled" else "volume") for e, r in
              zip(events["event_id"].to_list(), events["reason"].to_list())}

    out = {"kind": "month_boundary_sensitivity_revision_analysis", "confirmatory": False,
           "replaces_published_values": False,
           "method": {"statistic": "event_macro_mean_AP_difference_then_training_seed_mean",
                      "interval": "paired_training_seed_and_incident_day_block_percentile_ordinary_95",
                      "functions": ["bgbench.forecast_ranking.paired_bootstrap",
                                    "bgbench.forecast_analysis.incident_day_blocks"],
                      "repetitions": args.repetitions, "rng_seed": args.seed,
                      "day_definition": "day of month of the identifier time, event_id[6:8] (UTC)",
                      "blocks": "UTC day of each incident's first replay onset among the kept eligible events",
                      "subsets": {k: sorted(v) for k, v in SUBSETS.items()},
                      "p_values": "unadjusted, descriptive only"},
           "contrasts": {k: {"left": v[0], "right": v[1]} for k, v in CONTRASTS.items()},
           "source_sha256": sha(__file__)}
    results, comp_counts = {}, {}
    for period, loader in (("R1", load_r1), ("R2", load_r2)):
        arms, rows, published, provenance = loader(args)
        results[period] = evaluate(period, arms, rows, published, args.repetitions, args.seed)
        eligible = {d: [e["eligible"] for e in arms["sage_on"][d][0]] for d in HORIZONS}
        if period == "R1":
            missing = [r["event_id"] for d in HORIZONS for r in rows[d] if r["event_id"] not in reason]
            require(not missing, f"R1 events without a selection reason: {missing[:5]}")
        out[period] = {"provenance": provenance,
                       "composition": composition(rows, eligible, reason if period == "R1" else None),
                       "contrasts": results[period]}
        if period == "R2":
            out[period]["composition_note"] = (
                "Selection reason (Radar match vs volume) is not carried by the released R2 per-event scores; it is "
                "held only in the custodian event table and was not read for this analysis.")
        comp_counts[period] = {str(d): {s: results[period][f"C2@{d}"][s]["eligible_events"] for s in SUBSETS}
                               for d in HORIZONS}
        del arms
    Path(args.out_json).write_text(json.dumps(out, indent=1, sort_keys=False) + "\n")
    write_tex(args.out_tex, results, comp_counts)
    print("wrote", args.out_json, args.out_tex)


if __name__ == "__main__":
    main()
