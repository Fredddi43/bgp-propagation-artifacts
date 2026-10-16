"""Rung 4 with the other TSFMs: Moirai (uni2ts) and TimesFM zero-shot on the VP-session magnitude curve of sampled
growing test events, scored like curve_eventset (sMAPE at 15/60/120 min vs persistence). Runs in venv-tsfm.
usage: tsfm_curves.py <year> <set_tag or ''> <min_asns> <sample> <out_json>"""
from __future__ import annotations

import json
from importlib.metadata import version, PackageNotFoundError
import sys
from pathlib import Path

import numpy as np
import polars as pl

from bgbench import config
from bgbench.curve_eventset import event_series

DATA = config.DATA_ROOT
HORIZONS = {"T15m": 15, "T60m": 60, "T120m": 120}


def smape(a: float, b: float) -> float:
    return 2 * abs(a - b) / max(abs(a) + abs(b), 1e-9)


CURVE = "asn"


def load_series(eid: str, root: Path, onset: str):
    return event_series(root / eid, onset, CURVE)


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
            # The installed Torch 2.4 fused attention produces NaNs for fully
            # masked padding queries. Use TimesFM's own reference attention,
            # which applies its finite mask and preserves the trained weights.
            from timesfm.torch.transformer import MultiHeadAttention, _dot_product_attention
            for layer in tfm.model.modules():
                if isinstance(layer, MultiHeadAttention):
                    layer.attention_fn = _dot_product_attention
            tfm.compile(timesfm.ForecastConfig(max_context=256, max_horizon=128, normalize_inputs=True, use_continuous_quantile_head=True, force_flip_invariance=True, infer_is_positive=True, fix_quantile_crossing=True))

            def predict(ctx: np.ndarray, h: int) -> np.ndarray:
                point, _q = tfm.forecast(horizon=h, inputs=[ctx.astype(np.float32)])
                return np.asarray(point[0][:h])
            return "timesfm_2.5_200m", predict
        tfm = timesfm.TimesFm(hparams=timesfm.TimesFmHparams(backend="cpu", per_core_batch_size=1, horizon_len=128, context_len=512),
                              checkpoint=timesfm.TimesFmCheckpoint(huggingface_repo_id="google/timesfm-2.0-500m-pytorch"))

        def predict(ctx: np.ndarray, h: int) -> np.ndarray:
            point, _ = tfm.forecast([ctx.astype(np.float32)], freq=[0])
            return np.asarray(point[0][:h])
        return "timesfm_2.0_500m", predict
    except Exception as e:  # noqa: BLE001
        raise RuntimeError("Required TimesFM model failed initialization") from e


def main(year: int, set_tag: str, min_asns: int, sample: int, out: str) -> None:
    import torch
    torch.manual_seed(11)
    tbl = pl.read_parquet(DATA / "eventset" / (f"{year}_{set_tag}" if set_tag else str(year)) / "events.parquet").filter(pl.col("error").is_null())
    if set_tag.startswith("leak"):
        tbl = tbl.filter(pl.col("observation_lag_s").is_null() | (pl.col("observation_lag_s") >= -60))
    if min_asns:
        tbl = tbl.filter(pl.col("asns_final_2h") >= min_asns)
    test = tbl.filter((pl.col("split") == "test") & ((pl.col("asns_final_2h") > pl.col("asns_T5m")) if CURVE == "asn" else (pl.col("vp_final_2h") > pl.col("vp_T5m"))))
    rng = np.random.default_rng(11)
    ids = [test["event_id"][int(i)] for i in rng.choice(test.height, size=min(sample, test.height), replace=False)]
    root = DATA / ("events_replay_leak" if set_tag.startswith("leak") else "events_replay")
    onsets = dict(test.select("event_id", "t0_obs").iter_rows())
    models = {"moirai_small": moirai_forecaster("small")}
    tf = timesfm_forecaster()
    if tf:
        name, predictor = tf
        models[name] = predictor
    acc: dict = {}
    scored = []
    failures = []
    for delta in (1, 5, 15):
        for eid in ids:
            N = load_series(eid, root, onsets[eid])
            if N is None: continue
            ctx = N[: delta + 1]
            if ctx[-1] <= 0: continue
            for hk, hm in HORIZONS.items():
                if hm > delta:
                    acc.setdefault(("persistence", delta), {}).setdefault(hk, []).append(smape(float(ctx[-1]), N[hm]))
                    scored.append({"event_id": eid, "model": "persistence", "delta_min": delta, "horizon_min": hm, "truth": float(N[hm]), "observed_delta_count": float(ctx[-1]), "prediction": float(ctx[-1]), "smape": smape(float(ctx[-1]), N[hm]), "persistence_smape": smape(float(ctx[-1]), N[hm])})
            for name, f in models.items():
                try:
                    fc = np.asarray(f(ctx, 120 - delta), dtype=float).reshape(-1)
                    if len(fc) < 120-delta or not np.isfinite(fc).all():
                        raise ValueError("Forecast is incomplete or non-finite")
                except Exception as e:  # noqa: BLE001
                    acc.setdefault((name, delta), {}).setdefault("errors", []).append(str(e)[:80])
                    failures.append({"event_id": eid, "model": name, "delta_min": delta, "error": str(e)})
                    continue
                for hk, hm in HORIZONS.items():
                    if hm <= delta: continue
                    truth = N[hm]; pred = max(float(fc[hm - delta - 1]), float(ctx[-1]))    # monotone: never below the current count
                    acc.setdefault((name, delta), {}).setdefault(hk, []).append(smape(pred, truth))
                    scored.append({"event_id": eid, "model": name, "delta_min": delta, "horizon_min": hm, "truth": float(truth), "observed_delta_count": float(ctx[-1]), "prediction": pred, "smape": smape(pred, truth), "persistence_smape": smape(float(ctx[-1]), truth)})
    res = {f"{name}@d{delta}m": {k: (round(float(np.mean(v)), 4) if k != "errors" else len(v)) for k, v in d.items()} for (name, delta), d in acc.items()}
    res["measurement_definition"] = "exact_minute_counts_from_membership_at_t0_obs_v1"
    res["sampled_event_ids"] = ids
    res["events"] = len(ids); res["set_tag"] = set_tag; res["min_asns"] = min_asns; res["curve"] = CURVE
    res["input_scale"] = "raw_counts"
    res["required_models"] = list(models)
    res["seed"] = 11
    res["timesfm_attention"] = "package_reference_finite_mask" if "timesfm_2.5_200m" in models else "package_default"
    res["failures"] = failures
    res["package_versions"] = {}
    for package in ("torch", "timesfm", "uni2ts", "gluonts", "numpy"):
        try:
            res["package_versions"][package] = version(package)
        except PackageNotFoundError:
            res["package_versions"][package] = None
    from huggingface_hub import try_to_load_from_cache
    repositories = {"moirai_small": "Salesforce/moirai-1.1-R-small",
                    "timesfm_2.5_200m": "google/timesfm-2.5-200m-pytorch",
                    "timesfm_2.0_500m": "google/timesfm-2.0-500m-pytorch"}
    res["model_checkpoints"] = {}
    for name in models:
        revision = None
        for filename in ("config.json", "model.safetensors", "torch_model.ckpt"):
            cached = try_to_load_from_cache(repositories[name], filename)
            if isinstance(cached, str) and "/snapshots/" in cached:
                revision = cached.split("/snapshots/", 1)[1].split("/", 1)[0]
                break
        res["model_checkpoints"][name] = {"repository": repositories[name], "revision": revision}
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(scored).write_parquet(Path(out).with_suffix(".predictions.parquet"))
    Path(out).write_text(json.dumps(res, indent=1)); print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main(int(sys.argv[1]), sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5])
