"""Sprint-2 step 6: magnitude-curve baselines on the replayed event set (test split, sampled).

Series per event: cumulative VP sessions that switched to the new origin, 1-min bins, 0…120 min (curve_vp.csv).
Given Δ minutes, forecast to 120 min: persistence, linear-5, Chronos-2 raw p50, Chronos-2 increment-space p50.
sMAPE at 15/60/120 min, aggregated over events.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl

from . import config
from .curve_baseline import chronos_forecast, naive_forecasts


def _series(csv: Path, horizon_min: int = 120) -> np.ndarray:
    df = pl.read_csv(csv).filter(pl.col("rel_s") >= 0)
    N = np.zeros(horizon_min + 1)
    for s, n in zip(df["rel_s"].to_list(), df["N"].to_list()):
        m = int(s // 60)
        if m <= horizon_min:
            N[m] = max(N[m], n)
    for i in range(1, len(N)):
        N[i] = max(N[i], N[i - 1])
    return N


def logistic_forecast(ctx: np.ndarray, horizons_min: list[int], delta_min: int) -> dict[int, float]:
    """The plan's parametric alternative to a free-form curve: fit N(t) = K / (1 + exp(-r (t - t0))) to the observed
    minutes by least squares over a small grid (K ≥ current, r > 0), forecast the horizons. Falls back to persistence
    when the context is flat."""
    t = np.arange(len(ctx), dtype=float); cur = float(ctx[-1])
    if cur <= 0 or len(ctx) < 2 or ctx[-1] <= ctx[0]:
        return {h: cur for h in horizons_min}
    best, best_err = (cur, 0.0, 0.0), float("inf")
    for K in cur * np.array([1.0, 1.2, 1.5, 2, 3, 5, 8]):
        for r in (0.05, 0.1, 0.2, 0.5, 1.0, 2.0):
            for t0 in np.linspace(-len(ctx), 2 * len(ctx), 9):
                pred = K / (1 + np.exp(-r * (t - t0)))
                err = float(((pred - ctx) ** 2).mean())
                if err < best_err:
                    best, best_err = (K, r, t0), err
    K, r, t0 = best
    return {h: max(cur, float(K / (1 + np.exp(-r * (h - t0))))) for h in horizons_min}


def run(year: int = 2024, sample: int = 200, deltas=(1, 5, 15), use_chronos: bool = True, seed: int = 11, set_tag: str = "", min_asns: int = 0, curve: str = "asn") -> dict:
    """curve: 'asn' = pooled affected-AS count (the GNN curve head's target) or 'vp' = VP-session count (earlier notes)."""
    from .replay_day import roots
    tbl = pl.read_parquet(config.DATA_ROOT / "eventset" / (f"{year}_{set_tag}" if set_tag else str(year)) / "events.parquet")
    if set_tag.startswith("leak"):
        tbl = tbl.filter(pl.col("observation_lag_s").is_null() | (pl.col("observation_lag_s") >= -60))
    if min_asns:
        tbl = tbl.filter(pl.col("asns_final_2h") >= min_asns)
    replay_root = roots("leak" if set_tag.startswith("leak") else set_tag)[1]
    suffix = (f"_{set_tag}" if set_tag else "") + (f"_ge{min_asns}" if min_asns else "")
    grow = (pl.col("asns_final_2h") > pl.col("asns_T5m")) if curve == "asn" else (pl.col("vp_final_2h") > pl.col("vp_T5m"))
    test = tbl.filter((pl.col("split") == "test") & pl.col("error").is_null() & grow)
    rng = np.random.default_rng(seed)
    ids = [test["event_id"][int(i)] for i in rng.choice(test.height, size=min(sample, test.height), replace=False)]
    horizons = {"T15m": 15, "T60m": 60, "T120m": 120}
    acc: dict[str, dict[str, list]] = {}
    n_used = 0
    for eid in ids:
        f = replay_root / eid / ("curve_asn.csv" if curve == "asn" else "curve_vp.csv")
        if not f.exists():
            continue
        N = _series(f)
        n_used += 1
        for d in deltas:
            ctx, steps = N[: d + 1], 120 - d
            preds = naive_forecasts(ctx, steps)
            lg = logistic_forecast(ctx, list(range(d + 1, 121)), d)                 # parametric growth curve (plan's alternative head)
            preds["logistic"] = np.array([lg[h] for h in range(d + 1, 121)])
            if use_chronos:
                try:
                    c = chronos_forecast(ctx, steps)
                    preds["chronos2_raw"] = c["p50"]
                    inc = np.diff(ctx, prepend=0.0)
                    ci = chronos_forecast(inc, steps)
                    preds["chronos2_inc"] = ctx[-1] + np.cumsum(np.clip(ci["p50"], 0, None))
                except Exception as e:  # noqa: BLE001
                    preds["chronos2_error"] = str(e)[:80]
            for m, pred in preds.items():
                if isinstance(pred, str):
                    continue
                for hk, hm in horizons.items():
                    if hm <= d:
                        continue
                    y, yhat = N[hm], pred[hm - d - 1]
                    acc.setdefault(f"d{d}m", {}).setdefault(f"{m}:{hk}", []).append(2 * abs(y - yhat) / max(abs(y) + abs(yhat), 1e-9))
    res = {"events_used": n_used, "growing_test_events": test.height}
    for dk, mm in acc.items():
        res[dk] = {k: round(float(np.mean(v)), 3) for k, v in sorted(mm.items())}
    res["set_tag"] = set_tag; res["min_asns"] = min_asns; res["curve"] = curve
    (config.DATA_ROOT / "eventset" / (f"{year}_{set_tag}" if set_tag else str(year)) / f"curve_baselines{suffix}_{curve}.json").write_text(json.dumps(res, indent=1))
    return res
