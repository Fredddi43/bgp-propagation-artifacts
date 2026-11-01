"""Mean aggregation sensitivity fit adapter; the frozen primary temporal adapter is untouched.

Fits ``forecast_temporal_mean.EventMeanTGN`` through the unchanged ``forecast_train.fit`` hooks:
same input hash gate, train-only normalization, losses, optimizer, validation epoch selection and
threshold calibration as the Last TGN. Hyperparameters are not chosen here. The only configuration
accepted is the selected Last TGN configuration named by the unchanged tuning selector's output,
which is bound by an external hash; there is no default, no width/learning-rate flag and no retry.
A nonfinite objective writes a terminal numerical-failure receipt, exactly as the primary adapter.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import torch

from . import forecast_temporal, forecast_temporal_mean, forecast_temporal_train, forecast_train

KIND = "mean_tgn"
# The frozen grid's fixed TGN fields (TEMPORAL-MODELS.md); Mean gets no separate grid.
FIXED = {"dropout": .2, "memory_dim": 64, "time_dim": 16, "neighbors": 10, "curve_weight": 1., "pos_weight_cap": 20.}
EPOCHS = 20
NUMERICAL_REASONS = ("Nonfinite training objective", "Nonfinite validation objective")


def make_model(*, kind, in_dim, hidden, dropout, max_nodes, memory_dim, time_dim, neighbors):
    if kind != KIND:
        raise ValueError("The Mean adapter builds only the current-tick Mean TGN")
    return forecast_temporal_mean.EventMeanTGN(in_dim, max_nodes, hidden=hidden, memory_dim=memory_dim,
                                               time_dim=time_dim, neighbors=neighbors, dropout=dropout)


def selected_last_configuration(selection_path, expected_sha256):
    """The Last TGN configuration from the selector's output; a failed or unresolved Last arm has none."""
    raw = Path(selection_path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("Last selection differs from its external hash anchor")
    selection = json.loads(raw)
    if selection.get("all_configurations_resolved") is not True or selection.get("test_inputs_opened") is not False:
        raise ValueError("Last selection is unresolved")
    chosen = selection["selected"]["tgn"]
    if chosen.get("status") != "completed" or chosen.get("configuration_id") not in forecast_temporal_train.CONFIGURATIONS:
        raise ValueError("Mean is not executable: Last TGN has no finite selected configuration")
    return chosen["configuration_id"]


def fit(manifest_path, graph_dirs, out, *, input_audit, input_gate, last_selection, last_selection_sha256,
        configuration_id, seed, epochs=EPOCHS, device_name=None):
    pyg_version = forecast_temporal_train.check_pyg_version()
    manifest_path, out = Path(manifest_path), Path(out)
    if selected_last_configuration(last_selection, last_selection_sha256) != configuration_id:
        raise ValueError("Mean must use exactly the selected Last TGN configuration")
    settings = forecast_temporal_train.CONFIGURATIONS[configuration_id]
    manifest = json.loads(manifest_path.read_text())
    forecast_train.validate_manifest(manifest)
    if input_gate is None or input_audit is None:
        raise ValueError("Mean fits require the reviewed input gate and temporal input audit")
    if seed not in range(5):
        raise ValueError("Mean seeds are frozen to 0 through 4")
    if manifest.get("schema_version", 0) >= 1 and epochs != EPOCHS:
        raise ValueError("Production Mean fits use the frozen 20 epochs")
    audit = json.loads(Path(input_audit).read_text())
    if audit.get("passed") is not True or audit["manifest_sha256"] != forecast_train.sha256(manifest_path):
        raise ValueError("Temporal input audit does not bind this manifest")
    torch.use_deterministic_algorithms(True)
    model = {"kind": KIND, "hidden": settings["hidden"], "dropout": FIXED["dropout"],
             "max_nodes": audit["capacity_max_train_validation_nodes"],
             **{k: FIXED[k] for k in ("memory_dim", "time_dim", "neighbors")}}
    evidence = {"temporal_source_sha256": forecast_train.sha256(Path(forecast_temporal.__file__)),
                "temporal_adapter_sha256": forecast_train.sha256(Path(forecast_temporal_train.__file__)),
                "mean_source_sha256": forecast_train.sha256(Path(forecast_temporal_mean.__file__)),
                "mean_adapter_sha256": forecast_train.sha256(Path(__file__)),
                "temporal_configuration_id": configuration_id,
                "mean_configuration_source": "selected Last TGN configuration; no Mean tuning",
                "last_selection_sha256": last_selection_sha256,
                "temporal_pyg_version": pyg_version,
                "temporal_pyg_api_sha256": forecast_temporal_train.PYG_API_SHA256,
                "temporal_input_audit_sha256": forecast_train.sha256(Path(input_audit)),
                "temporal_deterministic_algorithms": True,
                "temporal_determinism_scope": "strict algorithms; Mean mechanics receipts bound by the driver",
                "temporal_objective": "shared supervised membership and extent; not original link prediction",
                "mean_aggregation": "reference PyG MeanAggregator; current tick only; original multiplicity",
                "temporal_memory_scope": "reset every event; shared matured history enters both readouts"}
    try:
        return forecast_train.fit(manifest_path, graph_dirs, out, seed=seed, epochs=epochs, lr=settings["lr"],
                                  curve_weight=FIXED["curve_weight"], pos_weight_cap=FIXED["pos_weight_cap"],
                                  device_name=device_name, input_gate=input_gate, history="on",
                                  model_factory=make_model, model_config=model,
                                  forward=forecast_temporal_train.temporal_forward, extra_receipt=evidence)
    except ValueError as error:
        if str(error) not in NUMERICAL_REASONS:
            raise
        failure = dict(evidence, status="numerical_failure", reason=str(error), seed=seed, model=model,
                       lr=settings["lr"], epochs=epochs, test_inputs_opened=False,
                       source_sha256=forecast_train.sha256(Path(forecast_train.__file__)),
                       manifest_sha256=forecast_train.sha256(manifest_path),
                       input_gate_sha256=forecast_train.sha256(Path(input_gate)))
        out.mkdir(parents=True, exist_ok=True)
        with (out / "numerical_failure.json").open("x") as handle:
            json.dump(failure, handle, indent=2, allow_nan=False)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", dest="manifest_path", type=Path, required=True)
    parser.add_argument("--graphs", dest="graph_dirs", type=Path, action="append", default=[])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--input-audit", type=Path, required=True)
    parser.add_argument("--input-gate", type=Path, required=True)
    parser.add_argument("--last-selection", type=Path, required=True)
    parser.add_argument("--last-selection-sha256", required=True)
    parser.add_argument("--configuration-id", type=int, choices=tuple(forecast_temporal_train.CONFIGURATIONS),
                        required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--epochs", type=int, required=True)
    parser.add_argument("--device", dest="device_name")
    receipt = fit(**vars(parser.parse_args()))
    print(json.dumps({k: receipt[k] for k in ("model", "selected_epoch", "threshold", "trainable_parameters")}))


if __name__ == "__main__":
    main()
