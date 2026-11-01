"""H1 prediction-only commitments: selected-K finals and the frozen original-model OOD diagnostic.

Pure checks and record builders for ``scripts/forecast_h1_commitments.py``. Nothing here fits,
calibrates, selects K, scores or reads a label. The only model code path is
``validation_predict``: the frozen ``forecast_train.predict`` steps with the split bound to
``validation`` (the frozen predictor is test-only), using the snapshot's own loader,
projection, normalisation, model and ``prediction_rows`` with the checkpoint's threshold.
"""
import hashlib
import json
from pathlib import Path

KS = (100, 500, 1000)
HORIZONS = (30, 60)
SEEDS = (0, 1, 2, 3, 4)
ARMS = (("sage", "on"), ("none", "on"))
CONFIGURATION = 3
FINALS_PHASE = "h1-retrospective-finals"
SELECTION_PHASE = "h1-k-selection"
# One ledger kind per exact scope; each needs its own independent approval.
KINDS = {
    "selected-k-test": {"scope": "h1-selected-k-retrospective-test-commitments-v1", "split": "test",
                        "expected": len(ARMS) * len(HORIZONS) * len(SEEDS)},
    "ood-test": {"scope": "h1-frozen-original-ood-test-commitments-v1", "split": "test",
                 "expected": len(ARMS) * len(HORIZONS) * len(SEEDS) * len(KS)},
    "ood-validation": {"scope": "h1-frozen-original-ood-validation-predictions-v1", "split": "validation",
                       "expected": len(ARMS) * len(HORIZONS) * len(SEEDS) * len(KS)},
}
HC2 = ("not applied: reserved/private ASNs stay in inputs, candidates and predictions; the HC2 sensitivity "
       "filters candidates and targets only in a separately labelled descriptive evaluation of every arm incl. K=0")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def file_sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024**2), b""):
            digest.update(block)
    return digest.hexdigest()


def bound_json(path, expected, what="Bound evidence"):
    raw = Path(path).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected, f"{what} changed: {path}")
    return json.loads(raw)


def ids_sha256(ids):
    return hashlib.sha256(json.dumps(sorted(ids), separators=(",", ":")).encode()).hexdigest()


def population(gate_manifest, manifest_doc, split, expected_count):
    """Exact IDs and gated input hashes of one split of one gated manifest."""
    ids = [r["event_id"] for r in manifest_doc["events"] if r["split"] == split]
    require(len(ids) == len(set(ids)), f"Duplicate {split} event ID in {gate_manifest['path']}")
    require(len(ids) == expected_count == gate_manifest["split_counts"][split],
            f"{split} population of {gate_manifest['path']} is not the declared {expected_count}")
    hashes = {}
    for row in gate_manifest["inputs"]:
        require(row["event_id"] not in hashes, f"Duplicate gated input: {row['event_id']}")
        hashes[row["event_id"]] = row["sha256"]
    require(set(ids) <= set(hashes), f"Gate lacks {split} inputs of {gate_manifest['path']}")
    return {"event_ids": sorted(ids), "event_ids_sha256": ids_sha256(ids),
            "inputs": {eid: hashes[eid] for eid in sorted(ids)}}


def check_h1_marker(marker, spec, core_gate_sha256, snapshot_sha256):
    """The reviewed H1 marker attests exactly the bound gates, snapshot and driver; it authorizes no scoring."""
    require(marker.get("passed") is True and marker.get("test_scoring_authorized") is False
            and marker.get("new_period_fits_authorized_by_this_marker") is False, "H1 marker authorizes too much")
    require(marker.get("integration_gate_sha256") == core_gate_sha256, "H1 marker names another primary gate")
    require(marker.get("code_snapshot_sha256") == snapshot_sha256, "H1 marker names another code snapshot")
    require(marker.get("driver_sha256") == spec["h1_driver"]["sha256"], "H1 marker names another H1 driver")
    for k in KS:
        gate = spec["k_gates"][str(k)]
        require(marker["k_integration_gate_sha256"].get(str(k)) == gate["sha256"]
                and Path(marker["k_integration_gate_paths"].get(str(k), "")) == Path(gate["path"]),
                f"K={k} gate path or hash differs from the H1 marker")
        require(marker["k_history_binding_sha256"].get(str(k)) == gate["history_binding_sha256"],
                f"K={k} history binding differs from the H1 marker")


def check_driver_constants(h1d):
    """Constants shared with the frozen H1 driver must agree; this module never redefines the design."""
    require(tuple(h1d.KS) == KS and tuple(map(tuple, h1d.ARMS)) == ARMS and tuple(h1d.FINAL_SEEDS) == SEEDS
            and tuple(h1d.FINAL_HORIZONS) == HORIZONS and h1d.FINALS_PHASE == FINALS_PHASE
            and h1d.PHASE == SELECTION_PHASE, "Frozen H1 driver constants differ from this orchestration")


def check_selection(record, marker_sha256, marker, h1_driver_sha256):
    """The selection record decides K; nothing here does. Returns the selected K."""
    k = record.get("selected_k")
    require(type(k) is int and k in KS, "Selection record names no valid nonzero K")
    require(record.get("test_outcomes_used") is False and record.get("frozen_model_diagnostic_used") is False,
            "Selection used test outcomes or the frozen-model diagnostic")
    require(record.get("selection_rule") == marker["k_selection_rule"], "Selection used another rule than the marker")
    require(record.get("implementation_review_sha256") == marker_sha256, "Selection was made under another marker")
    require(record.get("driver_sha256") == h1_driver_sha256, "Selection was written by another H1 driver")
    require(sorted(map(int, record["ledgers"])) == list(KS), "Selection did not bind all three K ledgers")
    return k


def run_key(run):
    return (run["message_passing"], run["history"], run["horizon_seconds"], run["seed"])


def declared_runs(runs, *, k=None):
    """Exactly one configuration-3 history-on run per arm, horizon and seed; decoys ignored, gaps refused."""
    wanted = {(mp, hist, d, s) for mp, hist in ARMS for d in HORIZONS for s in SEEDS}
    chosen = {}
    for run in runs:
        key = run_key(run)
        if run.get("configuration_id") != CONFIGURATION or key not in wanted:
            continue
        require(k is None or run.get("candidate_history_k") == k, f"Run {run['run_id']} has another K")
        require(key not in chosen, f"Duplicate frozen fit: {key}")
        chosen[key] = run
    missing = sorted(wanted - set(chosen))
    require(not missing, f"Missing declared frozen fits: {missing}")
    return [chosen[key] for key in sorted(chosen)]


def check_finals_ledger(finals, selection_sha256, k, marker_path, marker_sha256, k_gate, snapshot_sha256):
    require(finals.get("phase") == FINALS_PHASE and finals.get("candidate_history_k") == k,
            "Finals ledger is not the H1 retrospective finals at the selected K")
    require((finals.get("selection") or {}).get("sha256") == selection_sha256
            and finals["selection"].get("selected_k") == k, "Finals ledger binds another selection")
    require(Path(finals["implementation_review_path"]) == Path(marker_path)
            and finals["implementation_review_sha256"] == marker_sha256, "Finals ledger names another marker")
    require(Path(finals["gate_path"]) == Path(k_gate["path"]) and finals["gate_sha256"] == k_gate["sha256"],
            "Finals ledger trained on another K gate")
    require(finals.get("snapshot_sha256") == snapshot_sha256 and finals.get("selected_configuration") == CONFIGURATION,
            "Finals ledger names another snapshot or configuration")
    require(len(finals["runs"]) == 18 and len(finals.get("reused_runs", [])) == 2,
            "Finals ledger must hold 18 new and 2 reused fits")
    return declared_runs(finals["runs"] + finals["reused_runs"], k=k)


def check_frozen_output(commitment, entry, population_doc, predictions_sha256, split):
    """Metadata-only verification of a frozen predict (test) or the validation adapter output."""
    for key in ("manifest_sha256", "checkpoint_sha256", "input_gate_sha256", "prediction_source_sha256"):
        require(commitment.get(key) == entry[key], f"Prediction {key} differs")
    require(commitment.get("predictions_sha256") == predictions_sha256, "Prediction bytes changed")
    if split == "test":
        require(commitment.get("test_labels_used") is False, "Unexpected test prediction provenance")
    else:
        require(commitment.get("prediction_split") == "validation" and commitment.get("labels_used") is False
                and commitment.get("test_inputs_opened") is False
                and commitment.get("adapter_sha256") == entry["adapter_sha256"],
                "Unexpected validation prediction provenance")
    ids = commitment["event_ids"]
    require(len(ids) == len(set(ids)), "Duplicate predicted event ID")
    require(sorted(ids) == population_doc["event_ids"], f"Predictions must cover all and only the {split} IDs")
    seen = {}
    for row in commitment["inputs"]:
        require(row["event_id"] not in seen, f"Duplicate prediction input: {row['event_id']}")
        seen[row["event_id"]] = row["sha256"]
    require(seen == population_doc["inputs"], "Prediction input bytes differ from the gated inputs")


def h1_commitment(entry, population_doc, *, frozen_commitment_sha256, predictions_sha256, attempt):
    keep = ("kind", "scope", "name", "split", "candidate_history_k", "horizon_seconds", "run_id", "message_passing",
            "history", "seed", "checkpoint_sha256", "snapshot_sha256", "prediction_source_sha256", "manifest_sha256",
            "input_gate_sha256", "history_binding_sha256", "source_audit_sha256", "primary_gate_sha256",
            "primary_marker_sha256", "h1_marker_sha256", "selection_sha256", "finals_ledger_sha256",
            "core_ledger_sha256", "adapter_sha256", "population")
    return {**{k: entry[k] for k in keep if k in entry}, "attempt": attempt,
            "event_ids_sha256": population_doc["event_ids_sha256"], "events": len(population_doc["event_ids"]),
            "frozen_commitment_sha256": frozen_commitment_sha256, "predictions_sha256": predictions_sha256,
            "labels_used": False, "hc2_reserved_filter": HC2, "test_scoring_authorized": False,
            "r1_release_authorized": False, "k_selection_input": False}


def validation_predict(ft, checkpoint_path, manifest_path, input_gate, out, device_name, adapter_sha256):
    """``forecast_train.predict`` with the split bound to validation; no training, no calibration.

    ``ft`` is the frozen snapshot's ``bgbench.forecast_train``. Rows are projected to INPUT_KEYS by the
    frozen loader before inference; the checkpoint's own mu/sd, history setting and threshold are used.
    """
    import datetime as dt

    import torch
    manifest_path, out = Path(manifest_path), Path(out)
    manifest = json.loads(manifest_path.read_text())
    ft.validate_manifest(manifest)
    require(not manifest.get("protected_test") and not manifest.get("locked_test"),
            "Validation adapter is for retrospective manifests only")
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    require(checkpoint["history_feature_indices"] == manifest["history_feature_indices"],
            "Checkpoint/manifest history features differ")
    require(checkpoint["receipt"].get("feature_contract") == manifest.get("feature_contract"),
            "Checkpoint/manifest feature contracts differ")
    require(input_gate is not None, "Validation adapter requires the input gate")
    expected_hashes, gate_digest = ft.input_gate_hashes(input_gate, manifest_path, manifest)
    events, inputs = ft.load_partition(manifest_path, manifest, "validation", [], prediction=True,
                                       allow_label_containers=True, expected_hashes=expected_hashes)
    ft.reserve_output(out)
    ft.transform_events(events, checkpoint["history_feature_indices"], checkpoint["history"], checkpoint["mu"],
                        checkpoint["sd"])
    device = torch.device(device_name)
    model = ft.MatchedSAGE(**checkpoint["settings"]).to(device)
    model.load_state_dict(checkpoint["state_dict"])
    rows = ft.prediction_rows(model, events, device, checkpoint["threshold"])
    ft.write_json(out / "predictions.json", rows)
    commitment = {"created_utc": dt.datetime.now(dt.UTC).isoformat(), "prediction_split": "validation",
                  "manifest_sha256": ft.sha256(manifest_path), "input_gate_sha256": gate_digest,
                  "checkpoint_sha256": ft.sha256(Path(checkpoint_path)),
                  "predictions_sha256": ft.sha256(out / "predictions.json"), "inputs": inputs,
                  "event_ids": [r["event_id"] for r in rows], "labels_used": False, "test_inputs_opened": False,
                  "threshold": checkpoint["threshold"], "prediction_source_sha256": ft.sha256(Path(ft.__file__)),
                  "adapter_sha256": adapter_sha256}
    ft.write_json(out / "commitment.json", commitment)
    return commitment
