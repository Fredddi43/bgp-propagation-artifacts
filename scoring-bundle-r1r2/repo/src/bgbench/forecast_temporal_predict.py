"""Label-free retrospective test predictions from frozen temporal (GRU/TGN) checkpoints; never scores.

The core predictor (``forecast_train.predict``) instantiates ``MatchedSAGE`` and its input
projection drops the temporal message stream, so it cannot run these checkpoints. This adapter
changes neither: it calls the frozen loader with the existing prediction projection
(``prediction=True``, retrospective label containers allowed), which removes every label field
before inference. It then re-reads each hash-verified tensor only to attach its causal ``msgs``
input. Normalization, model factory, forward and row construction are the frozen
``forecast_train.transform_events``, ``forecast_temporal_train.make_model``,
``forecast_temporal_train.temporal_forward`` and ``forecast_train.prediction_rows``; their
source files must be byte-identical to the hashes the checkpoint's fit receipt recorded.
Nothing here imports a scorer, opens a label file or computes a metric.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
from pathlib import Path

import torch

from . import forecast_temporal, forecast_temporal_train, forecast_train, gnn_train, graph_metrics

# Fit-receipt field -> module whose exact source bytes the checkpoint was trained with.
FROZEN_MODULES = {"temporal_source_sha256": forecast_temporal,
                  "temporal_adapter_sha256": forecast_temporal_train,
                  "source_sha256": forecast_train,
                  "gnn_source_sha256": gnn_train,
                  "graph_metrics_sha256": graph_metrics}
# The only input beyond the core prediction projection: admitted path-hop interactions through the issue time.
TEMPORAL_INPUT_KEYS = ("msgs",)


def frozen_module_hashes(receipt):
    """Every imported model/trainer module must be the byte-exact file the fit recorded."""
    actual = {field: forecast_train.sha256(Path(module.__file__)) for field, module in FROZEN_MODULES.items()}
    for field, digest in actual.items():
        if receipt.get(field) != digest:
            raise ValueError(f"Frozen module differs from the checkpoint's fit receipt: {field}")
    return actual


def attach_messages(events, inputs):
    """Add only ``msgs`` from the same verified bytes; every other container field is discarded."""
    for event, item in zip(events, inputs, strict=True):
        content = Path(item["path"]).read_bytes()
        if hashlib.sha256(content).hexdigest() != item["sha256"]:
            raise ValueError(f"Tensor changed between projection and message read: {item['event_id']}")
        container = torch.load(io.BytesIO(content), map_location="cpu", weights_only=False)
        if container["event_id"] != event["event_id"]:
            raise ValueError(f"Tensor event ID mismatch: {item['path']}")
        for key in TEMPORAL_INPUT_KEYS:
            event[key] = torch.as_tensor(container[key]).clone()
        del container
        if forecast_train.LABEL_KEYS.intersection(event):
            raise ValueError("Label field reached the temporal prediction input")
    return events


def history_input_binding(receipt, manifest_path, manifest, input_gate, parent_manifest, parent_gate):
    """Authorize only descendants of the checkpoint's exact inputs, never an arbitrary new manifest."""
    if (parent_manifest is None) != (parent_gate is None):
        raise ValueError("History inference requires both parent manifest and parent gate")
    if parent_manifest is None:
        if receipt["manifest_sha256"] != forecast_train.sha256(manifest_path):
            raise ValueError("Checkpoint was fitted on another manifest")
        return None
    parent_manifest, parent_gate = Path(parent_manifest), Path(parent_gate)
    if (forecast_train.sha256(parent_manifest) != receipt["manifest_sha256"]
            or forecast_train.sha256(parent_gate) != receipt["input_gate_sha256"]):
        raise ValueError("History parent differs from the checkpoint's fitted inputs")
    original = json.loads(parent_manifest.read_text())
    parents, _ = forecast_train.input_gate_hashes(parent_gate, parent_manifest, original)
    gate = json.loads(Path(input_gate).read_text())
    sensitivity = manifest.get("history_sensitivity", {})
    intervention = sensitivity.get("intervention")
    if (gate.get("kind") != "history_sensitivity_variant_input_gate"
            or gate.get("passed") is not True or gate.get("fit_authority") != "none"
            or gate.get("training_authorized") is not False or manifest.get("fit_authority") != "none"
            or gate.get("primary_gate_sha256") != receipt["input_gate_sha256"]
            or sensitivity.get("original_manifest_sha256") != receipt["manifest_sha256"]
            or not isinstance(intervention, dict) or gate.get("intervention") != intervention
            or intervention.get("variant") not in ("delay900", "delay1800", "withhold")):
        raise ValueError("History variant lacks its inference-only parent binding")
    variant = intervention["variant"]
    if variant in ("delay900", "delay1800"):
        expected = {"kind": "availability_delay", "variant": variant,
                    "availability_delay_s": int(variant.removeprefix("delay"))}
        if intervention != expected:
            raise ValueError("History delay differs from its declared intervention")
    else:
        ids = intervention.get("withheld_event_ids")
        policy = intervention.get("policy_sha256")
        if (intervention.get("kind") != "withhold_unavailable_source_donors"
                or set(intervention) != {"kind", "variant", "policy_sha256",
                                          "withheld_event_ids", "withheld_ids_sha256"}
                or not isinstance(ids, list) or not ids or not all(isinstance(e, str) for e in ids)
                or ids != sorted(set(ids))
                or intervention.get("withheld_ids_sha256") != hashlib.sha256("\n".join(ids).encode()).hexdigest()
                or not isinstance(policy, str) or len(policy) != 64
                or any(c not in "0123456789abcdef" for c in policy)):
            raise ValueError("History withholding lacks its exact donor and policy identity")
    # Query metadata and splits are unchanged; only the derived tensor references may differ.
    def cohort(doc):
        rows = doc["events"]
        result = {r["event_id"]: {k: v for k, v in r.items()
                                if k not in ("graph_path", "graph_sha256")} for r in rows}
        if len(result) != len(rows):
            raise ValueError("History query cohort contains duplicate events")
        return result
    if (cohort(original) != cohort(manifest) or original["delta_s"] != manifest["delta_s"]
            or original["history_feature_indices"] != manifest["history_feature_indices"]
            or original.get("feature_contract") != manifest.get("feature_contract")):
        raise ValueError("History variant changed the fitted query cohort or feature contract")
    digest = forecast_train.sha256(manifest_path)
    members = [m for m in gate["manifests"] if m["sha256"] == digest]
    if len(members) != 1 or members[0].get("original_manifest_sha256") != receipt["manifest_sha256"]:
        raise ValueError("History gate must name the unique child of the fitted manifest")
    inputs = members[0]["inputs"]
    children = {r["event_id"]: r for r in inputs}
    test_ids = {r["event_id"] for r in original["events"] if r["split"] == "test"}
    if (len(children) != len(inputs) or not test_ids <= set(children)
            or not test_ids <= set(parents)
            or any(children[e].get("parent_sha256") != parents[e]
                   or sensitivity.get("parent_tensor_sha256", {}).get(e) != parents[e] for e in test_ids)):
        raise ValueError("History tensor lineage differs from the fitted input gate")
    return {"parent_manifest_sha256": receipt["manifest_sha256"],
            "parent_gate_sha256": receipt["input_gate_sha256"], "intervention": intervention}


def predict(checkpoint_path: Path, manifest_path: Path, out: Path, *, input_gate, expected_checkpoint_sha256,
            graph_dirs=(), device_name=None, history_parent_manifest=None, history_parent_gate=None):
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
    if checkpoint["settings"].get("kind") not in ("gru", "tgn") or checkpoint["history"] != "on":
        raise ValueError("Only primary-history GRU/TGN Last checkpoints are supported")
    manifest = json.loads(manifest_path.read_text())
    forecast_train.validate_manifest(manifest)
    if manifest.get("protected_test", False) or manifest.get("locked_test", False):
        raise ValueError("Protected tests require the custodian workflow")
    history_binding = history_input_binding(receipt, manifest_path, manifest, input_gate,
                                            history_parent_manifest, history_parent_gate)
    if checkpoint["history_feature_indices"] != manifest["history_feature_indices"]:
        raise ValueError("Checkpoint/manifest history features differ")
    if receipt.get("feature_contract") != manifest.get("feature_contract"):
        raise ValueError("Checkpoint/manifest feature contracts differ")
    expected_hashes, gate_digest = forecast_train.input_gate_hashes(input_gate, manifest_path, manifest)
    if gate_digest is None or (history_binding is None and gate_digest != receipt["input_gate_sha256"]):
        raise ValueError("Prediction input gate differs from the fit's gate")
    # Frozen projection first: label fields are removed here, before any model exists.
    events, inputs = forecast_train.load_partition(manifest_path, manifest, "test", list(graph_dirs), prediction=True,
                                                   allow_label_containers=True, expected_hashes=expected_hashes)
    attach_messages(events, inputs)
    forecast_train.reserve_output(out)
    forecast_train.transform_events(events, checkpoint["history_feature_indices"], checkpoint["history"],
                                    checkpoint["mu"], checkpoint["sd"])
    torch.use_deterministic_algorithms(True)
    device = torch.device(device_name or ("cuda" if torch.cuda.is_available() else "cpu"))
    model = forecast_temporal_train.make_model(**checkpoint["settings"]).to(device)
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
    if history_binding is not None:
        commitment["history_input_binding"] = history_binding
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
    parser.add_argument("--history-parent-manifest", type=Path)
    parser.add_argument("--history-parent-gate", type=Path)
    commitment = predict(**vars(parser.parse_args()))
    print(json.dumps({k: commitment[k] for k in ("predictions_sha256", "checkpoint_sha256", "manifest_sha256")}))


if __name__ == "__main__":
    main()
