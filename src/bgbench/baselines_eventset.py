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


def run(year: int = 2024, sample: int = 300, delta: str = "d5m", target: str = "final_2h", seed: int = 7,
        p: ICParams | None = None, coaffection: bool = False, alpha: float = 5.0, set_tag: str = "", min_asns: int = 0, rec: float = 1.0, valley_free: bool = False) -> dict:
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
    train_sets = [(set(a), set(b)) for a, b in zip(train[f"set_{delta}"].to_list(), train[f"set_{target}"].to_list()) if a]
    fitted: dict[str, object] = {}
    fit_stats: dict[str, dict] = {}
    test = tbl.filter((pl.col("split") == "test") & pl.col("error").is_null() & pl.col(f"set_{delta}").is_not_null()
                      & (pl.col(f"set_{target}").list.len() > pl.col(f"set_{delta}").list.len()))   # events that still grow
    rng = np.random.default_rng(seed)
    idx = rng.choice(test.height, size=min(sample, test.height), replace=False)
    test = test[sorted(int(i) for i in idx)]
    graphs: dict[str, object] = {}
    rows = []
    for r in test.iter_rows(named=True):
        month = r["event_id"][:6]
        g = graphs.setdefault(month, load_asgraph(month))
        seeds = set(r[f"set_{delta}"]); final = set(r[f"set_{target}"])
        if not seeds:
            continue
        P = None
        if coaffection:
            if month not in fitted:
                fitted[month], fit_stats[month] = fit_coaffection(g, [a for a, _ in train_sets], [b for _, b in train_sets], p, alpha)
            P = fitted[month]
        sim = simulate(g, sorted(seeds), p, P=P)
        cand = khop_candidates(g, seeds, 2) | seeds | final
        ev = evaluate_membership(sim["p_affected"], sim["asn"], final, cand)
        tp = len(seeds & final); fp = len(seeds - final); fn = len(final - seeds)
        rows.append({"event_id": r["event_id"], "vis_bucket": r.get("vis_bucket", "n/a"), "labelled": r.get("labelled"), "seeds": len(seeds), "final": len(final),
                     "cascade_jaccard": ev["jaccard"], "cascade_recall": ev["recall"], "cascade_precision": ev["precision"], "cascade_auprc": ev["auprc"],
                     "cascade_expected_size": float(sim["expected_curve"][-1]),
                     "cascade_size_smape": float(2 * abs(sim["expected_curve"][-1] - len(final)) / max(sim["expected_curve"][-1] + len(final), 1e-9)),
                     "persist_size_smape": float(2 * abs(len(seeds) - len(final)) / max(len(seeds) + len(final), 1e-9)),
                     "persist_jaccard": tp / max(tp + fp + fn, 1), "persist_recall": tp / max(tp + fn, 1)})
    df = pl.DataFrame(rows)
    out_dir = config.DATA_ROOT / "eventset" / str(year)
    tag = ("_coaffection" if coaffection else "") + suffix
    df.write_parquet(out_dir / f"cascade_vs_persistence_{delta}_{target}{tag}.parquet")
    summ = {"events_scored": df.height, "growing_test_events_total": test.height, "delta": delta, "target": target, "params": p.__dict__,
            "coaffection": coaffection, "alpha": alpha, "rec": rec, "valley_free": valley_free, "train_events_fit": len(train_sets), "fit_stats": fit_stats, "set_tag": set_tag, "min_asns": min_asns}
    if df.height:
        for c in ("cascade_jaccard", "cascade_recall", "cascade_auprc", "persist_jaccard", "persist_recall", "cascade_size_smape", "persist_size_smape"):
            summ[c + "_mean"] = round(float(df[c].mean()), 4)
        summ["cascade_beats_persistence_frac"] = round(float((df["cascade_jaccard"] > df["persist_jaccard"]).mean()), 4)
        summ["by_vis_bucket"] = df.group_by("vis_bucket").agg(n=pl.len(), cj=pl.col("cascade_jaccard").mean(), pj=pl.col("persist_jaccard").mean(), auprc=pl.col("cascade_auprc").mean()).sort("vis_bucket").to_dicts()
    (out_dir / f"cascade_vs_persistence_{delta}_{target}{tag}.json").write_text(json.dumps(summ, indent=1, default=str))
    return summ
