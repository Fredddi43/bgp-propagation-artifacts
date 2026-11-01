"""Matched-input gradient boosting; fitting never opens test tensors.

A CPU baseline for future AS membership. It consumes the same candidate features
as neural controls and is not a separate curve forecaster. Six development
configurations are enumerated up front; no hidden early stopping or test tuning.
"""
from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path
import time

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
import sklearn

from .forecast_train import (calibrate_threshold, load_partition, reserve_output,
                             sha256, validate_manifest, write_json, input_gate_hashes)

CONFIGURATIONS = {
    1: {"max_depth": 3, "max_iter": 100, "learning_rate": .1},
    2: {"max_depth": 3, "max_iter": 200, "learning_rate": .05},
    3: {"max_depth": 6, "max_iter": 100, "learning_rate": .1},
    4: {"max_depth": 6, "max_iter": 200, "learning_rate": .05},
    5: {"max_depth": 3, "max_iter": 100, "learning_rate": .05},
    6: {"max_depth": 6, "max_iter": 100, "learning_rate": .05},
}


def training_arrays(events, pos_weight_cap=20):
    """Event-balanced non-seed loss and positive weights match neural training."""
    xs, ys, weights = [], [], []
    for event in events:
        mask = ~event["persistence_pred"].numpy().astype(bool)
        y = event["y"].numpy()[mask]
        if not len(y):
            continue
        positive_weight = 1. if (y > .5).all() else min((len(y) - y.sum()) / max(y.sum(), 1), pos_weight_cap)
        xs.append(event["x"].numpy()[mask])
        ys.append(y)
        weights.append(np.where(y > .5, positive_weight, 1.) / len(y))
    if not xs:
        raise ValueError("No non-seed training examples")
    return np.concatenate(xs), np.concatenate(ys), np.concatenate(weights)


def rows(model, events, threshold):
    result = []
    classes = list(model.classes_)
    for event in events:
        start = time.perf_counter()
        probability = model.predict_proba(event["x"].numpy())
        p = probability[:, classes.index(1)] if 1 in classes else np.zeros(len(probability))
        seeds = sorted(map(int, event["seed_asns"].tolist()))
        candidates = event["asn"].tolist()
        result.append({"event_id": event["event_id"], "candidate_asns": candidates,
                       "probabilities": p.tolist(), "seed_asns": seeds,
                       "predicted_asns": sorted(set(seeds) | {a for a, probability in zip(candidates, p) if probability >= threshold}),
                       "threshold": threshold,
                       "observation_cutoff_s": float(event.get("observation_cutoff_s", event.get("delta_s", 30))),
                       "forward_seconds": time.perf_counter() - start,
                       "curve_output": "not_provided_membership_only_baseline"})
    return result


def fit(manifest_path, out, *, configuration=1, graph_dirs=(), seed=0, input_gate=None):
    started = time.perf_counter()
    doc = json.loads(Path(manifest_path).read_text())
    validate_manifest(doc)
    expected, gate_digest = input_gate_hashes(input_gate, manifest_path, doc)
    training, train_receipt = load_partition(Path(manifest_path), doc, "train", list(graph_dirs), expected_hashes=expected)
    validation, validation_receipt = load_partition(Path(manifest_path), doc, "validation", list(graph_dirs), expected_hashes=expected)
    reserve_output(Path(out))
    x, y, weights = training_arrays(training)
    settings = CONFIGURATIONS[configuration]
    model = HistGradientBoostingClassifier(**settings, max_leaf_nodes=min(31, 2 ** settings["max_depth"] - 1),
                                           early_stopping=False, random_state=seed)
    model.fit(x, y, sample_weight=weights)
    validation_predictions = rows(model, validation, .5)
    threshold, validation_jaccard = calibrate_threshold(validation_predictions, validation)
    for row in validation_predictions:
        row["threshold"] = threshold
        row["predicted_asns"] = sorted(set(row["seed_asns"]) | {a for a, p in zip(row["candidate_asns"], row["probabilities"]) if p >= threshold})
    receipt = {"model": "hist_gradient_boosting_membership", "configuration": configuration,
               "prespecified_configurations": CONFIGURATIONS, "settings": settings, "seed": seed,
               "manifest_sha256": sha256(Path(manifest_path)), "input_gate_sha256": gate_digest, "source_sha256": sha256(Path(__file__)),
               "protocol_source_sha256": sha256(Path(__file__).with_name("forecast_train.py")),
               "train_inputs": train_receipt, "validation_inputs": validation_receipt,
               "training_nodes": len(y), "training_events": len(training), "validation_events": len(validation),
               "history_feature_indices": doc["history_feature_indices"], "history": "on",
               "feature_contract": doc.get("feature_contract"), "feature_transform": "raw_shared_features",
               "threshold": threshold, "threshold_calibration_split": "validation",
               "validation_jaccard": validation_jaccard, "early_stopping": False, "test_inputs_opened": False,
               "objective": "event_balanced_nonseed_binary_log_loss_positive_weight_cap20",
               "positive_only_event_weight": 1.0,
               "elapsed_seconds": time.perf_counter() - started, "sklearn_version": sklearn.__version__}
    checkpoint = Path(out) / "checkpoint.pkl"
    with checkpoint.open("wb") as stream:
        pickle.dump({"model": model, "threshold": threshold, "receipt": receipt}, stream)
    receipt["checkpoint_sha256"] = sha256(checkpoint)
    write_json(Path(out) / "validation_predictions.json", validation_predictions)
    write_json(Path(out) / "fit_receipt.json", receipt)
    return receipt


def predict(checkpoint_path, manifest_path, out, *, graph_dirs=(), allow_label_containers=False, input_gate=None):
    from datetime import datetime, timezone
    doc = json.loads(Path(manifest_path).read_text())
    validate_manifest(doc)
    if allow_label_containers and (doc.get("locked_test") or doc.get("protected_test")):
        raise ValueError("Protected tests require label-free inputs")
    with Path(checkpoint_path).open("rb") as stream:
        checkpoint = pickle.load(stream)
    if checkpoint["receipt"]["feature_contract"] != doc.get("feature_contract"):
        raise ValueError("Checkpoint/manifest feature contracts differ")
    if checkpoint["receipt"]["history_feature_indices"] != doc["history_feature_indices"]:
        raise ValueError("Checkpoint/manifest history features differ")
    expected, gate_digest = input_gate_hashes(input_gate, manifest_path, doc)
    events, receipt = load_partition(Path(manifest_path), doc, "test", list(graph_dirs), prediction=True,
                                    allow_label_containers=allow_label_containers, expected_hashes=expected)
    reserve_output(Path(out))
    predictions = rows(checkpoint["model"], events, checkpoint["threshold"])
    write_json(Path(out) / "predictions.json", predictions)
    commitment = {"created_utc": datetime.now(timezone.utc).isoformat(),
                  "manifest_sha256": sha256(Path(manifest_path)), "input_gate_sha256": gate_digest, "checkpoint_sha256": sha256(Path(checkpoint_path)),
                  "predictions_sha256": sha256(Path(out) / "predictions.json"), "inputs": receipt,
                  "event_ids": [r["event_id"] for r in predictions], "test_labels_used": False,
                  "label_free_input_files": not allow_label_containers,
                  "prediction_source_sha256": sha256(Path(__file__))}
    write_json(Path(out) / "commitment.json", commitment)
    return commitment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("fit", "predict"):
        p = commands.add_parser(name)
        p.add_argument("--manifest", dest="manifest_path", type=Path, required=True)
        p.add_argument("--out", type=Path, required=True)
        p.add_argument("--input-gate", type=Path)
        p.add_argument("--graphs", dest="graph_dirs", type=Path, action="append", default=[])
        if name == "fit":
            p.add_argument("--configuration", type=int, choices=sorted(CONFIGURATIONS), default=1)
            p.add_argument("--seed", type=int, default=0)
        else:
            p.add_argument("--checkpoint", dest="checkpoint_path", type=Path, required=True)
            p.add_argument("--allow-label-containers", action="store_true")
    args = vars(parser.parse_args())
    command = args.pop("command")
    receipt = {"fit": fit, "predict": predict}[command](**args)
    print(json.dumps({k: v for k, v in receipt.items() if k not in ("train_inputs", "validation_inputs", "inputs")}))


if __name__ == "__main__":
    main()
