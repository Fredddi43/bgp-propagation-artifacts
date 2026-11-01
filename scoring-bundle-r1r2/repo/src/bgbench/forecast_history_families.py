"""Family adapters for the history-sensitivity commitments: parent ledgers in, frozen variant predictions out.

REVIEW-PACKET-HISTORY-COMMITMENTS.md. Pending independent review; nothing here is an execution approval.

Two halves, both reading metadata only (ledgers, completions, fit receipts, gates; never prediction values,
labels or test outcomes):

* ``normalize``: one family's existing prediction-commitment ledger -> the normalized parent ledger the
  consumer scope cross-checks (``forecast_history_variants.consumer_scope``). Cell identity, horizon, seed,
  series and terminal status come from the ledger and its completions, never from a declaration.
* ``variant_entry`` / ``predict_command`` / ``verify_output``: one parent entry re-pointed at the variant
  manifest and variant gate of the same horizon, the family's own frozen predictor command, and the family
  driver's own verification function (imported from its hash-bound bytes). The checkpoint, its stored
  normalization (``mu``/``sd``) and threshold are the parent's; nothing is fitted or recalibrated.

Families: ``core`` (neural + GBDT, forecast_retrospective_commitments), ``transfer`` (forecast_transfer_campaign),
``temporal`` (forecast_temporal_finals), ``mean`` (forecast_mean_finals), ``h3`` (forecast_h3_campaign),
``h1`` (forecast_h1_commitments) and ``baseline`` (forecast_campaign baseline phase; normalization only: variant
baselines are committed by ``forecast_history_sensitivity_campaign.py baseline``).
"""
from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import sys
from pathlib import Path

from .forecast_history_variants import PARENT_LEDGER_KIND, VariantError, require

FAMILIES = ("core", "transfer", "temporal", "mean", "h3", "h1", "baseline")
LEARNED = ("core", "transfer", "temporal", "mean", "h3", "h1")
H3_HISTORY_INDEX_KIND = "h3_history_extent_index_v1"
TEMPORAL_FAILED = ("ineligible_numerical_failure", "arm_failed_all_configurations_nonfinite")
MODULES = {"neural": "bgbench.forecast_train", "gbdt": "bgbench.forecast_baseline"}
# Which gate key each family's entries use, and where its outputs and completions live.
GATE_KEYS = {"core": ("gate_path", "gate_sha256"), "transfer": ("gate_path", "gate_sha256"),
             "temporal": ("gate_path", "gate_sha256"), "mean": ("gate_path", "gate_sha256"),
             "h3": ("input_gate", "input_gate_sha256"), "h1": ("input_gate", "input_gate_sha256")}


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024**2), b""):
            h.update(block)
    return h.hexdigest()


def bound_json(path, expected, what="evidence"):
    raw = Path(path).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected, f"Changed {what}: {path}")
    return json.loads(raw)


def ref(path):
    return {"path": str(path), "sha256": file_sha(path)}


def load_driver(name, driver, dependencies=()):
    """A family driver or helper module from its hash-bound bytes (and its hash-bound sibling imports).

    A helper inside the ``bgbench`` package (H3, H1) is imported as ``bgbench.<module>`` so its relative imports
    resolve; the imported file must then be exactly the pinned path.
    """
    for item in (*dependencies, driver):
        require(Path(item["path"]).is_file() and file_sha(item["path"]) == item["sha256"],
                f"Family driver changed: {item['path']}")
    path = Path(driver["path"]).resolve()
    if path.parent.name == "bgbench":
        module = importlib.import_module(f"bgbench.{path.stem}")
        require(Path(module.__file__).resolve() == path, f"bgbench.{path.stem} resolves to another file than {path}")
    else:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    require(file_sha(path) == driver["sha256"], f"Family driver changed while loading: {path}")
    return module


# ---- normalization ------------------------------------------------------------------------------------------------

def _completion(path, ledger_sha256, *, commitment_path=None, commitment_key="commitment_sha256"):
    """(status, commitment ref, failure ref, predictions sha) from one completion record; metadata only."""
    path = Path(path)
    if not path.is_file():
        return "incomplete", None, None, None
    done = json.loads(path.read_text())
    if done.get("ledger_sha256") not in (None, ledger_sha256):
        raise VariantError(f"{path} is bound to another ledger")
    if done.get("returncode") == 0 and done.get("predictions_sha256") and done.get(commitment_key):
        commitment = {"path": str(commitment_path), "sha256": done[commitment_key]}
        require(Path(commitment_path).is_file() and file_sha(commitment_path) == done[commitment_key],
                f"{commitment_path} differs from its completion")
        return "final", commitment, None, done["predictions_sha256"]
    return "failed", None, ref(path), None


def _history_off_proof(fit_dir, manifest):
    """Mechanical evidence from the frozen fit receipt (B-6); None for a history-on fit."""
    receipt_path = Path(fit_dir) / "fit_receipt.json"
    receipt = json.loads(receipt_path.read_text())
    if receipt.get("history") != "off":
        return None
    return {"history": "off", "zeroed_feature_indices": list(receipt.get("history_feature_indices") or []),
            "manifest_history_feature_indices": list(manifest.get("history_feature_indices") or []),
            "candidate_expansion": manifest.get("candidate_expansion"), "fit_receipt": ref(receipt_path),
            "rule": "forecast_train.transform_events zeroes x[:, history_feature_indices] when history is off, "
                    "before the stored normalization; candidates come from a manifest without candidate expansion"}


def _cell(name, horizon, seed, series, status, commitment, failure, predictions_sha256, *, model=None,
          history=None, proof=None, attributes=None):
    require(horizon in (30, 60), f"{name}: horizon must be 30 or 60")
    return {"name": name, "horizon": horizon, "seed": seed, "series": series, "status": status,
            "commitment": commitment, "failure_receipt": failure, "predictions_sha256": predictions_sha256,
            "model": model, "history": history, "history_off_proof": proof, "attributes": attributes or {}}


def normalize(family, ledger_id, ledger_path, ledger_sha256, *, seal=None):
    """The normalized parent commitment ledger of one family ledger (metadata only)."""
    require(family in FAMILIES, f"Unknown family {family!r}")
    ledger = bound_json(ledger_path, ledger_sha256, "parent ledger")
    root = Path(ledger_path).resolve().parent
    if family == "mean" and ledger.get("schema") != "temporal-mean-disposition-v1":
        seal = None
    cells = {}
    if family in ("core", "transfer"):
        fits = {}
        for e in ledger["runs"]:
            fit_path, fit_sha = ((e["fit_ledger"], e["fit_ledger_sha256"]) if family == "core"
                                 else (ledger["fit_ledger"], ledger["fit_ledger_sha256"]))
            if fit_path not in fits:
                fits[fit_path] = bound_json(fit_path, fit_sha, "parent fit ledger")
            fit = fits[fit_path]
            run_id = e["run_id"] if family == "core" else e["fit_run_id"]
            runs = [r for r in fit["runs"] + fit.get("reused_runs", []) if r["run_id"] == run_id]
            require(len(runs) == 1, f"{e['name']}: fit run missing or duplicated")
            run = runs[0]
            kind = e.get("family", "neural")
            status, commitment, failure, preds = _completion(
                root / "completions" / f"{e['name']}.json", ledger_sha256,
                commitment_path=root / "predictions" / e["name"] / "commitment.json")
            manifest = bound_json(e["manifest"], e["manifest_sha256"], "parent prediction manifest")
            history = run.get("history")
            attributes = {"model_family": kind, "message_passing": run.get("message_passing"), "history": history,
                          "configuration_id": run.get("configuration_id"),
                          **({"variant": fit.get("variant")} if family == "transfer" else {})}
            series = "/".join(str(attributes[k]) for k in sorted(attributes))
            cells[e["name"]] = _cell(e["name"], run["horizon_seconds"], run.get("seed"), series, status, commitment,
                                     failure, preds, model={"path": e["checkpoint"], "sha256": e["checkpoint_sha256"]},
                                     history=history, proof=_history_off_proof(run["out"], manifest)
                                     if history == "off" else None, attributes=attributes)
    elif family == "mean" and ledger.get("schema") == "temporal-mean-disposition-v1":
        require(seal is not None, "Mean disposition needs its hash-bound verifier driver")
        require(seal["sha256"] == ledger.get("driver_sha256"), "Mean disposition verifier differs from its producer")
        driver = load_driver("history_mean_disposition", seal)
        verified = driver.checked_disposition(ledger_path, ledger_sha256)
        require(verified == ledger, "Mean disposition verifier returned different bytes")
        require(ledger.get("executable") is False and ledger.get("runs") == []
                and ledger.get("predictions") == [] and ledger.get("prediction_count") == 0,
                "Mean disposition contains executable work")
        expected = {(h, s) for h in (30, 60) for s in range(5)}
        require(len(ledger["cells"]) == 10 and {(c["horizon_seconds"], c["seed"]) for c in ledger["cells"]} == expected,
                "Mean disposition must preserve both horizons and all five seeds")
        for c in ledger["cells"]:
            require(c["status"] == "not_executable_no_finite_last_configuration"
                    and c["last_failure_chain_sha256"] == ledger["last_failure_chain_sha256"],
                    "Mean cell differs from its terminal Last failure chain")
            cells[c["run_id"]] = _cell(c["run_id"], c["horizon_seconds"], c["seed"], "mean/not-executable",
                "failed", None, {"path": str(ledger_path), "sha256": ledger_sha256}, None, history="on",
                attributes={"kind": c["kind"], "status": c["status"],
                            "last_failure_chain_sha256": c["last_failure_chain_sha256"]})
    elif family in ("temporal", "mean"):
        entries = {e["name"]: e for e in ledger["runs"]}
        for c in ledger["cells"]:
            name = c["run_id"]
            attributes = {"kind": c["kind"], "configuration_id": c.get("configuration_id")}
            series = f"{c['kind']}/c{c.get('configuration_id')}"
            if c["status"] == "completed":
                e = entries[name]
                status, commitment, failure, preds = _completion(
                    root / "completions" / f"{name}.json", ledger_sha256,
                    commitment_path=root / "outputs" / name / "commitment.json")
                model = {"path": e["checkpoint"], "sha256": e["checkpoint_sha256"]}
            else:
                require(c["status"] in TEMPORAL_FAILED, f"{name}: unknown parent status {c['status']}")
                status, commitment, preds, model = "failed", None, None, None
                failure = {"path": str(ledger_path), "sha256": ledger_sha256}
                attributes["failure"] = {k: c.get(k) for k in ("status", "reason", "failure_sha256")}
            cells[name] = _cell(name, c["horizon_seconds"], c.get("seed"), series, status, commitment, failure, preds,
                                model=model, history="on", attributes=attributes)
    elif family == "h3":
        for e in ledger["runs"]:
            status, commitment, failure, preds = _completion(
                root / "completions" / f"{e['name']}.json", ledger_sha256,
                commitment_path=root / "commitments" / f"{e['name']}.json", commitment_key="h3_commitment_sha256")
            attributes = {"panel": e["panel"], "message_passing": e["message_passing"], "history": e["history"]}
            cells[e["name"]] = _cell(e["name"], e["horizon_seconds"], e["seed"],
                                     f"{e['panel']}/{e['message_passing']}/history-{e['history']}", status,
                                     commitment, failure, preds, model={"path": e["checkpoint"],
                                                                        "sha256": e["checkpoint_sha256"]},
                                     history=e["history"], attributes=attributes)
    elif family == "h1":
        sealed = {}
        if seal is not None:
            record = bound_json(seal["path"], seal["sha256"], "H1 seal")
            require(record.get("ledger_sha256") == ledger_sha256 and record.get("entries") == len(ledger["entries"]),
                    "H1 seal binds another ledger")
            sealed = {r["name"]: r for r in record["commitments"]}
        for e in ledger["entries"]:
            attributes = {"kind": e["kind"], "candidate_history_k": e["candidate_history_k"],
                          "message_passing": e["message_passing"], "history": e["history"], "split": e["split"]}
            row = sealed.get(e["name"])
            if row is None:
                status, commitment, preds = "incomplete", None, None
            else:
                path = root / "commitments" / f"{e['name']}.json"
                require(file_sha(path) == row["commitment_sha256"], f"{path} differs from the H1 seal")
                status, commitment, preds = "final", {"path": str(path), "sha256": row["commitment_sha256"]}, \
                    row["predictions_sha256"]
            cells[e["name"]] = _cell(e["name"], e["horizon_seconds"], e["seed"],
                                     f"{e['kind']}/k{e['candidate_history_k']}/{e['message_passing']}/history-{e['history']}",
                                     status, commitment, None, preds,
                                     model={"path": e["checkpoint"], "sha256": e["checkpoint_sha256"]},
                                     history=e["history"], attributes=attributes)
    elif family == "baseline" and ledger.get("kind") == H3_HISTORY_INDEX_KIND:
        # An H3 history-baseline policy index (one candidate protocol, 12 cells: 3 panels x 2 baselines x 2 horizons).
        # Each cell's parent commitment is the unchanged forecast_campaign.commit_baselines commitment
        # ("baseline_commitment"); its bytes and the H3 envelope are hash-checked here. Like the other baseline
        # parents, prediction bytes are bound through the commitment's predictions_sha256 and not re-hashed.
        protocol = {"matched_graph": "matched", "native_history_union": "native"}.get(ledger.get("candidate_protocol"))
        require(protocol is not None and ledger.get("test_labels_used") is False, "Unknown H3 history index protocol")
        for e in ledger["entries"]:
            parent = bound_json(e["baseline_commitment"]["path"], e["baseline_commitment"]["sha256"], "H3 baseline commitment")
            envelope = bound_json(e["commitment"]["path"], e["commitment"]["sha256"], "H3 history extent commitment")
            require(e["predictions"]["sha256"] == parent.get("predictions_sha256"),
                    f"{e['name']}: H3 baseline predictions differ from their commitment")
            require(parent.get("baseline") == e["baseline"] and parent.get("candidate_protocol") == ledger["candidate_protocol"]
                    and parent.get("input_gate_sha256") == e["gate"]["sha256"] and parent.get("manifest_sha256") == e["manifest"]["sha256"]
                    and parent.get("test_labels_used") is False
                    and envelope.get("baseline_commitment_sha256") == e["baseline_commitment"]["sha256"]
                    and envelope.get("panel") == e["panel"] and envelope.get("horizon_seconds") == e["horizon_seconds"],
                    f"{e['name']}: H3 index entry is not its own baseline commitment")
            require(e["name"] not in cells, f"{e['name']}: duplicate H3 index entry")
            attributes = {"baseline": e["baseline"], "candidate_protocol": protocol, "clock": "online", "frozen_at": None,
                          "history_arm": True, "panel": e["panel"], "reference_panel": e["panel"] == "reference"}
            cells[e["name"]] = _cell(e["name"], e["horizon_seconds"], None, f"h3/{e['panel']}/{e['baseline']}/{protocol}/online",
                                     "final", e["baseline_commitment"], None, e["predictions"]["sha256"], history="on",
                                     attributes=attributes)
    else:
        for run in ledger["runs"]:
            if run.get("model_family") != "baseline":
                continue
            argv = list(run.get("argv", []))
            frozen_at = argv[argv.index("--frozen-at") + 1] if "--frozen-at" in argv else None
            history_arm = "--data-root" in argv
            attributes = {"baseline": run["baseline"], "candidate_protocol": run["candidate_protocol"],
                          "clock": "frozen" if frozen_at else "online", "frozen_at": frozen_at,
                          "history_arm": history_arm}
            status, commitment, failure, preds = _completion(run["completion_path"], ledger_sha256,
                                                             commitment_path=Path(run["out"]) / "commitment.json")
            cells[run["run_id"]] = _cell(run["run_id"], run["horizon_seconds"], None,
                                         f"{run['baseline']}/{run['candidate_protocol']}/{attributes['clock']}",
                                         status, commitment, failure, preds, history="on" if history_arm else "off",
                                         attributes=attributes)
    return {"kind": PARENT_LEDGER_KIND, "ledger_id": ledger_id, "family": family,
            "source": {"path": str(Path(ledger_path).resolve()), "sha256": ledger_sha256},
            **({"seal": seal} if seal else {}), "cells": cells}


# ---- frozen variant predictions -----------------------------------------------------------------------------------

def parent_entries(family, ledger):
    """{name: entry} of a learned family's parent prediction ledger."""
    require(family in LEARNED, f"{family} has no learned prediction entries")
    return {e["name"]: e for e in (ledger["entries"] if family == "h1" else ledger["runs"])}


def parent_snapshot(family, ledger, entry):
    """(prediction snapshot directory, its file-map digest) the parent predicted with."""
    if family in ("core", "h3", "h1"):
        return entry["snapshot"], entry["snapshot_sha256"]
    if family == "temporal":
        return ledger["prediction_snapshot"], ledger["prediction_snapshot_sha256"]
    return ledger["snapshot"], ledger["snapshot_sha256"]


def variant_entry(family, entry, gate, gate_ref, manifest_doc, parent_inputs=None):
    """The parent entry re-pointed at the variant manifest and gate of its horizon.

    The variant gate must descend from exactly the parent's gate and manifest, and every expected test input
    must be the variant tensor whose ``parent_sha256`` is the parent's gated input (lineage, not a name match).
    """
    from .forecast_history_variants import GATE_KIND
    gate_key, gate_sha_key = GATE_KEYS[family]
    require(gate.get("kind") == GATE_KIND and gate.get("primary_gate_sha256") == entry[gate_sha_key],
            f"{entry['name']}: variant gate does not descend from the parent's gate")
    members = [m for m in gate["manifests"] if m["original_manifest_sha256"] == entry["manifest_sha256"]]
    require(len(members) == 1, f"{entry['name']}: no unique variant manifest descends from the parent manifest")
    member = members[0]
    require(manifest_doc["history_sensitivity"]["original_manifest_sha256"] == entry["manifest_sha256"]
            and manifest_doc["history_sensitivity"]["intervention"] == gate["intervention"],
            f"{entry['name']}: variant manifest names another parent or intervention")
    # H1 entries name a ledger population instead of expected_inputs; the caller passes its gated inputs.
    parents = dict(parent_inputs) if parent_inputs is not None else {r["event_id"]: r["sha256"]
                                                                       for r in entry["expected_inputs"]}
    inputs = {r["event_id"]: r for r in member["inputs"] if r["event_id"] in parents}
    require(set(inputs) == set(parents), f"{entry['name']}: variant gate does not cover the parent's test inputs")
    require(all(inputs[e]["parent_sha256"] == parents[e] for e in parents),
            f"{entry['name']}: a variant input does not descend from the parent's gated input")
    expected_inputs = sorted(({"event_id": e, "sha256": inputs[e]["sha256"]} for e in parents),
                             key=lambda r: r["event_id"])
    out = {**entry, "manifest": member["path"], "manifest_sha256": member["sha256"], gate_key: gate_ref["path"],
           gate_sha_key: gate_ref["sha256"], "expected_inputs": expected_inputs,
           "parent_manifest_sha256": entry["manifest_sha256"], "parent_gate_sha256": entry[gate_sha_key],
           "intervention": gate["intervention"]}
    if family == "h1":
        ids = sorted(parents)
        out["population_doc"] = {"event_ids": ids, "event_ids_sha256": hashlib.sha256("\n".join(ids).encode()).hexdigest(),
                                 "inputs": {r["event_id"]: r["sha256"] for r in expected_inputs}}
    return out


def predict_command(family, python, entry, output, device):
    """The parent family's own frozen predictor invocation, on the variant manifest and gate."""
    if family in ("core", "transfer"):
        command = [python, "-u", "-m", MODULES[entry.get("family", "neural")], "predict", "--checkpoint",
                   entry["checkpoint"], "--manifest", entry["manifest"], "--out", str(output),
                   "--allow-label-containers", "--input-gate", entry["gate_path"]]
        return command + (["--device", device] if entry.get("family", "neural") == "neural" else [])
    if family in ("h3", "h1"):
        return [python, "-B" if family == "h1" else "-u", *(["-u"] if family == "h1" else []), "-m",
                "bgbench.forecast_train", "predict", "--checkpoint", entry["checkpoint"], "--manifest",
                entry["manifest"], "--out", str(output), "--allow-label-containers", "--input-gate",
                entry["input_gate"], "--device", device]
    module = "bgbench.forecast_temporal_predict" if family == "temporal" else "bgbench.forecast_temporal_mean_predict"
    return [python, "-u", "-m", module, "--checkpoint", entry["checkpoint"], "--expected-checkpoint-sha256",
            entry["checkpoint_sha256"], "--manifest", entry["manifest"], "--input-gate", entry["gate_path"],
            "--out", str(output), "--device", device]


def verify_output(family, driver, entry, output, snapshot):
    """The family driver's own verification of a frozen output; returns the bound evidence.

    H3 and H1 also write their family commitment document (``h3_commitment`` / ``h1_commitment``), as their
    parent drivers do; the caller writes it once beside the output.
    """
    output = Path(output)
    if family in ("core", "transfer"):
        return driver.verify_commitment(entry, output), None
    if family in ("temporal", "mean"):
        return driver.verify_commitment(entry, output, snapshot), None
    frozen_sha = file_sha(output / "commitment.json")
    frozen = json.loads((output / "commitment.json").read_text())
    predictions_sha256 = file_sha(output / "predictions.json")
    if family == "h3":
        driver.check_frozen_commitment(frozen, entry, predictions_sha256)
        availability = bound_json(entry["availability"], entry["availability_sha256"], "H3 availability")["rows"]
        predictions = json.loads((output / "predictions.json").read_text())
        document = driver.h3_commitment(entry, availability, predictions, availability_sha256=entry["availability_sha256"],
                                        frozen_commitment_sha256=frozen_sha, predictions_sha256=predictions_sha256)
    else:
        driver.check_frozen_output(frozen, entry, entry["population_doc"], predictions_sha256, "test")
        document = driver.h1_commitment(entry, entry["population_doc"], frozen_commitment_sha256=frozen_sha,
                                        predictions_sha256=predictions_sha256, attempt=0)
    return {"predictions_sha256": predictions_sha256, "frozen_commitment_sha256": frozen_sha}, document


def h3_baseline_extent_commitment(entry, availability, predictions, baseline_commitment, *,
                                  availability_sha256, baseline_commitment_sha256, predictions_sha256):
    """Versioned H3 envelope for the existing k=20 mean/median final extent/ranking baseline.

    Metadata/committed predictions only. The caller hash-checks these objects before calling and validates
    availability against the H3 input-status ledger. No curve estimator, rounding, clipping or score is added.
    A variant entry also binds its separately verified intervention sidecar reference.
    """
    import math
    from . import forecast_h3_commitments as h3

    size = {"history-knn-mean": "mean", "history-knn-median": "median"}.get(entry.get("baseline"))
    require(size is not None, "Unknown history baseline")
    require(entry.get("candidate_protocol") in ("matched_graph", "native_history_union"), "Unknown candidate protocol")
    require(not {"checkpoint_sha256", "fit_receipt_sha256"} & set(baseline_commitment),
            "A history baseline cannot borrow learned output")
    for key in ("baseline", "manifest_sha256", "input_gate_sha256", "baseline_source_sha256", "library_digest",
                "candidate_protocol"):
        require(baseline_commitment.get(key) == entry.get(key) and entry.get(key), f"Baseline {key} differs")
    require(baseline_commitment.get("test_labels_used") is False and baseline_commitment.get("split") == "test",
            "Unexpected baseline prediction provenance")
    require(baseline_commitment.get("predictions_sha256") == predictions_sha256, "Baseline prediction bytes differ")
    require(sorted(baseline_commitment["event_ids"]) == entry["forecast_event_ids"]
            and len(set(baseline_commitment["event_ids"])) == len(baseline_commitment["event_ids"]),
            "Baseline population differs")
    inputs = sorted(({"event_id": r["event_id"], "sha256": r["sha256"]} for r in baseline_commitment["inputs"]),
                    key=lambda r: r["event_id"])
    require(inputs == entry["expected_inputs"], "Baseline input bytes differ")
    available = {r["event_id"]: r for r in availability if r["status"] == "available"}
    require(sorted(r["event_id"] for r in predictions) == sorted(available), "Missing/extra baseline forecasts")
    for row in predictions:
        eid = row["event_id"]
        require(row.get("baseline") == entry["baseline"] and row.get("size_statistic") == size and row.get("k") == 20,
                f"{eid}: baseline estimator differs")
        require(row.get("candidate_protocol") == entry["candidate_protocol"]
                and row.get("observation_cutoff_s") == entry["horizon_seconds"]
                and row.get("frozen_at") == entry.get("frozen_at"), f"{eid}: baseline candidates, horizon or clock differ")
        require(row.get("seed_asns") == available[eid]["input_seed_asns"], f"{eid}: audited seeds differ")
        extent = row.get("extent")
        require(type(extent) in (float, int) and math.isfinite(extent) and extent >= len(row["seed_asns"]),
                f"{eid}: invalid final extent")
        require(len(row["candidate_asns"]) == len(set(row["candidate_asns"])) == len(row["ranking_scores"])
                and all(type(v) in (int, float) and math.isfinite(v) and v >= 0 and int(v) == v for v in row["ranking_scores"]),
                f"{eid}: invalid candidate/ranking pairs")
        require(row.get("ranking_score") == "issue_time_completed_event_participation_count",
                f"{eid}: ranking definition differs")
        require(set(row["seed_asns"]) <= set(row["predicted_asns"]) <= set(row["candidate_asns"]) | set(row["seed_asns"]),
                f"{eid}: predictions outside seeds/candidates")
        from .forecast_history_variants import _hex64
        _hex64(row.get("history_event_ids_sha256"), "history snapshot membership")
    doc = h3.h3_commitment(entry, availability, predictions, availability_sha256=availability_sha256,
                            frozen_commitment_sha256=baseline_commitment_sha256, predictions_sha256=predictions_sha256)
    doc.pop("frozen_commitment_sha256")
    doc.update(kind="h3_history_baseline_extent_commitment", schema_version=1, family="history",
               baseline=entry["baseline"], size_statistic=size, k=20, count_definition="extent",
               curve_metrics="not_applicable", quantile_calibration_eligible=False,
               count_rule="frozen committed seed-floored kNN final extent; no rounding or cardinality conversion",
               candidate_protocol=entry["candidate_protocol"],
               library_digest=entry["library_digest"], frozen_at=entry.get("frozen_at"),
               baseline_source_sha256=entry["baseline_source_sha256"],
               baseline_commitment_sha256=baseline_commitment_sha256,
               manifest_sha256=entry["manifest_sha256"], input_gate_sha256=entry["input_gate_sha256"])
    if entry.get("history_intervention") is not None:
        from .forecast_history_variants import _ref
        doc.update(history_intervention=entry["history_intervention"],
                   history_intervention_sidecar=_ref(entry["history_intervention_sidecar"], "baseline sidecar"))
    return doc
