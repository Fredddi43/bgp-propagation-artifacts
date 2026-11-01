#!/usr/bin/env python3
"""Leaker recurrence: first-seen against repeat leakers, and a same-leaker memory baseline (revision analysis, review
round 4, Opus A2 and Codex "Truly required analyses" 2).

Part 1, split. Each test event is classed by its leaker AS (``a``, parsed from event_id ``<t0>_leak_<a>``):

* ``repeat``     the leaker is the ``a`` of at least one completed earlier event of the history library, that is an
                 event whose two-hour target window ended at or before this event's onset (its onset + 7200 s <=
                 this event's onset);
* ``first_seen`` otherwise.

The history library is the one the online history arm reads (sections/app-protocol.tex, "History timing"; scripts/
forecast_h2_recurrence.py): every successful (``error`` null) leak event with an onset (``t0_obs``) of the released
event tables. R1 (Sep--Dec 2025): 2023, 2024 and 2025, including the earlier R1 test events. R2 (1 Sep--16 Oct 2026):
2023 to 2026 (the released 2026 table ends on 31 August 2026) plus the earlier R2 test events from the R2 per-event
rows (onset, event_id). Gap: R2 identified 1,311 events, of which the 1,289 scored ones are local; the other 22 (onset
outside the window) are held only in the custodian event table, so a leaker whose only earlier event is one of them is
classed first-seen here. A sensitivity uses development history only (library events with onset before the test
period, 1 Sep 2025 or 1 Sep 2026).

For C2 (SAGE with history minus online history, shared candidates) and native (SAGE with history minus online history
on its native candidates), R1 and R2, 30 s and 60 s, each stratum gets the paired AP difference (event-macro mean over
its eligible events, then training-seed mean) with ordinary 95 % intervals from training seeds then incident-day blocks
rebuilt from the stratum's events (bgbench.forecast_ranking.paired_bootstrap, as in paper_month_boundary.py) and from the
two-way leaker x day bootstrap (paper_actor_bootstrap.two_way_bootstrap). The interaction, repeat minus first-seen, gets
a joint bootstrap: the same draws of training seeds and day blocks (or leakers and days) for both strata. The full
eligible cohort must reproduce the published contrasts first (difference, interval, events, blocks).

Part 2, same-leaker memory baseline (R1 only; R2 records name no target ASes). For each R1 test event at horizon
Delta, with issue time t0_obs + Delta:

* candidates: the native candidate set of online history, every AS with positive participation in the library events
  available at issue time (onset + 7200 s <= issue time), plus the seeds; seeds are removed before ranking;
* ``online_history_native`` (reconstruction): score = participation count in all available library events;
* ``same_leaker``: score = participation count in the available library events of the same leaker only; candidates
  without such participation form one tie group at the bottom;
* ``same_leaker_then_history``: same-leaker count first, global participation count second (lexicographic).

Scoring is the released evaluator (bgbench.forecast_ranking.event_ranking_metrics): AP over new members with the
candidate-complete denominator (new members = 2-h target minus seeds), the exact expectation over random orders within
ties, and P@10. Inputs are the released 2025 measurement sets: seeds ``set_d30s`` / ``set_d1m``, target
``set_final_2h``, library targets ``set_final_2h`` (data/corrected-release-20261016/eventset). These are released
measurement data, not protected labels.

Input gap. ``set_d30s`` / ``set_d1m`` count an AS by its raw first-seen time; the forecast input counts it by its
availability time (whole-second collectors +1 s; bgbench.forecast_protocol.available_at_expr). On some events the
released set therefore holds k >= 1 ASes that were not yet input seeds; k is known per event (published new members
minus the released-set new members) but the ASes are not, and k reaches 55, so they are not recovered. Two populations
follow:

* ``released_inputs``: all three rankings on the released seed sets, over the published eligible events that keep at
  least one new member under them. The paired difference same-leaker minus online history uses identical inputs; the
  levels differ from the published ones by the input gap, which is reported (``input_gap``).
* ``exact_inputs``: the events with k = 0. There the reconstruction must equal the published per-event record of online
  history native (AP and P@5/10/20/50 to 1e-12, ranked candidates, new members), otherwise the script stops, so these
  events carry the like-for-like comparison with SAGE with history (published per-event AP and P@10, five seeds). They
  are a selected subset (k depends on member arrivals just before the issue time), so their levels differ from the
  cohort's; ``input_gap`` gives the published online history mean AP on both.

On every event the script also checks 0 <= published ranked - reconstructed ranked <= k.

Comparisons: same-leaker (and the lexicographic variant) minus online history native, and (exact inputs) minus SAGE with
history, overall and by stratum, AP and P@10, with day-block and leaker x day intervals.

No model is retrained, no prediction regenerated, no protected label read and no published number changed.

Usage (repo root):
    .venv/bin/python -B scripts/paper_leaker_split.py \
        --r1-report .agents/operations/r1-v11-posteval-20261024/evidence/released/report.json \
        --r1-per-event <local copy of results/per_event> \
        --r1-arm-spec .agents/operations/r1-arm-spec-20261020/arm-spec.json \
        --r1-manifest-30 .agents/operations/r1-v11-posteval-20261024/evidence/released/retrospective-2025-v6-d30.json \
        --r1-manifest-60 .agents/operations/r1-v11-posteval-20261024/evidence/released/retrospective-2025-v6-d60.json \
        --r1-events data/corrected-release-20261016/eventset/2025_leak/events.parquet \
        --eventset-root data/corrected-release-20261016/eventset \
        --r2-scores <local copy of primary-scores.json> \
        --r2-report docs/paper/r2-report-20261030/primary.json \
        --out-json paper/generated/leaker_split.json --out-tex paper/generated/leaker_split.tex
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from bgbench.forecast_analysis import incident_day_blocks  # noqa: E402
from bgbench.forecast_ranking import event_ranking_metrics, paired_bootstrap  # noqa: E402
import paper_actor_bootstrap as ab  # noqa: E402  (leaker parse, two-way bootstrap, R1 leaker check)
import paper_month_boundary as mb  # noqa: E402  (released loaders and hash checks, formatting)

REPS = 10_000
SEED = 1701
HORIZONS = (30, 60)
TARGET_S = 7200
CONTRASTS = ab.CONTRASTS
R1_YEARS = (2023, 2024, 2025)
R2_YEARS = (2023, 2024, 2025, 2026)
TEST_START = {"R1": datetime(2025, 9, 1, tzinfo=timezone.utc), "R2": datetime(2026, 9, 1, tzinfo=timezone.utc)}
SEED_SET = {30: "set_d30s", 60: "set_d1m"}
BUDGETS = (5, 10, 20, 50)
STRATA = ("first_seen", "repeat")
KEEP = ("precision_at", "ranked", "new_members", "new_members_ranked", "true_size")
require = mb.require
FIELDS = ("difference", "ci95", "p_value")

# The released loaders keep only event_id, eligible and AP; this analysis also needs P@k and the candidate counts of
# the same records. Wrap the loader's record filter (the loaders and their hash checks are otherwise unchanged).
_slim = mb.slim
mb.slim = lambda rows: [dict(s, **{k: r[k] for k in KEEP if k in r}) for s, r in zip(_slim(rows), rows)]


def utc(value):
    t = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    require(t.tzinfo is not None, f"Timestamp without timezone: {value}")
    return t.astimezone(timezone.utc)


# ----------------------------------------------------------------------------- history library

def read_library(root, years, with_sets):
    """Successful leak events of the released tables: (completion, event_id, leaker, onset[, target])."""
    import polars as pl
    out, hashes = [], {}
    for year in years:
        path = Path(root) / f"{year}_leak" / "events.parquet"
        hashes[str(year)] = mb.sha(path)
        cols = ["event_id", "error", "t0_obs", "a"] + (["set_final_2h"] if with_sets else [])
        table = pl.read_parquet(path, columns=cols)
        bad = [e for e, a in zip(table["event_id"].to_list(), table["a"].to_list()) if int(ab.leaker(e)) != int(a)]
        require(not bad, f"{year}: event_id leaker differs from column a: {bad[:3]}")
        ok = table.filter(pl.col("error").is_null() & pl.col("t0_obs").is_not_null())
        for r in ok.iter_rows(named=True):
            onset = utc(r["t0_obs"])
            out.append((onset + timedelta(seconds=TARGET_S), r["event_id"], int(r["a"]), onset,
                        r["set_final_2h"] if with_sets else None))
        hashes[f"{year}_rows"] = table.height
        hashes[f"{year}_successful_rows"] = ok.height
    out.sort(key=lambda x: (x[0], x[1]))
    require(len({x[1] for x in out}) == len(out), "Duplicate event IDs in the history library")
    return out, hashes


def prior_counts(events, library, test_start):
    """For each (event_id, leaker, onset): completed earlier library events of the same leaker, all and development."""
    by_leaker = defaultdict(list)
    for completion, eid, a, onset, _ in library:
        by_leaker[a].append((completion, eid, onset))
    out = {}
    for eid, a, onset in events:
        prior = [x for x in by_leaker.get(int(a), []) if x[0] <= onset and x[1] != eid]
        out[eid] = {"history": len(prior), "development": sum(x[2] < test_start for x in prior)}
    return out


def familiarity(counts):
    bins = Counter()
    for n in counts:
        bins["0" if n == 0 else "1" if n == 1 else "2-4" if n <= 4 else "5-19" if n <= 19 else ">=20"] += 1
    return {k: bins[k] for k in ("0", "1", "2-4", "5-19", ">=20")}


# ----------------------------------------------------------------------------- bootstraps

def strata_joint(diff, stratum, blocks, *, repetitions, seed):
    """Repeat minus first-seen: training seeds then whole blocks, one draw for both strata."""
    groups = defaultdict(list)
    for i, b in enumerate(blocks):
        groups[str(b)].append(i)
    idx = [np.asarray(v) for _, v in sorted(groups.items())]
    sums = {k: np.stack([diff[:, i][:, stratum[i] == k].sum(axis=1) for i in idx], axis=1) for k in (0, 1)}
    cnt = {k: np.array([(stratum[i] == k).sum() for i in idx]) for k in (0, 1)}
    rng = np.random.default_rng(seed)
    samples = np.empty(repetitions)
    n_s = diff.shape[0]
    for r in range(repetitions):
        seeds = rng.integers(n_s, size=n_s)
        sel = rng.integers(len(idx), size=len(idx))
        v = [sums[k][np.ix_(seeds, sel)].sum() / (n_s * cnt[k][sel].sum()) if cnt[k][sel].sum() else np.nan
             for k in (0, 1)]
        samples[r] = v[1] - v[0]
    valid = samples[np.isfinite(samples)]
    point = diff[:, stratum == 1].mean() - diff[:, stratum == 0].mean()
    return {"difference": float(point), "ci95": np.quantile(valid, [.025, .975]).tolist(),
            "p_value": two_sided(valid), "blocks": len(idx), "degenerate_repetitions": int(repetitions - len(valid))}


def strata_joint_two_way(diff, stratum, leakers, days, *, repetitions, seed):
    """Repeat minus first-seen under the two-way leaker x day bootstrap (same RNG order as two_way_bootstrap)."""
    _, li = np.unique(np.asarray(leakers), return_inverse=True)
    _, di = np.unique(np.asarray(days), return_inverse=True)
    n_s, n_l, n_d = diff.shape[0], li.max() + 1, di.max() + 1
    rng = np.random.default_rng(seed)
    samples = np.empty(repetitions)
    masks = [stratum == 0, stratum == 1]
    for r in range(repetitions):
        seeds = rng.integers(n_s, size=n_s)
        ml = np.bincount(rng.integers(n_l, size=n_l), minlength=n_l)
        md = np.bincount(rng.integers(n_d, size=n_d), minlength=n_d)
        w = (ml[li] * md[di]).astype(float)
        seed_sum = np.bincount(seeds, minlength=n_s) @ diff
        v = []
        for m in masks:
            tot = w[m].sum()
            v.append(float(seed_sum[m] @ w[m]) / (n_s * tot) if tot else np.nan)
        samples[r] = v[1] - v[0]
    valid = samples[np.isfinite(samples)]
    point = diff[:, stratum == 1].mean() - diff[:, stratum == 0].mean()
    return {"difference": float(point), "ci95": np.quantile(valid, [.025, .975]).tolist(),
            "p_value": two_sided(valid), "degenerate_repetitions": int(repetitions - len(valid))}


def two_sided(samples):
    low = (np.sum(samples <= 0) + 1) / (len(samples) + 1)
    high = (np.sum(samples >= 0) + 1) / (len(samples) + 1)
    return float(min(1.0, 2 * min(low, high)))


def intervals(left, right, rows_kept, leakers, repetitions, seed):
    days = incident_day_blocks(rows_kept)
    day = paired_bootstrap(left, right, days, repetitions=repetitions, seed=seed)
    two = ab.two_way_bootstrap(left, right, leakers, days, repetitions=repetitions, seed=seed)
    return {"difference": day["difference"], "day_blocks": {**{k: day[k] for k in FIELDS}, "blocks": day["blocks"]},
            "leaker_x_day": {**{k: two[k] for k in FIELDS}, "leakers": two["leakers"], "days": two["days"]},
            "events": int(left.shape[1]), "training_seeds": int(max(left.shape[0], right.shape[0]))}


# ----------------------------------------------------------------------------- part 1: split

def split_period(period, arms, rows, published, priors, repetitions, seed):
    out = {}
    for delta in HORIZONS:
        for cid, (left_arm, right_arm) in CONTRASTS.items():
            key = f"{cid}@{delta}"
            a_seeds, b_seeds = arms[left_arm][delta], arms[right_arm][delta]
            left = np.array([[e["average_precision"] for e in s] for s in a_seeds], dtype=float)
            right = np.array([[e["average_precision"] for e in s] for s in b_seeds], dtype=float)
            masks = [np.array([e["eligible"] for e in s]) for s in list(a_seeds) + list(b_seeds)]
            require(all((m == masks[0]).all() for m in masks), f"{period} {key}: arms disagree on the eligible cohort")
            elig = masks[0]
            kept = [r for r, k in zip(rows[delta], elig) if k]
            # reproduction of the published contrast on the full eligible cohort (always the published RNG settings)
            full = paired_bootstrap(left[:, elig], right[:, elig], incident_day_blocks(kept), repetitions=REPS,
                                    seed=SEED)
            pub = published[key]
            require(round(full["difference"], 4) == round(pub["difference"], 4)
                    and [round(x, 4) for x in full["ci95"]] == [round(x, 4) for x in pub["ci95"]]
                    and int(elig.sum()) == pub["eligible_events"] and full["blocks"] == pub["blocks"],
                    f"{period} {key}: does not reproduce the published value")
            entry = {"left": left_arm, "right": right_arm, "horizon_seconds": delta,
                     "published": {k: pub[k] for k in ("difference", "ci95", "eligible_events", "blocks")},
                     "reproduced_exactly": bool(abs(full["difference"] - pub["difference"]) < 1e-12
                                                and np.allclose(full["ci95"], pub["ci95"], atol=1e-12, rtol=0))}
            lk = np.array([ab.leaker(r["event_id"]) for r in kept])
            for definition in ("history", "development"):
                stratum = np.array([int(priors[r["event_id"]][definition] > 0) for r in kept])
                d_all = (left[:, elig] - right[:, elig])
                res = {"counts": {"first_seen": int((stratum == 0).sum()), "repeat": int((stratum == 1).sum()),
                                  "repeat_share": float(stratum.mean())}}
                for k, name in enumerate(STRATA):
                    m = stratum == k
                    rk = [r for r, x in zip(kept, m) if x]
                    iv = intervals(left[:, elig][:, m], right[:, elig][:, m], rk, list(lk[m]), repetitions, seed)
                    iv.update(distinct_leakers=int(len(set(lk[m]))),
                              left_mean=float(left[:, elig][:, m].mean(axis=1).mean()),
                              right_mean=float(right[:, elig][:, m].mean(axis=1).mean()))
                    res[name] = iv
                res["repeat_minus_first_seen"] = {
                    "day_blocks": strata_joint(d_all, stratum, incident_day_blocks(kept), repetitions=repetitions,
                                               seed=seed),
                    "leaker_x_day": strata_joint_two_way(d_all, stratum, list(lk), incident_day_blocks(kept),
                                                         repetitions=repetitions, seed=seed)}
                entry[definition] = res
                if definition == "history":
                    f, r = res["first_seen"], res["repeat"]
                    x = res["repeat_minus_first_seen"]["day_blocks"]
                    print(f"{period} {key}: first-seen n={f['events']} {f['difference']:+.4f} "
                          f"[{f['day_blocks']['ci95'][0]:+.4f}, {f['day_blocks']['ci95'][1]:+.4f}]  repeat "
                          f"n={r['events']} {r['difference']:+.4f} [{r['day_blocks']['ci95'][0]:+.4f}, "
                          f"{r['day_blocks']['ci95'][1]:+.4f}]  rep-first {x['difference']:+.4f} "
                          f"[{x['ci95'][0]:+.4f}, {x['ci95'][1]:+.4f}]", flush=True)
            out[key] = entry
    return out


# ----------------------------------------------------------------------------- part 2: same-leaker baseline

RANKINGS = ("online_history_native", "same_leaker", "same_leaker_then_history")
GAP_BINS = ("0", "1", "2", "3-4", "5-9", ">=10")


def score(cands, scores, target, seeds):
    m = event_ranking_metrics(cands, scores, target, seeds)
    return {"eligible": m["eligible"], "ranked": m["ranked"], "new_members": m["new_members"],
            "ap": m["average_precision"], "precision_at": m["precision_at"]}


def same_leaker_r1(arms, rows, events, library, delta):
    """Per-event metrics of the three history rankings on the released seed sets, with the input gap k per event."""
    native = {r["event_id"]: r for r in arms["online_history_native"][delta][0]}
    sage0 = {r["event_id"]: r for r in arms["sage_on"][delta][0]}
    order = sorted(rows[delta], key=lambda r: (events[r["event_id"]]["onset"], r["event_id"]))
    cnt, by_leaker, i, per = Counter(), defaultdict(Counter), 0, {}
    for row in order:
        eid = row["event_id"]
        ev = events[eid]
        require(utc(row["onset"]) == ev["onset"], f"{eid}: manifest onset differs from t0_obs")
        issue = ev["onset"] + timedelta(seconds=delta)
        while i < len(library) and library[i][0] <= issue:
            cnt.update(library[i][4])
            by_leaker[library[i][2]].update(library[i][4])
            i += 1
        seeds, target = set(ev[SEED_SET[delta]]), set(ev["set_final_2h"])
        require(seeds <= target, f"{eid}: released seeds outside the target")
        require(len(target) == sage0[eid]["true_size"], f"{eid}: target size differs from the SAGE record")
        pub = native[eid]
        gap = pub["new_members"] - len(target - seeds)
        require(gap >= 0, f"{eid}: released seed set smaller than the input seed set")
        same = by_leaker.get(ev["a"], Counter())
        cands = list(set(cnt) | seeds)
        glob = [cnt.get(a, 0) for a in cands]
        own = [same.get(a, 0) for a in cands]
        top = max(glob, default=0) + 1
        res = {"online_history_native": score(cands, glob, target, seeds),
               "same_leaker": score(cands, own, target, seeds),
               "same_leaker_then_history": score(cands, [o * top + g for o, g in zip(own, glob)], target, seeds)}
        nat = res["online_history_native"]
        require(0 <= pub["ranked"] - nat["ranked"] <= gap, f"{eid}: native candidate count inconsistent with the gap")
        if gap == 0:
            require(nat["ranked"] == pub["ranked"] and nat["new_members"] == pub["new_members"],
                    f"{eid}: reconstructed native candidates or new members differ from the published record")
            if pub["eligible"]:
                require(abs(nat["ap"] - pub["average_precision"]) < 1e-12
                        and all(abs(nat["precision_at"][str(b)] - pub["precision_at"][str(b)]) < 1e-12
                                for b in BUDGETS),
                        f"{eid}: reconstructed online history native differs from the published record")
        entry = {"input_gap": gap, "published_eligible": bool(pub["eligible"]),
                 "eligible_released_inputs": bool(nat["eligible"]), "same_leaker_history_at_issue": bool(same)}
        if nat["eligible"]:
            entry.update({arm: {"ap": res[arm]["ap"], "p10": res[arm]["precision_at"]["10"]} for arm in RANKINGS})
        per[eid] = entry
    return per


def gap_bin(k):
    return "0" if k == 0 else "1" if k == 1 else "2" if k == 2 else "3-4" if k <= 4 else "5-9" if k <= 9 else ">=10"


def input_gap_summary(per, arms, delta):
    pub = {r["event_id"]: r for r in arms["online_history_native"][delta][0]}
    elig = [e for e, v in per.items() if v["published_eligible"]]
    both = [e for e in elig if per[e]["eligible_released_inputs"]]
    exact = [e for e in elig if per[e]["input_gap"] == 0]
    bins = Counter(gap_bin(v["input_gap"]) for v in per.values())

    def mean(ids, f):
        return float(np.mean([f(e) for e in ids]))
    return {"events": len(per), "events_by_gap": {k: bins[k] for k in GAP_BINS},
            "max_gap": int(max(v["input_gap"] for v in per.values())),
            "published_eligible_events": len(elig), "eligible_under_released_inputs": len(both),
            "published_eligible_without_new_members_under_released_inputs": len(elig) - len(both),
            "exact_input_eligible_events": len(exact),
            "exact_input_events_reproduced_1e-12": len(exact),
            "online_history_native_mean_ap": {
                "published_all_eligible": mean(elig, lambda e: pub[e]["average_precision"]),
                "published_released_cohort": mean(both, lambda e: pub[e]["average_precision"]),
                "reconstructed_released_cohort": mean(both, lambda e: per[e]["online_history_native"]["ap"]),
                "published_exact_inputs": mean(exact, lambda e: pub[e]["average_precision"]),
                "reconstructed_exact_inputs": mean(exact, lambda e: per[e]["online_history_native"]["ap"])}}


def baseline_comparisons(per, arms, rows, priors, repetitions, seed, delta, population):
    """Levels and paired contrasts on ``released_inputs`` (no SAGE contrast) or ``exact_inputs`` (with SAGE)."""
    sage = arms["sage_on"][delta]
    elig = np.array([e["eligible"] for e in sage[0]])
    require(all(bool(e) == per[r["event_id"]]["published_eligible"] for e, r in zip(elig, rows[delta])),
            "SAGE and online history native disagree on eligibility")
    pick = {"released_inputs": lambda v: v["eligible_released_inputs"],
            "exact_inputs": lambda v: v["input_gap"] == 0}[population]
    keep = elig & np.array([pick(per[r["event_id"]]) for r in rows[delta]])
    kept = [r for r, k in zip(rows[delta], keep) if k]
    lk = [ab.leaker(r["event_id"]) for r in kept]
    stratum = np.array([int(priors[r["event_id"]]["history"] > 0) for r in kept])
    vec = {arm: {m: np.atleast_2d([per[r["event_id"]][arm][m] for r in kept]) for m in ("ap", "p10")}
           for arm in RANKINGS}
    pairs = {"same_leaker_minus_online_history_native": ("same_leaker", "online_history_native"),
             "same_leaker_then_history_minus_online_history_native": ("same_leaker_then_history",
                                                                      "online_history_native")}
    if population == "exact_inputs":
        vec["sage_on"] = {"ap": np.array([[e["average_precision"] for e, k in zip(s, keep) if k] for s in sage]),
                          "p10": np.array([[e["precision_at"]["10"] for e, k in zip(s, keep) if k] for s in sage])}
        pairs.update({"same_leaker_minus_sage_on": ("same_leaker", "sage_on"),
                      "same_leaker_then_history_minus_sage_on": ("same_leaker_then_history", "sage_on"),
                      "online_history_native_minus_sage_on": ("online_history_native", "sage_on")})
    classes = (("all", np.ones(len(kept), bool)), ("first_seen", stratum == 0), ("repeat", stratum == 1))
    out = {"population": population, "events": int(keep.sum()), "first_seen": int((stratum == 0).sum()),
           "repeat": int((stratum == 1).sum()), "levels": {}, "contrasts": {}}
    for arm, v in vec.items():
        out["levels"][arm] = {name: {met: float(v[met][:, m].mean(axis=1).mean()) for met in ("ap", "p10")}
                              for name, m in classes}
    for key, (a, b) in pairs.items():
        out["contrasts"][key] = {}
        for met in ("ap", "p10"):
            res = {}
            for name, m in classes:
                rk = [r for r, x in zip(kept, m) if x]
                res[name] = intervals(vec[a][met][:, m], vec[b][met][:, m], rk, [x for x, y in zip(lk, m) if y],
                                      repetitions, seed)
            out["contrasts"][key][met] = res
    return out


# ----------------------------------------------------------------------------- LaTeX

def fmt_n(n):
    return f"{n:,}".replace(",", "{,}")


def write_tex(path, split, base):
    lines = [
        "% Generated by scripts/paper_leaker_split.py; do not edit by hand.",
        "% Panel A: C2 and native AP contrasts by leaker class. Repeat: the leaker AS led at least one completed earlier",
        "% event of the history library (2-h window ended by this event's onset); first seen: otherwise. Paired AP",
        "% difference over the class's eligible events, mean over five training seeds; ordinary 95% intervals from",
        "% training seeds then incident-day blocks (Day) or leakers and days drawn independently (Leaker x day),",
        "% 10,000 repetitions, seed 1701. Repeat - first: difference of the two class contrasts, joint resampling.",
        "% Panel B (R1 only): history rankings on the native candidates of online history. Same leaker: participation",
        "% in completed earlier events of the same leaker only; same leaker, then all: same-leaker count first, all-event",
        "% participation second. n: published eligible events that keep a new member under the released seed sets",
        "% (in parentheses: events whose released seed set equals the input seed set). AP / P@10 and AP - online",
        "% history: all three rankings on the released seed sets. AP - SAGE: SAGE with history (published per-event AP)",
        "% on the exact-input events only, where the reconstruction equals the published online history per event.",
        "% Differences: day-block intervals as in Panel A. Same ranking: without same-leaker history the lexicographic",
        "% ranking equals online history, so the difference is exactly zero.",
        "\\begin{tabular}{@{}lllrlll@{}}",
        "\\toprule",
        "\\multicolumn{7}{@{}l}{\\emph{A. C2 and native contrasts by leaker class}} \\\\",
        "Period & Contrast & Class & $n$ (leakers) & Diff. & Day blocks & Leaker $\\times$ day \\\\",
        "\\midrule",
    ]
    for period in ("R1", "R2"):
        first = True
        for delta in HORIZONS:
            for cid in CONTRASTS:
                e = split[period][f"{cid}@{delta}"]["history"]
                name = {"native": "Native"}.get(cid, cid) + f"@{delta}\\,s"
                for j, cls in enumerate(STRATA):
                    s = e[cls]
                    lead = period if first else ""
                    first = False
                    label = {"first_seen": "First seen", "repeat": "Repeat"}[cls]
                    lines.append(f"{lead} & {name if j == 0 else ''} & {label} & {fmt_n(s['events'])} "
                                 f"({fmt_n(s['distinct_leakers'])}) & {mb.signed(s['difference'])} & "
                                 f"{mb.interval(s['day_blocks']['ci95'])} & {mb.interval(s['leaker_x_day']['ci95'])} \\\\")
                x = e["repeat_minus_first_seen"]
                lines.append(f" & & Repeat $-$ first & & {mb.signed(x['day_blocks']['difference'])} & "
                             f"{mb.interval(x['day_blocks']['ci95'])} & {mb.interval(x['leaker_x_day']['ci95'])} \\\\")
        if period == "R1":
            lines.append("\\midrule")
    lines += [
        "\\midrule",
        "\\multicolumn{7}{@{}l}{\\emph{B. R1, history rankings on the native candidates}} \\\\",
        "$\\Delta$ & Ranking & Class & $n$ (exact) & AP / P@10 & AP $-$ online history & AP $-$ SAGE (exact) \\\\",
        "\\midrule",
    ]
    names = {"online_history_native": "Online history", "same_leaker": "Same leaker",
             "same_leaker_then_history": "Same leaker, then all"}
    keys = {"same_leaker": ("same_leaker_minus_online_history_native", "same_leaker_minus_sage_on"),
            "same_leaker_then_history": ("same_leaker_then_history_minus_online_history_native",
                                         "same_leaker_then_history_minus_sage_on"),
            "online_history_native": (None, "online_history_native_minus_sage_on")}
    for delta in HORIZONS:
        b = base[str(delta)]["released_inputs"]
        x = base[str(delta)]["exact_inputs"]
        first = True
        for arm in ("online_history_native", "same_leaker", "same_leaker_then_history"):
            for cls in ("all", "first_seen", "repeat"):
                lv = b["levels"][arm][cls]
                n = b["events"] if cls == "all" else b[cls]
                n_exact = x["events"] if cls == "all" else x[cls]
                cells = []
                for k, src in zip(keys[arm], (b, x)):
                    if k is None:
                        cells.append("--")
                    else:
                        c = src["contrasts"][k]["ap"][cls]
                        if c["difference"] == 0 and c["day_blocks"]["ci95"] == [0.0, 0.0]:
                            cells.append("0 (same ranking)")
                        else:
                            cells.append(f"{mb.signed(c['difference'])} {mb.interval(c['day_blocks']['ci95'])}")
                label = {"all": "All", "first_seen": "First seen", "repeat": "Repeat"}[cls]
                horizon = f"{delta}\\,s" if first else ""
                ranking = names[arm] if cls == "all" else ""
                lines.append(f"{horizon} & {ranking} & {label} & "
                             f"{fmt_n(n)} ({fmt_n(n_exact)}) & {lv['ap']:.3f} / {lv['p10']:.3f} & {cells[0]} & {cells[1]} \\\\")
                first = False
        if delta == HORIZONS[0]:
            lines.append("\\cmidrule(l){1-7}")
    lines += ["\\bottomrule", "\\end{tabular}", ""]
    Path(path).write_text("\n".join(lines))


# ----------------------------------------------------------------------------- main

def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ("r1-report", "r1-per-event", "r1-arm-spec", "r1-manifest-30", "r1-manifest-60", "r1-events",
                 "eventset-root", "r2-scores", "r2-report", "out-json", "out-tex"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--repetitions", type=int, default=REPS)
    p.add_argument("--seed", type=int, default=SEED)
    args = p.parse_args()
    import polars as pl

    out = {"kind": "leaker_recurrence_revision_analysis", "confirmatory": False, "replaces_published_values": False,
           "definitions": {
               "leaker": "a of the leak event, parsed from event_id '<t0>_leak_<a>'; checked against column a of every "
                         "released table row read",
               "repeat": "the leaker is the a of at least one completed earlier library event: its onset + 7200 s <= "
                         "this event's onset (history definition). Development definition: the same, counting only "
                         "library events with onset before the test period",
               "library": "successful (error null) leak events with t0_obs of the released event tables; R1: 2023-2025; "
                          "R2: 2023-2026 (2026 table ends 2026-08-31) plus the scored R2 events (onset from the R2 rows)",
               "contrast_statistic": "event-macro mean AP difference over the class's eligible events, then the "
                                     "training-seed mean (published estimand restricted to the class)",
               "intervals": "day_blocks: training seeds then incident-day blocks rebuilt from the class's events "
                            "(paired_bootstrap); leaker_x_day: paper_actor_bootstrap.two_way_bootstrap; "
                            "repeat_minus_first_seen: one joint draw for both classes (blocks or leakers and days of "
                            "all eligible events)",
               "repetitions": args.repetitions, "rng_seed": args.seed, "p_values": "unadjusted, descriptive only"},
           "source_sha256": mb.sha(__file__)}

    # ---------------- R1
    arms, rows, published, prov = mb.load_r1(args)
    prov["leaker_check"] = ab.check_r1_leakers(args.r1_events, rows)
    lib1, hashes1 = read_library(args.eventset_root, R1_YEARS, with_sets=True)
    t = pl.read_parquet(args.r1_events, columns=["event_id", "t0_obs", "a", "set_d30s", "set_d1m", "set_final_2h"])
    test_ids = {r["event_id"] for d in HORIZONS for r in rows[d]}
    events = {r["event_id"]: {**r, "onset": utc(r["t0_obs"]), "a": int(r["a"])}
              for r in t.iter_rows(named=True) if r["event_id"] in test_ids}
    require(set(events) == test_ids, "R1 test events missing from the 2025 table")
    pri1 = prior_counts([(e, v["a"], v["onset"]) for e, v in events.items()], lib1, TEST_START["R1"])
    r1 = {"provenance": {**prov, "library_tables": hashes1, "library_events": len(lib1)}}
    r1["familiarity"] = {str(d): {
        "all_events": familiarity([pri1[r["event_id"]]["history"] for r in rows[d]]),
        "eligible_events": familiarity([pri1[r["event_id"]]["history"]
                                        for r, e in zip(rows[d], arms["sage_on"][d][0]) if e["eligible"]]),
        "eligible_events_development": familiarity([pri1[r["event_id"]]["development"]
                                                    for r, e in zip(rows[d], arms["sage_on"][d][0]) if e["eligible"]])}
        for d in HORIZONS}
    r1["split"] = split_period("R1", arms, rows, published, pri1, args.repetitions, args.seed)

    base = {}
    for d in HORIZONS:
        print(f"R1@{d}: same-leaker baseline", flush=True)
        per = same_leaker_r1(arms, rows, events, lib1, d)
        b = {"input_gap": input_gap_summary(per, arms, d),
             "released_inputs": baseline_comparisons(per, arms, rows, pri1, args.repetitions, args.seed, d,
                                                     "released_inputs"),
             "exact_inputs": baseline_comparisons(per, arms, rows, pri1, args.repetitions, args.seed, d,
                                                  "exact_inputs")}
        g = b["input_gap"]
        for pop in ("released_inputs", "exact_inputs"):
            lv, c = b[pop]["levels"], b[pop]["contrasts"]
            print(f"R1@{d} {pop}: n={b[pop]['events']} native {lv['online_history_native']['all']['ap']:.4f}  "
                  f"same {lv['same_leaker']['all']['ap']:.4f}  lex {lv['same_leaker_then_history']['all']['ap']:.4f}  "
                  f"same-native {c['same_leaker_minus_online_history_native']['ap']['all']['difference']:+.4f}"
                  + (f"  same-sage {c['same_leaker_minus_sage_on']['ap']['all']['difference']:+.4f}"
                     if "same_leaker_minus_sage_on" in c else ""), flush=True)
        print(f"R1@{d} input gap: {g['events_by_gap']}  native mean AP {g['online_history_native_mean_ap']}", flush=True)
        base[str(d)] = b
    r1["same_leaker_baseline"] = base
    out["R1"] = r1
    del arms

    # ---------------- R2
    arms, rows, published, prov = mb.load_r2(args)
    lib2, hashes2 = read_library(args.eventset_root, R2_YEARS, with_sets=False)
    r2_rows = {r["event_id"]: r for d in HORIZONS for r in rows[d]}
    require(not set(r2_rows) & {x[1] for x in lib2}, "R2 test events already in the local history tables")
    lib2 += [(utc(r["onset"]) + timedelta(seconds=TARGET_S), e, int(ab.leaker(e)), utc(r["onset"]), None)
             for e, r in r2_rows.items()]
    lib2.sort(key=lambda x: (x[0], x[1]))
    pri2 = prior_counts([(e, ab.leaker(e), utc(r["onset"])) for e, r in r2_rows.items()], lib2, TEST_START["R2"])
    r2 = {"provenance": {**prov, "library_tables": hashes2, "library_events_local": len(lib2),
                         "scored_r2_events_in_library": len(r2_rows)},
          "history_gap": "R2 identified 1,311 events (sections/08-forecast.tex); the 1,289 scored ones are local. The "
                         "other 22 (onset outside the window) and their leakers are held only in the custodian event "
                         "table, so a leaker whose only completed earlier event is one of them is classed first-seen "
                         "here. The released 2026 table covers 1 January to 31 August 2026."}
    r2["familiarity"] = {str(d): {
        "all_events": familiarity([pri2[r["event_id"]]["history"] for r in rows[d]]),
        "eligible_events": familiarity([pri2[r["event_id"]]["history"]
                                        for r, e in zip(rows[d], arms["sage_on"][d][0]) if e["eligible"]]),
        "eligible_events_development": familiarity([pri2[r["event_id"]]["development"]
                                                    for r, e in zip(rows[d], arms["sage_on"][d][0]) if e["eligible"]])}
        for d in HORIZONS}
    r2["split"] = split_period("R2", arms, rows, published, pri2, args.repetitions, args.seed)
    r2["same_leaker_baseline"] = "not computed: R2 records name only the seeds, not the target or new members"
    out["R2"] = r2
    out["same_leaker_baseline_scope"] = {
        "candidates": "native candidates of online history (all ASes with positive participation in the available "
                      "library, plus the seeds); the shared (graph) candidate identities are held only in the graph "
                      "files, not in the per-event records, so the shared-candidate variant is not computed",
        "availability": "library events with onset + 7200 s <= issue time (onset + Delta), as the history arm; the "
                        "repeat class uses onset + 7200 s <= onset",
        "ties": "exact expectation over random orders within ties (event_ranking_metrics)",
        "input_gap": "the released seed sets count ASes by raw first-seen time, the forecast input by availability; "
                     "on events with gap k > 0 the released set holds k ASes that were not yet input seeds, which "
                     "cannot be identified from the released files (see the module docstring)",
        "populations": {"released_inputs": "published eligible events with a new member under the released seed sets; "
                                           "all three rankings on the released seed sets; no SAGE contrast",
                        "exact_inputs": "published eligible events with k = 0, where the reconstruction equals the "
                                        "published online history native record per event; SAGE contrasts here"}}
    Path(args.out_json).write_text(json.dumps(out, indent=1) + "\n")
    write_tex(args.out_tex, {"R1": r1["split"], "R2": r2["split"]}, base)
    print("wrote", args.out_json, args.out_tex)


if __name__ == "__main__":
    main()
