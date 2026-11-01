"""Simple count-only forecasting controls with physically separated test labels.

Quantile boosting sees the exact short observed count sequence. Exponential
saturation is a fixed parametric baseline, not an asserted BGP mechanism.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import pickle
import time

import numpy as np

QUANTILES = (.1, .5, .9)
CONFIGURATIONS = {
    1: {"max_depth": 3, "max_iter": 100, "learning_rate": .1},
    2: {"max_depth": 3, "max_iter": 200, "learning_rate": .05},
    3: {"max_depth": 6, "max_iter": 100, "learning_rate": .1},
    4: {"max_depth": 6, "max_iter": 200, "learning_rate": .05},
    5: {"max_depth": 3, "max_iter": 100, "learning_rate": .05},
    6: {"max_depth": 6, "max_iter": 100, "learning_rate": .05},
}
SATURATION_SECONDS = (30, 60, 120, 300, 600, 1800)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def partition(root, split, labels, *, expected_protocol_sha256=None):
    root = Path(root)
    protocol_bytes = (root / "partitions.json").read_bytes()
    if expected_protocol_sha256 and hashlib.sha256(protocol_bytes).hexdigest() != expected_protocol_sha256:
        raise ValueError("Count partition identity changed")
    protocol = json.loads(protocol_bytes)
    info = protocol["parts"][split]
    path = root / info["inputs"]
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != info["inputs_sha256"]:
        raise ValueError("Count input hash mismatch")
    inputs = dict(np.load(io.BytesIO(raw), allow_pickle=False))
    context, grid, horizons = inputs["context"], inputs["context_seconds"], inputs["target_seconds"]
    if (context.ndim != 2 or context.shape != (len(inputs["event_ids"]), len(grid))
            or len(set(inputs["event_ids"])) != len(context) or len(grid) < 2
            or not np.isfinite(grid).all() or grid[0] != 0 or (np.diff(grid) <= 0).any()
            or not np.isfinite(horizons).all() or (np.diff(horizons) <= 0).any()
            or not len(horizons) or horizons[-1] <= grid[-1]):
        raise ValueError("Invalid count shapes, IDs, or time grids")
    features(context)
    if labels:
        target_path = root / info["labels"]
        raw = target_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != info["labels_sha256"]:
            raise ValueError("Count label hash mismatch")
        target = dict(np.load(io.BytesIO(raw), allow_pickle=False))
        if not np.array_equal(inputs["event_ids"], target["event_ids"]):
            raise ValueError("Count input/label IDs differ")
        inputs["target"] = target["target"]
        truth = inputs["target"]
        if (truth.shape != (len(context), len(horizons)) or not np.isfinite(truth).all()
                or (truth < 0).any() or (np.diff(truth, axis=1) < 0).any()
                or (truth[:, horizons > grid[-1]] < context[:, -1, None]).any()):
            raise ValueError("Invalid cumulative count targets")
    return inputs


def features(context):
    counts = np.asarray(context, dtype=float)
    if not np.isfinite(counts).all() or (counts < 0).any() or (np.diff(counts, axis=1) < 0).any():
        raise ValueError("Contexts must be finite nonnegative cumulative counts")
    return np.concatenate((np.log1p(counts), np.log1p(np.diff(counts, axis=1))), axis=1)


def coherent(log_quantiles, context):
    q = np.maximum(log_quantiles, np.log1p(context[:, -1])[:, None, None])
    q = np.maximum.accumulate(np.maximum.accumulate(q, axis=2), axis=1)
    if not np.isfinite(q).all():
        raise ValueError("Nonfinite count prediction")
    return q


def predict_rows(checkpoint, data):
    x = features(data["context"])
    if checkpoint["method"] == "boosted":
        q = np.stack([np.stack([model.predict(x) for model in horizon], axis=1)
                      for horizon in checkpoint["models"]], axis=1)
    elif checkpoint["method"] == "persistence":
        q = np.broadcast_to(np.log1p(data["context"][:, -1])[:, None, None],
                            (len(x), len(data["target_seconds"]), 3)).copy()
    else:
        tau = checkpoint["saturation_seconds"]
        basis = -np.expm1(-data["context_seconds"] / tau)
        changes = data["context"] - data["context"][:, :1]
        amplitude = np.maximum(changes @ basis / max(basis @ basis, 1e-12), 0)
        count = data["context"][:, :1] + amplitude[:, None] * -np.expm1(-data["target_seconds"] / tau)
        q = np.repeat(np.log1p(count)[:, :, None], 3, axis=2)
    return coherent(q, data["context"])


def metrics(log_q, data, probabilistic=True):
    from bgbench.forecast_numeric import COVERAGE_CONVENTION, covered_log_interval
    count = np.expm1(log_q)
    truth = data["target"]
    future = data["target_seconds"] > data["context_seconds"][-1]
    if not future.any():
        raise ValueError("No future target horizons")
    score = 2 * abs(count[:, future, 1] - truth[:, future]) / np.maximum(count[:, future, 1] + truth[:, future], 1e-9)
    result = {"event_mean_smape": score.mean(axis=1).tolist(), "mean_smape": float(score.mean())}
    if probabilistic:
        error = np.log1p(truth[:, :, None]) - log_q
        loss = np.maximum(np.asarray(QUANTILES) * error, (np.asarray(QUANTILES) - 1) * error)
        result.update(log_count_pinball=float(loss[:, future].mean()),
                      interval80_coverage=float(covered_log_interval(
                          truth[:, future], log_q[:, future, 0], log_q[:, future, 2]).mean()),
                      interval80_coverage_convention=COVERAGE_CONVENTION,
                      interval80_mean_width=float((count[:, future, 2] - count[:, future, 0]).mean()))
    return result


def fit(dataset, out, method="boosted", configuration=1):
    from sklearn.ensemble import HistGradientBoostingRegressor
    import sklearn
    start = time.perf_counter()
    dataset, out = Path(dataset), Path(out)
    protocol = json.loads((dataset / "partitions.json").read_text())
    if protocol.get("protected_test"):
        raise ValueError("Protected campaign needs the separate approved fit/export workflow")
    validation = partition(dataset, "validation", True)
    checkpoint = {"method": method, "configuration": configuration, "models": []}
    if method == "boosted":
        train = partition(dataset, "train", True)
        x, y = features(train["context"]), np.log1p(train["target"])
        for index in range(y.shape[1]):
            models = []
            for quantile in QUANTILES:
                model = HistGradientBoostingRegressor(loss="quantile", quantile=quantile,
                    **CONFIGURATIONS[configuration], early_stopping=False, random_state=0)
                model.fit(x, y[:, index])
                models.append(model)
            checkpoint["models"].append(models)
    elif method == "saturating":
        checkpoint["saturation_seconds"] = SATURATION_SECONDS[configuration - 1]
    elif method != "persistence":
        raise ValueError("Unknown curve baseline")
    log_q = predict_rows(checkpoint, validation)
    validation_metrics = metrics(log_q, validation, method == "boosted")
    out.mkdir(parents=True, exist_ok=False)
    np.savez_compressed(out / "validation_predictions.npz", log_quantiles=log_q, event_ids=validation["event_ids"])
    receipt = {"method": method, "configuration": configuration, "sklearn_version": sklearn.__version__,
               "dataset_receipt_sha256": sha(dataset / "partitions.json"), "source_sha256": sha(__file__),
               "validation_metrics": validation_metrics, "test_files_opened": False,
               "configuration_scope": "six fixed configurations; select minimum validation meanSMAPE; ties lowestID",
               "probabilistic": method == "boosted", "quantiles": QUANTILES if method == "boosted" else None,
               "projection": "observed-count floor, quantile cummax, then temporal cummax",
               "elapsed_seconds": time.perf_counter() - start}
    checkpoint["receipt"] = receipt
    with (out / "checkpoint.pkl").open("wb") as stream:
        pickle.dump(checkpoint, stream)
    receipt["checkpoint_sha256"] = sha(out / "checkpoint.pkl")
    (out / "fit_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--method", choices=("boosted", "saturating", "persistence"), default="boosted")
    p.add_argument("--configuration", type=int, choices=range(1, 7), default=1)
    print(json.dumps(fit(**vars(p.parse_args()))))
