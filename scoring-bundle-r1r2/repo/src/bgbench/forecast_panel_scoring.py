"""H3 scoring adapter: audited partial-panel inputs, frozen cohorts and estimator-specific count definitions.

Implements ``H3-SCORING-DECISIONS.md`` with the corrections of
``reviews/h3-metadata-review-20261018.txt``. The strict ``forecast_panel.align_panel_predictions``
stays frozen and keeps refusing incomplete windows; this module is the separate adapter. It reads
label-free availability metadata and committed predictions only. It never opens targets, never
scores, never authorizes R1, and never repairs a forecast: every check refuses.

* Full-reference population: every reference test event (3,543 per horizon) stays in every arm.
  Certified no-input events are ``empty_set_zero_count`` abstentions, never forecasts.
* Partial-panel events keep their actual committed forecast. They need the audited partial flag,
  the exact missing-collector list from the bound input-status ledger, canonical observed seeds
  equal to the ledger's, ``parse_status: ok`` and a committed prediction. No ``source_failure``,
  parse or inference failure becomes a partial forecast or an abstention.
* Learned count: committed120-minute median; all4x3 curve values stay unchanged. History count:
  committed seed-floored kNN final extent, unchanged; curve metrics are not applicable.
* Cohorts per horizon: full reference; common-available (available in every compared arm); and
  the secondary common-complete (available and not partial in every compared arm). Arms are
  reference, ris7 and mixed7. ID lists and hashes are frozen from availability metadata before R1;
  scoring inputs are refused unless they reproduce the frozen document.
* Calibration: partial-eligible (all forecasts) and complete-only subsets with both denominators;
  no-input abstentions are excluded from both.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np

from .forecast_h3_commitments import PANELS, REFERENCE

SCOPE = "h3-panel-scoring-adapter-v1"
COHORT_KIND = "h3_scoring_cohorts"
AUDIT_KIND = "h3_arm_input_audit"
ARMS = ("reference", "ris7", "mixed7")
ARM_COLLECTORS = {"reference": REFERENCE, **PANELS}
HORIZONS = (30, 60)
REFERENCE_EVENTS = 3543
# population_sha256 of the sorted R1 reference test IDs (same at both horizons).
REFERENCE_POPULATION_SHA256 = "f5f212ba42fb58a5e9beab84643e9cde56a336d46edbfde9ac3e9592cbeeb20c"
CURVE_HORIZONS = (300, 900, 3600, 7200)
QUANTILES = (0.1, 0.5, 0.9)
POINT_INDEX = (3, 1)  # 7200 s, q0.5
PROJECTION = "expm1(curve_log_quantiles[3][1]); 120-minute median; no rounding, clamping or repair"
ABSTENTION = "empty_set_zero_count"
FAMILIES = ("learned", "history")
HISTORY_KIND = "h3_history_baseline_extent_commitment"
EXTENT_RULE = "frozen committed seed-floored kNN final extent; no rounding or cardinality conversion"
HISTORY_NA = "The frozen history estimator supplies final extent and participation ranking only; no quantile curve."
HISTORY_IDENTITY = ("baseline", "size_statistic", "k", "candidate_protocol", "library_digest", "frozen_at",
                    "baseline_source_sha256")
FROZEN_DEPENDENCIES = {
    # Reviewed hashes; the adapter never changes these files.
    "forecast_panel.py": "ac9468bceb62020da660993f2fdc80e4efbdca2297de4e7dcdfbfa348b876290",
    "forecast_h3_commitments.py": "d382885df6f43c0762d90bfe8cb9d1841564c859bdbeca95f67ba51461a5e777",
}
ROW_KEYS = frozenset(("event_id", "status", "ledger_status", "input_window_complete", "parse_status",
                      "input_seed_asns", "coverage_audit_sha256", "input_status_ledger_sha256",
                      "partial_panel_input", "panel_missing_collectors"))


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha256_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def population_sha256(ids):
    return sha256_bytes(json.dumps(sorted(ids), separators=(",", ":")).encode())


def ordered_sha256(ids):
    return sha256_bytes(json.dumps(list(ids), separators=(",", ":")).encode())


def canonical_sha256(doc):
    return sha256_bytes(json.dumps(doc, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())


def _hex64(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _asns(values, what):
    require(isinstance(values, list) and all(type(v) is int and v >= 0 for v in values)
            and values == sorted(set(values)), f"{what} must be sorted unique non-negative integer ASNs")
    return values


def frozen_dependency_hashes(root=None):
    """Byte hashes of the frozen modules this adapter sits beside (must equal ``FROZEN_DEPENDENCIES``)."""
    root = Path(root) if root else Path(__file__).parent
    return {name: sha256_bytes((root / name).read_bytes()) for name in FROZEN_DEPENDENCIES}


def require_frozen_dependencies(root=None):
    require(frozen_dependency_hashes(root) == FROZEN_DEPENDENCIES, "Frozen panel/H3 code changed")


def reference_ids(manifest):
    """Ordered reference test IDs of an original retrospective manifest (the exact R1 population)."""
    ids = [row["event_id"] for row in manifest["events"] if row["split"] == "test"]
    require(len(ids) == len(set(ids)) == REFERENCE_EVENTS and population_sha256(ids) == REFERENCE_POPULATION_SHA256,
            "Reference test population is not the declared R1 population")
    return ids


# --- audited availability -----------------------------------------------------------------

def panel_audit(arm, horizon, build, availability_doc, availability_sha256, input_status_ledger,
                input_status_ledger_sha256):
    """Audit of one panel build, derived only from the frozen H3 metadata and its bound ledger.

    ``build`` is the metadata-ledger build entry. The missing-collector list of each partial event is
    recomputed from the bound input-status ledger rows (status ``missing``), never taken on trust.
    """
    require(arm in PANELS and horizon in HORIZONS, "Undeclared panel or horizon")
    require(build.get("panel") == arm and build.get("horizon_seconds") == horizon, "Build entry binds another arm")
    require(build.get("availability_sha256") == availability_sha256, "Availability differs from the metadata ledger")
    require(build["bound_files"]["ledger"]["sha256"] == input_status_ledger_sha256,
            "Input-status ledger differs from the metadata ledger")
    require(input_status_ledger.get("contains_labels") is False and input_status_ledger.get("panel") == arm
            and input_status_ledger.get("delta_s") == horizon, "Input-status ledger binds another build")
    rows = {}
    for row in input_status_ledger["events"]:
        require(row["event_id"] not in rows, f"Duplicate ledger event: {row['event_id']}")
        rows[row["event_id"]] = row
    collectors = ARM_COLLECTORS[arm]
    partial, missing, no_input, seeds = [], {}, [], {}
    for row in availability_doc["rows"]:
        eid = row["event_id"]
        require(eid in rows, f"Availability event outside the input-status ledger: {eid}")
        source = rows[eid]
        require(source["status"] in ("available", "unavailable_no_input"),
                f"Ledger status has no reviewed scoring rule: {eid}: {source['status']}")
        require(all(v.get("status") in {"observed", "empty", "missing", "not_in_panel"}
                    for v in source["collectors"].values()), f"Unknown collector status: {eid}")
        gaps = sorted(c for c in collectors if source["collectors"][c]["status"] == "missing")
        require(source["partial_panel_input"] is bool(gaps), f"Ledger partial flag disagrees with collectors: {eid}")
        if source["status"] == "unavailable_no_input":
            require(not gaps, f"No-input row has missing collectors: {eid}")
            no_input.append(eid)
        elif gaps:
            partial.append(eid)
            missing[eid] = gaps
        seeds[eid] = list(source["input_seed_asns"])
    require(partial == list(build["partial_panel_test_event_ids"]), "Partial IDs differ from the metadata ledger")
    require(len(no_input) == build["abstained_test_events"]
            and len(availability_doc["rows"]) - len(no_input) == build["forecast_test_events"],
            "Availability counts differ from the metadata ledger")
    return {"kind": AUDIT_KIND, "arm": arm, "horizon_seconds": horizon, "contains_labels": False,
            "collectors": list(collectors), "availability_sha256": availability_sha256,
            "coverage_audit_sha256": build["bound_files"]["coverage"]["sha256"],
            "input_status_ledger_sha256": input_status_ledger_sha256,
            "partial_event_ids": partial, "missing_collectors": missing,
            "no_input_event_ids": no_input, "seed_asns_sha256": canonical_sha256(seeds)}


def check_audit(audit, arm, horizon, availability_sha256):
    """Schema of an arm audit. Reference audits have no producer yet and must be supplied explicitly."""
    require(isinstance(audit, dict) and audit.get("kind") == AUDIT_KIND and audit.get("contains_labels") is False,
            "Not a label-free arm input audit")
    require(audit.get("arm") == arm and audit.get("horizon_seconds") == horizon
            and audit.get("collectors") == list(ARM_COLLECTORS[arm]), "Audit binds another arm or collector set")
    require(audit.get("availability_sha256") == availability_sha256, "Audit binds other availability bytes")
    for key in ("coverage_audit_sha256", "input_status_ledger_sha256", "seed_asns_sha256"):
        require(_hex64(audit.get(key)), f"Audit lacks {key}")
    partial, missing = audit.get("partial_event_ids"), audit.get("missing_collectors")
    require(isinstance(partial, list) and isinstance(missing, dict) and set(partial) == set(missing)
            and len(partial) == len(set(partial)), "Audit partial IDs and missing-collector proof differ")
    for eid, gaps in missing.items():
        require(isinstance(gaps, list) and gaps and gaps == sorted(set(gaps)) and set(gaps) <= set(ARM_COLLECTORS[arm]),
                f"Audited missing collectors are not a sorted subset of the arm: {eid}")
    require(isinstance(audit.get("no_input_event_ids"), list), "Audit lacks certified no-input IDs")


def check_availability(doc, arm, horizon, ids, *, availability_sha256, audit):
    """Validate one arm's availability document against the reference IDs and its audit; return rows.

    Order, membership, status vocabulary, completeness flag, missing-collector proof, seeds and hashes
    must all agree. Anything unclassified, a ``source_failure`` or a parse failure refuses.
    """
    require(arm in ARMS and horizon in HORIZONS, "Undeclared arm or horizon")
    check_audit(audit, arm, horizon, availability_sha256)
    require(doc.get("contains_labels") is False and doc.get("horizon_seconds") == horizon
            and doc.get("panel") == arm, "Availability binds another arm or horizon")
    require(doc.get("reference_event_ids_sha256") == REFERENCE_POPULATION_SHA256, "Availability population differs")
    rows = doc["rows"]
    require([r.get("event_id") for r in rows] == list(ids), "Availability order or IDs drift from the reference")
    collectors, seeds = set(ARM_COLLECTORS[arm]), {}
    partial, no_input = [], []
    for row in rows:
        eid = row["event_id"]
        require(set(row) == ROW_KEYS, f"Availability row schema differs: {eid}")
        require(row["parse_status"] == "ok", f"Parse failure cannot be scored: {eid}")
        require(row["coverage_audit_sha256"] == audit["coverage_audit_sha256"]
                and row["input_status_ledger_sha256"] == audit["input_status_ledger_sha256"],
                f"Row binds another coverage audit or ledger: {eid}")
        gaps = row["panel_missing_collectors"]
        require(isinstance(gaps, list) and gaps == sorted(set(gaps)) and set(gaps) <= collectors,
                f"Missing collectors outside the arm: {eid}")
        require(type(row["partial_panel_input"]) is bool and row["partial_panel_input"] is bool(gaps)
                and row["input_window_complete"] is (not gaps), f"Completeness flags disagree: {eid}")
        seeds[eid] = _asns(row["input_seed_asns"], f"Input seeds of {eid}")
        status = (row["status"], row["ledger_status"])
        if status == ("available", "available"):
            require(seeds[eid], f"Available row without observed seeds: {eid}")
            if gaps:
                require(audit["missing_collectors"].get(eid) == gaps, f"Unaudited missing collectors: {eid}")
                partial.append(eid)
        elif status == ("no_input", "unavailable_no_input"):
            require(not seeds[eid] and not gaps, f"No-input row is not certified empty: {eid}")
            no_input.append(eid)
        else:
            raise ValueError(f"Status has no reviewed scoring rule: {eid}: {status}")
    require(partial == list(audit["partial_event_ids"]), "Partial rows differ from the audited partial IDs")
    require(no_input == list(audit["no_input_event_ids"]), "No-input rows differ from the audited abstentions")
    require(canonical_sha256(seeds) == audit["seed_asns_sha256"], "Input seeds differ from the audited ledger")
    return rows


# --- frozen cohorts -------------------------------------------------------------------------

def cohorts(arm_rows, ids):
    """Per-horizon cohort IDs over ALL of reference, ris7 and mixed7, in reference order."""
    require(set(arm_rows) == set(ARMS), "Cohorts need exactly the reference, ris7 and mixed7 arms")
    for arm in ARMS:
        require([r["event_id"] for r in arm_rows[arm]] == list(ids), f"{arm} does not keep the reference order")
    index = {arm: {r["event_id"]: r for r in rows} for arm, rows in arm_rows.items()}
    available = [e for e in ids if all(index[a][e]["status"] == "available" for a in ARMS)]
    complete = [e for e in available if not any(index[a][e]["partial_panel_input"] for a in ARMS)]
    require(available, "Common-available cohort is empty; refusing to freeze")
    require(complete, "Common-complete cohort is empty; refusing to freeze")
    out = {}
    for name, members in (("full_reference", list(ids)), ("common_available", available),
                          ("common_complete", complete)):
        out[name] = {"event_ids": members, "events": len(members), "population_sha256": population_sha256(members),
                     "ordered_sha256": ordered_sha256(members)}
    out["common_complete"]["label"] = "secondary: complete input in every compared arm"
    out["excluded_partial_by_arm"] = {a: [e for e in available if index[a][e]["partial_panel_input"]] for a in ARMS}
    return out


def freeze_document(per_horizon, bindings, scope_binding, *, reference_manifest_sha256, r1_absent_paths):
    """Label-free cohort freeze. ``per_horizon[h] = (ids, {arm: rows})``; bindings hold every hash.

    ``r1_absent_paths`` records the R1 paths the caller confirmed absent; the freeze never opens R1.
    """
    require(sorted(per_horizon) == list(HORIZONS), "Freeze needs both horizons")
    require(isinstance(scope_binding, dict) and _hex64(scope_binding.get("sha256"))
            and scope_binding.get("scope") == "h3-frozen-sensitivity-retrospective-predictions-v1",
            "Freeze must bind the approved H3 commitment scope")
    for h in HORIZONS:
        require(set(bindings.get(str(h), {})) == set(ARMS), f"Bindings must cover every arm at {h} s")
    require(sorted(reference_manifest_sha256) == [str(h) for h in HORIZONS]
            and all(_hex64(v) for v in reference_manifest_sha256.values()), "Freeze must bind both reference manifests")
    doc = {"kind": COHORT_KIND, "scope": SCOPE, "contains_labels": False, "label_free_inputs_only": True,
           "test_scoring_authorized": False, "r1_authorized": False,
           "frozen_before": "R1 label opening; the freeze never authorizes it",
           "arms": list(ARMS), "projection": PROJECTION, "count_definitions": {"learned": PROJECTION, "history": EXTENT_RULE},
           "abstention_policy": ABSTENTION,
           "scope_binding": scope_binding, "bindings": bindings,
           "adapter_source_sha256": sha256_bytes(Path(__file__).read_bytes()),
           "reference_manifest_sha256": reference_manifest_sha256, "r1_absent_paths": list(r1_absent_paths),
           "horizons": {str(h): cohorts(arm_rows, ids) for h, (ids, arm_rows) in sorted(per_horizon.items())}}
    doc["document_sha256"] = canonical_sha256(doc)
    return doc


def check_frozen_cohorts(frozen, raw_sha256, expected_sha256, per_horizon, bindings, reference_manifest_sha256, *, scope_binding):
    """Scoring inputs must reproduce the frozen cohorts and bindings exactly; no bypass."""
    require(raw_sha256 == expected_sha256, "Frozen cohort document changed")
    require(frozen.get("kind") == COHORT_KIND and frozen.get("scope") == SCOPE
            and frozen.get("contains_labels") is False and frozen.get("r1_authorized") is False,
            "Not the frozen label-free cohort document")
    body = {k: v for k, v in frozen.items() if k != "document_sha256"}
    require(canonical_sha256(body) == frozen.get("document_sha256"), "Frozen cohort self-digest differs")
    require(frozen.get("scope_binding") == scope_binding, "Scope approval differs from the freeze")
    require(frozen.get("adapter_source_sha256") == sha256_bytes(Path(__file__).read_bytes()),
            "Adapter source differs from the freeze")
    require(frozen["bindings"] == bindings, "Availability or audit bindings differ from the freeze")
    require(frozen["reference_manifest_sha256"] == reference_manifest_sha256, "Reference manifests differ from the freeze")
    require(sorted(per_horizon) == list(HORIZONS), "Scoring must re-derive both horizons")
    for h, (ids, arm_rows) in per_horizon.items():
        require(frozen["horizons"][str(h)] == cohorts(arm_rows, ids), f"Cohorts at {h} s differ from the freeze")
    return frozen


# --- committed forecasts and the count projection ------------------------------------------

def check_curve(log_quantiles, seed_count, *, temporal_monotone):
    """Refuse-only checks of a committed log-count curve; returns it unchanged.

    Axes 4 horizons x 3 quantiles; finite reals; quantile ordering per horizon; nondecreasing over
    horizons when the frozen projection declares it (``cummax``); observed-seed floor at the common
    float32 convention (one outward ULP below float32(log1p(seeds))). Nothing is clamped.
    """
    q = log_quantiles
    require(isinstance(q, list) and len(q) == len(CURVE_HORIZONS)
            and all(isinstance(r, list) and len(r) == len(QUANTILES) for r in q), "Curve axes differ from 4x3")
    require(all(type(v) in (int, float) and math.isfinite(v) for r in q for v in r), "Curve is not finite")
    a = np.asarray(q, dtype=np.float64)
    require(bool((np.diff(a, axis=1) >= 0).all()), "Curve quantiles are out of order")
    if temporal_monotone:
        require(bool((np.diff(a, axis=0) >= 0).all()), "Curve decreases over horizons")
    floor = np.nextafter(np.float32(np.log1p(np.float64(seed_count))), np.float32(-np.inf))
    require(bool((a.astype(np.float32) >= floor).all()), "Curve falls below the observed-seed floor")
    require(math.isfinite(point_count(q)), "Point count overflows")
    return q


def point_count(log_quantiles):
    """The learned H3 count projection, identical across its reference and panel arms."""
    with np.errstate(over="ignore"):  # an overflow is refused by ``check_curve``, never clipped
        return float(np.expm1(np.float64(log_quantiles[POINT_INDEX[0]][POINT_INDEX[1]])))


def check_binding(binding, forecast_ids, predictions_sha256):
    """Exact committed-prediction binding: same bytes, all and only the forecast IDs."""
    require(isinstance(binding, dict) and binding.get("predictions_sha256") == predictions_sha256,
            "Prediction bytes differ from the commitment")
    require(binding.get("forecast_event_ids") == sorted(forecast_ids),
            "Commitment does not cover all and only the input-available IDs")
    require(binding.get("test_labels_used") is False, "Commitment used test labels")


def h3_binding(commitment, audit, ids):
    """Binding extracted from an H3 ``h3_commitment`` document, cross-checked with the audit."""
    require(commitment.get("reference_event_ids_sha256") == population_sha256(ids)
            and commitment.get("reference_events") == len(ids), "Commitment population differs")
    require(commitment.get("partial_panel_event_ids") == sorted(audit["partial_event_ids"]),
            "Committed partial IDs differ from the audit")
    require(sorted(a["event_id"] for a in commitment["abstentions"]) == sorted(audit["no_input_event_ids"])
            and all(a["abstention_policy"] == ABSTENTION and a["calibration_eligible"] is False
                    for a in commitment["abstentions"]), "Committed abstentions differ from the audit")
    if commitment.get("kind") == HISTORY_KIND or commitment.get("family") == "history":
        require(commitment.get("availability_sha256") == audit["availability_sha256"], "History availability differs")
        history_identity(commitment, audit["arm"], audit["horizon_seconds"])
        return dict(commitment)  # retain the typed estimator/source lineage, including abstentions
    return {"predictions_sha256": commitment["predictions_sha256"],
            "forecast_event_ids": commitment["forecast_event_ids"], "test_labels_used": commitment["test_labels_used"]}


def history_identity(binding, arm, horizon):
    """Typed history contract, also retained on no-input rows; never inferred from a family flag."""
    require(binding.get("kind") == HISTORY_KIND and binding.get("schema_version") == 1
            and binding.get("family") == "history", "History requires its typed extent commitment")
    require(binding.get("panel") == arm and binding.get("horizon_seconds") == horizon,
            "History commitment arm/horizon differs")
    require(binding.get("count_definition") == "extent" and binding.get("count_rule") == EXTENT_RULE
            and binding.get("curve_metrics") == "not_applicable" and binding.get("quantile_calibration_eligible") is False,
            "History count or curve definition differs")
    require(not {"curve_projection", "checkpoint_sha256", "fit_receipt_sha256", "frozen_commitment_sha256"} & set(binding),
            "History commitment borrows learned identity")
    size = {"history-knn-mean": "mean", "history-knn-median": "median"}.get(binding.get("baseline"))
    require(size is not None and binding.get("size_statistic") == size and type(binding.get("k")) is int
            and binding["k"] == 20, "History baseline/size/k identity differs")
    require(binding.get("candidate_protocol") in ("matched_graph", "native_history_union"), "History candidate protocol differs")
    require("frozen_at" in binding and (binding["frozen_at"] is None or isinstance(binding["frozen_at"], str)),
            "History clock absent")
    if binding["frozen_at"] is not None:
        require(datetime.fromisoformat(binding["frozen_at"]).tzinfo is not None, "History frozen clock must be timezone-aware")
    for key in ("library_digest", "baseline_source_sha256", "baseline_commitment_sha256", "manifest_sha256",
                "input_gate_sha256", "availability_sha256"):
        require(_hex64(binding.get(key)), f"History commitment lacks {key}")
    identity = {k: binding[k] for k in HISTORY_IDENTITY}
    if "history_intervention" in binding:
        sidecar = binding.get("history_intervention_sidecar", {})
        require(isinstance(binding["history_intervention"], dict) and isinstance(sidecar.get("path"), str)
                and _hex64(sidecar.get("sha256")), "History intervention lacks bound sidecar")
        identity["history_intervention"] = binding["history_intervention"]
    else:
        require("history_intervention_sidecar" not in binding, "Sidecar has no intervention identity")
    return identity


def history_extent(row, identity, horizon):
    for key in ("baseline", "size_statistic", "k", "candidate_protocol", "frozen_at"):
        require(row.get(key) == identity[key], f"History row {key} differs")
    require(type(row.get("k")) is int and row.get("observation_cutoff_s") == horizon, "History row k/horizon differs")
    require(not {"curve_log_quantiles", "curve_projection", "probabilities"} & set(row),
            "History extent cannot supply a fabricated learned curve/probability")
    extent = row.get("extent")
    require(type(extent) in (float, int) and math.isfinite(extent) and extent >= len(row["seed_asns"]),
            "Invalid committed history extent")
    candidates, scores = row["candidate_asns"], row.get("ranking_scores")
    require(all(type(a) is int and a >= 0 for a in candidates) and isinstance(scores, list)
            and len(scores) == len(candidates) and all(type(v) in (int, float) and math.isfinite(v)
            and v >= 0 and int(v) == v for v in scores), "Invalid history candidate/ranking pairs")
    require(row.get("ranking_score") == "issue_time_completed_event_participation_count"
            and _hex64(row.get("history_event_ids_sha256")), "History ranking definition or snapshot differs")
    return extent


def aligned_rows(arm, family, rows, predictions, binding, predictions_sha256, *, temporal_monotone, horizon_seconds):
    """Full-reference rows for the frozen ``score_panel_predictions``, plus preserved curves and flags.

    Every learned forecast uses ``point_count``; history preserves its committed extent. A prediction for
    a no-input event, a missing prediction, a seed mismatch or an invalid curve refuses.
    """
    require(arm in ARMS and family in FAMILIES, "Undeclared arm or consumer family")
    require(horizon_seconds in HORIZONS, "Undeclared input horizon")
    identity = history_identity(binding, arm, horizon_seconds) if family == "history" else None
    if family == "learned":
        require(binding.get("kind") != HISTORY_KIND and binding.get("family", "learned") == "learned",
                "Learned forecasts cannot use a history commitment")
    forecast_ids = [r["event_id"] for r in rows if r["status"] == "available"]
    check_binding(binding, forecast_ids, predictions_sha256)
    index = {}
    for p in predictions:
        require(p["event_id"] not in index, f"Duplicate prediction: {p['event_id']}")
        index[p["event_id"]] = p
    no_input = {r["event_id"] for r in rows if r["status"] == "no_input"}
    require(not set(index) & no_input, "A certified no-input event carries a forecast")
    require(set(index) == set(forecast_ids), "Inference failures cannot become abstentions")
    out = []
    for row in rows:
        eid, seeds = row["event_id"], row["input_seed_asns"]
        base = {"event_id": eid, "horizon_seconds": horizon_seconds, "arm": arm, "family": family, "input_status": row["status"],
                "input_seed_asns": list(seeds), "coverage_audit_sha256": row["coverage_audit_sha256"],
                "partial_panel_input": row["partial_panel_input"],
                "panel_missing_collectors": list(row["panel_missing_collectors"])}
        if identity is not None:
            base.update(estimator_identity=identity, count_definition="extent", curve_metrics="not_applicable",
                        curve_metrics_reason=HISTORY_NA, quantile_calibration_eligible=False,
                        baseline_commitment_sha256=binding["baseline_commitment_sha256"])
            if "history_intervention_sidecar" in binding:
                base["history_intervention_sidecar"] = binding["history_intervention_sidecar"]
        if row["status"] == "no_input":
            if identity is not None:
                base.update(ranking_scores=[], ranking_score="issue_time_completed_event_participation_count")
            out.append({**base, "predicted_asns": [], "candidate_asns": [], "predicted_count": 0.0,
                        "curve_log_quantiles": None, "forecast_available": False, "calibration_eligible": False,
                        "complete_input_calibration_eligible": False, "abstention_policy": ABSTENTION,
                        "count_projection": "abstention_zero"})
            continue
        p = index[eid]
        require(p.get("seed_asns") == seeds, f"Committed seeds differ from the audited input seeds: {eid}")
        candidates = p.get("candidate_asns")
        require(isinstance(candidates, list) and len(candidates) == len(set(candidates)),
                f"Candidate list invalid: {eid}")
        predicted = _asns(sorted(p.get("predicted_asns", [])), f"Predicted ASNs of {eid}")
        require(set(seeds) <= set(predicted) <= set(candidates) | set(seeds),
                f"Prediction outside seeds/candidates: {eid}")
        if identity is not None:
            extent = history_extent(p, identity, horizon_seconds)
            out.append({**base, "predicted_asns": predicted, "candidate_asns": list(candidates),
                        "predicted_count": extent, "extent": extent, "curve_log_quantiles": None,
                        "ranking_scores": list(p["ranking_scores"]), "ranking_score": p["ranking_score"],
                        "history_event_ids_sha256": p["history_event_ids_sha256"],
                        "forecast_available": True, "calibration_eligible": False,
                        "complete_input_calibration_eligible": False, "abstention_policy": None,
                        "count_projection": EXTENT_RULE})
            continue
        require("curve_log_quantiles" in p, f"No committed curve; no reviewed count rule: {eid}")
        curve = check_curve(p["curve_log_quantiles"], len(seeds), temporal_monotone=temporal_monotone)
        out.append({**base, "predicted_asns": predicted, "candidate_asns": list(candidates),
                    "predicted_count": point_count(curve), "curve_log_quantiles": curve,
                    "forecast_available": True, "calibration_eligible": True,
                    "complete_input_calibration_eligible": not row["partial_panel_input"],
                    "abstention_policy": None, "count_projection": PROJECTION})
    return out


def calibration_sets(rows):
    """Partial-eligible and complete-only calibration subsets with their denominators."""
    families = {r["family"] for r in rows}
    require(len(families) == 1, "Calibration rows mix estimator families")
    if families == {"history"}:
        require(all(r["curve_metrics"] == "not_applicable" and not r["calibration_eligible"]
                    and not r["complete_input_calibration_eligible"] for r in rows), "History quantile calibration undefined")
        return {"status": "not_applicable", "reason": HISTORY_NA, "quantile_calibration_eligible": False,
                "calibration_coverage": None,
                "partial_eligible": {"event_ids": [], "denominator": None},
                "complete_only": {"event_ids": [], "denominator": None},
                "available_forecasts": sum(r["forecast_available"] for r in rows),
                "complete_input_forecasts": sum(r["forecast_available"] and not r["partial_panel_input"] for r in rows),
                "excluded_abstentions": sum(r["input_status"] == "no_input" for r in rows), "reference_events": len(rows)}
    partial_eligible = [r["event_id"] for r in rows if r["calibration_eligible"]]
    complete = [r["event_id"] for r in rows if r["complete_input_calibration_eligible"]]
    require(set(complete) <= set(partial_eligible), "Complete-only subset outside the forecasts")
    return {"partial_eligible": {"event_ids": partial_eligible, "denominator": len(partial_eligible)},
            "complete_only": {"event_ids": complete, "denominator": len(complete)},
            "excluded_abstentions": sum(r["input_status"] == "no_input" for r in rows),
            "reference_events": len(rows)}


def cohort_rows(frozen, horizon, cohort, arm_aligned):
    """Rows of one frozen cohort: panel contrasts must share estimator identity and count definition."""
    members = frozen["horizons"][str(horizon)][cohort]["event_ids"]
    require(set(arm_aligned) <= set(ARMS) and len(arm_aligned) >= 2, "A contrast needs at least two declared arms")
    out, identities = {}, set()
    for arm, rows in arm_aligned.items():
        require(all(r.get("horizon_seconds") == horizon and r.get("arm") == arm for r in rows),
                f"{arm} rows bind another arm or horizon")
        require(len(rows) == len({r["event_id"] for r in rows}), f"{arm} contains duplicate rows")
        index = {r["event_id"]: r for r in rows}
        require(set(index) == set(frozen["horizons"][str(horizon)]["full_reference"]["event_ids"]),
                f"{arm} rows do not cover the full reference")
        arm_identities = set()
        for r in rows:  # include abstentions and rows outside the chosen subset
            family = r.get("family")
            require(family in FAMILIES, "Missing estimator family")
            if family == "history":
                require(r.get("count_definition") == "extent" and isinstance(r.get("estimator_identity"), dict),
                        "Missing history estimator identity")
                arm_identities.add(canonical_sha256(r["estimator_identity"]))
                # The library digest includes panel-specific signature collectors/signatures.
                # Preserve and bind it within an arm; it is not a cross-panel estimator policy.
                invariant = {k: v for k, v in r["estimator_identity"].items() if k != "library_digest"}
                identities.add(canonical_sha256({"family": family, "identity": invariant}))
            else:
                identities.add(canonical_sha256({"family": family, "projection": PROJECTION}))
        require(len(arm_identities) <= 1, f"{arm} mixes history identities/library provenance")
        picked = [index[e] for e in members]
        require(all(r["count_projection"] in ((EXTENT_RULE, "abstention_zero") if r["family"] == "history"
                                               else (PROJECTION, "abstention_zero")) for r in picked),
                f"{arm} mixes count definitions")
        if cohort != "full_reference":
            require(all(r["forecast_available"] for r in picked), f"{arm} has an abstention inside {cohort}")
        if cohort == "common_complete":
            require(not any(r["partial_panel_input"] for r in picked), f"{arm} has a partial row in {cohort}")
        out[arm] = picked
    require(len(identities) == 1, "Panel contrast mixes estimator identities/families")
    return out
