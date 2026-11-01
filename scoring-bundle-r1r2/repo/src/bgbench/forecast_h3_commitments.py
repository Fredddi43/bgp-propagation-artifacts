"""H3 frozen-model sensitivity: label-free panel metadata, input gate and commitment checks.

Everything here reads only label-free documents: the panel input-status ledgers,
the hash-bound coverage extracts, build/assembly/CB1/CB2 receipts, forecast
contracts, history-source lists and file hashes. It never opens
``membership-report.json`` or ``index.csv`` (label-bearing) and never
deserializes a tensor; tensors are only hashed.

The frozen predictor (``forecast_train.predict``) later loads the panel test
tensors with ``--allow-label-containers`` and keeps only ``INPUT_KEYS``; that
runtime projection is outside this module and needs explicit review.
"""
import hashlib
import json
from pathlib import Path

from .forecast_panel import align_panel_predictions

PANELS = {
    "ris7": ("rrc00", "rrc01", "rrc03", "rrc12", "rrc15", "rrc20", "rrc25"),
    "mixed7": ("route-views.linx", "route-views2", "route-views3", "rrc00", "rrc03", "rrc12", "rrc25"),
}
REFERENCE = ("route-views.linx", "route-views2", "route-views3", "rrc00", "rrc01", "rrc03",
             "rrc12", "rrc15", "rrc20", "rrc25")
HORIZONS = (30, 60)
CUTOFF_RULE = "availability_v1_whole_second_plus_1s"
CB2_SAMPLE = {"sample_size": 100, "sample_seed": 20261018}
FEATURE_DIMS = [11]
LABEL_BEARING = frozenset(("membership-report.json", "index.csv"))
ABSTENTION = "empty_set_zero_count"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def file_sha(path):
    path = Path(path)
    require(path.name not in LABEL_BEARING, f"Label-bearing file must not be read: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024**2), b""):
            digest.update(block)
    return digest.hexdigest()


def bound_json(path, expected):
    path = Path(path)
    require(path.name not in LABEL_BEARING, f"Label-bearing file must not be read: {path}")
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected, f"Changed evidence: {path}")
    return json.loads(raw)


def population_sha256(ids):
    return hashlib.sha256(json.dumps(sorted(ids), separators=(",", ":")).encode()).hexdigest()


def self_digest(doc):
    payload = {k: v for k, v in doc.items() if k != "manifest_sha256"}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def status_counts(ledger):
    counts = {"available": 0, "unavailable_no_input": 0, "source_failure": 0}
    for row in ledger["events"]:
        require(row["status"] in counts, f"Unknown input status: {row['event_id']}: {row['status']}")
        counts[row["status"]] += 1
    return counts


def _file_sources(history):
    return [s for s in history["sources"] if "path" in s], [s for s in history["sources"] if "path" not in s]


def check_build(panel, horizon, docs, hashes, *, original_manifest_sha256, reference_build_sha256,
                reference_history, verifier_sha256, graph_dir):
    """Cross-bind one panel/horizon build's label-free receipts; return its declared counts.

    ``docs``/``hashes`` hold ledger, build, assembly, contract, history, coverage, cb1, cb2.
    """
    require(panel in PANELS and horizon in HORIZONS, "Undeclared panel or horizon")
    collectors = list(PANELS[panel])
    ledger, build, assembly = docs["ledger"], docs["build"], docs["assembly"]
    contract, history, coverage, cb1, cb2 = (docs[k] for k in ("contract", "history", "coverage", "cb1", "cb2"))
    require(ledger.get("panel") == panel and ledger.get("delta_s") == horizon, "Ledger panel/horizon differs")
    require(ledger.get("input_collectors") == collectors and ledger.get("reference_collectors") == list(REFERENCE),
            "Ledger collectors differ from the declared panel")
    require(ledger.get("contains_labels") is False, "Input-status ledger must be label-free")
    counts = status_counts(ledger)
    require(ledger.get("event_status_counts") == counts, "Ledger status counts are inconsistent")
    for name, doc in (("build", build), ("assembly", assembly)):
        require(doc.get("passed") is True and doc.get("training_authorized") is False,
                f"{name} receipt did not pass or authorizes training")
        require(doc.get("panel") == panel and doc.get("manifest_file_sha256") == original_manifest_sha256,
                f"{name} receipt binds another panel or manifest")
        require(doc.get("input_status_counts") == counts and doc.get("event_count") == counts["available"],
                f"{name} receipt counts differ from the input-status ledger")
    require(build.get("delta_s") == horizon and build.get("input_cutoff_rule") == CUTOFF_RULE, "Build rule differs")
    require(build["assembly"]["sha256"] == hashes["assembly"], "Build receipt binds another assembly")
    require(build["reference_build_verification"]["sha256"] == reference_build_sha256,
            "Build receipt binds another reference build")
    require(assembly.get("manifest_ids_exact") is True, "Assembly did not cover the exact manifest")
    require(contract.get("manifest_sha256") == original_manifest_sha256, "Contract binds another manifest")
    require(contract.get("input_collectors") == collectors and contract.get("reference_collectors") == list(REFERENCE),
            "Contract collectors differ")
    require(contract.get("history_mode") == "shared_completed"
            and contract.get("history_target_scope") == "fixed_reference_collectors",
            "History targets must stay on the fixed reference panel")
    require(contract.get("delta_s") == horizon and contract.get("input_cutoff_rule") == CUTOFF_RULE,
            "Contract horizon/cutoff differs")
    # The panel signature changes the library digest; the completed-event library itself is shared.
    require(history.get("source_digest") == contract.get("history_source_digest"), "History digest differs from contract")
    require(_file_sources(history) == _file_sources(reference_history),
            "Panel history library differs from the reference library sources")
    require(coverage.get("kind") == "h3_panel_coverage_extract" and coverage.get("panel_name") == panel
            and coverage.get("panel") == collectors and coverage.get("delta_s") == horizon
            and coverage["manifest"]["sha256"] == original_manifest_sha256, "Coverage extract binds another build")
    require({e["event_id"] for e in ledger["events"]} == set(coverage["events"]), "Coverage extract IDs differ")
    for name, doc in (("CB1", cb1), ("CB2", cb2)):
        require(doc.get("passed") is True and doc.get("training_authorized") is False
                and doc.get("events_failed") == 0 and doc.get("failures") == [],
                f"{name} receipt did not pass cleanly")
        require(doc.get("verifier_sha256") == verifier_sha256[name], f"{name} verifier differs from the committed source")
        require(doc.get("available_events") == counts["available"], f"{name} available count differs")
        require(Path(doc["panel_graphs"]) == Path(graph_dir), f"{name} checked another graph directory")
        require(doc["bound_inputs"]["panel_ledger"]["sha256"] == hashes["ledger"]
                and doc["bound_inputs"]["panel_build_verification"]["sha256"] == hashes["build"],
                f"{name} binds another ledger or build")
    require(cb1["bound_inputs"]["reference_build_verification"]["sha256"] == reference_build_sha256,
            "CB1 compared another reference build")
    require(cb1.get("events_checked") == counts["available"] and cb1.get("tensors_on_disk_equal_available") is True,
            "CB1 did not check every available tensor")
    require(cb1.get("feature_dims") == FEATURE_DIMS, "Panel tensors do not carry the frozen 11 features")
    require(cb2.get("panel") == panel and cb2.get("delta_s") == horizon
            and all(cb2.get(k) == v for k, v in CB2_SAMPLE.items())
            and len(set(cb2.get("sampled_event_ids", []))) == CB2_SAMPLE["sample_size"], "CB2 sample differs")
    return {"counts": counts, "cb2_ambiguous_decodes": cb2.get("nmsg_ambiguous_decodes"),
            "check_cpu": {"cb1": cb1.get("host_cpu_model"), "cb2": cb2.get("host_cpu_model")}}


def translate_availability(ledger, coverage, panel, test_ids, *, ledger_sha256, coverage_sha256):
    """Map builder statuses to the ``forecast_panel`` adapter without reclassifying failures.

    available -> available (window complete only when no panel collector is missing);
    unavailable_no_input -> no_input only when every panel collector is certified empty
    by both the ledger and the bound coverage extract; source_failure fails closed.
    """
    collectors, rows = PANELS[panel], {}
    for row in ledger["events"]:
        require(row["event_id"] not in rows, f"Duplicate ledger event: {row['event_id']}")
        rows[row["event_id"]] = row
    certifying = set(coverage["certifying_day_statuses"])
    out = []
    for eid in test_ids:
        row = rows[eid]
        require(row["input_collectors"] == list(collectors) and set(row["collectors"]) == set(REFERENCE),
                f"Ledger row collectors differ: {eid}")
        states = {c: row["collectors"][c]["status"] for c in REFERENCE}
        require(all(states[c] == "not_in_panel" for c in REFERENCE if c not in collectors)
                and all(states[c] in ("observed", "empty", "missing") for c in collectors),
                f"Unexpected collector status: {eid}")
        missing = sorted(c for c in collectors if states[c] == "missing")
        seeds = row["input_seed_asns"]
        status = row["status"]
        if status == "source_failure":
            raise ValueError(f"source_failure has no reviewed H3 rule; refusing: {eid}")
        if status == "available":
            require(seeds and row["forecast_available"] is True and row["abstention_policy"] is None
                    and any(states[c] == "observed" for c in collectors)
                    and row["partial_panel_input"] is bool(missing), f"Inconsistent available row: {eid}")
            adapter, complete = "available", not missing
        elif status == "unavailable_no_input":
            evidence = coverage["events"][eid]
            require(seeds == [] and row["forecast_available"] is False and row["abstention_policy"] == ABSTENTION
                    and row["partial_panel_input"] is False and all(states[c] == "empty" for c in collectors),
                    f"No-input row lacks certified empty panel collectors: {eid}")
            require(not set(evidence["missing_retained_part_collectors"]) & set(collectors)
                    and all(evidence["day_evidence"].get(c) and set(evidence["day_evidence"][c]) <= certifying
                            for c in collectors), f"No-input row lacks certifying issue-window evidence: {eid}")
            adapter, complete = "no_input", True
        else:
            raise ValueError(f"Unknown input status: {eid}: {status}")
        out.append({"event_id": eid, "status": adapter, "input_window_complete": complete,
                    # Build/assembly receipts passed for every manifest event (checked before translation).
                    "parse_status": "ok", "input_seed_asns": list(seeds),
                    "coverage_audit_sha256": coverage_sha256, "ledger_status": status,
                    "partial_panel_input": bool(missing), "panel_missing_collectors": missing,
                    "input_status_ledger_sha256": ledger_sha256})
    return out


def panel_manifest(original, original_sha256, ledger, ledger_sha256, panel, graph_dir, tensor_hashes):
    """Panel-only eligible manifest: the original rows of available events, all three splits.

    Tensors carry the ORIGINAL v6 manifest digest, so ``source_manifest_sha256`` is that file hash.
    """
    require("source_manifest_sha256" not in original, "Original manifest is already derived")
    require(not original.get("locked_test") and not original.get("protected_test")
            and not original.get("manifest_kind"), "Only retrospective manifests are supported")
    statuses = {}
    for row in ledger["events"]:
        require(row["event_id"] not in statuses, f"Duplicate ledger event: {row['event_id']}")
        statuses[row["event_id"]] = row["status"]
    ids = [row["event_id"] for row in original["events"]]
    require(len(ids) == len(set(ids)) and set(ids) == set(statuses), "Ledger must cover the exact manifest IDs")
    require("source_failure" not in statuses.values(), "source_failure has no reviewed H3 rule")
    available = {eid for eid, status in statuses.items() if status == "available"}
    require(set(tensor_hashes) == available, "Tensor files must cover exactly the available events")
    events, incidents = [], {}
    for row in original["events"]:
        if row["event_id"] in available:
            path = Path(graph_dir) / f"{row['event_id']}.pt"
            events.append({**row, "graph_path": str(path), "graph_sha256": tensor_hashes[row["event_id"]]})
            incidents.setdefault(row["split"], set()).add(row["incident_id"])
    counts = {split: sum(r["split"] == split for r in events) for split in ("train", "validation", "test")}
    doc = {k: v for k, v in original.items() if k not in ("events", "manifest_sha256")}
    doc.update(
        source_manifest_sha256=original_sha256, counts=counts,
        independent_incidents={split: len(incidents.get(split, ())) for split in counts},
        h3_panel_derivation={
            "panel": panel, "input_collectors": list(PANELS[panel]), "reference_collectors": list(REFERENCE),
            "input_status_ledger_sha256": ledger_sha256,
            "rule": "events with input status 'available' only; certified no-input test events are committed "
                    "abstentions outside this manifest; the reference population is unchanged",
            "source_counts": original["counts"], "source_independent_incidents": original.get("independent_incidents"),
            "reference_test_population_sha256": population_sha256(
                r["event_id"] for r in original["events"] if r["split"] == "test"),
            "abstained_by_split": {split: sum(r["split"] == split and r["event_id"] not in available
                                              for r in original["events"]) for split in counts}},
        events=events)
    doc["manifest_sha256"] = self_digest(doc)
    return doc


def check_frozen_commitment(commitment, entry, prediction_bytes_sha256):
    """Metadata-only verification of a frozen ``forecast_train.predict`` commitment."""
    for key in ("manifest_sha256", "checkpoint_sha256", "prediction_source_sha256"):
        require(commitment.get(key) == entry[key], f"Prediction {key} differs")
    require(commitment.get("input_gate_sha256") == entry["input_gate_sha256"], "Prediction gate differs")
    require(commitment.get("test_labels_used") is False and commitment.get("label_free_input_files") is False,
            "Unexpected retrospective prediction provenance")
    require(commitment.get("predictions_sha256") == prediction_bytes_sha256, "Prediction bytes changed")
    ids = commitment["event_ids"]
    require(len(ids) == len(set(ids)) and sorted(ids) == entry["forecast_event_ids"],
            "Predictions must cover all and only input-available reference IDs")
    inputs = sorted(({"event_id": r["event_id"], "sha256": r["sha256"]} for r in commitment["inputs"]),
                    key=lambda r: r["event_id"])
    require(inputs == entry["expected_inputs"], "Prediction input bytes differ from the H3 gate")


def h3_commitment(entry, availability, predictions, *, availability_sha256, frozen_commitment_sha256,
                  predictions_sha256):
    """Full-reference commitment: forecasts for available IDs, explicit abstentions for certified no-input.

    ``align_panel_predictions`` checks the structure when no partial-panel row is present. Its count is a
    placeholder: the aligned rows are not stored and no count or scoring rule is declared here.
    """
    ids = [r["event_id"] for r in availability]
    require(ids == entry["reference_event_ids"], "Availability does not cover the exact reference population")
    forecast = sorted(r["event_id"] for r in availability if r["status"] == "available")
    require(forecast == entry["forecast_event_ids"], "Available set changed after preparation")
    require(sorted(r["event_id"] for r in predictions) == forecast, "Inference failures cannot become abstentions")
    partial = sorted(r["event_id"] for r in availability if r["partial_panel_input"])
    if partial:
        alignment = {"status": "pending_reviewed_partial_panel_rule", "partial_panel_event_ids": partial,
                     "reason": "forecast_panel.align_panel_predictions requires a complete input window"}
    else:
        projected = [{"event_id": r["event_id"], "predicted_asns": r["predicted_asns"],
                      "candidate_asns": r["candidate_asns"], "predicted_count": 0.0} for r in predictions]
        align_panel_predictions(ids, availability, projected)
        alignment = {"status": "passed", "partial_panel_event_ids": []}
    return {"scope": entry["scope"], "name": entry["name"], "panel": entry["panel"],
            "horizon_seconds": entry["horizon_seconds"], "run_id": entry["run_id"],
            "reference_event_ids_sha256": population_sha256(ids), "reference_events": len(ids),
            "forecast_event_ids": forecast,
            "abstentions": [{"event_id": r["event_id"], "input_status": "no_input",
                             "ledger_status": r["ledger_status"], "abstention_policy": ABSTENTION,
                             "calibration_eligible": False}
                            for r in availability if r["status"] == "no_input"],
            "partial_panel_event_ids": partial, "alignment_adapter": alignment,
            "availability_sha256": availability_sha256, "frozen_commitment_sha256": frozen_commitment_sha256,
            "predictions_sha256": predictions_sha256, "test_labels_used": False,
            "test_scoring_authorized": False}
