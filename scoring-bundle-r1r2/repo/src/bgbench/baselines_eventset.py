"""Sprint-2 step 6: cascade baseline on the replayed event set (test split), comparable to persistence.

Per test event: seeds = ASes seen by Δ (5 min), target = ASes at 2 h (from eventset/events.parquet lists);
cascade with the calibrated probabilities (p_c2p 0.05, p_p2c 0.001, p_p2p 0.002 — docs/results diffusion addendum)
on the CAIDA graph of the event month, 2-hop candidate universe; score Jaccard/recall/AUPRC at p ≥ 0.5 against the
target, alongside persistence on the same universe. Sampled (default 300 events) because each cascade is ~10 s.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import polars as pl

from . import config
from .diffusion import ICParams, evaluate_membership, fit_coaffection, khop_candidates, load_asgraph, simulate


def complete_cascade_footprint(sim: dict, seeds: set[int], final: set[int], candidates: set[int] | None = None) -> tuple[np.ndarray, np.ndarray, float]:
    """Retain known seeds and score every true member, including outside CAIDA."""
    asns = np.asarray(sim["asn"], dtype=np.int64)
    probabilities = np.asarray(sim["p_affected"], dtype=float).copy()
    if candidates is not None:
        probabilities[~np.isin(asns, list(candidates | seeds))] = 0.0
    probabilities[np.isin(asns, list(seeds))] = 1.0
    missing = sorted((seeds | final) - set(asns.tolist()))
    probabilities = np.concatenate([probabilities, [1.0 if asn in seeds else 0.0 for asn in missing]])
    expected_size = float(probabilities.sum())
    return np.concatenate([asns, np.asarray(missing, dtype=np.int64)]), probabilities, expected_size


def run(year: int = 2024, sample: int = 300, delta: str = "d5m", target: str = "final_2h", seed: int = 7,
        p: ICParams | None = None, coaffection: bool = False, alpha: float = 5.0, set_tag: str = "", min_asns: int = 0, rec: float = 1.0, valley_free: bool = False, output_dir: Path | None = None) -> dict:
    """coaffection=True (#21): per-edge probabilities fitted on the *train* split (seeds at Δ → members at target),
    shrunk to the type prior `p` with weight alpha; one fit per test month's CAIDA graph."""
    p = p or ICParams(p_c2p=0.05, p_p2c=0.001, p_p2p=0.002, rollouts=50)
    if rec < 1.0 or valley_free:
        p = ICParams(**{**p.__dict__, "rec": rec, "valley_free": valley_free})
    from .replay_day import roots
    tbl = pl.read_parquet(config.DATA_ROOT / "eventset" / (f"{year}_{set_tag}" if set_tag else str(year)) / "events.parquet")
    if set_tag.startswith("leak"):
        tbl = tbl.filter(pl.col("observation_lag_s").is_null() | (pl.col("observation_lag_s") >= -60))
    if min_asns:
        tbl = tbl.filter(pl.col("asns_final_2h") >= min_asns)
    replay_root = roots("leak" if set_tag.startswith("leak") else set_tag)[1]
    suffix = (f"_{set_tag}" if set_tag else "") + (f"_ge{min_asns}" if min_asns else "") + (f"_sir{rec}" if rec < 1.0 else "") + ("_vf" if valley_free else "")
    train = tbl.filter((pl.col("split") == "train") & pl.col("error").is_null() & pl.col(f"set_{delta}").is_not_null()
                       & pl.col(f"set_{target}").is_not_null())
    fitted: dict[str, object] = {}
    fit_stats: dict[str, dict] = {}
    test = tbl.filter((pl.col("split") == "test") & pl.col("error").is_null() & pl.col(f"set_{delta}").is_not_null()
                      & (pl.col(f"set_{target}").list.len() > pl.col(f"set_{delta}").list.len()))   # events that still grow
    embargo = {}
    if coaffection and test.height:
        from .graph_metrics import embargo_training_events
        kept, embargo = embargo_training_events(train.to_dicts(), test.to_dicts(), dict(tbl.select("event_id", "t0_obs").iter_rows()))
        train = train.filter(pl.col("event_id").is_in([row["event_id"] for row in kept]))
    train_sets = [(set(a), set(b)) for a, b in zip(train[f"set_{delta}"].to_list(), train[f"set_{target}"].to_list()) if a]
    growing_test_events_total = test.height
    rng = np.random.default_rng(seed)
    idx = rng.choice(test.height, size=min(sample, test.height), replace=False)
    test = test[sorted(int(i) for i in idx)]
    graphs: dict[str, object] = {}
    rows = []
    excluded = []
    for r in test.iter_rows(named=True):
        month = r["event_id"][:6]
        if month not in graphs:
            graphs[month] = load_asgraph(month)
        g = graphs[month]
        seeds = set(r[f"set_{delta}"]); final = set(r[f"set_{target}"])
        if not seeds or not any(asn in g.index for asn in seeds):
            excluded.append({"event_id": r["event_id"], "reason": "no_observed_seed_in_CAIDA_graph"})
            continue
        P = None
        if coaffection:
            if month not in fitted:
                fitted[month], fit_stats[month] = fit_coaffection(g, [a for a, _ in train_sets], [b for _, b in train_sets], p, alpha)
            P = fitted[month]
        sim = simulate(g, sorted(seeds), p, P=P)
        prediction_candidates = khop_candidates(g, seeds, 2) | seeds
        cand = prediction_candidates | final
        scored_asns, scored_probabilities, expected_size = complete_cascade_footprint(sim, seeds, final, prediction_candidates)
        ev = evaluate_membership(scored_probabilities, scored_asns, final, cand)
        tp = len(seeds & final); fp = len(seeds - final); fn = len(final - seeds)
        rows.append({"event_id": r["event_id"], "vis_bucket": r.get("vis_bucket", "n/a"), "labelled": r.get("labelled"), "seeds": len(seeds), "final": len(final),
                     "prediction_candidate_asns": sorted(prediction_candidates),
                     "scored_asns": scored_asns[np.isin(scored_asns, list(cand))].tolist(),
                     "scored_probabilities": scored_probabilities[np.isin(scored_asns, list(cand))].tolist(),
                     "observed_seed_asns": sorted(seeds), "true_final_asns": sorted(final),
                     "cascade_predicted_asns": scored_asns[(scored_probabilities >= 0.5) & np.isin(scored_asns, list(cand))].tolist(),
                     "cascade_jaccard": ev["jaccard"], "cascade_recall": ev["recall"], "cascade_precision": ev["precision"], "cascade_auprc": ev["auprc"],
                     "cascade_expected_size": expected_size,
                     "cascade_size_smape": float(2 * abs(expected_size - len(final)) / max(expected_size + len(final), 1e-9)),
                     "persist_size_smape": float(2 * abs(len(seeds) - len(final)) / max(len(seeds) + len(final), 1e-9)),
                     "persist_jaccard": tp / max(tp + fp + fn, 1), "persist_recall": tp / max(tp + fn, 1)})
    df = pl.DataFrame(rows)
    out_dir = output_dir or config.DATA_ROOT / "eventset" / str(year)
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = ("_coaffection" if coaffection else "") + suffix
    df.write_parquet(out_dir / f"cascade_vs_persistence_{delta}_{target}{tag}.parquet")
    summ = {"events_scored": df.height, "growing_test_events_total": growing_test_events_total, "sample_requested": sample, "sampling_seed": seed, "delta": delta, "target": target, "params": p.__dict__,
            "training_embargo": embargo, "excluded_events": excluded, "auprc_scope": "two_hop_candidates_union_all_observed_seeds_union_full_truth", "prediction_floor": "all_observed_seeds", "coaffection": coaffection, "alpha": alpha, "rec": rec, "valley_free": valley_free, "train_events_fit": len(train_sets), "fit_stats": fit_stats, "set_tag": set_tag, "min_asns": min_asns}
    if df.height:
        for c in ("cascade_jaccard", "cascade_recall", "cascade_auprc", "persist_jaccard", "persist_recall", "cascade_size_smape", "persist_size_smape"):
            summ[c + "_mean"] = round(float(df[c].mean()), 4)
        summ["cascade_beats_persistence_frac"] = round(float((df["cascade_jaccard"] > df["persist_jaccard"]).mean()), 4)
        summ["by_vis_bucket"] = df.group_by("vis_bucket").agg(n=pl.len(), cj=pl.col("cascade_jaccard").mean(), pj=pl.col("persist_jaccard").mean(), auprc=pl.col("cascade_auprc").mean()).sort("vis_bucket").to_dicts()
    (out_dir / f"cascade_vs_persistence_{delta}_{target}{tag}.json").write_text(json.dumps(summ, indent=1, default=str))
    return summ
