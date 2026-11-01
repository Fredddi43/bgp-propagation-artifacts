#!/usr/bin/env python3
"""Actor-dependence sensitivity of the C2 and native forecast contrasts (revision analysis, review round 3, A1).

The published intervals resample whole incident-day blocks. The same leaker AS can leak again on later days, and the
history arms exploit exactly that recurrence, so day blocks may understate the dependence between events. This script
keeps the published statistic and re-draws only its interval, with the leaker AS (the actor) as the resampling unit.

Contrasts (paired AP difference, eligible events, event-macro mean then training-seed mean):
* ``C2``     SAGE with history minus online history, on the shared candidate set;
* ``native`` SAGE with history minus online history on its native candidate set.
Periods R1 (Sep--Dec 2025) and R2 (1 Sep--16 Oct 2026), horizons 30 s and 60 s.

Intervals (ordinary percentile 95 %, 10,000 repetitions, numpy default_rng(1701), training seeds resampled first,
exactly as in the released evaluator; a single-run baseline is broadcast):
* ``day_blocks``   the published interval: whole incident-day blocks (bgbench.forecast_analysis.incident_day_blocks),
                   recomputed here and required to reproduce the released value;
* ``leaker_blocks`` whole leaker ASes as blocks, through the released bgbench.forecast_ranking.paired_bootstrap,
                   called unchanged with the leaker as the block label. No incident spans two leakers, so incidents
                   stay intact;
* ``leaker_x_day`` a two-way (pigeonhole, Owen 2007) bootstrap: leakers and incident days are resampled independently
                   and each event is weighted by the product of its leaker's and its day's multiplicities. It captures
                   both dependence sources at once and is known to be mildly conservative.

The leaker AS is the ``a`` of the leak event; the event identifier is built as ``<t0 %Y%m%dT%H%M%S>_leak_<a>``
(bgbench.leak_events.build_events). For R1 the parsed leaker is checked against the ``a`` column of the corrected
release's 2025 leak event table (only the columns event_id and a are read). R2 uses the identifier alone.

No model is retrained, no prediction is regenerated, no label is read and no published number is changed. Point
estimates are the published ones; only the interval changes. p-values are unadjusted and descriptive.

Usage (repo root):
    .venv/bin/python -B scripts/paper_actor_bootstrap.py \
        --r1-report .agents/operations/r1-v11-posteval-20261024/evidence/released/report.json \
        --r1-per-event <local copy of results/per_event> \
        --r1-arm-spec .agents/operations/r1-arm-spec-20261020/arm-spec.json \
        --r1-manifest-30 .agents/operations/r1-v11-posteval-20261024/evidence/released/retrospective-2025-v6-d30.json \
        --r1-manifest-60 .agents/operations/r1-v11-posteval-20261024/evidence/released/retrospective-2025-v6-d60.json \
        --r1-events data/corrected-release-20261016/eventset/2025_leak/events.parquet \
        --r2-scores <local copy of primary-scores.json> \
        --r2-report docs/paper/r2-report-20261030/primary.json \
        --out-json paper/generated/actor_bootstrap.json --out-tex paper/generated/actor_bootstrap.tex
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from bgbench.forecast_analysis import incident_day_blocks  # noqa: E402
from bgbench.forecast_ranking import paired_bootstrap, ranking_contrast  # noqa: E402
import paper_month_boundary as mb  # noqa: E402  (released loaders, hash checks and formatting)

REPS = 10_000
SEED = 1701
HORIZONS = (30, 60)
CONTRASTS = {"C2": ("sage_on", "online_history"), "native": ("sage_on", "online_history_native")}
EVENT_ID = re.compile(r"^\d{8}T\d{6}_leak_(\d+)$")
# The values quoted in the paper; the released reports are the reference, these guard against a wrong input set.
QUOTED = {("R1", "C2@30"): (0.0054, (-0.0003, 0.0107)), ("R1", "native@30"): (-0.0237, None),
          ("R2", "C2@30"): (0.0003, (-0.0075, 0.0079)), ("R2", "native@30"): (-0.0298, None)}
require = mb.require


def leaker(event_id):
    m = EVENT_ID.match(event_id)
    require(m is not None, f"Unexpected event_id {event_id}")
    return m.group(1)


def two_way_bootstrap(left, right, leakers, days, *, repetitions, seed):
    """Pigeonhole bootstrap over leakers x incident days, after the evaluator's training-seed draw.

    Same estimand and RNG order as paired_bootstrap: per repetition the training seeds are drawn first, then the
    leakers, then the days. Each event gets weight m_leaker * m_day; the replicate is the weighted event mean of the
    seed-summed differences divided by the number of drawn seeds.
    """
    a, b = np.atleast_2d(left).astype(float), np.atleast_2d(right).astype(float)
    difference = a - b
    require(difference.shape[1] == len(leakers) == len(days), "two-way bootstrap: misaligned inputs")
    lab_l, li = np.unique(np.asarray(leakers), return_inverse=True)
    lab_d, di = np.unique(np.asarray(days), return_inverse=True)
    n_s, n_l, n_d = difference.shape[0], len(lab_l), len(lab_d)
    rng = np.random.default_rng(seed)
    samples = np.empty(repetitions)
    degenerate = 0
    for repetition in range(repetitions):
        seeds = rng.integers(n_s, size=n_s)
        ml = np.bincount(rng.integers(n_l, size=n_l), minlength=n_l)
        md = np.bincount(rng.integers(n_d, size=n_d), minlength=n_d)
        w = (ml[li] * md[di]).astype(float)
        total = w.sum()
        if total == 0:
            degenerate += 1
            samples[repetition] = np.nan
            continue
        seed_sum = np.bincount(seeds, minlength=n_s) @ difference
        samples[repetition] = float(seed_sum @ w) / (n_s * total)
    valid = samples[np.isfinite(samples)]
    low = (np.sum(valid <= 0) + 1) / (len(valid) + 1)
    high = (np.sum(valid >= 0) + 1) / (len(valid) + 1)
    return {"difference": float(difference.mean()), "ci95": np.quantile(valid, [.025, .975]).tolist(),
            "p_value": float(min(1.0, 2 * min(low, high))), "events": int(difference.shape[1]), "leakers": n_l,
            "days": n_d, "training_seeds": n_s, "repetitions": repetitions, "degenerate_repetitions": degenerate,
            "rng_seed": seed}


def actors(leakers):
    c = Counter(leakers)
    top, top_n = c.most_common(1)[0]
    repeat = [n for n in c.values() if n > 1]
    return {"eligible_events": len(leakers), "distinct_leakers": len(c), "largest_leaker_asn": int(top),
            "largest_leaker_events": top_n, "largest_leaker_share": top_n / len(leakers),
            "leakers_with_multiple_events": len(repeat), "events_from_repeat_leakers": int(sum(repeat)),
            "events_from_repeat_leakers_share": sum(repeat) / len(leakers),
            "top5": [{"asn": int(k), "events": v} for k, v in c.most_common(5)]}


def half(ci):
    return (ci[1] - ci[0]) / 2


def evaluate(period, arms, rows, published, repetitions, seed):
    out = {}
    for delta in HORIZONS:
        for cid, (left_arm, right_arm) in CONTRASTS.items():
            key = f"{cid}@{delta}"
            a_seeds, b_seeds = arms[left_arm][delta], arms[right_arm][delta]
            left = np.array([[e["average_precision"] for e in s] for s in a_seeds], dtype=float)
            right = np.array([[e["average_precision"] for e in s] for s in b_seeds], dtype=float)
            masks = [np.array([e["eligible"] for e in s]) for s in list(a_seeds) + list(b_seeds)]
            require(all((m == masks[0]).all() for m in masks), f"{period} {key}: arms disagree on the eligible cohort")
            keep = masks[0]
            kept = [r for r, k in zip(rows[delta], keep) if k]
            lk = [leaker(r["event_id"]) for r in kept]
            days = incident_day_blocks(kept)
            inc = defaultdict(set)
            for r, x in zip(kept, lk):
                inc[r["incident_id"]].add(x)
            require(all(len(v) == 1 for v in inc.values()), f"{period} {key}: an incident spans two leakers")

            day = paired_bootstrap(left[:, keep], right[:, keep], days, repetitions=repetitions, seed=seed)
            ref = ranking_contrast(a_seeds, b_seeds, rows[delta], metric="average_precision",
                                   repetitions=repetitions, seed=seed)
            require(abs(ref["difference"] - day["difference"]) < 1e-12
                    and np.allclose(ref["ci95"], day["ci95"], atol=1e-12, rtol=0),
                    f"{period} {key}: day-block path differs from ranking_contrast")
            pub = published[key]
            ok = (round(day["difference"], 4) == round(pub["difference"], 4)
                  and [round(x, 4) for x in day["ci95"]] == [round(x, 4) for x in pub["ci95"]]
                  and ref["eligible_events"] == pub["eligible_events"] and day["blocks"] == pub["blocks"])
            require(ok, f"{period} {key} does not reproduce the published value: got {day['difference']:.6f} "
                        f"{day['ci95']} ({ref['eligible_events']} events, {day['blocks']} blocks), published "
                        f"{pub['difference']:.6f} {pub['ci95']} ({pub['eligible_events']}, {pub['blocks']})")
            quoted = QUOTED.get((period, key))
            if quoted:
                require(round(day["difference"], 4) == quoted[0], f"{period} {key}: differs from the quoted value")
                if quoted[1]:
                    require(tuple(round(x, 4) for x in day["ci95"]) == quoted[1],
                            f"{period} {key}: interval differs from the quoted value")

            act = paired_bootstrap(left[:, keep], right[:, keep], lk, repetitions=repetitions, seed=seed)
            two = two_way_bootstrap(left[:, keep], right[:, keep], lk, days, repetitions=repetitions, seed=seed)
            require(abs(act["difference"] - day["difference"]) < 1e-15 and abs(two["difference"] - day["difference"]) < 1e-15,
                    f"{period} {key}: point estimate changed")
            fields = ("difference", "ci95", "p_value", "blocks", "training_seeds")
            entry = {
                "left": left_arm, "right": right_arm, "horizon_seconds": delta,
                "published": {k: pub[k] for k in ("difference", "ci95", "eligible_events", "blocks")},
                "reproduced_exactly": bool(abs(day["difference"] - pub["difference"]) < 1e-12
                                           and np.allclose(day["ci95"], pub["ci95"], atol=1e-12, rtol=0)),
                "day_blocks": {k: day[k] for k in fields},
                "leaker_blocks": {k: act[k] for k in fields},
                "leaker_x_day": {k: two[k] for k in ("difference", "ci95", "p_value", "leakers", "days",
                                                       "training_seeds", "degenerate_repetitions")},
                "half_width": {"day_blocks": half(day["ci95"]), "leaker_blocks": half(act["ci95"]),
                               "leaker_x_day": half(two["ci95"])},
                "actors": actors(lk),
            }
            entry["half_width_ratio_to_day"] = {k: entry["half_width"][k] / entry["half_width"]["day_blocks"]
                                                for k in ("leaker_blocks", "leaker_x_day")}
            out[key] = entry
            print(f"{period} {key}: {day['difference']:+.4f}  day [{day['ci95'][0]:+.4f}, {day['ci95'][1]:+.4f}] "
                  f"({day['blocks']})  leaker [{act['ci95'][0]:+.4f}, {act['ci95'][1]:+.4f}] ({act['blocks']})  "
                  f"leaker x day [{two['ci95'][0]:+.4f}, {two['ci95'][1]:+.4f}]  "
                  f"largest {entry['actors']['largest_leaker_share']:.3%}", flush=True)
    return out


def check_r1_leakers(path, rows):
    import polars as pl
    table = pl.read_parquet(path, columns=["event_id", "a"])
    a = dict(zip(table["event_id"].to_list(), table["a"].to_list()))
    ids = {r["event_id"] for d in HORIZONS for r in rows[d]}
    missing = sorted(ids - set(a))
    require(not missing, f"R1 events missing from the event table: {missing[:5]}")
    bad = sorted(e for e in ids if int(leaker(e)) != int(a[e]))
    require(not bad, f"R1 identifier leaker differs from the event table: {bad[:5]}")
    return {"events_checked": len(ids), "identifier_matches_event_table_a": True, "event_table_sha256": mb.sha(path)}


def fmt_ci(ci):
    return mb.interval(ci)


def write_tex(path, results):
    lines = [
        "% Generated by scripts/paper_actor_bootstrap.py; do not edit by hand.",
        "% Paired AP difference (eligible events, mean over five training seeds); ordinary 95% percentile intervals,",
        "% training seeds resampled first, 10,000 repetitions, seed 1701. Day: published incident-day blocks.",
        "% Leaker: whole leaker ASes as blocks. Leaker x day: two-way (pigeonhole) resampling of leakers and days.",
        "% Leakers: distinct leaker ASes among the eligible events (largest leaker's share of those events).",
        "\\begin{tabular}{@{}llrllll@{}}",
        "\\toprule",
        "Period & Contrast & Diff. & Day blocks (published) & Leaker blocks & Leaker $\\times$ day & Leakers (largest) \\\\",
        "\\midrule",
    ]
    for period in ("R1", "R2"):
        first = True
        for delta in HORIZONS:
            for cid in CONTRASTS:
                e = results[period][f"{cid}@{delta}"]
                act = e["actors"]
                name = {"native": "Native"}.get(cid, cid) + f"@{delta}\\,s"
                lead = period if first else ""
                first = False
                count = f"{act['distinct_leakers']:,}".replace(",", "{,}")
                share = f"{count} ({100 * act['largest_leaker_share']:.1f}\\,\\%)"
                lines.append(f"{lead} & {name} & {mb.signed(e['day_blocks']['difference'])} & "
                             f"{fmt_ci(e['day_blocks']['ci95'])} & {fmt_ci(e['leaker_blocks']['ci95'])} & "
                             f"{fmt_ci(e['leaker_x_day']['ci95'])} & {share} \\\\")
        if period == "R1":
            lines.append("\\midrule")
    lines += ["\\bottomrule", "\\end{tabular}", ""]
    Path(path).write_text("\n".join(lines))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ("r1-report", "r1-per-event", "r1-arm-spec", "r1-manifest-30", "r1-manifest-60", "r1-events",
                 "r2-scores", "r2-report", "out-json", "out-tex"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--repetitions", type=int, default=REPS)
    p.add_argument("--seed", type=int, default=SEED)
    args = p.parse_args()

    out = {"kind": "actor_block_bootstrap_revision_analysis", "confirmatory": False,
           "replaces_published_values": False,
           "method": {"statistic": "event_macro_mean_AP_difference_then_training_seed_mean (unchanged)",
                      "intervals": {
                          "day_blocks": "published: training seeds, then incident-day blocks (paired_bootstrap)",
                          "leaker_blocks": "training seeds, then whole leaker ASes (paired_bootstrap, leaker as block)",
                          "leaker_x_day": "training seeds, then leakers and incident days drawn independently; event "
                                          "weight = leaker multiplicity x day multiplicity (pigeonhole bootstrap)"},
                      "repetitions": args.repetitions, "rng_seed": args.seed, "population": "eligible events",
                      "leaker": "a of the leak event, parsed from event_id '<t0>_leak_<a>' "
                                "(bgbench.leak_events.build_events); R1 checked against the 2025 event table",
                      "incidents_nested_in_leakers": True, "p_values": "unadjusted, descriptive only"},
           "contrasts": {k: {"left": v[0], "right": v[1]} for k, v in CONTRASTS.items()},
           "source_sha256": mb.sha(__file__)}
    results = {}
    for period, loader in (("R1", mb.load_r1), ("R2", mb.load_r2)):
        arms, rows, published, provenance = loader(args)
        if period == "R1":
            provenance["leaker_check"] = check_r1_leakers(args.r1_events, rows)
        else:
            provenance["leaker_check"] = {"events_checked": len({r["event_id"] for d in HORIZONS for r in rows[d]}),
                                          "source": "event_id only (the R2 event table was not read)"}
        results[period] = evaluate(period, arms, rows, published, args.repetitions, args.seed)
        out[period] = {"provenance": provenance, "contrasts": results[period]}
        del arms
    Path(args.out_json).write_text(json.dumps(out, indent=1) + "\n")
    write_tex(args.out_tex, results)
    print("wrote", args.out_json, args.out_tex)


if __name__ == "__main__":
    main()
