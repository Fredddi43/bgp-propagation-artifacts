"""Rung 4 with the other TSFMs: Moirai (uni2ts) and TimesFM zero-shot on the VP-session magnitude curve of sampled
growing test events, scored like curve_eventset (sMAPE at 15/60/120 min vs persistence). Runs in venv-tsfm.
usage: tsfm_curves.py <year> <set_tag or ''> <min_asns> <sample> <out_json>"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import polars as pl

DATA = Path("data")
HORIZONS = {"T15m": 15, "T60m": 60, "T120m": 120}


def smape(a: float, b: float) -> float:
    return 2 * abs(a - b) / max(abs(a) + abs(b), 1e-9)


CURVE = "asn"


def load_series(eid: str, root: Path):
    f = root / eid / ("curve_asn.csv" if CURVE == "asn" else "curve_vp.csv")
    if not f.exists():
        return None
    c = pl.read_csv(f).sort("rel_s")
    # per-second cumulative VP-session count over [0, 7200], forward-filled → per-minute series
    t = np.arange(0, 7201); N = np.zeros_like(t, dtype=float)
    idx = np.searchsorted(c["rel_s"].to_numpy(), t, side="right") - 1
    N[idx >= 0] = c["N"].to_numpy()[idx[idx >= 0]]
    return N[::60]                        # 121 points, minute resolution


def moirai_forecaster(size: str = "small"):
    import torch
    from uni2ts.model.moirai import MoiraiForecast, MoiraiModule
    module = MoiraiModule.from_pretrained(f"Salesforce/moirai-1.1-R-{size}")

    def predict(ctx: np.ndarray, h: int) -> np.ndarray:
        model = MoiraiForecast(module=module, prediction_length=h, context_length=len(ctx), patch_size="auto", num_samples=50, target_dim=1, feat_dynamic_real_dim=0, past_feat_dynamic_real_dim=0)
        pred = model.create_predictor(batch_size=1)
        from gluonts.dataset.common import ListDataset
        ds = ListDataset([{"target": ctx.astype(np.float32), "start": "2024-01-01 00:00"}], freq="min")
        fc = next(iter(pred.predict(ds)))
        return np.median(fc.samples, axis=0)
    return predict


def timesfm_forecaster():
    import timesfm
    try:
        if hasattr(timesfm, "TimesFM_2p5_200M_torch"):                        # timesfm ≥ 2.5 API
            tfm = timesfm.TimesFM_2p5_200M_torch.from_pretrained("google/timesfm-2.5-200m-pytorch")
            tfm.compile(timesfm.ForecastConfig(max_context=256, max_horizon=128, normalize_inputs=True, use_continuous_quantile_head=True, force_flip_invariance=True, infer_is_positive=True, fix_quantile_crossing=True))

            def predict(ctx: np.ndarray, h: int) -> np.ndarray:
                point, _q = tfm.forecast(horizon=h, inputs=[ctx.astype(np.float32)])
                return np.asarray(point[0][:h])
            return predict
        tfm = timesfm.TimesFm(hparams=timesfm.TimesFmHparams(backend="cpu", per_core_batch_size=1, horizon_len=128, context_len=512),
                              checkpoint=timesfm.TimesFmCheckpoint(huggingface_repo_id="google/timesfm-2.0-500m-pytorch"))

        def predict(ctx: np.ndarray, h: int) -> np.ndarray:
            point, _ = tfm.forecast([ctx.astype(np.float32)], freq=[0])
            return np.asarray(point[0][:h])
        return predict
    except Exception as e:  # noqa: BLE001
        print("timesfm init failed:", repr(e)[:200], "| attrs:", [a for a in dir(timesfm) if "Times" in a][:8]); return None


def main(year: int, set_tag: str, min_asns: int, sample: int, out: str) -> None:
    tbl = pl.read_parquet(DATA / "eventset" / (f"{year}_{set_tag}" if set_tag else str(year)) / "events.parquet").filter(pl.col("error").is_null())
    if set_tag.startswith("leak"):
        tbl = tbl.filter(pl.col("observation_lag_s").is_null() | (pl.col("observation_lag_s") >= -60))
    if min_asns:
        tbl = tbl.filter(pl.col("asns_final_2h") >= min_asns)
    test = tbl.filter((pl.col("split") == "test") & ((pl.col("asns_final_2h") > pl.col("asns_T5m")) if CURVE == "asn" else (pl.col("vp_final_2h") > pl.col("vp_T5m"))))
    rng = np.random.default_rng(11)
    ids = [test["event_id"][int(i)] for i in rng.choice(test.height, size=min(sample, test.height), replace=False)]
    root = DATA / ("events_replay_leak" if set_tag.startswith("leak") else "events_replay")
    models = {"moirai_small": moirai_forecaster("small")}
    tf = timesfm_forecaster()
    if tf: models["timesfm_2.0_500m"] = tf
    acc: dict = {}
    for delta in (1, 5, 15):
        for eid in ids:
            N = load_series(eid, root)
            if N is None: continue
            ctx = N[: delta + 1]
            if ctx[-1] <= 0: continue
            for name, f in models.items():
                try:
                    fc = f(ctx, 120 - delta)
                except Exception as e:  # noqa: BLE001
                    acc.setdefault((name, delta), {}).setdefault("errors", []).append(str(e)[:80]); continue
                for hk, hm in HORIZONS.items():
                    if hm <= delta: continue
                    truth = N[hm]; pred = max(float(fc[hm - delta - 1]), float(ctx[-1]))    # monotone: never below the current count
                    acc.setdefault((name, delta), {}).setdefault(hk, []).append(smape(pred, truth))
                    acc.setdefault(("persistence", delta), {}).setdefault(hk, []).append(smape(float(ctx[-1]), truth))
    res = {f"{name}@d{delta}m": {k: (round(float(np.mean(v)), 4) if k != "errors" else len(v)) for k, v in d.items()} for (name, delta), d in acc.items()}
    res["events"] = len(ids); res["set_tag"] = set_tag; res["min_asns"] = min_asns; res["curve"] = CURVE
    Path(out).write_text(json.dumps(res, indent=1)); print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main(int(sys.argv[1]), sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5])
