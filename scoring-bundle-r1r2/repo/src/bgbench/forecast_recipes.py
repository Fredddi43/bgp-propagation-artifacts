"""New-period recipe freeze contract (metadata only; versioned for the R1 custody consumer).

RETAINED-ARM-LEDGER-DRAFT.md requires every new-period recipe to be frozen before R1, because new-period
fitting can only start after R1 and R1 results must not be able to change any new-period choice. This module
defines what a recipe must say and checks it semantically, not only by hash:

* every required arm is present, including failed, not-executable and conditional arms; only N-trigger may
  be declared absent, and only with the bound infeasible trigger-selection report;
* calendars, horizons, seeds, panels, cohort, K, configuration source and fit counts agree with the frozen
  protocol constants below (these constants restate already frozen decisions; they choose nothing);
* every failure disposition is predeclared; nothing falls back to a default configuration;
* an unresolved recipe-level dependency keeps the recipe ``unresolved`` and the draft unsealable.

It never opens a model output, label, protected input or score. ``freeze_receipt`` only assembles the receipt
that ``forecast_retrospective_custody.checked_recipes`` reads; writing it is the CLI's job and needs an
independent review gate over the exact draft bytes.

Receipt contract ``new-period-recipe-freeze-v1`` (consumed by R1):

    kind = "new_period_recipe_freeze", contract_version, scope, frozen_before_r1 = True,
    passed = True, reviewer (actual independent reviewer), review {path, sha256}, draft {path, sha256},
    freezer_source_sha256, module_source_sha256, recipes {arm: {path, sha256} | "declared_absent"}, exposure_ledger {path, sha256},
    retuning_reserve_closed = True.

Every bound recipe file carries ``arm`` equal to its key, so a consumer can refuse a file that lacks it.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

CONTRACT_VERSION = "new-period-recipe-freeze-v1"
SCOPE = "new-period-recipe-freeze-v1"
DRAFT_KIND = "new_period_recipe_freeze_draft"
RECEIPT_KIND = "new_period_recipe_freeze"
RECIPE_SCHEMA = "newperiod-recipe-v1"
REVIEWER = re.compile(r"(?:(?:anthropic/)?claude-opus-5-5|(?:openai/)?gpt-6-astra)")
HEX64 = re.compile(r"^[0-9a-f]{64}$")

# Arms the R1 consumer requires (forecast_retrospective_custody.REQUIRED_RECIPES) plus L-recipe, which is
# frozen with the others although R1 only needs it before R2.
R1_REQUIRED = ("N-core", "N-frozen2025", "N-base", "N-gbdt", "N-temporal", "N-mean", "N-tsfm",
               "N-chronos-ad", "N-counts", "N-h1", "N-h3", "N-timing", "N-family", "N-delay",
               "N-withhold", "N-stable", "N-trigger")
REQUIRED = R1_REQUIRED + ("L-recipe",)
DECLARABLE_ABSENT = frozenset({"N-trigger"})

STATUSES = frozenset({"complete", "unresolved", "declared_absent"})  # "complete" = content complete; frozen only via receipt
KINDS = frozenset({"fit", "frozen_inference", "deterministic", "zero_shot_inference", "hash_only", "absent"})
FAILURE_KEYS = ("numerical", "resource", "software", "not_executable", "missing_input")
DEPENDENCY_KINDS = frozenset({"recipe", "execution"})

NEW_PERIOD_CALENDAR = {"train_start": "2025-01-01T00:00:00+00:00", "validation_start": "2026-04-01T00:00:00+00:00",
                       "test_start": "2026-09-01T00:00:00+00:00", "test_end": "2026-10-16T00:00:00+00:00"}
LIVE_CALENDAR = {"train_start": "2025-01-01T00:00:00+00:00", "validation_start": "2026-09-16T00:00:00+00:00",
                 "validation_end": "2026-10-01T00:00:00+00:00"}
REFERENCE_PANEL = ("route-views.linx", "route-views2", "route-views3", "rrc00", "rrc01",
                   "rrc03", "rrc12", "rrc15", "rrc20", "rrc25")
H3_PANELS = {"ris7": ("rrc00", "rrc01", "rrc03", "rrc12", "rrc15", "rrc20", "rrc25"),
             "mixed7": ("route-views.linx", "route-views2", "route-views3", "rrc00", "rrc03", "rrc12", "rrc25")}
SEEDS = [0, 1, 2, 3, 4]
REPRESENTATIVES = ["sage_history_on", "none_history_on"]

# Already frozen selections (no new choice): source record hashes.
CORE_SELECTION = {"configuration_id": 3, "record_sha256": "713883deb6dbc8b9f1b8e000895a95226e82c1b38696ac735a4e7ecf38f4fedb"}
GBDT_SELECTION = {"configuration_id": 4, "record_sha256": "f78b709f49147e356d85bfd83ced38c9e4407c5e5ab3d221f9c5cf3dd25e3f71"}
CHRONOS_SELECTION = {"configuration_id": 6, "record_sha256": "103667fa5f17215fdf2fed7c96dca93d3bf1c700f87268f86c361344b2be9a61"}
H1_SELECTION = {"k": 500, "record_sha256": "14595bc344728cfa4a10c4d23c9b5669f4eec938ecb8264d1437196178e7524a"}
TEMPORAL_SELECTION_SHA256 = "52d1a0f0a2effcb0400837180da74facb1ef7749d17f8269529c5c01ddf9ae1b"
SLICE_RULE_SHA256 = "0291d789ed0e2f9df87a7aac55414ca4c755ba0eaae545c0643bcf2a29759004"
TRIGGER_REPORT_SHA256 = "4fa6a15f2db36df33a0c46e0a3a86474980f559023a0e848c4c67c2cd4c2ab41"
NCORE_RECIPE_SHA256 = "1071f730961a31b405721d4ddf1781816a95b69303b8e91a8d9d23f0f0728b86"
NCORE_SNAPSHOT_SHA256 = "dae04f85e8f9120716719a145ed806ba702435e2d45d62633e5612114b820587"
FROZEN2025_PLAN_SHA256 = "d0b727fbf19cafe6947a24e2d6796e2fd1151b2e13760a5b31f63fa384396edf"
STABLE_SELECTION_SHA256 = "7ebedd6e32dd64b6de53425fcadc358a211cce29207cf9e025464f2bdb1eff77"
WITHHOLD_POLICY_SHA256 = "f6b0b7d4f574c4d669df0fab40c6f26e826e6dfcc5e1f6f3f779a5ecb66f4a13"

# Per-arm protocol expectations restated from the frozen documents (see REVIEW-PACKET-ALL-RECIPES.md).
# horizons: exact list; seeds: exact list; fits: exact logical fit count (None = must stay unresolved);
# selection: expected bound selection record; panels: exact input panels.
ARM_RULES = {
    "N-core": {"kind": "fit", "horizons": [30, 60], "seeds": SEEDS, "fits": 40, "selection": CORE_SELECTION},
    "N-frozen2025": {"kind": "frozen_inference", "horizons": [30, 60], "seeds": SEEDS, "fits": 0,
                     "selection": {"configuration_id": 3, "record_sha256": FROZEN2025_PLAN_SHA256}},
    "N-base": {"kind": "deterministic", "horizons": [30, 60], "seeds": [], "fits": 0},
    "N-gbdt": {"kind": "fit", "horizons": [30, 60], "seeds": [], "fits": 2, "selection": GBDT_SELECTION},
    "N-temporal": {"kind": "fit", "horizons": [30, 60], "seeds": SEEDS, "fits": 20},
    "N-mean": {"kind": "fit", "horizons": [30, 60], "seeds": SEEDS, "fits": 10},
    "N-tsfm": {"kind": "zero_shot_inference", "horizons": [30, 60], "seeds": [0], "fits": 0},
    "N-chronos-ad": {"kind": "fit", "horizons": [30, 60], "seeds": SEEDS, "fits": 5, "selection": CHRONOS_SELECTION},
    "N-counts": {"kind": "frozen_inference", "horizons": [30, 60], "seeds": [0], "fits": 0},
    "N-h1": {"kind": "fit", "horizons": [30, 60], "seeds": SEEDS, "fits": 20, "selection": CORE_SELECTION},
    "N-h3": {"kind": "fit", "horizons": [30, 60], "seeds": SEEDS, "fits": 40, "selection": CORE_SELECTION,
             "panels": ["ris7", "mixed7"]},
    "N-timing": {"kind": "fit", "horizons": [5, 10, 300, 900], "seeds": SEEDS, "fits": 40, "selection": CORE_SELECTION},
    "N-family": {"kind": "fit", "horizons": [30, 60], "seeds": SEEDS, "fits": 40, "selection": CORE_SELECTION},
    "N-delay": {"kind": "frozen_inference", "horizons": [30, 60], "seeds": SEEDS, "fits": 0},
    "N-withhold": {"kind": "frozen_inference", "horizons": [30, 60], "seeds": SEEDS, "fits": 0},
    "N-stable": {"kind": "frozen_inference", "horizons": [30, 60], "seeds": SEEDS, "fits": 0},
    "N-trigger": {"kind": "absent", "horizons": [], "seeds": [], "fits": 0},
    "L-recipe": {"kind": "hash_only", "horizons": [30, 60], "seeds": SEEDS, "fits": 20, "selection": CORE_SELECTION},
}
TWO_REPRESENTATIVE_ARMS = frozenset({"N-h1", "N-h3", "N-timing", "N-family", "L-recipe"})


def require(ok, message):
    if not ok:
        raise ValueError(message)


def canonical_bytes(doc) -> bytes:
    return (json.dumps(doc, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _ref(value, what):
    require(isinstance(value, dict) and isinstance(value.get("path"), str) and value["path"]
            and isinstance(value.get("sha256"), str) and HEX64.fullmatch(value["sha256"]), f"{what} is not a bound {{path, sha256}}")
    return value


def _cells(doc):
    """Declared cell count: models x horizons x seeds x panels x families (absent factors count once)."""
    n = 1
    for key in ("models", "horizons_s", "seeds", "panels", "families", "grids", "variants"):
        if key == "horizons_s" and doc.get("horizons_share_model") is True:
            continue
        values = doc.get(key)
        if values:
            n *= len(values)
    return n


def recipe_issues(arm, doc):
    """Semantic problems with one recipe; an empty list means the recipe text is internally complete.

    Dependencies are reported separately (``unresolved_dependencies``): a recipe can be well formed and still
    blocked.
    """
    issues = []

    def check(ok, message):
        if not ok:
            issues.append(f"{arm}: {message}")

    rules = ARM_RULES.get(arm)
    check(rules is not None, "not a required new-period arm")
    if rules is None or not isinstance(doc, dict):
        return issues or [f"{arm}: recipe is not an object"]
    check(doc.get("arm") == arm, "recipe must name its own arm in `arm`")
    check(doc.get("schema") == RECIPE_SCHEMA, f"schema must be {RECIPE_SCHEMA}")
    status = doc.get("status")
    check(status in STATUSES, f"status must be one of {sorted(STATUSES)}")
    check(doc.get("kind") == rules["kind"], f"kind must be {rules['kind']}")
    for i, item in enumerate(doc.get("documents") or [None]):
        try:
            _ref(item, f"document {i}")
        except ValueError as exc:
            issues.append(f"{arm}: {exc}")
    deps = doc.get("dependencies", [])
    check(isinstance(deps, list), "dependencies must be a list")
    for dep in deps if isinstance(deps, list) else []:
        check(isinstance(dep, dict) and dep.get("id") and dep.get("kind") in DEPENDENCY_KINDS
              and dep.get("status") in ("resolved", "unresolved") and isinstance(dep.get("detail"), str),
              f"malformed dependency {dep!r}")
        if isinstance(dep, dict) and dep.get("status") == "resolved":
            check(dep.get("evidence") is not None, f"resolved dependency {dep.get('id')} has no bound evidence")
            if dep.get("evidence") is not None:
                try:
                    _ref(dep["evidence"], f"evidence of {dep.get('id')}")
                except ValueError as exc:
                    issues.append(f"{arm}: {exc}")
    blocked = any(isinstance(d, dict) and d.get("kind") == "recipe" and d.get("status") == "unresolved" for d in deps or [])
    if status == "complete":
        check(not blocked, "a recipe with an unresolved recipe-level dependency cannot be complete")

    if arm == "N-trigger":
        check(status == "declared_absent", "N-trigger is declared absent under the frozen rule")
        evidence = doc.get("absence_evidence") or {}
        check(evidence.get("sha256") == TRIGGER_REPORT_SHA256 and evidence.get("selected") is None
              and evidence.get("status") == "infeasible_or_no_supported_incidents"
              and evidence.get("newperiod_outcomes_used") is False,
              "absence must bind the infeasible trigger-selection report 4fa6a15f… with selected null")
        check(isinstance(doc.get("consequence"), str) and doc["consequence"].strip(), "consequence of absence missing")
        return issues
    check(status != "declared_absent", "only N-trigger may be declared absent")

    check(doc.get("horizons_s") == rules["horizons"], f"horizons_s must be {rules['horizons']}")
    check(doc.get("seeds") == rules["seeds"], f"seeds must be {rules['seeds']}")
    calendar = LIVE_CALENDAR if arm == "L-recipe" else NEW_PERIOD_CALENDAR
    if arm == "L-recipe":
        check(doc.get("calendar") == calendar, "calendar must be the live-refit calendar of LIVE-REFIT-RECIPE.md")
    else:
        check(doc.get("calendar") == calendar, "calendar must equal the frozen new-period calendar")
    target = doc.get("target_panel")
    check(target == list(REFERENCE_PANEL), "target panel must be the fixed ten-collector reference panel")
    panels = doc.get("panels")
    if "panels" in rules:
        check(panels == rules["panels"], f"panels must be {rules['panels']}")
        for name in panels or []:
            check(doc.get("panel_members", {}).get(name) == list(H3_PANELS.get(name, ())),
                  f"panel {name} members differ from H3-PANEL-BUILDER.md")
    if arm in TWO_REPRESENTATIVE_ARMS:
        check(doc.get("models") == REPRESENTATIVES, f"models must be the two representatives {REPRESENTATIVES}")
    cohort = doc.get("cohort")
    check(isinstance(cohort, dict) and isinstance(cohort.get("id"), str) and isinstance(cohort.get("rule"), str),
          "cohort must name an id and a rule")
    config = doc.get("configuration")
    check(isinstance(config, dict) and isinstance(config.get("selection_rule"), str) and config["selection_rule"].strip(),
          "configuration must state its (already frozen) selection rule")
    if isinstance(config, dict):
        check(config.get("fallback") == "none", "configuration fallback must be 'none' (no default configuration)")
        expected = rules.get("selection")
        if expected and status == "complete":
            check(config.get("configuration_id") == expected["configuration_id"],
                  f"configuration_id must be {expected['configuration_id']}")
            record = config.get("record") or {}
            check(record.get("sha256") == expected["record_sha256"], "configuration record differs from the frozen selection")
    if arm == "N-h1":
        k = doc.get("k") or {}
        check(k.get("value") == H1_SELECTION["k"] and (k.get("record") or {}).get("sha256") == H1_SELECTION["record_sha256"],
              "N-h1 K must be 500 bound to h1-k-selection-v6b.json 14595bc3…")
        check(doc.get("slice_rule_sha256") == SLICE_RULE_SHA256, "N-h1 must retain the common 2025-training slice cut")
    if arm in ("N-temporal", "N-mean"):
        check(isinstance(config, dict) and (config.get("record") or {}).get("sha256") == TEMPORAL_SELECTION_SHA256,
              "temporal choice must bind the completed frozen selector")
        unavailable = {"status": "not_executable_no_finite_last_configuration", "configuration_id": None,
                       "logical_cells": 10}
        expected = ({"gru": {"status": "executable", "configuration_id": 4, "logical_cells": 10},
                     "tgn": unavailable} if arm == "N-temporal" else {"mean_tgn": unavailable})
        check(doc.get("model_dispositions") == expected, "retain unavailable Last/Mean cells without a fallback")
        check(doc.get("executable_fits") == (10 if arm == "N-temporal" else 0), "wrong executable temporal fit count")
    if arm == "N-delay":
        check(doc.get("consumers") == ["sage_history_on", "online_history_k20"], "N-delay must follow the Q1 consumer scope")
    if arm == "N-counts":
        check(doc.get("checkpoint_origin") == "retrospective-2025-count-controls", "N-counts must reuse the frozen 2025 controls")
    fits = doc.get("fits")
    if rules["fits"] is None:
        check(status == "unresolved", "fit count is not fixed by any frozen document; the recipe stays unresolved")
    else:
        check(fits == rules["fits"], f"fits must be {rules['fits']}")
        if rules["kind"] in ("fit", "hash_only"):
            check(_cells(doc) == rules["fits"],
                  f"declared cells (models x horizons x seeds x panels x families x grids x variants) must equal {rules['fits']}")
    failure = doc.get("failure_rule")
    check(isinstance(failure, dict), "failure_rule must be a mapping")
    for key in FAILURE_KEYS:
        check(isinstance(failure, dict) and isinstance(failure.get(key), str) and failure[key].strip(),
              f"failure_rule.{key} must be predeclared")
    check(doc.get("retuning") == "none", "retuning must be 'none' (the counted reserve closes before R1)")
    check(isinstance(doc.get("implementation"), dict), "implementation must state snapshot/driver status")
    return issues


def unresolved_dependencies(arm, doc):
    return [{"arm": arm, **d} for d in doc.get("dependencies", []) if isinstance(d, dict) and d.get("status") == "unresolved"]


def validate_draft(draft):
    """Whole-draft check. Returns a report; never raises for content problems (they are listed)."""
    require(isinstance(draft, dict) and draft.get("kind") == DRAFT_KIND, "Not a new-period recipe freeze draft")
    require(draft.get("contract_version") == CONTRACT_VERSION, f"Draft must use contract {CONTRACT_VERSION}")
    recipes = draft.get("recipes")
    require(isinstance(recipes, dict), "Draft has no recipes mapping")
    issues = [f"missing required recipe {arm}" for arm in REQUIRED if arm not in recipes]
    issues += [f"unknown recipe {arm}" for arm in recipes if arm not in REQUIRED]
    blockers = {"recipe": [], "execution": []}
    status = {}
    for arm in REQUIRED:
        doc = recipes.get(arm)
        if doc is None:
            continue
        issues += recipe_issues(arm, doc)
        if not isinstance(doc, dict):
            continue
        status[arm] = doc.get("status")
        for dep in unresolved_dependencies(arm, doc):
            if dep.get("kind") in blockers:
                blockers[dep["kind"]].append(dep)
        if doc.get("status") == "unresolved" and not any(d["arm"] == arm for d in blockers["recipe"]):
            issues.append(f"{arm}: status unresolved but no recipe-level dependency explains why")
    reserve = draft.get("retuning_reserve") or {}
    if reserve.get("closes_before_r1") is not True:
        issues.append("retuning reserve must close before R1")
    if reserve.get("invoked_fits") != 0:
        issues.append("retuning reserve invocation must be explicit: 0, or each invoked fit enumerated as its own recipe")
    for addendum in draft.get("addenda", []):
        if not (isinstance(addendum, dict) and addendum.get("id") and addendum.get("supersedes_text_in")
                and addendum.get("decision_source")):
            issues.append(f"malformed addendum {addendum!r}")
    ready = (not issues and not blockers["recipe"]
             and all(status.get(a) == ("declared_absent" if a in DECLARABLE_ABSENT else "complete") for a in REQUIRED))
    return {"contract_version": CONTRACT_VERSION, "issues": issues, "status": status,
            "recipe_blockers": blockers["recipe"], "execution_blockers": blockers["execution"],
            "seal_ready": ready}


def verify_local_documents(draft, root):
    """Re-hash every document a recipe cites that exists under ``root`` (repo-relative paths)."""
    mismatches, checked = [], 0
    for arm, doc in sorted((draft.get("recipes") or {}).items()):
        for item in doc.get("documents", []) + [d.get("evidence") for d in doc.get("dependencies", []) if d.get("evidence")]:
            if not isinstance(item, dict) or str(item.get("path", "")).startswith("/"):
                continue
            path = Path(root) / item["path"]
            if not path.exists():
                mismatches.append({"arm": arm, "path": item["path"], "problem": "missing"})
                continue
            checked += 1
            if sha256_bytes(path.read_bytes()) != item["sha256"]:
                mismatches.append({"arm": arm, "path": item["path"], "problem": "sha256 differs"})
    return {"checked": checked, "mismatches": mismatches}


def verify_recipe_evidence(draft, root, read_bytes=None):
    """Rehash documentary/selection/dependency evidence, including absolute cluster refs.

    Execution-only source snapshots can be directories with their own manifest digest;
    those are checked by the separately approved execution adapter, not as file hashes.
    """
    reader = read_bytes or (lambda path: Path(path).read_bytes())
    refs = []
    for doc in draft["recipes"].values():
        refs.extend(doc.get("documents", []))
        refs.extend(d["evidence"] for d in doc.get("dependencies", []) if d.get("status") == "resolved")
        for field in ("configuration", "k"):
            record = (doc.get(field) or {}).get("record")
            if record:
                refs.append(record)
        absence = doc.get("absence_evidence") or {}
        if absence.get("path"):
            refs.append(absence)
    for addendum in draft.get("addenda", []):
        refs.append(addendum["supersedes_text_in"])
        refs.extend(addendum["decision_source"])
    for ref in refs:
        _ref(ref, "recipe evidence")
        path = Path(ref["path"])
        if not path.is_absolute():
            path = Path(root) / path
        require(sha256_bytes(reader(str(path))) == ref["sha256"], f"Recipe evidence changed: {path}")
    return len(refs)


def check_existing_core(doc_bytes):
    """N-core is already frozen (metadata only): its immutable file must carry the expected semantics."""
    require(sha256_bytes(doc_bytes) == NCORE_RECIPE_SHA256, "N-core recipe bytes differ from 1071f730…")
    doc = json.loads(doc_bytes)
    require(doc.get("arm") == "N-core" and doc.get("schema") == "newperiod-core-development-recipe-v1"
            and doc.get("configuration_id") == 3 and doc.get("horizons") == [30, 60] and doc.get("seeds") == SEEDS
            and doc.get("fit_count") == 40 and doc.get("epochs") == 20
            and (doc.get("fit_snapshot") or {}).get("sha256") == NCORE_SNAPSHOT_SHA256
            and (doc.get("core_ledger") or {}).get("sha256") == CORE_SELECTION["record_sha256"]
            and doc.get("calendar") == {"train_start": NEW_PERIOD_CALENDAR["train_start"],
                                        "validation_start": NEW_PERIOD_CALENDAR["validation_start"],
                                        "validation_end": NEW_PERIOD_CALENDAR["test_start"]}
            and isinstance(doc.get("failure_rule"), str) and "numerical" in doc["failure_rule"],
            "N-core recipe semantics differ from the frozen metadata")
    return doc


def checked_review(review_doc, *, draft_sha256, freezer_source_sha256, module_source_sha256,
                   exposure_ledger_sha256):
    require(review_doc.get("passed") is True, "Independent review has not passed")
    require(REVIEWER.fullmatch(str(review_doc.get("reviewer", ""))), "Independent authorized review required")
    require(review_doc.get("scope") == SCOPE, "Review covers another scope")
    require(review_doc.get("draft_sha256") == draft_sha256, "Review covers other draft bytes")
    require(review_doc.get("freezer_source_sha256") == freezer_source_sha256, "Review covers other freezer code")
    require(review_doc.get("module_source_sha256") == module_source_sha256, "Review covers other recipe module")
    require(review_doc.get("exposure_ledger_sha256") == exposure_ledger_sha256, "Review covers another exposure ledger")
    require(review_doc.get("labels_authorized") is False and review_doc.get("fits_authorized") is False,
            "A recipe review never authorizes labels or fits")
    return review_doc


def check_exposure(doc):
    require(doc.get("kind") == "forecast_exposure_ledger" and doc.get("schema_version") == 1,
            "Wrong exposure ledger schema")
    require(doc.get("pristine_holdout_claim") is False and doc.get("complete_access_audit_claim") is False,
            "Exposure ledger must retain known audit limitations")
    require(isinstance(doc.get("known_exposures"), list) and bool(doc["known_exposures"])
            and any(e.get("influence_on_decisions") == "unknown; absence of influence is not established"
                    for e in doc["known_exposures"]), "Prior exposure and unknown influence must remain explicit")
    require(doc.get("test_scoring_authorized") is False and doc.get("r1_release_authorized") is False,
            "Exposure ledger is not release authority")


def verify_exposure_evidence(doc, root, read_bytes=None):
    """Verify both ledger-level and individual exposure documentary anchors."""
    reader = read_bytes or (lambda path: Path(path).read_bytes())
    refs = list(doc.get("evidence", []))
    for exposure in doc.get("known_exposures", []):
        refs.extend(exposure.get("evidence", []))
    for ref in refs:
        _ref(ref, "exposure evidence")
        path = Path(ref["path"])
        if not path.is_absolute():
            path = Path(root) / path
        require(sha256_bytes(reader(str(path))) == ref["sha256"], f"Exposure evidence changed: {path}")
    return len(refs)


def freeze_receipt(*, draft, draft_ref, review_doc, review_ref, recipe_refs, exposure_ledger_ref,
                   freezer_source_sha256, module_source_sha256, evidence_root):
    """Assemble (not write) the receipt. ``recipe_refs`` maps arm -> {path, sha256} of the written recipe file."""
    report = validate_draft(draft)
    require(report["seal_ready"], f"Draft is not seal-ready: {len(report['issues'])} issues, "
                                  f"{len(report['recipe_blockers'])} recipe blockers")
    checked_review(review_doc, draft_sha256=draft_ref["sha256"], freezer_source_sha256=freezer_source_sha256,
                   module_source_sha256=module_source_sha256, exposure_ledger_sha256=exposure_ledger_ref["sha256"])
    recipes = {}
    for arm in REQUIRED:
        if arm in DECLARABLE_ABSENT and draft["recipes"][arm]["status"] == "declared_absent":
            recipes[arm] = "declared_absent"
        else:
            recipes[arm] = _ref(recipe_refs.get(arm), f"recipe file of {arm}")
    return {"kind": RECEIPT_KIND, "contract_version": CONTRACT_VERSION, "scope": SCOPE,
            "frozen_before_r1": True, "passed": True, "reviewer": review_doc["reviewer"],
            "review": _ref(review_ref, "review"), "draft": _ref(draft_ref, "draft"),
            "freezer_source_sha256": freezer_source_sha256, "recipes": recipes,
            "module_source_sha256": module_source_sha256,
            "evidence_root": str(Path(evidence_root).resolve()),
            "exposure_ledger": _ref(exposure_ledger_ref, "exposure ledger"),
            "retuning_reserve_closed": True}


def receipt_issues(receipt, read_bytes):
    """Revalidate a complete freeze, using the caller's read-once byte cache."""
    def load(ref, name):
        _ref(ref, name)
        raw = read_bytes(ref["path"])
        require(sha256_bytes(raw) == ref["sha256"], f"{name} bytes differ")
        return raw, json.loads(raw)

    try:
        require(receipt.get("kind") == RECEIPT_KIND and receipt.get("contract_version") == CONTRACT_VERSION
                and receipt.get("scope") == SCOPE and receipt.get("passed") is True, "receipt kind/scope/status")
        require(receipt.get("frozen_before_r1") is True and receipt.get("retuning_reserve_closed") is True,
                "receipt is not a pre-R1 freeze with reserve closed")
        _, draft = load(receipt["draft"], "draft")
        _, review = load(receipt["review"], "review")
        _, exposure = load(receipt["exposure_ledger"], "exposure ledger")
        check_exposure(exposure)
        verify_exposure_evidence(exposure, receipt["evidence_root"], read_bytes)
        report = validate_draft(draft)
        require(report["seal_ready"], "bound draft is not seal-ready")
        verify_recipe_evidence(draft, receipt["evidence_root"], read_bytes)
        checked_review(review, draft_sha256=receipt["draft"]["sha256"],
                       freezer_source_sha256=receipt["freezer_source_sha256"],
                       module_source_sha256=receipt["module_source_sha256"],
                       exposure_ledger_sha256=receipt["exposure_ledger"]["sha256"])
        require(receipt.get("reviewer") == review["reviewer"], "receipt reviewer differs")
        recipes = receipt["recipes"]
        require(set(recipes) == set(REQUIRED), "receipt recipe set differs")
        for arm in REQUIRED:
            item = recipes[arm]
            if item == "declared_absent":
                require(arm in DECLARABLE_ABSENT and draft["recipes"][arm]["status"] == "declared_absent",
                        f"{arm} cannot be declared absent")
                continue
            raw, doc = load(item, arm)
            require(doc.get("arm") == arm, f"{arm} file lacks or misnames arm")
            if arm == "N-core":
                check_existing_core(raw)
            else:
                require(doc == draft["recipes"][arm], f"{arm} differs from reviewed draft")
                require(not recipe_issues(arm, doc) and doc.get("status") == "complete", f"{arm} is incomplete")
        return []
    except (ValueError, KeyError, TypeError, OSError) as exc:
        return [str(exc)]
