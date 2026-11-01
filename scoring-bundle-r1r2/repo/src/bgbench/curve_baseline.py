"""ADR-0007 rung 4 — time-series foundation model on the magnitude curve (zero-shot), plus naive baselines.

Series: cumulative count of leaked prefixes N(t) at 1-min bins from t₀ (from leak_prefix_growth_curve.csv).
Task: given the first Δ minutes, forecast N(t) for t up to 120 min; score MAE / sMAPE at T ∈ {15, 60, 120} and
prediction-interval coverage. Baselines: persistence (flat), linear extrapolation of the last 5 minutes.
Chronos-2 (amazon/chronos-2, Apache-2.0) zero-shot via the `chronos-forecasting` package; CPU is fine.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from . import config


def minute_series(name: str, horizon_min: int = 120) -> np.ndarray:
    df = pl.read_csv(config.EVENT_DIR / name / "_extent" / "leak_prefix_growth_curve.csv").filter(
        pl.col("rel_s") >= 0
    )
    N = np.zeros(horizon_min + 1)
    for s, n in zip(df["rel_s"].to_list(), df["N"].to_list()):
        m = int(s // 60)
        if m <= horizon_min:
            N[m] = max(N[m], n)
    # cumulative: carry forward
    for i in range(1, len(N)):
        N[i] = max(N[i], N[i - 1])
    return N


def naive_forecasts(ctx: np.ndarray, steps: int) -> dict[str, np.ndarray]:
    last = ctx[-1]
    slope = (ctx[-1] - ctx[max(0, len(ctx) - 6)]) / max(min(5, len(ctx) - 1), 1)
    return {"persistence": np.full(steps, last), "linear5": last + slope * np.arange(1, steps + 1)}


def chronos_forecast(ctx: np.ndarray, steps: int, model_id: str = "amazon/chronos-2") -> dict:
    import torch
    from chronos import BaseChronosPipeline

    pipe = BaseChronosPipeline.from_pretrained(
        model_id, device_map="cpu", torch_dtype=torch.float32
    )
    q_levels = [0.1, 0.5, 0.9]
    x = torch.tensor(ctx, dtype=torch.float32)
    try:  # Chronos-2 API: predict_quantiles(inputs 3-D (n_series, n_variates, history), prediction_length, quantile_levels)
        quantiles, mean = pipe.predict_quantiles(
            x[None, None, :], prediction_length=steps, quantile_levels=q_levels
        )
    except (TypeError, ValueError):  # Chronos-1 / Bolt API: 2-D context
        quantiles, mean = pipe.predict_quantiles(
            context=x[None, :], prediction_length=steps, quantile_levels=q_levels
        )
    q = quantiles[0].detach().cpu().numpy()
    q = q.reshape(-1, len(q_levels)) if q.ndim != 2 else q  # (steps, 3)
    m = mean[0].detach().cpu().numpy().reshape(-1)
    return {"p10": q[:, 0], "p50": q[:, 1], "p90": q[:, 2], "mean": m}


def score(truth: np.ndarray, pred: np.ndarray, ctx_len: int) -> dict:
    out = {}
    for lbl, secs in (("T15m", 900), ("T60m", 3600), ("final_2h", 7200)):
        t = secs // 60
        if t <= ctx_len:
            continue
        i = t - ctx_len - 1
        if i < len(pred):
            y, yhat = truth[t], pred[i]
            out[lbl] = {
                "truth": float(y),
                "pred": float(yhat),
                "abs_err": float(abs(y - yhat)),
                "smape": float(2 * abs(y - yhat) / max(abs(y) + abs(yhat), 1e-9)),
            }
    return out


def run(
    name: str,
    deltas_min: tuple[int, ...] = (5, 15),
    horizon_min: int = 120,
    use_chronos: bool = True,
) -> dict:
    N = minute_series(name, horizon_min)
    res = {"event": name, "final_truth": float(N[-1]), "deltas": {}}
    for d in deltas_min:
        ctx = N[: d + 1]
        steps = horizon_min - d
        fc = naive_forecasts(ctx, steps)
        entry = {k: score(N, v, d) for k, v in fc.items()}
        if use_chronos:
            try:
                c = chronos_forecast(ctx, steps)
                entry["chronos2_p50"] = score(N, c["p50"], d)
                truth_h = N[d + 1 :]
                entry["chronos2_coverage80"] = float(
                    np.mean((truth_h >= c["p10"]) & (truth_h <= c["p90"]))
                )
                # monotone variant: forecast per-minute increments (clipped ≥ 0), cumulate from the last value
                inc = np.diff(ctx, prepend=0.0)
                ci = chronos_forecast(inc, steps)
                cum = {
                    k: ctx[-1] + np.cumsum(np.clip(ci[k], 0, None)) for k in ("p10", "p50", "p90")
                }
                entry["chronos2_inc_p50"] = score(N, cum["p50"], d)
                entry["chronos2_inc_coverage80"] = float(
                    np.mean((truth_h >= cum["p10"]) & (truth_h <= cum["p90"]))
                )
            except Exception as e:  # noqa: BLE001
                entry["chronos2_error"] = f"{type(e).__name__}: {e}"
        res["deltas"][f"delta_{d}m"] = entry
    out = config.EVENT_DIR / name / "_extent" / "curve_baseline.json"
    import json

    out.write_text(json.dumps(res, indent=1))
    return res
