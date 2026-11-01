"""R1 custody for retrospective predictions that are ALREADY committed (verify-then-join).

The old ``forecast_campaign.prepare_evaluation``/``run`` evaluate phase predicts again before it
scores, and ``forecast_custody.freeze``/``seal`` require protected manifests and label-free input
files, which the retrospective commitments do not have (RETAINED-ARM-LEDGER-DRAFT.md item 1). This
module is the reviewed retrospective commitment wrapper: it never predicts, fits, selects or
calibrates. It reads metadata and file bytes only; prediction values are decoded only by
``payload_checks`` inside ``forecast_retrospective_release.evaluate``, after the whole batch has
verified and before the one-time label marker.

Every check runs over the whole batch in one pass (``verify_batch``) and is repeated unchanged at
freeze, seal, plan and evaluation:

* the retained-arm ledger (JSON form) is covered exactly: every R1 arm is bound to committed cells of
  a supported format, or explicitly excluded where the draft allows it; anything else is refused;
* every cell of every family ledger is kept (committed or explicit failure); an unresolved cell refuses;
* per committed cell: family ledger, review gate, completion, commitment, prediction bytes, model
  bytes, manifest, input gate, every input file, prediction source, population and R1 window;
* batch prerequisites: new-period recipe freeze receipt, exposure ledger, scientific protocol, the
  history-withholding guard (``require_sensitivity_for_reporting`` is called, every time), the
  common scorer/numeric bundle, frozen slice rules, validation-only decision rules, arm spec and the
  independent review of this retention spec.

Each file is read once per pass; hashes are computed from those bytes and JSON is parsed from them.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path

SCOPE = "r1-committed-retrospective-evaluation-v1"
R1_WINDOW = {"start": "2025-09-01T00:00:00+00:00", "end": "2026-01-01T00:00:00+00:00"}
R1_EVENTS = 3543
R1_POPULATION_SHA256 = "f5f212ba42fb58a5e9beab84643e9cde56a336d46edbfde9ac3e9592cbeeb20c"
REVIEWER = re.compile(r"^(?:(?:anthropic/)?claude-opus-5-5|(?:openai/)?gpt-6-astra)$")
O_ROOT = Path("<FORECAST_ROOT>/occurrence-final-v1")
# One registry for the single R1 opening; it is never taken from the spec alone (a copied spec would
# otherwise name a fresh directory).
ACCESS_REGISTRY = O_ROOT / "custody" / "r1-access"
MARKER = "r1-unblinding.json"

# R1 part of RETAINED-ARM-LEDGER-DRAFT.md (18 October draft). The frozen JSON ledger must contain all.
R1_LEDGER_ARMS = ("R-core", "R-base", "R-gbdt", "R-transfer", "R-panelfix", "R-temporal", "R-temporal-order",
                  "R-mean", "R-tsfm", "R-chronos-ad", "R-counts", "R-h1", "R-h1-ood", "R-h3", "R-delay",
                  "R-withhold", "R-stable")
# Every retained arm is mandatory under the latest execution decisions.
EXCLUDABLE = frozenset()
# New-period recipes frozen before R1 (draft table 2). L-recipe is required only before R2; N-trigger may be
# declared absent when no valid trigger is frozen.
REQUIRED_RECIPES = ("N-core", "N-frozen2025", "N-base", "N-gbdt", "N-temporal", "N-mean", "N-tsfm",
                    "N-chronos-ad", "N-counts", "N-h1", "N-h3", "N-timing", "N-family", "N-delay",
                    "N-withhold", "N-stable", "N-trigger")
DECLARABLE_ABSENT = frozenset({"N-trigger"})

# Arms without a committed-prediction schema today. Refused by name, never silently skipped.
UNSUPPORTED_ARMS = {}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def population_sha256(ids):
    return hashlib.sha256(json.dumps(sorted(ids), separators=(",", ":")).encode()).hexdigest()


def canonical(doc):
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


CONSUMER_MODULES = (
    "forecast_retrospective_scoring", "forecast_train", "gnn_train", "graph_metrics", "forecast_numeric",
    "forecast_history", "forecast_ranking", "forecast_analysis", "forecast_custodian_eval", "forecast_curve",
    "forecast_panel", "forecast_panel_scoring", "forecast_h3_commitments", "forecast_h1_predictions",
    "forecast_history_variants", "forecast_sensitivity_gate", "forecast_recipes", "forecast_stable_peer",
)


def consumer_source_hashes(reads=None):
    """Exact in-process scientific dependency closure required in the independently reviewed draft."""
    import importlib
    reads = Reads() if reads is None else reads
    root = Path(__file__).resolve().parent
    result = {}
    for name in CONSUMER_MODULES:
        module = importlib.import_module("bgbench." + name)
        path = root / (name + ".py")
        require(Path(module.__file__).resolve() == path, f"Consumer dependency resolves elsewhere: {name}")
        result[name] = reads.digest(path)
    return result


def write_once(path, doc):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(doc, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


class Reads:
    """One read per path per verification pass; hashes and parses come from the same bytes."""

    def __init__(self, keep=(), *, max_retained_bytes=512 << 30, max_file_bytes=8 << 30):
        self.raw, self.digests, self.keep = {}, {}, set(keep)
        self.max_retained_bytes, self.max_file_bytes = max_retained_bytes, max_file_bytes
        self.retained_bytes = 0

    def bytes(self, path):
        key = str(Path(path).resolve())
        if key not in self.raw:
            allowance = min(self.max_file_bytes, self.max_retained_bytes - self.retained_bytes)
            size = Path(key).stat().st_size
            require(size <= allowance, "Verified-buffer resource budget exceeded")
            with Path(key).open("rb") as stream:
                data = stream.read(size + 1)
            require(len(data) == size, "Verified file size changed while reading")
            self.raw[key] = data
            self.retained_bytes += len(data)
            self.digests[key] = hashlib.sha256(data).hexdigest()
        return self.raw[key], self.digests[key]

    def digest(self, path):
        """Streamed hash for large files whose content is never parsed (models, inputs)."""
        key = str(Path(path).resolve())
        if key not in self.digests:
            h = hashlib.sha256()
            with Path(key).open("rb") as stream:
                for block in iter(lambda: stream.read(8 << 20), b""):
                    h.update(block)
            self.digests[key] = h.hexdigest()
        return self.digests[key]

    def bound(self, path, expected, what):
        raw, digest = self.bytes(path)
        require(isinstance(expected, str) and digest == expected, f"{what} differs from its hash anchor: {path}")
        return raw

    def json(self, path, expected, what):
        return json.loads(self.bound(path, expected, what))

    def ref(self, ref, what):
        require(isinstance(ref, dict) and ref.get("path") and ref.get("sha256"), f"{what} is not bound")
        return self.json(ref["path"], ref["sha256"], what)

    def file(self, ref, what):
        require(isinstance(ref, dict) and ref.get("path") and ref.get("sha256"), f"{what} is not bound")
        require(self.digest(ref["path"]) == ref["sha256"], f"{what} differs from its hash anchor: {ref['path']}")


def checked_snapshot(reads, root, expected):
    """A staged snapshot's file map digest and the bytes of every file in it."""
    root = Path(root).resolve()
    files = json.loads(reads.bytes(root / "snapshot.json")[0])["files"]
    require(hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest() == expected,
            f"Snapshot file map changed: {root}")
    for relative, checksum in files.items():
        path = (root / relative).resolve()
        require(path.is_relative_to(root) and reads.digest(path) == checksum, f"Snapshot file changed: {relative}")
    return files


def checked_review(gate, *, scope=None):
    require(gate.get("passed") is True, "Independent approval has not passed")
    # Existing immutable approval schemas did not all require a reviewer-name field.
    if "reviewer" in gate:
        reviewer = gate["reviewer"]
        # The frozen 18 October TSFM approval uses this exact descriptive spelling.
        # Read it compatibly without rewriting the approval or relaxing new-review schemas.
        if reviewer == "claude-opus-5-5 independent":
            reviewer = "claude-opus-5-5"
        require(isinstance(reviewer, str) and REVIEWER.fullmatch(reviewer),
                "Independent Claude Opus or GPT-6 Astra review required")
    if scope is not None:
        require(gate.get("scope") == scope, "Approval covers another scope")
    return gate


def in_window(onset):
    instant = datetime.fromisoformat(str(onset))
    instant = instant if instant.tzinfo else instant.replace(tzinfo=UTC)
    return (datetime.fromisoformat(R1_WINDOW["start"]) <= instant < datetime.fromisoformat(R1_WINDOW["end"]))


def checked_manifest(reads, path, expected, ids=None, *, secondary=False):
    manifest = reads.json(path, expected, "Manifest")
    require(not manifest.get("protected_test") and not manifest.get("locked_test")
            and not manifest.get("manifest_kind"), "Only retrospective manifests are R1 cells")
    test = sorted((r for r in manifest["events"] if r["split"] == "test"), key=lambda r: r["event_id"])
    require(test and all((str(r["onset"]).startswith("2025-") if secondary else in_window(r["onset"])) for r in test),
            "Test split outside the R1 window (separate windows, e.g. 2025 transfer, need their own review)")
    if ids is not None:
        require([r["event_id"] for r in test] == sorted(ids), "Manifest test population differs from the commitment")
    return [{"event_id": r["event_id"], "incident_id": r["incident_id"], "onset": r["onset"],
             **({"actor": r["actor"]} if "actor" in r else {})} for r in test]


def checked_inputs(reads, records, expected):
    """Commitment input receipts equal the gate's, and each input file still has those bytes."""
    got = sorted(({"event_id": r["event_id"], "sha256": r["sha256"]} for r in records), key=lambda r: r["event_id"])
    require(got == expected, "Prediction input bytes differ from the input gate")
    for record in records:
        if record.get("path"):
            require(reads.digest(record["path"]) == record["sha256"], f"Input changed: {record['event_id']}")
    return canonical(got)


def gate_inputs(gate, manifest_sha256, ids):
    members = [m for m in gate.get("manifests", []) if m.get("sha256") == manifest_sha256]
    require(gate.get("passed") is True and len(members) == 1, "Manifest absent from (or duplicated in) a passed gate")
    wanted = set(ids)
    return sorted(({"event_id": r["event_id"], "sha256": r["sha256"]} for r in members[0]["inputs"]
                   if r["event_id"] in wanted), key=lambda r: r["event_id"])


def _cell(family, name, role, **fields):
    return {"cell_id": f"{family['family_id']}/{name}", "family_id": family["family_id"], "format": family["format"],
            "role": role, **fields}


def _failed(family, name, role, why, **evidence):
    return _cell(family, name, role, status="failed", failure=why, **evidence)


# --------------------------------------------------------------------------- adapters (one per format)

def checked_core_lineage(family, reads, ledger):
    require(family.get("verifier") and ledger.get("driver_sha256") == family["verifier"]["sha256"],
            "Core producer source is not externally bound")
    driver = bound_verifier(reads, family["verifier"], "r1_core_verifier")
    gate = reads.json(ledger["review_gate"], ledger["review_gate_sha256"], "Core producer approval")
    checked_review(gate, scope=driver.SCOPE)
    require(gate.get("driver_sha256") == family["verifier"]["sha256"]
            and gate.get("specification_sha256") == ledger["specification_sha256"]
            and all(gate.get(k) is False for k in driver.FORBIDDEN), "Core producer approval differs")
    files = checked_snapshot(reads, gate["orchestration_source"], gate["orchestration_snapshot_sha256"])
    campaign = bound_verifier(reads, {"path": str(Path(gate["orchestration_source"]) / "scripts/forecast_campaign.py"),
                                      "sha256": files["scripts/forecast_campaign.py"]}, "r1_core_campaign")
    spec = reads.json(ledger["specification"], ledger["specification_sha256"], "Core selected-run specification")
    require(driver.checked_selection(campaign, spec) == ledger["runs"], "Core ledger differs from complete selected-fit resolution")


def checked_baseline_lineage(family, reads, ledger):
    require(family.get("verifier"), "Deterministic baseline requires its actual approved producer")
    campaign = bound_verifier(reads, family["verifier"], "r1_baseline_campaign")
    gate = reads.json(ledger["implementation_review_path"], ledger["implementation_review_sha256"], "Baseline implementation review")
    checked_review(gate)
    if ledger.get("orchestration_marker_path"):
        orchestration = reads.json(ledger["orchestration_marker_path"], ledger["orchestration_marker_sha256"], "Baseline orchestration marker")
        campaign.ORCHESTRATION_REVIEWER = REVIEWER
        checked, digest = campaign.checked_orchestration_marker(ledger["orchestration_marker_path"], "history-baselines",
            root=ledger["root"], code_snapshot_sha256=orchestration["code_snapshot_sha256"],
            gate_path=ledger["gate_path"], history_binding_sha256=ledger.get("history_binding_sha256"))
        require(checked == orchestration and digest == ledger["orchestration_marker_sha256"], "Baseline orchestration differs")
        producer_root = str(Path(family["verifier"]["path"]).resolve().parents[1])
        _, files, digest = campaign.source_file_digest(producer_root)
        require(digest == orchestration["code_snapshot_sha256"], "Actual baseline orchestration source map differs")
        for name, digest in files.items():
            require(reads.digest(Path(producer_root) / name) == digest, "Baseline orchestration source changed")
    else:
        campaign.checked_review_marker(ledger["implementation_review_path"], ledger["implementation_review_sha256"])
        producer_root = ledger["snapshot"]
        files = checked_snapshot(reads, producer_root, ledger["snapshot_sha256"])
    require(Path(family["verifier"]["path"]).resolve() == Path(producer_root, "scripts/forecast_campaign.py").resolve()
            and family["verifier"]["sha256"] == files["scripts/forecast_campaign.py"], "Baseline verifier is not its actual producer")
    return files["scripts/forecast_campaign.py"]


def adapt_core_gbdt(family, reads):
    """``forecast_retrospective_commitments.py`` ledger: neural (R-core) and GBDT (R-gbdt) commitments."""
    ledger = reads.ref(family["ledger"], "Core/GBDT commitment ledger")
    require(ledger.get("scope") == "retrospective-neural-gbdt-prediction-commitments-v1"
            and ledger.get("test_scoring_authorized") is False, "Not a core/GBDT commitment ledger")
    checked_review(reads.json(ledger["review_gate"], ledger["review_gate_sha256"], "Commitment review gate"),
                   scope=ledger["scope"])
    require(reads.digest(ledger["specification"]) == ledger["specification_sha256"], "Commitment spec changed")
    checked_core_lineage(family, reads, ledger)
    return core_cells(family, reads, ledger)


def calibration_fit_evidence(reads, run, checkpoint_sha256, snapshot_files):
    completion_raw, completion_sha = reads.bytes(run["completion_path"])
    completion = json.loads(completion_raw)
    require(completion.get("returncode") == 0 and completion.get("checkpoint_sha256") == checkpoint_sha256,
            "Calibration fit completion names another checkpoint")
    root = Path(run["out"])
    receipt = reads.json(root / "fit_receipt.json", completion["fit_receipt_sha256"], "Original calibration fit receipt")
    require(receipt.get("checkpoint_sha256") == checkpoint_sha256
            and receipt.get("test_inputs_opened") is False and receipt.get("threshold_calibration_split") == "validation",
            "Calibration fit violated checkpoint/validation provenance")
    return {"run_id": run["run_id"], "completion_sha256": completion_sha, "threshold": receipt["threshold"],
            "validation_predictions_sha256": reads.digest(root / "validation_predictions.json"),
            "fit_receipt_sha256": completion["fit_receipt_sha256"], "completed_utc": completion["completed_utc"],
            "source_sha256": snapshot_files["scripts/forecast_campaign.py"]}


def core_cells(family, reads, ledger, arm=None, *, secondary=False):
    """Common frozen membership commitment checks after family-specific provenance validation."""
    root = Path(ledger["root"])
    cells = []
    for entry in ledger["runs"]:
        fit_ledger = reads.json(entry["fit_ledger"], entry["fit_ledger_sha256"], "Fit ledger")
        runs = [r for r in fit_ledger["runs"] + fit_ledger.get("reused_runs", []) if r["run_id"] == entry["run_id"]]
        require(len(runs) == 1, f"Fit run missing or duplicated: {entry['run_id']}")
        run = runs[0]
        family_name = run.get("model_family", "neural")
        require(family_name == entry["family"] and family_name in ("neural", "gbdt"), "Fit family differs")
        role = {"arm_id": arm or ("R-core" if family_name == "neural" else "R-gbdt"), "model_family": family_name,
                "horizon_seconds": run["horizon_seconds"], "seed": run["seed"], "history": run["history"],
                "message_passing": run["message_passing"], "configuration_id": run.get("configuration_id")}
        completion_path = root / "completions" / f"{entry['name']}.json"
        require(completion_path.is_file(), f"Unresolved cell (no completion): {entry['name']}")
        completion_raw, completion_sha = reads.bytes(completion_path)
        completion = json.loads(completion_raw)
        if completion.get("returncode") != 0:
            cells.append(_failed(family, entry["name"], role, "nonzero prediction returncode",
                                 completion_sha256=completion_sha, returncode=completion.get("returncode")))
            continue
        output = root / "predictions" / entry["name"]
        commitment = reads.json(output / "commitment.json", completion.get("commitment_sha256"), "Commitment")
        _, predictions_sha = reads.bytes(output / "predictions.json")
        require(predictions_sha == commitment.get("predictions_sha256") == completion.get("predictions_sha256"),
                f"Prediction bytes changed: {entry['name']}")
        for key in ("manifest_sha256", "checkpoint_sha256", "prediction_source_sha256"):
            require(commitment.get(key) == entry[key], f"Commitment {key} differs: {entry['name']}")
        require(commitment.get("input_gate_sha256") == entry["gate_sha256"], "Commitment gate differs")
        require(commitment.get("test_labels_used") is False, "Commitment used test labels")
        ids = commitment["event_ids"]
        require(len(ids) == len(set(ids)) and sorted(ids) == entry["expected_test_ids"], "Prediction population differs")
        require(reads.digest(entry["checkpoint"]) == entry["checkpoint_sha256"], f"Model changed: {entry['name']}")
        snapshot = checked_snapshot(reads, entry["snapshot"], entry["snapshot_sha256"])
        module = "src/bgbench/" + ("forecast_train.py" if family_name == "neural" else "forecast_baseline.py")
        require(snapshot.get(module) == entry["prediction_source_sha256"], "Prediction source differs from snapshot")
        rows = checked_manifest(reads, entry["manifest"], entry["manifest_sha256"], ids, secondary=secondary)
        gate = reads.json(entry["gate_path"], entry["gate_sha256"], "Input gate")
        expected_inputs = gate_inputs(gate, entry["manifest_sha256"], ids)
        require(expected_inputs == entry["expected_inputs"], "Ledger inputs differ from the gate")
        cells.append(_cell(family, entry["name"], role, status="committed", completion_sha256=completion_sha,
                           commitment_path=str(output / "commitment.json"),
                           commitment_sha256=completion["commitment_sha256"],
                           predictions_path=str(output / "predictions.json"), predictions_sha256=predictions_sha,
                           payload="forecast_rows_json", model_sha256=entry["checkpoint_sha256"],
                           manifest_path=entry["manifest"], manifest_sha256=entry["manifest_sha256"],
                           gate_path=entry["gate_path"], gate_sha256=entry["gate_sha256"],
                           snapshot=entry["snapshot"], snapshot_sha256=entry["snapshot_sha256"],
                           source_sha256=entry["prediction_source_sha256"],
                           inputs_sha256=checked_inputs(reads, commitment["inputs"], expected_inputs),
                           population_sha256=population_sha256(ids), event_ids=sorted(ids), cohort_rows=rows,
                           calibration_fit={**calibration_fit_evidence(reads, run, entry["checkpoint_sha256"], snapshot),
                                            "fit_ledger": {"path": entry["fit_ledger"], "sha256": entry["fit_ledger_sha256"]}},
                           learned=True))
    return cells


def frozen_at(argv):
    return argv[argv.index("--frozen-at") + 1] if "--frozen-at" in argv else None


def adapt_deterministic(family, reads):
    """``forecast_campaign.prepare_baselines`` ledger: committed deterministic history/topology rankings (R-base).

    GBDT fit runs in such a ledger are fits, not prediction cells; their commitments are core/GBDT cells.
    """
    ledger = reads.ref(family["ledger"], "Deterministic baseline ledger")
    require(ledger.get("phase") == "baseline", "Not a deterministic baseline ledger")
    producer_sha = checked_baseline_lineage(family, reads, ledger)
    checked_snapshot(reads, ledger["snapshot"], ledger["snapshot_sha256"])
    gate = reads.json(ledger["gate_path"], ledger["gate_sha256"], "Baseline input gate")
    manifests = {m["sha256"]: m for m in ledger["manifests"]}
    cells = []
    for run in ledger["runs"]:
        if run.get("model_family") != "baseline":
            continue
        role = {"arm_id": "R-base", "model_family": "baseline", "baseline": run["baseline"],
                "candidate_protocol": run["candidate_protocol"], "horizon_seconds": run["horizon_seconds"],
                "seed": 0, "history": run["history"], "message_passing": run["message_passing"],
                "configuration_id": None, "frozen_at": frozen_at(run["argv"])}
        require(Path(run["completion_path"]).is_file(), f"Unresolved cell (no completion): {run['run_id']}")
        completion_raw, completion_sha = reads.bytes(run["completion_path"])
        completion = json.loads(completion_raw)
        if completion.get("returncode") != 0:
            cells.append(_failed(family, run["run_id"], role, "nonzero commitment returncode",
                                 completion_sha256=completion_sha, returncode=completion.get("returncode")))
            continue
        out = Path(run["out"])
        commitment = reads.json(out / "commitment.json", completion.get("commitment_sha256"), "Baseline commitment")
        _, predictions_sha = reads.bytes(out / "predictions.json")
        require(predictions_sha == commitment.get("predictions_sha256") == completion.get("predictions_sha256"),
                f"Prediction bytes changed: {run['run_id']}")
        require(commitment.get("test_labels_used") is False and commitment.get("split") == "test"
                and commitment.get("baseline") == run["baseline"], "Unexpected baseline commitment provenance")
        require(commitment.get("input_gate_sha256") == ledger["gate_sha256"]
                and commitment.get("manifest_sha256") in manifests, "Baseline committed on another gate/manifest")
        require(commitment.get("baseline_source_sha256") == producer_sha,
                "Baseline source differs from its snapshot")
        if run["baseline"] != "topology-seed-adjacency":
            check = json.loads(reads.bound(out / "participation-check.json", commitment.get("participation_check_sha256"),
                                           "Participation check"))
            require(check.get("mismatched_events") == 0, "History ranking lacks a passing participation check")
        ids = commitment["event_ids"]
        require(len(ids) == len(set(ids)), "Duplicate baseline event IDs")
        manifest = manifests[commitment["manifest_sha256"]]
        rows = checked_manifest(reads, manifest["path"], manifest["sha256"], ids)
        expected_inputs = gate_inputs(gate, manifest["sha256"], ids)
        cells.append(_cell(family, run["run_id"], role, status="committed", completion_sha256=completion_sha,
                           commitment_path=str(out / "commitment.json"),
                           commitment_sha256=completion["commitment_sha256"],
                           predictions_path=str(out / "predictions.json"), predictions_sha256=predictions_sha,
                           payload="forecast_rows_json", model_sha256=None,
                           manifest_path=manifest["path"], manifest_sha256=manifest["sha256"],
                           gate_path=ledger["gate_path"], gate_sha256=ledger["gate_sha256"],
                           snapshot=ledger["snapshot"], snapshot_sha256=ledger["snapshot_sha256"],
                           source_sha256=commitment["baseline_source_sha256"],
                           inputs_sha256=checked_inputs(reads, commitment["inputs"], expected_inputs),
                           population_sha256=population_sha256(ids), event_ids=sorted(ids), cohort_rows=rows,
                           learned=False))
    return cells


TEMPORAL_FAILED_ARM = "arm_failed_all_configurations_nonfinite"


def checked_temporal_lineage(family, reads, ledger):
    require(family.get("verifier") and ledger.get("driver_sha256") == family["verifier"]["sha256"],
            "Temporal finals need their reviewed metadata verifier")
    verifier = bound_verifier(reads, family["verifier"], "r1_temporal_verifier")
    fresh, _, _ = verifier.prediction_resolution(ledger["specification"], ledger["fit_ledger"],
                                                ledger["fit_ledger_sha256"], ledger["fit_review_gate_sha256"])
    require(all(ledger.get(key) == value for key, value in fresh.items()),
            "Temporal fits, selection or numerical-failure evidence differs from complete resolution")
    verifier.approval(ledger["review_gate"], ledger["review_gate_sha256"], ledger["specification"], "predictions")


def adapt_temporal(family, reads):
    """``forecast_temporal_finals.py`` prediction ledger: committed GRU/TGN finals plus explicit failed cells."""
    ledger = reads.ref(family["ledger"], "Temporal finals prediction ledger")
    require(ledger.get("scope") == "temporal-retrospective-finals-v1"
            and ledger.get("phase") == "temporal-retrospective-finals-predictions"
            and ledger.get("test_scoring_authorized") is False, "Not a temporal finals prediction ledger")
    checked_temporal_lineage(family, reads, ledger)
    checked_review(reads.json(ledger["review_gate"], ledger["review_gate_sha256"], "Temporal review gate"),
                   scope="temporal-retrospective-finals-v1:predictions")
    snapshot = checked_snapshot(reads, ledger["prediction_snapshot"], ledger["prediction_snapshot_sha256"])
    predictor = snapshot.get("src/bgbench/forecast_temporal_predict.py")
    require(predictor == ledger["predictor_sha256"], "Temporal predictor differs from its snapshot")
    root = Path(family["ledger"]["path"]).resolve().parent
    entries = {e["name"]: e for e in ledger["runs"]}
    require(len(entries) == len(ledger["runs"]), "Duplicate temporal prediction entry")
    cells, used = [], set()
    for status in ledger["cells"]:
        name = status.get("run_id") or f"{status['kind']}-d{status['horizon_seconds']}-s{status.get('seed')}"
        role = {"arm_id": "R-temporal", "model_family": "temporal", "kind": status["kind"],
                "horizon_seconds": status["horizon_seconds"], "seed": status.get("seed"),
                "configuration_id": status.get("configuration_id")}
        if status["status"] in ("ineligible_numerical_failure", TEMPORAL_FAILED_ARM):
            cells.append(_failed(family, name, role, status["status"],
                                 failure_evidence={k: status.get(k) for k in ("failure_sha256", "reason")}))
            continue
        require(status["status"] == "completed" and name in entries, f"Unresolved temporal cell: {name}")
        used.add(name)
        entry = entries[name]
        completion_path = root / "completions" / f"{name}.json"
        require(completion_path.is_file(), f"Unresolved cell (no completion): {name}")
        completion_raw, completion_sha = reads.bytes(completion_path)
        completion = json.loads(completion_raw)
        if completion.get("returncode") != 0:
            cells.append(_failed(family, name, role, "nonzero prediction returncode",
                                 completion_sha256=completion_sha, returncode=completion.get("returncode")))
            continue
        output = root / "outputs" / name
        commitment = reads.json(output / "commitment.json", completion.get("commitment_sha256"), "Temporal commitment")
        _, predictions_sha = reads.bytes(output / "predictions.json")
        require(predictions_sha == commitment.get("predictions_sha256") == completion.get("predictions_sha256"),
                f"Prediction bytes changed: {name}")
        for key in ("manifest_sha256", "checkpoint_sha256"):
            require(commitment.get(key) == entry[key], f"Temporal commitment {key} differs")
        require(commitment.get("input_gate_sha256") == entry["gate_sha256"]
                and commitment.get("prediction_source_sha256") == predictor
                and commitment.get("split") == "test" and commitment.get("test_labels_used") is False
                and commitment.get("scores_computed") is False
                and commitment.get("label_fields_projected_before_inference") is True,
                "Unexpected temporal prediction provenance")
        ids = commitment["event_ids"]
        require(len(ids) == len(set(ids)) and sorted(ids) == entry["expected_test_ids"], "Prediction population differs")
        require(reads.digest(entry["checkpoint"]) == entry["checkpoint_sha256"], f"Model changed: {name}")
        rows = checked_manifest(reads, entry["manifest"], entry["manifest_sha256"], ids)
        gate = reads.json(entry["gate_path"], entry["gate_sha256"], "Temporal input gate")
        require(gate_inputs(gate, entry["manifest_sha256"], ids) == entry["expected_inputs"],
                "Temporal prediction inputs differ from the gate")
        cells.append(_cell(family, name, role, status="committed", completion_sha256=completion_sha,
                           commitment_path=str(output / "commitment.json"),
                           commitment_sha256=completion["commitment_sha256"],
                           predictions_path=str(output / "predictions.json"), predictions_sha256=predictions_sha,
                           payload="forecast_rows_json", model_sha256=entry["checkpoint_sha256"],
                           manifest_path=entry["manifest"], manifest_sha256=entry["manifest_sha256"],
                           gate_path=entry["gate_path"], gate_sha256=entry["gate_sha256"], source_sha256=predictor,
                           inputs_sha256=checked_inputs(reads, commitment["inputs"], entry["expected_inputs"]),
                           population_sha256=population_sha256(ids), event_ids=sorted(ids), cohort_rows=rows,
                           learned=True))
    require(used == set(entries), "A temporal prediction entry has no resolved cell")
    return cells


def checked_h3_alignment(family, reads, metadata_sha256=None):
    """Resolve all three panels through the independently bound consumer and cohort freeze."""
    require(family.get("alignment"), "H3 requires reviewed alignment, reference receipt and a fresh cohort freeze")
    alignment = family["alignment"]
    driver = bound_verifier(reads, alignment["verifier"], "r1_h3_alignment_verifier")
    from types import SimpleNamespace
    driver.bound = lambda path, digest: (reads.json(path, digest, "H3 alignment evidence"), digest)
    args = SimpleNamespace(**alignment["arguments"])
    if metadata_sha256 is not None:
        require(args.expected_metadata_sha256 == metadata_sha256, "H3 alignment names other metadata")
    per_horizon, bindings, manifests, audits, scope = driver.resolve(args)
    frozen = reads.json(args.cohorts, args.expected_cohorts_sha256, "H3 frozen cohorts")
    driver.s.check_frozen_cohorts(frozen, args.expected_cohorts_sha256, args.expected_cohorts_sha256,
                                  per_horizon, bindings, manifests, scope_binding=scope)
    reference_gate = reads.ref(alignment["reference_gate"], "H3 reference target gate")
    return driver, args, per_horizon, audits, reference_gate


def adapt_h3(family, reads):
    """``forecast_h3_campaign.py`` ledger: frozen-model panel forecasts plus certified no-input abstentions."""
    from . import forecast_h3_commitments as h3
    ledger = reads.ref(family["ledger"], "H3 commitment ledger")
    require(ledger.get("scope") == "h3-frozen-sensitivity-retrospective-predictions-v1"
            and ledger.get("test_scoring_authorized") is False, "Not an H3 commitment ledger")
    checked_review(reads.json(ledger["approval"], ledger["approval_sha256"], "H3 approval"))
    reads.json(ledger["metadata_ledger"], ledger["metadata_ledger_sha256"], "H3 metadata ledger")
    driver, args, per_horizon, audits, reference_gate = checked_h3_alignment(
        family, reads, ledger["metadata_ledger_sha256"])
    alignment = family["alignment"]
    root = Path(ledger["root"])
    cells = []
    for entry in ledger["runs"]:
        role = {"arm_id": "R-h3", "model_family": "neural", "panel": entry["panel"],
                "horizon_seconds": entry["horizon_seconds"], "seed": entry["seed"], "history": entry["history"],
                "message_passing": entry["message_passing"]}
        completion_path = root / "completions" / f"{entry['name']}.json"
        require(completion_path.is_file(), f"Unresolved cell (no completion): {entry['name']}")
        completion_raw, completion_sha = reads.bytes(completion_path)
        completion = json.loads(completion_raw)
        if completion.get("returncode") != 0:
            cells.append(_failed(family, entry["name"], role, "nonzero prediction returncode",
                                 completion_sha256=completion_sha, returncode=completion.get("returncode")))
            continue
        output = root / "predictions" / entry["name"]
        frozen_raw, frozen_sha = reads.bytes(output / "commitment.json")
        _, predictions_sha = reads.bytes(output / "predictions.json")
        require(predictions_sha == completion.get("predictions_sha256"), f"Prediction bytes changed: {entry['name']}")
        h3.check_frozen_commitment(json.loads(frozen_raw), entry, predictions_sha)
        doc_path = root / "commitments" / f"{entry['name']}.json"
        doc = reads.json(doc_path, completion.get("h3_commitment_sha256"), "H3 full-reference commitment")
        require(doc.get("frozen_commitment_sha256") == frozen_sha and doc.get("predictions_sha256") == predictions_sha
                and doc.get("availability_sha256") == entry["availability_sha256"]
                and doc.get("test_labels_used") is False, "H3 commitment is bound to other bytes")
        reference = entry["reference_event_ids"]
        delta, panel = entry["horizon_seconds"], entry["panel"]
        require(reference == per_horizon[delta][0], "H3 reference IDs differ from frozen cohorts")
        reference_path, reference_sha = driver.pair(getattr(args, f"reference_manifest_d{delta}"))
        reference_rows = checked_manifest(reads, reference_path, reference_sha, reference)
        require(len(gate_inputs(reference_gate, reference_sha, reference)) == len(reference),
                "H3 target gate does not cover the complete reference population")
        fit = reads.ref(alignment["fit_receipts"][entry["name"]], "H3 original fit receipt")
        require(fit.get("checkpoint_sha256") == entry["checkpoint_sha256"], "H3 projection receipt names another fit")
        projection = fit["model"]["curve_projection"]
        require(projection in ("cummax", "none"), "H3 projection is undeclared")
        abstained = [a["event_id"] for a in doc["abstentions"]]
        require(doc.get("reference_event_ids_sha256") == population_sha256(reference)
                and len(reference) == len(set(reference)), "H3 reference population differs")
        require(sorted(doc["forecast_event_ids"] + abstained) == sorted(reference)
                and not set(abstained) & set(doc["forecast_event_ids"]),
                "H3 forecasts and abstentions must partition the full reference population")
        require(all(a.get("input_status") == "no_input" and a.get("abstention_policy") == h3.ABSTENTION
                    and a.get("calibration_eligible") is False for a in doc["abstentions"]),
                "Every H3 abstention must be a certified no-input abstention")
        require(doc.get("alignment_adapter", {}).get("status") in
                ("passed", "pending_reviewed_partial_panel_rule"),
                "Unknown frozen H3 alignment state")
        # The externally reviewed resolve/freeze above supplies the partial rule; preserve the original envelope.
        source_files = checked_snapshot(reads, entry["snapshot"], entry["snapshot_sha256"])
        require(source_files.get("src/bgbench/forecast_train.py") == entry["prediction_source_sha256"],
                "H3 prediction source differs from its complete frozen snapshot")
        require(reads.digest(entry["checkpoint"]) == entry["checkpoint_sha256"], "H3 model changed")
        reads.bound(entry["availability"], entry["availability_sha256"], "H3 availability")
        checked_manifest(reads, entry["manifest"], entry["manifest_sha256"], doc["forecast_event_ids"])
        gate = reads.json(entry["input_gate"], entry["input_gate_sha256"], "H3 input gate")
        expected_inputs = gate_inputs(gate, entry["manifest_sha256"], doc["forecast_event_ids"])
        require(expected_inputs == entry["expected_inputs"], "H3 ledger inputs differ from the gate")
        cells.append(_cell(family, entry["name"], role, status="committed", completion_sha256=completion_sha,
                           commitment_path=str(doc_path), commitment_sha256=completion["h3_commitment_sha256"],
                           frozen_commitment_sha256=frozen_sha,
                           predictions_path=str(output / "predictions.json"), predictions_sha256=predictions_sha,
                           payload="forecast_rows_json_with_abstentions", model_sha256=entry["checkpoint_sha256"],
                           manifest_path=entry["manifest"], manifest_sha256=entry["manifest_sha256"],
                           gate_path=entry["input_gate"], gate_sha256=entry["input_gate_sha256"],
                           source_sha256=entry["prediction_source_sha256"],
                           inputs_sha256=checked_inputs(reads, json.loads(frozen_raw)["inputs"], expected_inputs),
                           population_sha256=population_sha256(reference), event_ids=sorted(reference),
                           forecast_event_ids=sorted(doc["forecast_event_ids"]), abstention_event_ids=sorted(abstained),
                           cohort_rows=reference_rows,
                           reference_manifest={"path": reference_path, "sha256": reference_sha},
                           reference_gate=alignment["reference_gate"],
                           h3_context={"arm": panel, "horizon": delta, "family": "learned",
                                       "rows": per_horizon[delta][1][panel],
                                       "binding": driver.s.h3_binding(doc, audits[(panel, delta)], reference),
                                       "temporal_monotone": projection == "cummax"},
                           learned=True))
    return cells


def adapt_h3_history(family, reads):
    """Consume externally reviewed extent-only baseline envelopes for all three H3 panels."""
    ledger = reads.ref(family["ledger"], "H3 history envelope index")
    require(ledger.get("kind") == "h3_history_extent_index_v1" and ledger.get("test_labels_used") is False,
            "Invalid H3 history index")
    checked_review(reads.ref(family["approval"], "H3 history lineage approval"))
    approval = reads.ref(family["approval"], "H3 history lineage approval")
    require(approval.get("index_sha256") == family["ledger"]["sha256"], "H3 history approval names another index")
    driver, args, per_horizon, audits, reference_gate = checked_h3_alignment(family, reads)
    candidate_protocol = ledger.get("candidate_protocol")
    require(candidate_protocol in ("matched_graph", "native_history_union"), "H3 history index candidate policy differs")
    baselines = ledger["baselines"]
    require(baselines and len(set(baselines)) == len(baselines)
            and set(baselines) <= {"history-knn-mean", "history-knn-median"}, "Unknown H3 baseline estimator")
    entries = ledger["entries"]
    require(len(entries) == len(baselines) * 6 and
            {(e["panel"], e["horizon_seconds"], e["baseline"]) for e in entries} ==
            {(p, h, b) for p in ("reference", "ris7", "mixed7") for h in (30, 60) for b in baselines},
            "H3 baseline index omits or duplicates an estimator/panel/horizon")
    result = []
    from types import SimpleNamespace
    for entry in entries:
        panel, delta = entry["panel"], entry["horizon_seconds"]
        doc = reads.ref(entry["commitment"], "H3 history extent envelope")
        prediction = entry["predictions"]
        reads.bound(prediction["path"], prediction["sha256"], "H3 history predictions")
        require(doc.get("kind") == "h3_history_baseline_extent_commitment"
                and doc.get("panel") == panel and doc.get("baseline") == entry["baseline"]
                and doc.get("candidate_protocol") == candidate_protocol
                and doc.get("predictions_sha256") == prediction["sha256"], "H3 history envelope identity differs")
        original = reads.ref(entry["baseline_commitment"], "H3 original baseline commitment")
        reads.file(entry["baseline_source"], "H3 baseline source")
        driver.history_lineage(SimpleNamespace(
            baseline_commitment=f'{entry["baseline_commitment"]["path"]}:{entry["baseline_commitment"]["sha256"]}',
            baseline_source=f'{entry["baseline_source"]["path"]}:{entry["baseline_source"]["sha256"]}',
            history_sidecar=None), doc, prediction["sha256"])
        manifest, gate = entry["manifest"], entry["gate"]
        require(doc.get("manifest_sha256") == manifest["sha256"] and doc.get("input_gate_sha256") == gate["sha256"],
                "H3 history manifest/gate differs")
        checked_manifest(reads, manifest["path"], manifest["sha256"], doc["forecast_event_ids"])
        expected = gate_inputs(reads.ref(gate, "H3 history input gate"), manifest["sha256"], doc["forecast_event_ids"])
        inputs_sha = checked_inputs(reads, original["inputs"], expected)
        reference = per_horizon[delta][0]
        reference_path, reference_sha = driver.pair(getattr(args, f"reference_manifest_d{delta}"))
        cohort = checked_manifest(reads, reference_path, reference_sha, reference)
        gate_inputs(reference_gate, reference_sha, reference)
        result.append(_cell(family, entry["name"],
            {"arm_id": "R-h3", "model_family": "baseline", "panel": panel, "horizon_seconds": delta,
             "baseline": entry["baseline"], "candidate_protocol": candidate_protocol, "seed": 0}, status="committed",
            commitment_path=entry["commitment"]["path"], commitment_sha256=entry["commitment"]["sha256"],
            baseline_commitment=entry["baseline_commitment"],
            predictions_path=prediction["path"], predictions_sha256=prediction["sha256"],
            payload="forecast_rows_json_with_abstentions", model_sha256=None,
            manifest_path=manifest["path"], manifest_sha256=manifest["sha256"],
            gate_path=gate["path"], gate_sha256=gate["sha256"], inputs_sha256=inputs_sha,
            source_sha256=entry["baseline_source"]["sha256"], population_sha256=population_sha256(reference),
            event_ids=reference, forecast_event_ids=doc["forecast_event_ids"], cohort_rows=cohort,
            reference_manifest={"path": reference_path, "sha256": reference_sha},
            reference_gate=family["alignment"]["reference_gate"],
            h3_context={"arm": panel, "horizon": delta, "family": "history",
                        "rows": per_horizon[delta][1][panel],
                        "binding": driver.s.h3_binding(doc, audits[(panel, delta)], reference),
                        "temporal_monotone": False}, learned=False))
    return result


def checked_retained_paths(cells):
    """Allow only proven H3 reference-baseline forecast reuse; keep scoring independent.

    H3 wraps the existing baseline commitment in a separate extent envelope. It
    must retain its H3 scorer/context, so this is deliberately not ``alias_of``
    (which reuses already computed metrics). All other shared paths still fail.
    """
    committed = [c for c in cells if c["status"] == "committed"]
    require(all("prediction_reuse_of" not in c for c in cells), "Unverified prediction reuse declaration")
    parents_used = set()
    for cell in committed:
        role = cell["role"]
        if not (cell["format"] == "h3_history_extent_index_v1" and role.get("panel") == "reference"):
            continue
        original = cell.get("baseline_commitment", {})
        parents = [p for p in committed if p["format"] == "deterministic_baseline_v1"
                   and p["role"]["arm_id"] == "R-base" and not p.get("alias_of")
                   and str(Path(p["commitment_path"]).resolve())
                   == str(Path(original.get("path", "")).resolve())
                   and p["commitment_sha256"] == original.get("sha256")]
        require(len(parents) == 1, "H3 reference baseline needs exactly one retained original commitment")
        parent = parents[0]
        policy = {"matched_graph": "matched", "native_history_union": "native"}.get(role.get("candidate_protocol"))
        require(role.get("arm_id") == "R-h3" and role.get("model_family") == "baseline"
                and parent["role"].get("model_family") == "baseline"
                and policy is not None and parent["role"].get("candidate_protocol") == policy
                and role.get("baseline") in ("history-knn-mean", "history-knn-median")
                and all(role.get(k) == parent["role"].get(k) for k in ("baseline", "horizon_seconds"))
                and cell.get("model_sha256") is None and parent.get("model_sha256") is None
                and not cell.get("alias_of") and not cell.get("secondary") and not parent.get("secondary")
                and cell["payload"] == "forecast_rows_json_with_abstentions"
                and parent["payload"] == "forecast_rows_json",
                "H3 reference baseline reuse changes the estimator, policy or scoring role")
        require(all(cell[k] == parent[k] for k in ("predictions_sha256", "manifest_sha256", "gate_sha256",
                                                   "inputs_sha256", "source_sha256", "population_sha256", "cohort_rows"))
                and all(Path(cell[k]).resolve() == Path(parent[k]).resolve()
                        for k in ("predictions_path", "manifest_path", "gate_path"))
                and sorted(cell["event_ids"]) == sorted(cell["forecast_event_ids"]) == sorted(parent["event_ids"]),
                "H3 reference baseline reuse changes forecast bytes, source, inputs or cohort")
        require(parent["cell_id"] not in parents_used, "One baseline has multiple H3 reference reuses")
        parents_used.add(parent["cell_id"])
        cell["prediction_reuse_of"] = parent["cell_id"]
    for key in ("predictions_path", "commitment_path"):
        paths = [str(Path(c[key]).resolve()) for c in committed if not c.get("alias_of")
                 and not (key == "predictions_path" and c.get("prediction_reuse_of"))]
        require(len(paths) == len(set(paths)), f"Two cells share one {key}")


def checked_final_weights(reads, weight_root, weights, *, zero_shot_model=None):
    """Hash confined checkpoint files, or a pinned HF snapshot's own direct cache blobs."""
    root = Path(weight_root)
    require(isinstance(weights, dict) and weights, "Finals model weight map is empty")
    for relative, digest in weights.items():
        require(isinstance(relative, str) and relative not in ("", ".", "..") and not Path(relative).is_absolute()
                and ".." not in Path(relative).parts and str(Path(relative)) == relative,
                "Model weight requires a normalized relative path")
        entry = root / relative
        resolved = entry.resolve()
        if not resolved.is_relative_to(root.resolve()):
            require(isinstance(zero_shot_model, dict), "Model weight escapes its bound root")
            repository, revision = zero_shot_model.get("repository"), zero_shot_model.get("revision")
            require(isinstance(repository, str) and re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
                    and isinstance(revision, str) and re.fullmatch(r"[0-9a-f]{40}", revision)
                    and root.is_absolute() and root.resolve() == root
                    and Path(zero_shot_model.get("snapshot", "")) == root
                    and root.name == revision and root.parent.name == "snapshots"
                    and root.parent.parent.name == "models--" + repository.replace("/", "--"),
                    "Escaping zero-shot weight is not in its bound repository/revision cache")
            cache = root.parent.parent
            blobs = cache / "blobs"
            require(blobs.is_dir() and blobs.resolve() == blobs and resolved.parent == blobs
                    and re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", resolved.name)
                    and resolved.is_file() and not resolved.is_symlink()
                    and entry.is_symlink() and entry.parent.resolve() == entry.parent,
                    "Zero-shot weight must link directly to its own canonical repository blob")
            direct_link = Path(*([".."] * len(entry.parent.relative_to(cache).parts)), "blobs", resolved.name)
            require(entry.readlink() == direct_link, "Zero-shot cache link must be direct and relative")
        reads.file({"path": str(resolved), "sha256": digest}, "Finals model weights")


def adapt_retro_finals(family, reads):
    """``forecast_retro_finals.py`` ledger: zero-shot TSFM (R-tsfm) and adapted Chronos (R-chronos-ad) curves."""
    ledger = reads.ref(family["ledger"], "Retrospective finals ledger")
    require(ledger.get("status") == "approved_execution" and ledger.get("scores_authorized") is False
            and ledger.get("test_labels_authorized") is False, "Not an approved prediction-only finals ledger")
    require(family.get("verifier") and family["verifier"]["sha256"] == ledger.get("runner_sha256"),
            "Finals require their bound runner and source snapshot")
    verifier = bound_verifier(reads, family["verifier"], "r1_retro_finals_verifier")
    require(verifier.checked_ledger(family["ledger"]["path"], family["ledger"]["sha256"]) == ledger,
            "Finals verifier opened different ledger bytes")
    source = Path(family["snapshot"]["path"]).resolve()
    files = checked_snapshot(reads, source, family["snapshot"]["sha256"])
    gate = checked_review(reads.ref(ledger["review_gate"], "Finals review gate"))
    require(ledger.get("draft_sha256") and gate.get("command_plan_sha256") == ledger["draft_sha256"],
            "Finals approval covers another ledger draft")
    cells = []
    for run in ledger["runs"]:
        if run["kind"] == "fit":
            continue
        require(run["kind"] in ("zero_shot", "adapted"), f"Undeclared finals entry kind {run['kind']!r}")
        expect = run["expect"]
        argv = run["argv"]
        def argument(name, argv=argv):
            require(argv.count(name) == 1, f"Finals argv requires exactly one {name}")
            return argv[argv.index(name) + 1]
        require(argument("--expected-source-sha256") == expect["worker_sha256"]
                == files.get("scripts/forecast_retro_test_predict.py"), "Finals worker source differs")
        dataset = Path(argument("--dataset"))
        require(argument("--expected-partition-sha256") == expect["partition_sha256"], "Finals partition argv differs")
        protocol = reads.json(dataset / "partitions.json", expect["partition_sha256"], "Finals partition")
        require(not protocol.get("protected_test") and not protocol.get("locked_test"), "Protected finals refused")
        target = protocol["parts"]["test"]
        require(Path(target["inputs"]).name == target["inputs"] and Path(target["labels"]).name == target["labels"]
                and target["inputs"] != target["labels"], "Finals labels must be a separate local partition")
        reads.file({"path": str(dataset / target["inputs"]), "sha256": target["inputs_sha256"]}, "Finals inputs")
        role = {"arm_id": "R-tsfm" if run["kind"] == "zero_shot" else "R-chronos-ad", "model_family": run["kind"],
                "model": expect["model"], "seed": expect.get("seed"), "horizon_seconds": run.get("horizon_seconds"),
                "bin_seconds": run.get("bin_seconds")}
        require(Path(run["completion_path"]).is_file(), f"Unresolved cell (no completion): {run['run_id']}")
        completion_raw, completion_sha = reads.bytes(run["completion_path"])
        completion = json.loads(completion_raw)
        if completion.get("returncode") != 0:
            cells.append(_failed(family, run["run_id"], role, "nonzero prediction returncode",
                                 completion_sha256=completion_sha, returncode=completion.get("returncode")))
            continue
        out = Path(run["out"])
        commitment = reads.json(out / "commitment.json", completion.get("commitment_sha256"), "Finals commitment")
        _, predictions_sha = reads.bytes(out / "predictions.npz")
        require(predictions_sha == commitment.get("predictions_sha256") == completion.get("predictions_sha256"),
                f"Prediction bytes changed: {run['run_id']}")
        require(commitment.get("split") == "test" and commitment.get("test_labels_opened") is False
                and commitment.get("labels_opened") is False and commitment.get("scores_computed") is False
                and commitment.get("full_cohort") is True and commitment.get("events") == expect["events"] == R1_EVENTS
                and commitment.get("partition_receipt_sha256") == expect["partition_sha256"]
                and commitment.get("source_sha256") == expect["worker_sha256"]
                and commitment.get("model") == expect["model"], "Finals commitment differs from its declared run")
        if run["kind"] == "adapted":
            require(commitment.get("fit_receipt_sha256") == expect["fit_receipt_sha256"]
                    and commitment.get("seed") == expect["seed"], "Adapted prediction differs from its declared fit")
            fit_root = Path(argument("--fit-dir"))
            fit = reads.json(fit_root / "fit_receipt.json", expect["fit_receipt_sha256"], "Adapted fit receipt")
            selection_sha = argument("--expected-selection-sha256")
            selection = reads.json(argument("--selection"), selection_sha, "Adapted selection")
            require(fit.get("resource_pilot") is False and fit.get("scientific_comparison_eligible") is True
                    and fit.get("test_files_opened") is False and fit.get("validation_inputs_opened") is False
                    and fit["configuration"] == selection["selected_configuration"] == commitment["configuration"]
                    and fit["seed"] == expect["seed"] and fit["final_weights"] == commitment["final_weights"]
                    and commitment["selection_receipt_sha256"] == selection_sha
                    and fit["actual_optimizer_steps"] == fit["settings"]["num_steps"], "Adapted fit/selection differs")
            weight_root, weights = fit_root / "checkpoint", fit["final_weights"]
        else:
            model = family["models"][expect["model"]]
            require(commitment["repository"] == model["repository"] and commitment["revision"] == model["revision"],
                    "Zero-shot repository/revision differs from the reviewed model binding")
            weight_root, weights = Path(model["snapshot"]), commitment["weight_sha256"]
        checked_final_weights(reads, weight_root, weights,
                              zero_shot_model=model if run["kind"] == "zero_shot" else None)
        require(commitment.get("test_input_sha256") == target["inputs_sha256"]
                and commitment.get("adapter_source_sha256") == files.get("scripts/forecast_tsfm.py")
                and commitment.get("partition_loader_sha256") == files.get("src/bgbench/forecast_curve.py")
                and commitment.get("batch_size") == 4 and commitment.get("inference_seed") == 0,
                "Finals input/worker dependency chain differs")
        grid = commitment["grid"]
        require(grid["cutoff_seconds"] == protocol["delta_s"] and grid["bin_seconds"] == protocol["bin_seconds"],
                "Finals time grid differs from the bound partition")
        cells.append(_cell(family, run["run_id"], role, status="committed", completion_sha256=completion_sha,
                           commitment_path=str(out / "commitment.json"),
                           commitment_sha256=completion["commitment_sha256"],
                           predictions_path=str(out / "predictions.npz"), predictions_sha256=predictions_sha,
                           payload="curve_npz", model_sha256=expect.get("fit_receipt_sha256"),
                           source_sha256=expect["worker_sha256"], partition_sha256=expect["partition_sha256"],
                           population_events=R1_EVENTS, learned=run["kind"] == "adapted", probabilistic=True,
                           target_seconds=[300, 900, 3600, 7200],
                           context_seconds=list(range(0, grid["cutoff_seconds"] + 1, grid["bin_seconds"])),
                           labels={"path": str(dataset / target["labels"]), "sha256": target["labels_sha256"]}))
    return cells


def adapt_counts(family, reads):
    """``forecast_count_commitments.py`` sealed ``complete.json``: twelve count-control cells (R-counts)."""
    ledger = reads.ref(family["ledger"], "Count commitment ledger")
    require(ledger.get("scope") == "count-control-retrospective-test-commitments-v1"
            and ledger.get("test_scoring_authorized") is False, "Not a count commitment ledger")
    require(family.get("verifier") and family["verifier"]["sha256"] == ledger.get("driver_sha256"),
            "Counts require the bound producer verifier for complete source/fit/partition resolution")
    verifier = bound_verifier(reads, family["verifier"], "r1_count_verifier")
    checked = verifier.checked_ledger(family["ledger"]["path"], family["ledger"]["sha256"],
                                      ledger["review_gate_sha256"])
    require(checked == ledger, "Count verifier opened different ledger bytes")
    require(len(ledger["cells"]) == 12, "Count controls require all twelve retained cells")
    sealed = reads.ref(family["seal"], "Count commitment seal")
    require(sealed.get("ledger_sha256") == family["ledger"]["sha256"]
            and Path(family["seal"]["path"]).resolve() == Path(ledger["campaign"]).resolve() / "complete.json",
            "Count seal is not this ledger's seal at its path")
    require(ledger.get("test_population_sha256") == R1_POPULATION_SHA256 and ledger.get("test_events") == R1_EVENTS,
            "Count test population differs from R1")
    records = {r["run_id"]: r for r in sealed["cells"]}
    require([c["run_id"] for c in ledger["cells"]] == [r["run_id"] for r in sealed["cells"]],
            "Count seal does not cover every ledger cell")
    cells = []
    for cell in ledger["cells"]:
        record = records[cell["run_id"]]
        verified_record = verifier.verify_commitment(ledger, family["ledger"]["sha256"], cell)
        require(verified_record == record, "Count sealed cell differs from the complete producer verification")
        role = {"arm_id": "R-counts", "model_family": "count", "method": cell["method"],
                "configuration_id": cell["configuration"], "horizon_seconds": cell["delta_s"],
                "bin_seconds": cell["bin_seconds"]}
        completion = json.loads(reads.bound(cell["completion"], record["completion_sha256"], "Count completion"))
        require(completion.get("status") == "completed", f"Count cell not completed: {cell['run_id']}")
        output = Path(cell["output"])
        commitment = reads.json(output / "commitment.json", record["commitment_sha256"], "Count commitment")
        _, predictions_sha = reads.bytes(output / "predictions.npz")
        require(predictions_sha == record["predictions_sha256"] == commitment.get("predictions_sha256"),
                f"Prediction bytes changed: {cell['run_id']}")
        for key in ("checkpoint_sha256", "fit_receipt_sha256", "partitions_sha256", "test_inputs_sha256"):
            require(commitment.get(key) == cell[key], f"Count commitment {key} differs")
        require(commitment.get("test_population_sha256") == R1_POPULATION_SHA256
                and commitment.get("test_labels_opened") is False and commitment.get("scores_computed") is False,
                "Unexpected count commitment provenance")
        require(all(commitment.get(k) is False for k in
                    ("labels_opened", "fit_called", "metrics_called", "calibration_changed")),
                "Count commitment called a forbidden fit, metric, calibration or label path")
        probabilistic = cell["method"] == "boosted"
        require(cell.get("probabilistic") is probabilistic and commitment.get("probabilistic") is probabilistic
                and commitment.get("prediction_kind") == cell.get("prediction_kind")
                == ("quantile" if probabilistic else verifier.NONPROBABILISTIC),
                "Count method/quantile semantics differ")
        for key in ("run_id", "method", "configuration", "delta_s", "bin_seconds", "target_seconds", "context_seconds"):
            require(commitment.get(key) == cell[key], f"Count identity differs: {key}")
        require(commitment.get("ledger_sha256") == family["ledger"]["sha256"]
                and completion.get("ledger_sha256") == family["ledger"]["sha256"]
                and completion.get("review_gate_sha256") == ledger["review_gate_sha256"], "Count lineage differs")
        protocol = reads.json(Path(cell["dataset"]) / "partitions.json", cell["partitions_sha256"], "Count partition")
        target = protocol["parts"]["test"]
        reads.file({"path": cell["test_inputs"], "sha256": cell["test_inputs_sha256"]}, "Count test inputs")
        cells.append(_cell(family, cell["run_id"], role, status="committed", completion_sha256=record["completion_sha256"],
                           commitment_path=str(output / "commitment.json"), commitment_sha256=record["commitment_sha256"],
                           predictions_path=str(output / "predictions.npz"), predictions_sha256=predictions_sha,
                           payload="count_npz", model_sha256=cell["checkpoint_sha256"],
                           source_sha256=ledger["curve_source_sha256"], population_sha256=R1_POPULATION_SHA256,
                           population_events=R1_EVENTS, learned=probabilistic, probabilistic=probabilistic,
                           target_seconds=cell["target_seconds"], context_seconds=cell["context_seconds"],
                           labels={"path": str(Path(cell["dataset"]) / target["labels"]),
                                   "sha256": target["labels_sha256"]}))
    return cells


def bound_verifier(reads, ref, name):
    """Load externally pinned verifier source, admitting the user's actual Astra reviewer identity."""
    import sys
    import types
    raw = reads.bound(ref["path"], ref["sha256"], name)
    module = types.ModuleType(name)
    module.__file__ = str(Path(ref["path"]).resolve())
    sys.modules[name] = module
    exec(compile(raw, module.__file__, "exec"), module.__dict__)  # noqa: S102 - externally anchored captured source
    for dependency in [module, *module.__dict__.values()]:
        if isinstance(dependency, types.ModuleType) and hasattr(dependency, "REVIEWER"):
            dependency.REVIEWER = REVIEWER
    return module


TRANSFER_APPROVAL_MODULE = "forecast_transfer_prediction_approval"


def transfer_prediction_approval(family, reads, ledger):
    """The separate transfer prediction approval, anchored by the R1 family and never by the ledger itself.

    Ledgers prepared under the completed 44-fit campaign's separate prediction approval store its ref; the immutable
    fit marker never covered predictions. Such a ledger is accepted only when the family carries the identical
    external ref plus the externally pinned validator source. The validator is registered under its import name so
    the bound producer drivers resolve exactly this source, and it re-proves the 44 fits, the validation-only
    calibration and the approval while R1 is still closed (every verify_batch caller refuses after the marker).
    Returns the bound validator, or None for a ledger prepared under the original marker scope.
    """
    stored, external = ledger.get("separate_prediction_approval"), family.get("prediction_approval")
    if stored is None:
        require(external is None and family.get("prediction_approval_validator") is None,
                "A transfer prediction approval anchor names a ledger prepared without one")
        return None
    require(isinstance(external, dict) and set(external) == {"path", "sha256"} and external == stored,
            "Transfer prediction approval needs the identical external anchor; a stored ref never self-authorizes")
    reads.ref(external, "Separate transfer prediction approval")
    require(family.get("prediction_approval_validator"), "Transfer prediction approval needs its pinned validator source")
    return bound_verifier(reads, family["prediction_approval_validator"], TRANSFER_APPROVAL_MODULE)


def adapt_transfer(family, reads):
    """Primary Sep–Dec transfer test commitments, preserving the transfer training gate."""
    ledger = reads.ref(family["ledger"], "Transfer prediction ledger")
    require(ledger.get("driver_sha256") == family["verifier"]["sha256"], "Transfer producer source differs")
    verifier = bound_verifier(reads, family["verifier"], "r1_transfer_verifier")
    require(ledger.get("scope") == verifier.SCOPE_PREDICTIONS and ledger.get("test_scoring_authorized") is False,
            "Only primary-window transfer commitments are authorized by R1")
    fits = reads.json(ledger["fit_ledger"], ledger["fit_ledger_sha256"], "Transfer fit ledger")
    approval = transfer_prediction_approval(family, reads, ledger)
    if approval is None:
        verifier.checked_marker(fits["root"], verifier.SCOPE_PREDICTIONS, ledger["implementation_review_sha256"])
    else:
        require(Path(ledger["root"]).resolve() == Path(family["ledger"]["path"]).resolve().parent
                and len({(r["gate_path"], r["gate_sha256"]) for r in ledger["runs"]}) == 1,
                "Transfer prediction ledger root or gate differs")
        approval.checked(family["prediction_approval"], driver_path=family["verifier"]["path"],
                         fits_path=ledger["fit_ledger"], fits_sha=ledger["fit_ledger_sha256"],
                         marker_sha=ledger["implementation_review_sha256"], gate_path=ledger["runs"][0]["gate_path"],
                         out=ledger["root"], device=ledger["device"])
    transfer_gate = reads.json(fits["gate_path"], fits["gate_sha256"], "Transfer training gate")
    checked_snapshot(reads, fits["snapshot"], fits["snapshot_sha256"])
    runs = {r["run_id"]: r for r in fits["runs"]}
    require(len(runs) == len(fits["runs"]) and {e["fit_run_id"] for e in ledger["runs"]} == set(runs),
            "Transfer prediction ledger omits or invents fit cells")
    entries = []
    for entry in ledger["runs"]:
        receipt, member, completion = verifier.checked_fit(runs[entry["fit_run_id"]], transfer_gate)
        require(receipt and entry["checkpoint_sha256"] == completion["checkpoint_sha256"]
                and entry["fit_receipt_sha256"] == completion["fit_receipt_sha256"]
                and member["prediction_manifest"]["sha256"] == entry["manifest_sha256"],
                "Transfer prediction differs from its training fit/gate")
        entries.append({**entry, "run_id": entry["fit_run_id"], "fit_ledger": ledger["fit_ledger"],
                        "fit_ledger_sha256": ledger["fit_ledger_sha256"], "snapshot": fits["snapshot"],
                        "snapshot_sha256": fits["snapshot_sha256"]})
    cells = core_cells(family, reads, {**ledger, "runs": entries}, arm="R-transfer")
    for cell in cells:
        cell["role"]["variant"] = fits["variant"]
        cell["training_gate_sha256"] = fits["gate_sha256"]
    return cells


def adapt_transfer_secondary(family, reads):
    """Verify only the two extra subsets; the primary forecasts are joined by existing cell reference."""
    ledger = reads.ref(family["ledger"], "Transfer secondary ledger")
    approval = transfer_prediction_approval(family, reads, ledger)
    verifier = bound_verifier(reads, family["verifier"], "r1_transfer_secondary_verifier")
    require(ledger.get("driver_sha256") == family["verifier"]["sha256"], "Secondary source differs")
    if approval is None:
        verified, fits = verifier.checked_ledger(family["ledger"]["path"], family["ledger"]["sha256"])
    else:
        verified, fits = verifier.checked_ledger(family["ledger"]["path"], family["ledger"]["sha256"],
                                                 family["prediction_approval"])
    require(verified == ledger, "Secondary ledger changed during verification")
    union = reads.ref(family["union"], "Transfer secondary union")
    require(union.get("separate_prediction_approval") == family.get("prediction_approval"),
            "Secondary union was produced under another prediction approval")
    plan = reads.ref(union["plan"], "Transfer secondary population plan")
    require(verifier.checked_plan(union["plan"]["path"], union["plan"]["sha256"]) == plan,
            "Secondary plan changed during verification")
    require(union.get("passed") is True and union.get("secondary_ledger") == family["ledger"]
            and union.get("driver_sha256") == family["verifier"]["sha256"]
            and union.get("labels_read") is False and union.get("prediction_values_decoded") is False
            and union.get("secondary_events") == 8399 and union.get("secondary_population_sha256") == plan["secondary_population_sha256"],
            "Secondary union provenance differs")
    populations = {k: v["event_ids"] for k, v in plan["subsets"].items()}
    require(set(populations) == {"primary", "v6_other", "built"}
            and {k: len(v) for k, v in populations.items()} == {"primary": 3543, "v6_other": 4828, "built": 28}
            and population_sha256(populations["primary"]) == R1_POPULATION_SHA256
            and len({eid for ids in populations.values() for eid in ids}) == 8399
            and population_sha256([eid for ids in populations.values() for eid in ids]) == plan["secondary_population_sha256"], "Secondary subsets overlap or change population")
    run_map = {r["run_id"]: r for r in fits["runs"]}
    unions = {r["fit_run_id"]: r for r in union["fits"]}
    require(set(unions) == set(run_map) and len(unions) == len(union["fits"]), "Secondary union omits fit cells")
    entries = []
    for entry in ledger["runs"]:
        require(entry["subset"] in ("v6_other", "built")
                and entry["expected_test_ids"] == populations[entry["subset"]], "Secondary subset IDs differ")
        entries.append({**entry, "run_id": entry["fit_run_id"], "fit_ledger": ledger["fit_ledger"],
                        "fit_ledger_sha256": ledger["fit_ledger_sha256"], "snapshot": ledger["snapshot"],
                        "snapshot_sha256": ledger["snapshot_sha256"]})
    require(len(entries) == len(run_map) * 2 and
            {(e["fit_run_id"], e["subset"]) for e in entries} ==
            {(r, subset) for r in run_map for subset in ("v6_other", "built")}, "Secondary subset grid differs")
    cells = core_cells(family, reads, {**ledger, "runs": entries}, arm="R-transfer", secondary=True)
    for cell, entry in zip(cells, entries):
        require(cell["status"] == "committed", "Secondary mechanical union requires all subset commitments")
        union_fit = unions[entry["fit_run_id"]]
        part = union_fit["subsets"][entry["subset"]]
        require(part["predictions_sha256"] == cell["predictions_sha256"]
                and part["commitment_sha256"] == cell["commitment_sha256"]
                and union_fit["checkpoint_sha256"] == cell["model_sha256"], "Secondary union names other subset bytes")
        primary_id = family["primary_cells"][entry["fit_run_id"]]
        cell.update(secondary=True, secondary_union=family["union"], primary_cell_id=primary_id,
                    primary_binding=union_fit["subsets"]["primary"], secondary_population_sha256=plan["secondary_population_sha256"])
        cell["role"].update(variant=ledger["variant"], subset=entry["subset"], series="secondary_" + entry["subset"])
    return cells


def adapt_h1(family, reads):
    """Consume the sealed selected-K20 or OOD60 test ledger; validation60 cannot enter R1."""
    from . import forecast_h1_predictions as helper
    ledger = reads.ref(family["ledger"], "H1 prediction ledger")
    kind = ledger.get("kind")
    require(kind in ("selected-k-test", "ood-test"), "H1 validation predictions are not R1 cells")
    require(ledger.get("driver_sha256") == family["verifier"]["sha256"]
            and ledger.get("helper_sha256") == reads.digest(helper.__file__), "H1 source chain differs")
    driver = bound_verifier(reads, family["verifier"], "r1_h1_verifier")
    verified, _, spec, fc, root = driver.opened(family["ledger"]["path"], family["ledger"]["sha256"],
                                              family["approval"]["path"], family["approval"]["sha256"])
    require(verified == ledger, "H1 verifier opened different ledger bytes")
    driver.resolved_ledger(ledger, spec, fc)
    seal = reads.ref(family["seal"], "H1 commitment seal")
    require(seal.get("ledger_sha256") == family["ledger"]["sha256"]
            and seal.get("approval_sha256") == family["approval"]["sha256"]
            and seal.get("entries") == len(ledger["entries"]) == helper.KINDS[kind]["expected"],
            "H1 seal does not cover the complete reviewed test ledger")
    records = {r["name"]: r for r in seal["commitments"]}
    require(len(records) == len(seal["commitments"]) and set(records) == {r["name"] for r in ledger["entries"]},
            "H1 seal omits or duplicates cells")
    result = []
    for entry in ledger["entries"]:
        require(entry["split"] == "test", "Validation row in H1 test ledger")
        record = records[entry["name"]]
        paths = driver.paths(root, entry["name"], record["attempt"])
        doc = reads.json(paths["commitment"], record["commitment_sha256"], "H1 envelope")
        completion_raw, completion_sha = reads.bytes(paths["completion"])
        completion = json.loads(completion_raw)
        require(completion.get("committed") is True and completion.get("ledger_sha256") == family["ledger"]["sha256"]
                and completion.get("h1_commitment_sha256") == record["commitment_sha256"]
                and completion.get("predictions_sha256") == record["predictions_sha256"], "H1 completion differs")
        predictions = paths["output"] / "predictions.json"
        reads.bound(predictions, record["predictions_sha256"], "H1 forecasts")
        frozen = reads.json(paths["output"] / "commitment.json", doc["frozen_commitment_sha256"], "H1 frozen commitment")
        population = ledger["populations"][entry["population"]]
        helper.check_frozen_output(frozen, entry, population, record["predictions_sha256"], "test")
        require(doc == helper.h1_commitment(entry, population, frozen_commitment_sha256=doc["frozen_commitment_sha256"],
                                            predictions_sha256=record["predictions_sha256"], attempt=record["attempt"]),
                "H1 envelope differs from its exact typed contract")
        reads.file({"path": entry["checkpoint"], "sha256": entry["checkpoint_sha256"]}, "H1 checkpoint")
        snapshot_files = checked_snapshot(reads, entry["snapshot"], entry["snapshot_sha256"])
        calibration = {}
        if kind == "ood-test":
            core = reads.ref(spec["core"], "H1 OOD original core fits")
            original_runs = [r for r in core["runs"] + core.get("reused_runs", []) if r["run_id"] == entry["run_id"]]
            require(len(original_runs) == 1, "H1 OOD calibration fit is missing or duplicated")
            calibration["calibration_fit"] = {**calibration_fit_evidence(
                reads, original_runs[0], entry["checkpoint_sha256"], snapshot_files), "fit_ledger": spec["core"]}
        ids = population["event_ids"]
        cohort = checked_manifest(reads, entry["manifest"], entry["manifest_sha256"], ids)
        gate = reads.json(entry["input_gate"], entry["input_gate_sha256"], "H1 gate")
        expected = gate_inputs(gate, entry["manifest_sha256"], ids)
        role = {"arm_id": "R-h1" if kind == "selected-k-test" else "R-h1-ood", "model_family": "neural",
                **{k: entry[k] for k in ("horizon_seconds", "seed", "message_passing", "history", "candidate_history_k")},
                "kind": kind, "run_id": entry["run_id"]}
        result.append(_cell(family, entry["name"], role, status="committed", completion_sha256=completion_sha,
                            commitment_path=str(paths["commitment"]), commitment_sha256=record["commitment_sha256"],
                            predictions_path=str(predictions), predictions_sha256=record["predictions_sha256"],
                            payload="forecast_rows_json", model_sha256=entry["checkpoint_sha256"],
                            manifest_path=entry["manifest"], manifest_sha256=entry["manifest_sha256"],
                            gate_path=entry["input_gate"], gate_sha256=entry["input_gate_sha256"],
                            snapshot=entry["snapshot"], snapshot_sha256=entry["snapshot_sha256"],
                            source_sha256=entry["prediction_source_sha256"],
                            inputs_sha256=checked_inputs(reads, frozen["inputs"], expected),
                            population_sha256=population_sha256(ids), event_ids=ids, cohort_rows=cohort, learned=True, **calibration))
    return result


def history_variant_panel(entry, scope, reads):
    """Resolve H3 panels from the bound producer ledger; frozen declarations may omit them."""
    if entry["arm_id"] != "R-h3":
        return entry["panel"]
    parent = entry["parent"]
    binding = scope["parent_ledgers"][parent["ledger"]]
    require(binding["family"] == parent["family"]
            and binding["source"]["sha256"] == parent["ledger_sha256"],
            "H3 history parent ledger binding differs")
    ledger = reads.ref(binding["source"], "H3 history parent source")
    learned = parent["family"] == "h3"
    require((learned and ledger.get("scope") == "h3-frozen-sensitivity-retrospective-predictions-v1")
            or (parent["family"] == "baseline" and ledger.get("kind") == "h3_history_extent_index_v1"),
            "H3 history parent source has the wrong family/schema")
    matches = [row for row in ledger["runs" if learned else "entries"] if row["name"] == parent["name"]]
    require(len(matches) == 1, "H3 history parent cell is missing or duplicated")
    row = matches[0]
    panel = row["panel"]
    require(panel in ("ris7", "mixed7") and entry["panel"] in (None, panel)
            and row["horizon_seconds"] == entry["horizon"]
            and row.get("seed") == entry["seed"], "H3 history parent panel/horizon/seed differs")
    if entry["status"] == "planned":
        if learned:
            require({"path": row["checkpoint"], "sha256": row["checkpoint_sha256"]}
                    == parent["model"] == entry["model"], "H3 history parent checkpoint differs")
            expected = Path(ledger["root"]) / "commitments" / f'{row["name"]}.json'
            require(Path(parent["commitment"]["path"]).resolve() == expected.resolve(),
                    "H3 history parent commitment path differs")
            commitment = reads.ref(parent["commitment"], "H3 history parent commitment")
            require(all(commitment.get(key) == row[key] for key in
                        ("name", "panel", "horizon_seconds", "run_id", "availability_sha256"))
                    and commitment.get("test_labels_used") is False,
                    "H3 history parent commitment identity differs")
        else:
            require(entry["model"] is None and parent["model"] is None
                    and row["baseline_commitment"] == parent["commitment"],
                    "H3 history parent baseline commitment/model differs")
    return panel


def adapt_history_variant(family, reads):
    """Consume every scoped delayed/withheld cell from the canonical typed commitment index."""
    from . import forecast_history_variants as variants
    ledger = reads.ref(family["ledger"], "History variant ledger")
    receipt = reads.ref(family["receipt"], "History variant receipt")
    index = reads.ref(family["index"], "History variant index")
    scope = reads.ref(family["consumer_scope"], "History consumer scope")
    variant = family["variant"]
    variants.verify_receipt_bundle(receipt, ledger, index, scope, variant=variant)
    withholding = ({"kind": variants.WITHHOLD_KIND, "retraining_fits": receipt["retraining_fits"],
                    "policy_sha256": receipt["policy_sha256"], "withheld_event_ids": receipt["withheld_ids"]}
                   if variant == "withhold" else None)
    identity = variants.intervention_identity(variant, spec=withholding)
    if variant != "withhold":
        primary_gate = reads.ref(family["primary_gate"], "Delay primary history gate")
        variant_gate = reads.ref(family["variant_integration_gate"], "Delay integrated history gate")
        require(receipt.get("primary_library_digest") == gate_library_digest(primary_gate)
                and receipt.get("variant_library_digest") == gate_library_digest(variant_gate)
                and receipt.get("variant_input_gate_sha256") == family["variant_integration_gate"]["sha256"],
                "Delay receipt library, gate or primary cohort differs")

    entries = {e["cell_id"]: e for e in ledger["entries"]}
    result = []
    for record in index["entries"]:
        entry = entries[record["cell_id"]]
        panel = history_variant_panel(entry, scope, reads)
        role = {"arm_id": "R-withhold" if variant == "withhold" else "R-delay",
                "parent_arm": entry["arm_id"], "model_family": "baseline" if entry.get("model") is None else "neural",
                "horizon_seconds": entry["horizon"], "seed": entry["seed"], "panel": panel,
                "series": entry["series"], "variant": variant}
        if record["status"] == "failed":
            reads.ref(record["failure_receipt"], "History failed-cell receipt")
            result.append(_failed(family, record["cell_id"], role, "bound_history_prediction_or_parent_failure",
                                  failure_receipt=record["failure_receipt"]))
            continue
        doc = reads.ref(record["commitment"], "History prediction commitment")
        predictions = record["predictions"]
        reads.bound(predictions["path"], predictions["sha256"], "History variant forecasts")
        require(doc.get("predictions_sha256") == predictions["sha256"], "History index differs from forecast commitment")
        frozen_path = Path(predictions["path"]).parent / "commitment.json"
        require(not (panel in ("ris7", "mixed7") and entry["model"] is None
                     and "frozen_commitment_sha256" in doc),
                "H3 history baseline cannot use learned frozen-commitment identity")
        if doc.get("frozen_commitment_sha256"):
            original = reads.json(frozen_path, doc["frozen_commitment_sha256"], "History original frozen commitment")
        elif (panel in ("ris7", "mixed7") and entry["model"] is None
              and doc.get("kind") == "h3_history_baseline_extent_commitment" and doc.get("family") == "history"):
            original = reads.json(frozen_path, doc["baseline_commitment_sha256"],
                                  "History original baseline commitment")
        else:
            require(Path(record["commitment"]["path"]).resolve() == frozen_path.resolve(),
                    "History commitment is neither original nor a bound typed envelope")
            original = doc
        require(original.get("test_labels_used") is False and original.get("predictions_sha256") == predictions["sha256"],
                "History commitment provenance differs")
        manifest_ref, gate_ref = entry["variant_manifest"], entry["variant_gate"]
        manifest = reads.ref(manifest_ref, "History variant manifest")
        gate = reads.ref(gate_ref, "History variant gate")
        require(gate.get("intervention") == identity
                and original.get("manifest_sha256") == manifest_ref["sha256"]
                and original.get("input_gate_sha256") == gate_ref["sha256"], "History forecast intervention/gate differs")
        ids = original["event_ids"]
        cohort = checked_manifest(reads, manifest_ref["path"], manifest_ref["sha256"], ids)
        inputs = gate_inputs(gate, manifest_ref["sha256"], ids)
        source = family["source_bindings"][record["cell_id"]]
        files = checked_snapshot(reads, source["snapshot"], source["snapshot_sha256"])
        source_hash = original.get("prediction_source_sha256", original.get("baseline_source_sha256"))
        require(source_hash in files.values(), "History prediction source is outside its reviewed snapshot")
        if entry["model"]:
            reads.file(entry["model"], "History frozen checkpoint")
            require(original.get("checkpoint_sha256") == entry["model"]["sha256"], "History checkpoint differs")
        else:
            require(manifest.get("history_sensitivity"), "History baseline lacks intervention manifest")
        extra = {}
        payload = "forecast_rows_json"
        if panel in ("ris7", "mixed7"):
            require(doc.get("panel") == panel and doc.get("forecast_event_ids") == sorted(ids),
                    "H3 history variant lacks its full-reference typed envelope")
            driver, args, per_horizon, audits, reference_gate = checked_h3_alignment(family, reads)
            delta = entry["horizon"]
            reference = per_horizon[delta][0]
            require(doc.get("panel") == panel and doc.get("forecast_event_ids") == sorted(ids)
                    and doc.get("reference_event_ids_sha256") == population_sha256(reference),
                    "H3 history variant lacks its full-reference typed envelope")
            reference_path, reference_sha = driver.pair(getattr(args, f"reference_manifest_d{delta}"))
            cohort = checked_manifest(reads, reference_path, reference_sha, reference)
            gate_inputs(reference_gate, reference_sha, reference)
            projection = source.get("curve_projection") if entry["model"] else "none"
            require(projection in ("cummax", "none"), "H3 history variant projection is unbound")
            if entry["model"]:
                fit = reads.ref(source["fit_receipt"], "H3 history variant original fit")
                require(fit.get("checkpoint_sha256") == entry["model"]["sha256"]
                        and fit["model"]["curve_projection"] == projection, "H3 variant fit projection differs")
            else:
                from types import SimpleNamespace
                lineage = source["history_lineage"]
                for ref in lineage.values():
                    reads.file(ref, "H3 variant history lineage")
                driver.history_lineage(SimpleNamespace(**{
                    key: f'{lineage[key]["path"]}:{lineage[key]["sha256"]}'
                    for key in ("baseline_commitment", "baseline_source", "history_sidecar")}),
                    doc, predictions["sha256"])

            extra = {"forecast_event_ids": sorted(ids),
                     "reference_manifest": {"path": reference_path, "sha256": reference_sha},
                     "reference_gate": family["alignment"]["reference_gate"],
                     "h3_context": {"arm": panel, "horizon": delta,
                                    "family": "learned" if entry["model"] else "history",
                                    "rows": per_horizon[delta][1][panel],
                                    "binding": driver.s.h3_binding(doc, audits[(panel, delta)], reference),
                                    "temporal_monotone": projection == "cummax"}}
            ids = reference
            payload = "forecast_rows_json_with_abstentions"
        result.append(_cell(family, record["cell_id"], role, status="committed",
                            commitment_path=record["commitment"]["path"], commitment_sha256=record["commitment"]["sha256"],
                            predictions_path=predictions["path"], predictions_sha256=predictions["sha256"],
                            payload=payload, model_sha256=entry["model"]["sha256"] if entry["model"] else None,
                            manifest_path=manifest_ref["path"], manifest_sha256=manifest_ref["sha256"],
                            gate_path=gate_ref["path"], gate_sha256=gate_ref["sha256"], source_sha256=source_hash,
                            snapshot=source["snapshot"], snapshot_sha256=source["snapshot_sha256"],
                            inputs_sha256=checked_inputs(reads, original["inputs"], inputs),
                            population_sha256=population_sha256(ids), event_ids=ids, cohort_rows=cohort,
                            learned=entry["model"] is not None, **extra))
    return result


STABLE_VERIFIER_MODULES = {
    "fam": "bgbench.forecast_history_families",
    "sp": "bgbench.forecast_stable_peer",
    "campaign": "forecast_stable_peer_campaign",
    "fc": "forecast_campaign",
    "stage": "stage_stable_peer_inputs",
}
STABLE_VARIANTS_MODULE = "bgbench.forecast_history_variants"


def stable_bound_verifier(family, reads, ledger):
    """Load the original stable verifier's exact private source closure.

    A cached current bgbench package must not substitute newer source into the
    immutable producer ledger. Canonical module names remain intact because the
    producer reconstructs its dependency hash map from them.
    """
    import builtins
    import importlib.util
    import sys
    import types

    direct = set(STABLE_VERIFIER_MODULES.values())
    refs = family.get("verifier_dependencies", {})
    require(isinstance(refs, dict) and set(refs) == direct | {STABLE_VARIANTS_MODULE},
            "Stable verifier requires its exact six-module source closure")
    require(ledger.get("dependency_sha256") == {name: refs[name]["sha256"] for name in direct},
            "Stable verifier dependencies differ from original ledger")
    require(ledger.get("source_sha256") == family["verifier"]["sha256"], "Stable producer source differs")
    all_refs = {**refs, "r1_stable_verifier": family["verifier"]}
    # Verify every source before executing any of it.
    sources = {name: reads.bound(ref["path"], ref["sha256"], "Stable source " + name)
               for name, ref in all_refs.items()}
    private = {}
    package = types.ModuleType("bgbench")
    package.__path__ = []
    private_sys = types.ModuleType("sys")
    private_sys.__dict__.update(vars(sys))
    private_sys.path = list(sys.path)
    private_sys.modules = dict(sys.modules)

    def private_import(name, globals=None, locals=None, fromlist=(), level=0):
        absolute = (importlib.util.resolve_name("." * level + name, globals["__package__"])
                    if level else name)
        if absolute == "sys":
            return private_sys
        if absolute == "bgbench":
            require(fromlist and all("bgbench." + child in refs for child in fromlist),
                    "Unbound stable package import")
            for child in fromlist:
                setattr(package, child, load("bgbench." + child))
            return package
        if absolute in refs:
            module = load(absolute)
            if not fromlist and absolute.startswith("bgbench."):
                setattr(package, absolute.split(".", 1)[1], module)
                return package
            return module
        require(not absolute.startswith("bgbench."), "Unbound stable dependency import")
        return builtins.__import__(name, globals, locals, fromlist, level)

    def load(name):
        if name in private:
            return private[name]
        module = types.ModuleType(name)
        module.__file__ = str(Path(all_refs[name]["path"]).resolve())
        module.__package__ = name.rpartition(".")[0]
        module.__builtins__ = {**vars(builtins), "__import__": private_import}
        private[name] = module
        exec(compile(sources[name], module.__file__, "exec"), module.__dict__)  # noqa: S102
        if hasattr(module, "REVIEWER"):
            module.REVIEWER = REVIEWER
        return module

    verifier = load("r1_stable_verifier")
    for alias, name in STABLE_VERIFIER_MODULES.items():
        require(getattr(verifier, alias, None) is load(name), "Stable verifier dependency identity differs")
    fam, variants = load(STABLE_VERIFIER_MODULES["fam"]), load(STABLE_VARIANTS_MODULE)
    require(fam.PARENT_LEDGER_KIND == variants.PARENT_LEDGER_KIND
            and fam.VariantError is variants.VariantError and fam.require is variants.require,
            "Stable family variant symbols differ")
    return verifier


def adapt_stable(family, reads):
    """Retain all24 stable cells and bind their own stable target source, including abstentions."""
    index = reads.ref(family["ledger"], "Stable prediction index")
    require(index.get("kind") == "stable_peer_prediction_index_v1", "Wrong stable index")
    ledger = reads.ref(index["ledger"], "Stable prediction scope")
    require(ledger.get("source_sha256") == family["verifier"]["sha256"], "Stable producer source differs")
    verifier = stable_bound_verifier(family, reads, ledger)
    outputs = [str(Path(c["commitment"]["path"]).parent) for c in index["cells"]]
    require(verifier.commitment_index(index["ledger"], outputs) == index, "Stable index differs from its complete verification")
    spec = ledger["spec"]
    linkage = reads.ref(index["target_linkage"], "Stable own-target linkage")
    stage = reads.ref(spec["stage_receipt"], "Stable stage receipt")
    verifier.stage.check_stage_data(stage)
    own = linkage["stable_target_source"]
    table = {"path": str(Path(own["data_root"]) / "eventset/2025_leak/events.parquet"),
             "sha256": own["event_tables_sha256"]["2025"]}
    # Hash only before R1. Target rows are decoded only by the post-marker scorer.
    reads.file(table, "Stable own-target event table")
    result = []
    for entry, record in zip(ledger["cells"], index["cells"], strict=True):
        doc = reads.ref(record["commitment"], "Stable commitment")
        predictions = record["predictions"]
        reads.bound(predictions["path"], predictions["sha256"], "Stable forecasts")
        output = Path(predictions["path"]).parent
        original = {"path": str(output / "predictor/predictions.json"), "sha256": doc["original_predictions_sha256"]}
        projection = {"path": str(output / "predictor/stable-input-projection.json"), "sha256": doc["input_projection_sha256"]}
        reads.bound(original["path"], original["sha256"], "Stable original forecasts")
        reads.bound(projection["path"], projection["sha256"], "Stable issue-time seed projection")
        delta = entry["delta_s"]
        manifest_ref = spec["manifests"][str(delta)]
        manifest = reads.ref(manifest_ref, "Stable own-target manifest")
        population = verifier.test_population(manifest)
        checked_manifest(reads, manifest_ref["path"], manifest_ref["sha256"], population["built"])
        gate = reads.ref(spec["gate"], "Stable gate")
        inputs = gate_inputs(gate, manifest_ref["sha256"], population["built"])
        require(len(inputs) == len(population["built"]), "Stable gate omits built targets")
        source = entry.get("parent_entry")
        snapshot = source["snapshot"] if source else spec["baseline_snapshot"]["path"]
        snapshot_sha = source["snapshot_sha256"] if source else spec["baseline_snapshot"]["sha256"]
        checked_snapshot(reads, snapshot, snapshot_sha)
        role = {"arm_id": "R-stable", "model_family": "neural" if entry["model"] else "baseline",
                "horizon_seconds": delta, "seed": entry["seed"], "stable_arm": entry["arm"]}
        name = f"{entry['arm']}-d{delta}-s{entry['seed']}"
        result.append(_cell(family, name, role, status="committed", commitment_path=record["commitment"]["path"],
                            commitment_sha256=record["commitment"]["sha256"], predictions_path=predictions["path"],
                            predictions_sha256=predictions["sha256"], payload="stable_full_population_json",
                            manifest_path=manifest_ref["path"], manifest_sha256=manifest_ref["sha256"],
                            gate_path=spec["gate"]["path"], gate_sha256=spec["gate"]["sha256"],
                            model_sha256=entry["model"]["sha256"] if entry["model"] else None,
                            population_sha256=population_sha256(population["all"]), event_ids=population["all"],
                            learned=entry["model"] is not None, snapshot=snapshot, snapshot_sha256=snapshot_sha,
                            stable_target_table=table, stable_target_linkage=index["target_linkage"],
                            stable_context={"verifier": family["verifier"], "manifest": manifest,
                                            "original": original, "projection": projection, "arm": entry["arm"],
                                            "built": population["built"], "abstentions": population["abstentions"]}))
    return result


def adapt_disposition(family, reads):
    """Retain every unavailable Mean/order cell using the reviewed producer's full verifier."""
    doc = reads.ref(family["ledger"], "Terminal disposition")
    driver = family["verifier"]
    require(len(family["arm_ids"]) == 1, "A terminal disposition must serve exactly one arm")
    module = bound_verifier(reads, driver, "r1_disposition_verifier")
    checked = module.checked_disposition(family["ledger"]["path"], family["ledger"]["sha256"])
    require(checked == doc, "Disposition verifier returned other content")
    arm = family["arm_ids"][0]
    source_key = "driver_sha256" if arm == "R-mean" else "adapter_sha256"
    require(doc.get(source_key) == driver["sha256"] and doc.get("executable") is False
            and doc.get("runs") == [] and doc.get("predictions") == []
            and doc.get("prediction_count") == 0 and doc.get("fit_count") == 0,
            "Disposition is not a source-bound unavailable arm")
    cells = doc["cells"]
    require(len(cells) == 10 and {(c["horizon_seconds"], c["seed"]) for c in cells}
            == {(h, seed) for h in (30, 60) for seed in range(5)}, "Disposition omits retained cells")
    result = []
    for cell in cells:
        require(cell["status"] == "not_executable_no_finite_last_configuration"
                and cell["last_failure_chain_sha256"] == doc["last_failure_chain_sha256"],
                "Disposition cell lacks its terminal failure chain")
        role = {"arm_id": arm, "model_family": "temporal", "kind": cell["kind"],
                "horizon_seconds": cell["horizon_seconds"], "seed": cell["seed"], "configuration_id": None}
        result.append(_failed(family, cell["run_id"], role, cell["status"],
                              disposition=family["ledger"], verifier=driver,
                              last_failure_chain_sha256=doc["last_failure_chain_sha256"]))
    return result


FORMATS = {
    "transfer_secondary_v1": (adapt_transfer_secondary, {"R-transfer"}),
    "h3_history_extent_index_v1": (adapt_h3_history, {"R-h3"}),
    "stable_prediction_index_v1": (adapt_stable, {"R-stable"}),
    "history_variant_index_v1": (adapt_history_variant, {"R-delay", "R-withhold"}),
    "transfer_primary_v1": (adapt_transfer, {"R-transfer"}),
    "h1_sealed_test_v1": (adapt_h1, {"R-h1", "R-h1-ood"}),
    "terminal_disposition_v1": (adapt_disposition, {"R-mean", "R-temporal-order"}),
    "core_gbdt_commitments_v1": (adapt_core_gbdt, {"R-core", "R-gbdt"}),
    "deterministic_baseline_v1": (adapt_deterministic, {"R-base"}),
    "temporal_finals_v1": (adapt_temporal, {"R-temporal"}),
    "h3_frozen_v1": (adapt_h3, {"R-h3"}),
    "retro_finals_v1": (adapt_retro_finals, {"R-tsfm", "R-chronos-ad"}),
    "count_commitments_v1": (adapt_counts, {"R-counts"}),
}


# --------------------------------------------------------------------------- batch prerequisites

def checked_recipes(reads, ref):
    from . import forecast_recipes
    receipt = checked_review(reads.ref(ref, "New-period recipe freeze receipt"))
    require(receipt.get("module_source_sha256") == reads.digest(forecast_recipes.__file__),
            "Recipe freeze was reviewed against another recipe verifier")
    issues = forecast_recipes.receipt_issues(receipt, lambda path: reads.bytes(path)[0])
    require(not issues, f"Recipe freeze is incomplete or changed: {issues}")
    require(receipt.get("kind") == "new_period_recipe_freeze" and receipt.get("frozen_before_r1") is True,
            "New-period recipes are not recorded as frozen before R1")
    recipes = receipt.get("recipes") or {}
    missing = [r for r in REQUIRED_RECIPES if r not in recipes]
    require(not missing, f"New-period recipes not frozen: {missing}")
    bound = {}
    for name, item in sorted(recipes.items()):
        if item == "declared_absent":
            require(name in DECLARABLE_ABSENT, f"{name} cannot be declared absent")
            bound[name] = item
            continue
        doc = reads.ref(item, f"Recipe {name}")
        require(doc.get("arm", name) == name, f"Recipe file of {name} names another arm")
        bound[name] = item["sha256"]
    return bound


def bound_file(reads, ref, what):
    reads.file(ref, what)
    return ref["sha256"]


def gate_library_digest(gate):
    digests = {r.get("forecast_contract", {}).get("history_source_digest")
               for m in gate.get("manifests", []) for r in m.get("inputs", [])}
    require(gate.get("passed") is True and len(digests) == 1 and None not in digests,
            "Integration gate must pass and name exactly one history library")
    return digests.pop()


def checked_sensitivity(reads, refs, cohort_ids, primary_gates, guard):
    """Call the history-withholding reporting guard on the hash-verified receipts (never a boolean claim)."""
    from .forecast_history_variants import verify_receipt_bundle
    keys = ("spec", "impact_report_30", "impact_report_60", "frozen_model_receipt", "integration_gate",
            "frozen_model_ledger", "commitment_index", "consumer_scope")
    require(isinstance(refs, dict) and set(refs) == set(keys), f"History sensitivity must bind exactly {keys}")
    docs = {k: reads.ref(refs[k], f"History sensitivity {k}") for k in keys}
    verify_receipt_bundle(docs["frozen_model_receipt"], docs["frozen_model_ledger"],
                          docs["commitment_index"], docs["consumer_scope"], variant="withhold")
    require(docs["commitment_index"]["entries"], "History sensitivity index is empty")
    for entry in docs["commitment_index"]["entries"]:
        if entry["status"] == "committed":
            commitment = reads.ref(entry["commitment"], "History sensitivity commitment")
            reads.bound(entry["predictions"]["path"], entry["predictions"]["sha256"], "History sensitivity predictions")
            require(commitment.get("predictions_sha256") == entry["predictions"]["sha256"],
                    "History sensitivity index names other predictions")
        else:
            reads.ref(entry["failure_receipt"], "History sensitivity failure")
    require(refs["integration_gate"]["sha256"] in primary_gates,
            "Sensitivity integration gate is not the gate of the primary core cells")
    result = guard(Path(refs["spec"]["path"]), {30: docs["impact_report_30"], 60: docs["impact_report_60"]},
                   docs["frozen_model_receipt"], library_digest=gate_library_digest(docs["integration_gate"]),
                   cohort_event_ids=list(cohort_ids))
    require(reads.digest(refs["spec"]["path"]) == refs["spec"]["sha256"], "Sensitivity spec changed during the guard")
    return result


def checked_history_reporting_binding(family, sensitivity):
    """The reported withholding impact must describe the exact retained history bundle."""
    if family["format"] != "history_variant_index_v1":
        return
    require(family["consumer_scope"] == sensitivity["consumer_scope"],
            "History family and reporting guard name different consumer scopes")
    if family["variant"] == "withhold":
        require(all(family[key] == sensitivity[target] for key, target in (
            ("ledger", "frozen_model_ledger"), ("index", "commitment_index"),
            ("receipt", "frozen_model_receipt"))),
            "Withholding family and reporting guard name different frozen bundles")


def checked_decision_rules(reads, refs, cells, slice_ref=None, calibration_binding=None):
    """Validation-calibrated slice/remainder thresholds for every committed learned membership cell."""
    provenance = None
    if calibration_binding is not None:
        provenance = reads.ref(calibration_binding["receipt"], "Original decision calibration publication")
        source = calibration_binding["source"]
        files = checked_snapshot(reads, source["path"], source["sha256"])
        require(provenance.get("passed") is True and provenance.get("test_outcomes_opened") is False
                and provenance.get("new_threshold_search") is False
                and provenance.get("slice_rule_sha256") == slice_ref["sha256"]
                and provenance.get("driver_sha256") == files["scripts/forecast_campaign.py"],
                "Original calibration publication/source differs")
        for fit_ref in provenance["fit_ledgers"]:
            reads.ref(fit_ref, "Published calibration fit ledger")
        require(len({r["run_id"] for r in provenance["decision_rules"]}) == len(provenance["decision_rules"]),
                "Calibration publication duplicates a run")
    out, learned = {}, {c["cell_id"] for c in cells if c["format"] in
                       ("core_gbdt_commitments_v1", "h1_sealed_test_v1") and not c.get("alias_of")}
    for cell in cells:
        if cell["status"] != "committed" or cell["cell_id"] not in learned:
            continue
        ref = (refs or {}).get(cell["cell_id"])
        require(ref is not None, f"Decision rules not prepared for {cell['cell_id']} (frozen from validation)")
        rules = reads.ref(ref, f"Decision rules of {cell['cell_id']}")
        require(rules.get("calibration_split") == "validation" and rules.get("test_outcomes_used") is False
                and isinstance(rules.get("slice_rule"), dict)
                and all(type(rules.get(k)) in (int, float) and math.isfinite(rules[k]) and 0 <= rules[k] <= 1.01
                        for k in ("global_threshold", "slice_threshold", "remainder_threshold")),
                "Decision rules must be validation-only slice/remainder thresholds")
        require(slice_ref is not None, "Decision rules need the exact frozen slice source")
        slices = reads.ref(slice_ref, "Frozen slice rule")
        delta = str(cell["role"]["horizon_seconds"])
        require(rules.get("slice_rules_sha256") == slice_ref["sha256"]
                and rules["slice_rule"] == {k: slices["horizons"][delta][k] for k in ("variable", "cut")}
                and slices.get("fit_outcomes_used") is False, "Decision rule slice provenance differs")
        if cell["role"]["arm_id"] != "R-h1":
            evidence = cell.get("calibration_fit")
            expected_source = evidence["source_sha256"] if evidence else None
            if provenance is not None:
                published = [r for r in provenance["decision_rules"] if r["run_id"] == rules.get("run_id")]
                require(evidence is not None and evidence.get("fit_ledger") in provenance["fit_ledgers"]
                        and len(published) == 1 and published[0]["path"] == ref["path"]
                        and published[0]["sha256"] == ref["sha256"]
                        and published[0]["validation_predictions_sha256"] == evidence["validation_predictions_sha256"],
                        "Decision rule is not bound to its published original calibration")
                expected_source = provenance["driver_sha256"]
            require(evidence is not None and rules.get("run_id") == evidence["run_id"]
                    and rules["global_threshold"] == evidence["threshold"]
                    and rules.get("validation_predictions_sha256") == evidence["validation_predictions_sha256"]
                    and rules.get("source_sha256") == expected_source
                    and datetime.fromisoformat(slices["created_utc"]) < datetime.fromisoformat(evidence["completed_utc"]),
                    "Decision rules differ from the original validation fit/source")
        cell["decision_global_threshold"] = rules["global_threshold"]
        out[cell["cell_id"]] = ref["sha256"]
    require(set(refs or {}) <= learned, "Decision rules bound for cells that are not learned membership cells")
    return out


def checked_h1_calibration(reads, binding, cells, rules):
    selected = [c for c in cells if c["role"]["arm_id"] == "R-h1" and c["status"] == "committed"]
    if not selected:
        require(binding is None, "H1 calibration bound without selected-K cells")
        return None
    require(binding is not None, "H1 selected-K test cells require the complete validation-only calibration commitment")
    doc = reads.ref(binding["commitment"], "H1 calibration commitment")
    require(doc.get("scope") == "h1-calibration-v1" and doc.get("interface_version") == 1
            and doc.get("complete") is True and doc.get("test_inputs_opened") is False
            and doc.get("test_outcomes_used") is False, "Invalid H1 calibration commitment")
    evidence = doc["evidence"]
    require(evidence["adapter_sha256"] == binding["verifier"]["sha256"], "H1 calibration source differs")
    verifier = bound_verifier(reads, binding["verifier"], "r1_h1_calibration_verifier")
    specification = reads.ref(evidence["spec"], "H1 calibration specification")
    audit = reads.ref(evidence["metadata_audit"], "H1 calibration metadata audit")
    require(audit.get("spec") == evidence["spec"] and audit.get("validation_values_opened") is False
            and audit.get("test_inputs_opened") is False
            and audit.get("numerical_source_map") == evidence["numerical_source_map"],
            "H1 calibration audit/source map differs")
    for field, spec_key in (("slice_rule", "rule"), ("selection", "selection"), ("finals", "finals")):
        require(evidence[field] == specification[spec_key], "H1 calibration specification evidence differs")
        reads.ref(evidence[field], "H1 calibration " + field)
    audited = {r["run"]["run_id"]: r for r in audit["records"]}
    require(len(audited) == len(audit["records"]) == 20, "H1 calibration audit omits fits")
    verifier.approval_check(evidence["approval"], evidence["spec"], evidence["metadata_audit"], specification)
    records = {r["run_id"]: r for r in doc["decision_rules"]}
    require(len(records) == len(doc["decision_rules"]) == len(selected) == 20
            and set(records) == {c["role"]["run_id"] for c in selected}, "H1 calibration does not cover exactly twenty fits")
    for cell in selected:
        entry = records[cell["role"]["run_id"]]
        rule = reads.ref(entry, "H1 validation decision rule")
        record = audited[cell["role"]["run_id"]]
        fit = reads.ref(record["fit_receipt"], "H1 calibration audited fit receipt")
        reads.ref(record["completion"], "H1 calibration audited fit completion")
        require(record["checkpoint"]["sha256"] == cell["model_sha256"]
                and reads.digest(record["checkpoint"]["path"]) == cell["model_sha256"]
                and rule.get("fit_receipt_sha256") == record["fit_receipt"]["sha256"]
                and rule.get("validation_predictions_sha256") == record["predictions"]["sha256"]
                and reads.digest(record["predictions"]["path"]) == record["predictions"]["sha256"]
                and rule.get("global_threshold") == fit.get("threshold")
                and rule.get("source_sha256") == evidence["numerical_source_map"]["scripts/forecast_campaign.py"],
                "H1 calibration does not bind this checkpoint and its unchanged global threshold")
        require(entry["sha256"] == rules[cell["cell_id"]]["sha256"]
                and Path(entry["path"]).resolve() == Path(rules[cell["cell_id"]]["path"]).resolve()
                and rule.get("candidate_history_k") == 500
                and rule.get("slice_rules_sha256") == evidence["slice_rule"]["sha256"]
                and rule.get("fit_ledger_sha256") == evidence["finals"]["sha256"]
                and rule.get("adapter_sha256") == evidence["adapter_sha256"], "H1 decision rule provenance differs")
    return binding["commitment"]["sha256"]


def checked_coverage(ledger_doc, families, exclusions):
    require(ledger_doc.get("kind") == "r1_retained_arm_ledger", "Retained-arm ledger is not the R1 JSON ledger")
    arms = [a["arm_id"] for a in ledger_doc.get("arms", [])]
    require(len(arms) == len(set(arms)), "Duplicate arm in the retained-arm ledger")
    missing = [a for a in R1_LEDGER_ARMS if a not in arms]
    require(not missing, f"Retained-arm ledger lacks R1 arms {missing}")
    excluded = {e["arm_id"]: e for e in exclusions}
    require(len(excluded) == len(exclusions) and set(excluded) <= EXCLUDABLE,
            "Every retained arm, including R-h3, must be resolved")
    bound = {a for f in families for a in f["arm_ids"]}
    if "R-panelfix" in arms and "R-core" in bound:
        bound.add("R-panelfix")
    require(not bound & set(excluded), "An arm is both bound and excluded")
    for arm in arms:
        if arm in excluded:
            continue
        require(arm not in UNSUPPORTED_ARMS, f"{arm}: unsupported committed schema ({UNSUPPORTED_ARMS.get(arm)})")
        require(arm in bound, f"Retained arm {arm} has no committed binding")
    require(bound <= set(arms), "A bound arm is not in the retained-arm ledger")
    return sorted(arms)


def checked_h3_reference_bindings(reads, reference, cells):
    """Bind the twenty existing history-on core forecasts as H3's reference-panel comparisons."""
    if not any(c["role"]["arm_id"] == "R-h3" for c in cells):
        require(reference is None, "H3 references supplied without H3 cells")
        return None
    require(reference is not None, "H3 requires the twenty exact core reference bindings")
    doc = reads.ref(reference, "H3 core reference bindings")
    require(doc.get("kind") == "h3_core_reference_bindings_v1" and doc.get("test_labels_used") is False,
            "Invalid H3 reference binding document")
    expected = {c["cell_id"]: c for c in cells if c["role"]["arm_id"] == "R-core"
                and c["role"].get("history") == "on" and c["role"].get("message_passing") in ("sage", "none")}
    require(len(expected) == 20 and {(c["role"]["horizon_seconds"], c["role"]["seed"], c["role"]["message_passing"])
            for c in expected.values()} == {(h, seed, mp) for h in (30, 60) for seed in range(5) for mp in ("sage", "none")},
            "H3 reference core grid differs")
    records = {r["cell_id"]: r for r in doc["entries"]}
    require(len(records) == len(doc["entries"]) == 20 and set(records) == set(expected), "H3 reference binding grid differs")
    for cid, cell in expected.items():
        record = records[cid]
        require(cell["status"] == "committed" and all(record.get(k) == cell[k] for k in (
            "commitment_sha256", "predictions_sha256", "manifest_sha256", "gate_sha256", "model_sha256")),
            "H3 reference points to another core forecast/model/cohort")
        fit = reads.ref(record["fit_receipt"], "H3 reference original fit receipt")
        require(fit.get("checkpoint_sha256") == cell["model_sha256"]
                and fit["model"]["curve_projection"] == record.get("curve_projection")
                and record["curve_projection"] in ("cummax", "none"), "H3 reference fit projection differs")
    return reference["sha256"]


def checked_probability_calibration(reads, binding):
    require(binding is not None, "Probability reliability needs the separately reviewed pre-R1 scientific definition")
    reads.file(binding["decision"], "Probability reliability decision")
    review = checked_review(reads.ref(binding["approval"], "Probability reliability scientific approval"),
                            scope="r1-probability-reliability-v1")
    require(REVIEWER.fullmatch(str(review.get("reviewer", ""))) and review.get("test_outcomes_used") is False
            and review.get("decision_sha256") == binding["decision"]["sha256"]
            and review.get("release_driver_sha256") == reads.digest(Path(__file__).resolve().parents[2] / "scripts/forecast_retrospective_release.py")
            and review.get("scoring_source_sha256") == reads.digest(Path(__file__).with_name("forecast_retrospective_scoring.py")),
            "Probability reliability approval differs from the decision and implementation")
    return binding


def verify_batch(doc, *, guard=None, review=True):
    """Every R1 prerequisite and every retained cell, in one pass. Returns (result, reads)."""
    if guard is None:
        from .forecast_sensitivity_gate import require_sensitivity_for_reporting as guard
    from . import forecast_numeric
    resources = doc.get("resources", {})
    cap = resources.get("verified_buffer_bytes", 512 << 30)
    max_file = resources.get("maximum_file_bytes", 8 << 30)
    require(type(cap) is int and type(max_file) is int and 0 < max_file <= cap <= 1 << 40,
            "Verified byte buffers require a finite budget no larger than 1 TiB")
    reads = Reads(max_retained_bytes=cap, max_file_bytes=max_file)
    require(doc.get("scope") == SCOPE and doc.get("released_window") == R1_WINDOW, "Not an R1 Sep-Dec 2025 document")
    require(doc.get("access_registry") == str(ACCESS_REGISTRY) and Path(ACCESS_REGISTRY).resolve() == Path(ACCESS_REGISTRY),
            "Access registry is not the single R1 registry")
    require(doc.get("release_driver_sha256") == reads.digest(
        Path(__file__).resolve().parents[2] / "scripts/forecast_retrospective_release.py"),
        "Running release driver differs from the reviewed source")
    require(doc.get("consumer_sources") == consumer_source_hashes(reads),
            "Consumer scientific source closure differs from the reviewed draft")
    families = doc["families"]
    names = [f["family_id"] for f in families]
    require(len(names) == len(set(names)) and len({f["ledger"]["sha256"] for f in families}) == len(families),
            "Duplicate family or family ledger")
    for family in families:
        require(family["format"] in FORMATS, f"Unsupported commitment format {family['format']!r}")
        require(set(family["arm_ids"]) <= FORMATS[family["format"]][1], "Format cannot serve the declared arm")
    arms = checked_coverage(reads.ref(doc["retained_arm_ledger"], "Retained-arm ledger"), families,
                            doc.get("exclusions", []))
    scope = reads.ref(doc["history_sensitivity"]["consumer_scope"], "History consumer scope")
    require(scope.get("retained_arm_ledger_sha256") == doc["retained_arm_ledger"]["sha256"],
            "History sensitivity scope names another retained-arm ledger")
    for parent in scope.get("parent_ledgers", {}).values():
        reads.ref(parent["source"], "History consumer parent ledger")
    cells = []
    for family in families:
        checked_history_reporting_binding(family, doc["history_sensitivity"])
        produced = FORMATS[family["format"]][0](family, reads)
        require({c["role"]["arm_id"] for c in produced} == set(family["arm_ids"]),
                f"{family['family_id']}: cells do not cover exactly its declared arms")
        cells += produced
    if "R-panelfix" in arms:
        primary = [c for c in cells if c["role"]["arm_id"] == "R-core"
                   and c["role"].get("message_passing") == "sage" and c["role"].get("history") == "on"]
        require(len(primary) == 10 and {(c["role"]["horizon_seconds"], c["role"]["seed"]) for c in primary}
                == {(h, seed) for h in (30, 60) for seed in range(5)},
                "R-panelfix requires exactly the ten retained core SAGE/history-on cells")
        for parent in primary:
            cells.append({**parent, "cell_id": "panelfix/" + parent["cell_id"], "alias_of": parent["cell_id"],
                          "role": {**parent["role"], "arm_id": "R-panelfix"}})
    h3_references = checked_h3_reference_bindings(reads, doc.get("h3_reference_bindings"), cells)
    ids = [c["cell_id"] for c in cells]
    require(len(ids) == len(set(ids)), "Duplicate retained cell")
    checked_retained_paths(cells)
    # Large ID lists stay out of the sealed records; the records keep their digests.
    side = {}
    for cell in cells:
        side[cell["cell_id"]] = {k: cell.pop(k) for k in ("event_ids", "cohort_rows", "forecast_event_ids", "h3_context", "stable_context",
                                                         "abstention_event_ids") if k in cell}
        for key, value in side[cell["cell_id"]].items():
            if key in ("h3_context", "stable_context"):
                cell[key + "_sha256"] = canonical(value)
            elif key != "cohort_rows":
                cell[key + "_sha256"] = population_sha256(value)
    committed = [c for c in cells if c["status"] == "committed"]
    models = [(c["family_id"], c["role"].get("panel"), c["role"].get("candidate_history_k"), c["role"].get("series"), c["role"].get("horizon_seconds"), c["role"].get("bin_seconds"),
               c["model_sha256"]) for c in committed if c.get("model_sha256") and not c.get("alias_of")]
    require(len(models) == len(set(models)), "One model is retained twice within a family/panel")
    populations = {c["population_sha256"] for c in committed if c.get("population_sha256") and not c.get("secondary")}
    require(populations == {R1_POPULATION_SHA256}, "Committed populations differ from the R1 population")
    with_ids = [side[c["cell_id"]]["event_ids"] for c in committed if "event_ids" in side[c["cell_id"]] and not c.get("secondary")]
    require(with_ids and all(i == with_ids[0] for i in with_ids) and len(with_ids[0]) == R1_EVENTS
            and population_sha256(with_ids[0]) == R1_POPULATION_SHA256, "R1 event IDs disagree across cells")
    r1_ids = with_ids[0]
    from .forecast_sensitivity_gate import cohort_ids_sha256
    for family in families:
        if family["format"] == "history_variant_index_v1" and family["variant"] != "withhold":
            receipt = reads.ref(family["receipt"], "Delay primary cohort receipt")
            require(receipt.get("cohort_ids_sha256") == cohort_ids_sha256(r1_ids), "Delay primary cohort differs")
    secondary = [c for c in committed if c.get("secondary")]
    require(bool(secondary) == bool(doc.get("secondary_authorization")), "Secondary requires its separate all-2025 authorization")
    if secondary:
        authorization = reads.ref(doc["secondary_authorization"], "Separate all-2025 transfer authorization")
        checked_review(authorization)
        require(authorization.get("scope") == "transfer-all-2025-secondary-scoring"
                and authorization.get("released_window") == {"start": "2025-01-01T00:00:00+00:00", "end": "2026-01-01T00:00:00+00:00"}
                and set(authorization.get("union_sha256", [])) == {c["secondary_union"]["sha256"] for c in secondary},
                "Separate secondary authorization has the wrong window or union")
        by_id = {c["cell_id"]: c for c in committed}
        for cell in secondary:
            primary = by_id[cell["primary_cell_id"]]
            require(primary["role"]["arm_id"] == "R-transfer" and not primary.get("secondary")
                    and primary["model_sha256"] == cell["model_sha256"]
                    and all(primary[k] == cell["primary_binding"][k] for k in ("predictions_sha256", "commitment_sha256"))
                    and not set(side[cell["cell_id"]]["event_ids"]) & set(r1_ids), "Secondary primary reuse differs")
    cohorts = {}
    for cell in committed:
        rows = side[cell["cell_id"]].get("cohort_rows")
        if rows is not None and not cell.get("secondary"):
            delta = cell["role"]["horizon_seconds"]
            require(cohorts.setdefault(delta, rows) == rows, f"Cells at {delta} s disagree on the reference cohort rows")
    primary_gates = {c["gate_sha256"] for c in committed if c["role"]["arm_id"] == "R-core"}
    prerequisites = {
        "probability_calibration": checked_probability_calibration(reads, doc.get("probability_calibration")),
        "h3_reference_bindings": h3_references,
        "recipes": checked_recipes(reads, doc["new_period_recipes"]),
        "exposure_ledger": bound_file(reads, doc["exposure_ledger"], "Exposure ledger"),
        "scientific_protocol": bound_file(reads, doc["scientific_protocol"], "Scientific protocol"),
        "history_sensitivity": checked_sensitivity(reads, doc["history_sensitivity"], r1_ids, primary_gates, guard),
        "decision_rules": checked_decision_rules(reads, doc.get("decision_rules"), cells, doc["slice_rules"],
                                                 doc.get("decision_calibration")),
        "h1_calibration": checked_h1_calibration(reads, doc.get("h1_calibration"), cells, doc.get("decision_rules") or {}),
    }
    scorer = doc["scorer"]
    reads.file(scorer["scorer"], "Frozen scorer")
    reads.file(scorer["numeric"], "Frozen numeric helper")
    require(scorer["numeric"]["sha256"] == reads.digest(forecast_numeric.__file__)
            and scorer.get("coverage_convention") == forecast_numeric.COVERAGE_CONVENTION,
            "Scorer bundle does not use the common numeric coverage rule")
    from . import forecast_retrospective_scoring
    reads.file(scorer["adapter"], "Pure retrospective scoring adapter")
    require(scorer["adapter"]["sha256"] == reads.digest(forecast_retrospective_scoring.__file__),
            "Imported scoring adapter differs from the reviewed source")
    slice_rules = reads.ref(doc["slice_rules"], "Frozen slice rules")
    require(set(slice_rules.get("horizons", {})) == {"30", "60"}, "Slice rules must be frozen at both horizons")
    if doc.get("arm_spec"):
        reads.ref(doc["arm_spec"], "Frozen arm spec")
    analysis = doc.get("analysis") or {}
    require(type(analysis.get("repetitions")) is int and type(analysis.get("bootstrap_seed")) is int
            and type(analysis.get("alpha")) is float, "Analysis constants must be frozen")
    if review:
        gate = checked_review(reads.ref(doc["review"], "Retention-spec review"), scope=SCOPE)
        require(REVIEWER.fullmatch(str(gate.get("reviewer", ""))), "Retention review requires its actual reviewer identity")
        require(gate.get("draft_sha256") == doc["draft_sha256"], "Review covers another retention draft")
        require(gate.get("custody_source_sha256") == reads.digest(__file__)
                and gate.get("release_driver_sha256") == doc["release_driver_sha256"],
                "Review covers other custody/release code")
        require(all(gate.get(k) is False for k in ("labels_authorized", "scoring_authorized")),
                "A retention review never authorizes labels or scoring (only the R1 authorization does)")
    unique_predictions = {str(Path(c["predictions_path"]).resolve()) for c in committed}
    accounting = {"prediction_bytes": sum(len(reads.raw[path]) for path in unique_predictions),
                  "maximum_prediction_bytes": max((len(reads.raw[path]) for path in unique_predictions), default=0),
                  "verified_buffer_limit_bytes": cap, "maximum_file_bytes": max_file,
                  "expanded_prediction_cells_retained_at_once": 1}
    return {"cells": cells, "arms": arms, "resource_accounting": accounting,
            "r1_event_ids_sha256": population_sha256(r1_ids),
            "prerequisites": prerequisites, "cohort_rows": {str(k): v for k, v in sorted(cohorts.items())},
            "r1_event_ids": r1_ids, "side": side}, reads


def sealed_view(result):
    """What the seal records (deterministic; no timestamps)."""
    return {"cells": result["cells"], "arms": result["arms"], "r1_event_ids_sha256": result["r1_event_ids_sha256"],
            "prerequisites": result["prerequisites"], "resource_accounting": result["resource_accounting"]}


# --------------------------------------------------------------------------- freeze / seal / one-time marker

def marker_path():
    return Path(ACCESS_REGISTRY) / MARKER


def refuse_if_unblinded():
    registry = Path(ACCESS_REGISTRY)
    require(registry.is_absolute() and registry.is_dir() and registry.resolve() == registry,
            "Canonical R1 registry must exist at its literal path without redirected ancestors")
    existing = sorted(p.name for p in registry.iterdir() if p.name.startswith("r1-unblinding"))
    require(not existing, f"R1 labels were already opened once ({existing}); no reseal, rerun or second opening")


def freeze(draft_path, out, *, review, release_driver_sha256, guard=None):
    """Write the retention spec once. ``review`` ({path, sha256}) is the independent review of the draft bytes."""
    refuse_if_unblinded()
    raw = Path(draft_path).read_bytes()
    draft = json.loads(raw)
    require(draft.get("kind") == "r1_committed_retention_draft", "Not an R1 retention draft")
    require("review" not in draft, "The draft cannot carry its own review")
    doc = dict(draft, kind="r1_committed_retention_spec", draft_sha256=hashlib.sha256(raw).hexdigest(),
               release_driver_sha256=release_driver_sha256, review=review)
    result, reads = verify_batch(doc, guard=guard)
    spec = dict(doc, custody_source_sha256=reads.digest(__file__), cells_at_freeze=len(result["cells"]),
                frozen_utc=datetime.now(UTC).isoformat(), labels_opened=False,
                predictions_decoded=False)
    write_once(out, spec)
    return spec


def seal_path_for(spec_path, spec_sha256):
    return Path(ACCESS_REGISTRY).resolve() / f"r1-seal-{spec_sha256}.json"


def checked_spec(spec_path, expected_spec_sha256):
    raw = Path(spec_path).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected_spec_sha256, "Retention spec differs from its external anchor")
    spec = json.loads(raw)
    require(spec.get("kind") == "r1_committed_retention_spec", "Not a frozen R1 retention spec")
    return spec


def seal(spec_path, expected_spec_sha256, *, guard=None):
    """Verify the whole batch and write the one seal of this spec at its canonical path."""
    refuse_if_unblinded()
    spec = checked_spec(spec_path, expected_spec_sha256)
    result, _ = verify_batch(spec, guard=guard)
    doc = {"kind": "r1_committed_seal", "scope": SCOPE, "spec_path": str(Path(spec_path).resolve()),
           "spec_sha256": expected_spec_sha256, **sealed_view(result),
           "all_retained_cells_verified": True, "labels_opened": False, "predictions_decoded": False,
           "sealed_utc": datetime.now(UTC).isoformat()}
    path = seal_path_for(spec_path, expected_spec_sha256)
    write_once(path, doc)
    return path, doc


def checked_seal(spec_path, expected_spec_sha256, seal_path, expected_seal_sha256):
    require(Path(seal_path).resolve() == seal_path_for(spec_path, expected_spec_sha256),
            "Seal is not at the canonical path of its spec (copied seal)")
    raw = Path(seal_path).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected_seal_sha256, "Seal differs from its external anchor")
    doc = json.loads(raw)
    require(doc.get("kind") == "r1_committed_seal" and doc.get("spec_sha256") == expected_spec_sha256
            and doc.get("all_retained_cells_verified") is True
            and Path(doc["spec_path"]) == Path(spec_path).resolve(), "Seal belongs to another spec")
    return doc


def reverify(spec_path, expected_spec_sha256, seal_path, expected_seal_sha256, *, guard=None):
    """Everything again, compared field by field with the seal. Returns (spec, seal, result, reads)."""
    spec = checked_spec(spec_path, expected_spec_sha256)
    sealed = checked_seal(spec_path, expected_spec_sha256, seal_path, expected_seal_sha256)
    result, reads = verify_batch(spec, guard=guard)
    current = sealed_view(result)
    require(current == {k: sealed[k] for k in current}, "Retained batch changed after sealing")
    return spec, sealed, result, reads
