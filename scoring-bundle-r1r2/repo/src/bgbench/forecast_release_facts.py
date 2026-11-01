"""Lossless paper-facts projection of released R1/N reports; no metric computation."""
import hashlib
import json
import re
from copy import deepcopy

SCHEMA = "forecast_released_report_facts_v1"
FAMILIES = {"primary_ap", "p_at_10", "full_target_jaccard", "slice_jaccard", "whole_system_ap"}
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def pointer(*parts):
    return "/" + "/".join(str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def _object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"Duplicate report key: {key}")
        out[key] = value
    return out


def _nonfinite(value):
    raise ValueError(f"Non-finite report value: {value}")


def _hashes(report, keys):
    for key in keys:
        value = report.get(key)
        if not isinstance(value, str) or not SHA256.fullmatch(value):
            raise ValueError(f"Released report lacks {key}")


def collect(raw, expected_sha256):
    """Preserve every report field, with exact JSON pointers for comparison rows.

    This validates and transforms an already released report. It neither grants
    data-access authority nor substitutes for independent numerical verification.
    """
    digest = hashlib.sha256(raw).hexdigest()
    if not isinstance(expected_sha256, str) or not SHA256.fullmatch(expected_sha256) or digest != expected_sha256:
        raise ValueError("Report differs from its external hash")
    report = json.loads(raw, object_pairs_hook=_object, parse_constant=_nonfinite)
    json.dumps(report, allow_nan=False)  # Also refuse overflow such as a JSON 1e999.
    if not isinstance(report, dict):
        raise TypeError("Report must be an object")
    population = report.get("population")
    if population == "retrospective_r1":
        if (report.get("kind") != "r1_committed_evaluation_report" or report.get("confirmatory") is not False
                or report.get("predictions_regenerated") is not False
                or report.get("model_selection_or_calibration_on_test") is not False):
            raise ValueError("Not a retrospective committed evaluation report")
        _hashes(report, ("spec_sha256", "seal_sha256", "ledger_sha256", "r1_authorization_sha256",
                         "driver_sha256", "custody_source_sha256"))
        analysis = report.get("analysis_ranking_v1_c1_c4")
        prefix = ("analysis_ranking_v1_c1_c4",)
        sections = {k: deepcopy(v) for k, v in report.items() if k != prefix[0]}
    elif population == "new_period":
        if report.get("confirmatory") is not True:
            raise ValueError("New-period evidence designation differs")
        _hashes(report, ("seal_sha256", "custody_spec_sha256", "arm_spec_sha256", "labels_sha256",
                         "extension_decision_sha256", "source_sha256"))
        analysis = report
        prefix = ()
        sections = {}
    else:
        raise ValueError("Unsupported released-report population")
    if not isinstance(analysis, dict):
        raise TypeError("Missing analysis report")
    comparisons = []
    families = analysis.get("families")
    if population == "retrospective_r1" and (
            ("population" in analysis and analysis["population"] != population)
            or ("confirmatory" in analysis and analysis["confirmatory"] is not False)
            or (families is not None and
                (analysis.get("population") != population or analysis.get("confirmatory") is not False))):
        raise ValueError("Nested retrospective evidence designation differs")
    if families is None:
        if population != "retrospective_r1" or analysis.get("status") not in (
                "not_bound", "unavailable_scoring_failures"):
            raise ValueError("Analysis lacks comparison families or an explicit unavailable status")
        analysis_metadata = deepcopy(analysis)
    else:
        if not isinstance(families, dict) or not families or set(families) - FAMILIES:
            raise ValueError("Unexpected comparison families")
        analysis_metadata = {k: deepcopy(v) for k, v in analysis.items() if k != "families"}
        for name, family in families.items():
            if not isinstance(family, dict) or type(family.get("declares_primary_finding")) is not bool:
                raise ValueError("Missing family evidence designation")
            if family["declares_primary_finding"] and (population != "new_period" or name != "primary_ap"):
                raise ValueError("Only new-period primary AP can declare a primary finding")
            source = pointer(*prefix, "families", name)
            if "contrasts" not in family:
                if family.get("status") != "unavailable" or not family.get("reason"):
                    raise ValueError("Missing explicit unavailable-family reason")
                comparisons.append({"family": name, "source_pointer": source,
                                    "family_metadata": deepcopy(family), "contrast_key": None,
                                    "result": None})
                continue
            contrasts = family["contrasts"]
            if (not isinstance(contrasts, dict) or not contrasts
                    or type(family.get("holm_family_size")) is not int
                    or family["holm_family_size"] != len(contrasts)):
                raise ValueError("Multiplicity family size differs from the complete contrast set")
            metadata = {k: deepcopy(v) for k, v in family.items() if k != "contrasts"}
            for key, result in contrasts.items():
                if not isinstance(result, dict):
                    raise TypeError("Contrast result must be an object")
                comparisons.append({"family": name, "contrast_key": key,
                                    "source_pointer": pointer(*prefix, "families", name, "contrasts", key),
                                    "family_metadata": deepcopy(metadata), "result": deepcopy(result)})
    return {"schema": SCHEMA, "source_report_sha256": digest, "population": population,
            "confirmatory": report["confirmatory"], "comparisons": comparisons,
            "analysis_metadata": analysis_metadata, "report_sections": sections,
            "numerical_verification_performed": False,
            "status": "source_projection_only_pending_independent_numerical_verification"}
