"""Label-free retrospective test predictions from Mean-sensitivity checkpoints; never scores.

Mirrors ``forecast_temporal_predict`` for the one extra model kind without changing it: the frozen
loader projects every label away before any model exists, the reviewed ``attach_messages`` re-reads
only the hash-verified ``msgs``, and normalization, row construction and the forward are the frozen
``transform_events``, ``prediction_rows`` and ``temporal_forward``. The model comes from the Mean fit
adapter's ``make_model`` with a strict state-dict load. All model, trainer and adapter sources must be
byte-identical to the fit receipt. Nothing here imports a scorer, opens a label file or computes a metric.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
from pathlib import Path

import torch

from . import (
    forecast_temporal_mean,
    forecast_temporal_mean_train,
    forecast_temporal_predict,
    forecast_temporal_train,
    forecast_train,
)

FROZEN_MODULES = dict(forecast_temporal_predict.FROZEN_MODULES,
                      mean_source_sha256=forecast_temporal_mean, mean_adapter_sha256=forecast_temporal_mean_train)


def frozen_module_hashes(receipt):
    actual = {field: forecast_train.sha256(Path(module.__file__)) for field, module in FROZEN_MODULES.items()}
    for field, digest in actual.items():
        if receipt.get(field) != digest:
            raise ValueError(f"Frozen module differs from the checkpoint's fit receipt: {field}")
    return actual


def predict(checkpoint_path: Path, manifest_path: Path, out: Path, *, input_gate, expected_checkpoint_sha256,
            graph_dirs=(), device_name=None):
    pyg_version = forecast_temporal_train.check_pyg_version()
    checkpoint_path, manifest_path, out = Path(checkpoint_path), Path(manifest_path), Path(out)
    raw = checkpoint_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_checkpoint_sha256:
        raise ValueError("Checkpoint differs from its external hash anchor")
    checkpoint = torch.load(io.BytesIO(raw), map_location="cpu", weights_only=False)
    receipt = checkpoint["receipt"]
    modules = frozen_module_hashes(receipt)
    if (receipt.get("temporal_pyg_version") != pyg_version
            or receipt.get("temporal_pyg_api_sha256") != forecast_temporal_train.PYG_API_SHA256):
        raise ValueError("Installed PyG differs from the version this checkpoint was fitted with")
    if receipt.get("test_inputs_opened") is not False or receipt.get("threshold_calibration_split") != "validation":
        raise ValueError("Checkpoint violated the validation-only fit protocol")
    if checkpoint["settings"].get("kind") != forecast_temporal_mean_train.KIND or checkpoint["history"] != "on":
        raise ValueError("Only primary-history Mean TGN checkpoints are supported")
    manifest = json.loads(manifest_path.read_text())
    forecast_train.validate_manifest(manifest)
    if manifest.get("protected_test", False) or manifest.get("locked_test", False):
        raise ValueError("Protected tests require the custodian workflow")
    if receipt["manifest_sha256"] != forecast_train.sha256(manifest_path):
        raise ValueError("Checkpoint was fitted on another manifest")
    if checkpoint["history_feature_indices"] != manifest["history_feature_indices"]:
        raise ValueError("Checkpoint/manifest history features differ")
    if receipt.get("feature_contract") != manifest.get("feature_contract"):
        raise ValueError("Checkpoint/manifest feature contracts differ")
    expected_hashes, gate_digest = forecast_train.input_gate_hashes(input_gate, manifest_path, manifest)
    if gate_digest is None or gate_digest != receipt["input_gate_sha256"]:
        raise ValueError("Prediction input gate differs from the fit's gate")
    # Frozen projection first: label fields are removed here, before any model exists.
    events, inputs = forecast_train.load_partition(manifest_path, manifest, "test", list(graph_dirs), prediction=True,
                                                   allow_label_containers=True, expected_hashes=expected_hashes)
    forecast_temporal_predict.attach_messages(events, inputs)
    forecast_train.reserve_output(out)
    forecast_train.transform_events(events, checkpoint["history_feature_indices"], checkpoint["history"],
                                    checkpoint["mu"], checkpoint["sd"])
    torch.use_deterministic_algorithms(True)
    device = torch.device(device_name or ("cuda" if torch.cuda.is_available() else "cpu"))
    model = forecast_temporal_mean_train.make_model(**checkpoint["settings"]).to(device)
    model.load_state_dict(checkpoint["state_dict"], strict=True)
    rows = forecast_train.prediction_rows(model, events, device, checkpoint["threshold"],
                                          forward=forecast_temporal_train.temporal_forward)
    forecast_train.write_json(out / "predictions.json", rows)
    commitment = {"created_utc": dt.datetime.now(dt.UTC).isoformat(),
                  "split": "test", "manifest_sha256": forecast_train.sha256(manifest_path),
                  "input_gate_sha256": gate_digest, "checkpoint_sha256": expected_checkpoint_sha256,
                  "fit_receipt_checkpoint_fields": {"kind": checkpoint["settings"]["kind"],
                                                    "temporal_configuration_id": receipt.get("temporal_configuration_id"),
                                                    "seed": receipt["seed"], "threshold": checkpoint["threshold"]},
                  "predictions_sha256": forecast_train.sha256(out / "predictions.json"), "inputs": inputs,
                  "event_ids": [r["event_id"] for r in rows], "test_labels_used": False,
                  "label_free_input_files": False, "label_fields_projected_before_inference": True,
                  "scores_computed": False, "prediction_source_sha256": forecast_train.sha256(Path(__file__)),
                  "frozen_module_sha256": modules, "temporal_pyg_version": pyg_version,
                  "deterministic_algorithms": True, "device": str(device),
                  "hardware": torch.cuda.get_device_name(device) if device.type == "cuda" else "CPU",
                  "torch_version": str(torch.__version__)}
    forecast_train.write_json(out / "commitment.json", commitment)
    return commitment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", dest="checkpoint_path", type=Path, required=True)
    parser.add_argument("--expected-checkpoint-sha256", required=True)
    parser.add_argument("--manifest", dest="manifest_path", type=Path, required=True)
    parser.add_argument("--input-gate", type=Path, required=True)
    parser.add_argument("--graphs", dest="graph_dirs", type=Path, action="append", default=[])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--device", dest="device_name")
    commitment = predict(**vars(parser.parse_args()))
    print(json.dumps({k: commitment[k] for k in ("predictions_sha256", "checkpoint_sha256", "manifest_sha256")}))


if __name__ == "__main__":
    main()
