"""History-sensitivity variants R-delay900, R-delay1800 and R-withhold: inputs, scope and commitment receipts.

REVIEW-PACKET-HISTORY-SENSITIVITY-EXECUTION.md A1-A5 under the owner choices of
HISTORY-SENSITIVITY-EXECUTION-DECISIONS.md (pending independent review; nothing here is an
execution approval). Pure functions; the I/O drivers are in
``scripts/forecast_history_sensitivity_campaign.py``.

* ``derive_variant_event``: one primary tensor -> its variant tensor for NON-expanded candidates.
  Only ``x[:, 10]``, ``history_provenance`` and ``forecast_contract`` (library digest, explicit
  ``history_intervention``) change, each recomputed independently from the libraries; every other
  field is required to be exactly equal. Expanded (H1) tensors are refused: their candidate set
  depends on history and needs the builder hook ``tgn_data.build_split(history_intervention=)``.
* ``variant_manifest`` / ``variant_gate``: separate derived manifest and input gate per variant and
  horizon (H3 pattern), binding variant kind/value, policy, donor IDs, original manifest and library,
  parent tensor bytes and variant tensor bytes. Original and other-variant tensors are refused.
* ``consumer_scope``: every retained history consumer with its declared seeds, failures and
  missing-parent dependencies, enumerated from the retained-arm ledger; one factor per variant.
* ``commitment_index`` / ``frozen_model_ledger`` / ``frozen_model_receipt``: the pre-R1 receipt binds
  prediction commitments (``scores_computed: false``), never scores (decision 4).

``withhold_snapshot`` keeps ``source_digest``, so a withheld tensor's library digest equals the
primary's: the intervention identity is the explicit ``history_intervention`` contract field.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np

HISTORY_INDEX = 10
WITHHOLD_KIND = "withhold_unavailable_source_donors"
DELAY_KIND = "availability_delay"
# The three one-factor variants of decision 1. Delay values are the only ones the new-period path accepts too.
VARIANTS = {"delay900": (DELAY_KIND, 900), "delay1800": (DELAY_KIND, 1800), "withhold": (WITHHOLD_KIND, None)}
# Fields a derived non-expanded variant tensor may differ in; everything else must be exactly equal.
CHANGED_FIELDS = ("x", "history_provenance", "forecast_contract", "history_sensitivity_derivation")
INDEX_KIND = "history_sensitivity_prediction_commitment_index"
LEDGER_KIND = "history_sensitivity_frozen_model_ledger"
SCOPE_KIND = "history_sensitivity_consumer_scope"
DECLARATION_KIND = "history_sensitivity_consumer_declaration"
GATE_KIND = "history_sensitivity_variant_input_gate"
RECEIPT_RESULTS_KIND = "prediction_commitment_index_v1"
DELAY_RECEIPT_KIND = "history_delay_frozen_model_sensitivity"
# Decision 1. Arms that must be declared history consumers, and arms that consume no history. R-panelfix (the
# frozen SAGE+history fits) consumes history through ten aliases of R-core cells, never duplicate predictions.
REQUIRED_CONSUMERS = ("R-core", "R-base", "R-gbdt", "R-temporal", "R-mean", "R-h1", "R-h1-ood", "R-h3", "R-transfer",
                      "R-panelfix")
ALIAS_ARMS = {"R-panelfix": {"target_arm": "R-core", "cells": 10}}
# Diagnostic axes: crossing them with a history sensitivity is a forbidden cross-product (decision 1).
DIAGNOSTIC_AXES = ("R-temporal-order",)
ROLES = ("history_consumer", "no_history", "sensitivity_axis", "diagnostic_axis_not_crossed")
PARENT_LEDGER_KIND = "history_sensitivity_parent_commitment_ledger"
NON_CONSUMERS = ("R-counts", "R-tsfm", "R-chronos-ad")
# The intervention axes themselves: never crossed with each other (decision 1, last sentence).
SENSITIVITY_AXES = ("R-delay", "R-withhold", "R-stable")
PARENT_STATUSES = ("final", "failed", "pending_parent")


class VariantError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise VariantError(message)


def canonical_sha(doc):
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def ids_sha256(ids):
    """The ``withhold_snapshot``/gate convention: newline-joined sorted IDs."""
    return hashlib.sha256("\n".join(sorted(ids)).encode()).hexdigest()


def _hex64(value, name):
    require(isinstance(value, str) and len(value) == 64 and not set(value) - set("0123456789abcdef"),
            f"{name} must be a SHA256 hex digest")
    return value


# ---- intervention identity ----------------------------------------------------------------------------------------

def intervention_identity(variant, *, spec=None):
    """The explicit identity a variant tensor's contract carries (``history_intervention``)."""
    require(variant in VARIANTS, f"Unknown history variant {variant!r}; only {sorted(VARIANTS)} are declared")
    kind, value = VARIANTS[variant]
    if kind == DELAY_KIND:
        require(spec is None, "A delay variant takes no withholding spec")
        return {"kind": DELAY_KIND, "variant": variant, "availability_delay_s": value}
    require(isinstance(spec, dict), "The withhold variant needs the frozen withholding spec")
    require(spec.get("kind") == WITHHOLD_KIND and spec.get("retraining_fits") == 0, "Not the withholding spec")
    ids = sorted(spec.get("withheld_event_ids") or [])
    require(ids and len(set(ids)) == len(ids), "The spec must name unique withheld donors")
    return {"kind": WITHHOLD_KIND, "variant": variant, "policy_sha256": _hex64(spec.get("policy_sha256"), "policy_sha256"),
            "withheld_event_ids": ids, "withheld_ids_sha256": ids_sha256(ids)}


def builder_intervention(value, *, availability_delay_s):
    """Validate ``tgn_data.build_split(history_intervention=...)``; returns the contract identity.

    A delay identity must equal the manifest delay the builder already applies; a withhold identity is
    applied by the builder through ``withhold_snapshot``.
    """
    require(isinstance(value, dict), "history_intervention must be an identity dict")
    variant = value.get("variant")
    require(variant in VARIANTS and VARIANTS[variant][0] == value.get("kind"), "Unknown history intervention")
    if value["kind"] == DELAY_KIND:
        expected = intervention_identity(variant)
        require(value == expected, "Delay intervention differs from its declared identity")
        require(availability_delay_s == expected["availability_delay_s"],
                "Delay intervention differs from the manifest availability_delay_s the builder applies")
        return expected
    identity = intervention_identity(variant, spec={"kind": WITHHOLD_KIND, "retraining_fits": 0,
                                                    "policy_sha256": value.get("policy_sha256"),
                                                    "withheld_event_ids": value.get("withheld_event_ids")})
    require(value == identity, "Withhold intervention differs from its declared identity")
    require(availability_delay_s == 0, "Withholding is never crossed with a delay")
    return identity


# ---- source rule (decision 7) ---------------------------------------------------------------------------------------

def require_no_label_available_override(data_root, years, family="leak"):
    """Refuse event tables whose absolute ``label_available_at`` would defeat a delay intervention.

    ``CompletedEventLibrary.from_eventsets`` uses ``max(boundary, label_available_at)`` instead of
    ``boundary + delay`` whenever a row carries that value, so a delay would be silently ignored.
    """
    import polars as pl
    checked = {}
    for year in sorted(set(map(int, years))):
        path = Path(data_root) / "eventset" / (f"{year}_{family}" if family else str(year)) / "events.parquet"
        schema = pl.read_parquet_schema(path)
        if "label_available_at" in schema:
            values = pl.read_parquet(path, columns=["error", "label_available_at"]).filter(pl.col("error").is_null())
            require(values["label_available_at"].null_count() == values.height,
                    f"{path} carries label_available_at; it would override the declared history delay")
        checked[str(year)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return checked


def variant_library(data_root, years, family, variant, *, panel_options=None, primary_library=None):
    """The library a variant reads: the delayed library, or the primary library for withholding."""
    from .forecast_history import CompletedEventLibrary
    kind, value = VARIANTS[variant]
    if kind == WITHHOLD_KIND:
        require(primary_library is not None, "Withholding reads the primary library")
        return primary_library
    require_no_label_available_override(data_root, years, family)
    return CompletedEventLibrary.from_eventsets(Path(data_root), years, family, **(panel_options or {}),
                                                availability_delay_s=value)


def panel_options_of(provenance):
    """The ``from_eventsets`` panel options that reproduce a recorded snapshot scope."""
    if provenance.get("collectors") == "separate_signature_and_target_panels":
        pick = lambda v: None if v == "pooled" else tuple(v)  # noqa: E731
        return {"signature_collectors": pick(provenance["signature_collectors"]),
                "target_collectors": pick(provenance["target_collectors"])}
    collectors = provenance.get("collectors")
    return {"collectors": None if collectors == "pooled" else tuple(collectors)}


# ---- tensor transform (A1 for non-expanded candidates) ------------------------------------------------------------

def _np(value):
    return value.numpy() if hasattr(value, "numpy") else np.asarray(value)


def history_column(asns, participation):
    """``tgn_data.build_event``'s column 10, bit for bit: float32(log1p(count)) per candidate."""
    return np.array([np.log1p(participation.get(int(a), 0)) for a in _np(asns).tolist()], dtype=np.float32)


def _same(a, b):
    if hasattr(a, "shape") or hasattr(b, "shape"):
        a, b = _np(a), _np(b)
        return a.shape == b.shape and a.dtype == b.dtype and np.array_equal(a, b)
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_same(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return type(a) is type(b) and len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
        return True
    return type(a) is type(b) and a == b


def _expected_provenance(snapshot, provenance, signature_digest):
    if provenance.get("history_root") is None:
        return snapshot.provenance
    return {**snapshot.provenance, "history_root": provenance["history_root"], "signature_source_digest": signature_digest}


def derive_variant_event(container, *, primary_library, library, identity, parent_sha256,
                         signature_digest=None):
    """Variant tensor of one primary non-expanded tensor; refuses anything else.

    ``library`` is the variant library (delay) or the primary library (withhold). ``signature_digest``
    is the variant data-root signature library digest, needed only for split-root (transfer) tensors.
    """
    from .forecast_history import utc
    from .forecast_history_sensitivity import withhold_snapshot
    eid = container["event_id"]
    contract, provenance = container.get("forecast_contract"), container.get("history_provenance")
    require(isinstance(contract, dict) and contract.get("history_mode") == "shared_completed" and provenance,
            f"{eid}: not a shared completed-history tensor")
    require("candidate_expansion" not in contract and "candidate_expansion" not in container,
            f"{eid}: expanded candidates depend on history; rebuild with the builder hook instead")
    require("history_intervention" not in contract and "history_sensitivity_derivation" not in container
            and "history_intervention" not in provenance, f"{eid}: input is already a variant tensor")
    require(contract.get("history_source_digest") == primary_library.digest == provenance.get("source_digest"),
            f"{eid}: tensor was not built from the primary library")
    _hex64(parent_sha256, "parent tensor sha256")
    issue_time, frozen_at = utc(provenance["issue_time"]), contract.get("history_frozen_at")
    primary = primary_library.snapshot(issue_time, exclude_event_id=eid, frozen_at=frozen_at)
    split_root = provenance.get("history_root") is not None
    require(provenance == _expected_provenance(primary, provenance, provenance.get("signature_source_digest")),
            f"{eid}: stored history provenance differs from the primary library snapshot")
    x = _np(container["x"])
    require(x.dtype == np.float32 and x.ndim == 2 and x.shape[1] > HISTORY_INDEX, f"{eid}: unexpected feature tensor")
    require(np.array_equal(x[:, HISTORY_INDEX], history_column(container["asn"], primary.participation)),
            f"{eid}: stored column 10 differs from the independent primary recomputation")
    donor_row = False
    if identity["kind"] == WITHHOLD_KIND:
        require(library is primary_library, "Withholding must read the primary library")
        require(all(d in primary_library.by_id for d in identity["withheld_event_ids"]),
                "Withheld donors are not in the primary library")
        # A withheld donor's own query row (the transfer cohort keeps it): its snapshot already excludes it, so
        # withholding is a no-op there. The row is carried with the identity and an explicit annotation, never
        # dropped from the cohort; transfer training membership stays unchanged (spec).
        donor_row = eid in identity["withheld_event_ids"]
        require(not donor_row or all(e.event_id != eid for e in primary.events),
                f"{eid}: a donor's own snapshot must exclude it")
        variant = withhold_snapshot(primary, identity["withheld_event_ids"], policy_sha256=identity["policy_sha256"])
        new_signature_digest = provenance.get("signature_source_digest")
        new_digest = primary_library.digest
    else:
        require(library is not primary_library and library.digest != primary_library.digest,
                "A delay variant needs its own library")
        require(library.sources[0] == {"availability_delay_s": identity["availability_delay_s"]},
                "Variant library delay differs from the declared identity")
        require(library.scope == {k: provenance.get(k) for k in library.scope},
                f"{eid}: variant library scope differs from the primary panel scope")
        require(library.sources[1:] == primary_library.sources[1:],
                "Variant library reads different source files than the primary library")
        variant = library.snapshot(issue_time, exclude_event_id=eid, frozen_at=frozen_at)
        new_digest = library.digest
        new_signature_digest = signature_digest
        if split_root:
            require(isinstance(signature_digest, str) and signature_digest != provenance["signature_source_digest"],
                    f"{eid}: a split-root delay variant needs its delayed signature library digest")
    for key in ("issue_time", "availability_cutoff", "excluded_event_id"):
        require(variant.provenance[key] == primary.provenance[key], f"{eid}: intervention changed the forecast clock")
    new_x = x.copy()
    new_x[:, HISTORY_INDEX] = history_column(container["asn"], variant.participation)
    new_contract = {**contract, "history_source_digest": new_digest, "history_intervention": identity}
    if split_root:
        new_contract["signature_source_digest"] = new_signature_digest
    derived = dict(container)
    if isinstance(container["x"], np.ndarray):
        derived["x"] = new_x
    else:
        import torch
        derived["x"] = torch.from_numpy(new_x)
    derived["history_provenance"] = _expected_provenance(variant, provenance, new_signature_digest)
    derived["forecast_contract"] = new_contract
    derived["history_sensitivity_derivation"] = {
        "method": "independent_column10_and_provenance_recomputation_non_expanded_candidates",
        "parent_tensor_sha256": parent_sha256, "intervention": identity,
        "primary_library_digest": primary_library.digest, "variant_library_digest": new_digest,
        "changed_fields": ["x[:, 10]", "history_provenance", "forecast_contract.history_source_digest",
                           "forecast_contract.history_intervention"]
                          + (["forecast_contract.signature_source_digest", "history_provenance.signature_source_digest"]
                             if split_root and identity["kind"] == DELAY_KIND else []),
        "column10_entries_changed": int((new_x[:, HISTORY_INDEX] != x[:, HISTORY_INDEX]).sum())}
    if donor_row:
        require(variant.participation == primary.participation and np.array_equal(new_x, x),
                f"{eid}: withholding changed a donor's own query row")
        derived["history_sensitivity_derivation"]["withheld_donor_own_query_row"] = (
            "no-op: the donor's own snapshot excludes it; column 10 and participation are bit-identical to the "
            "primary; the row stays in the cohort and in transfer training")
    check_unchanged(container, derived)
    return derived


def check_unchanged(primary, derived):
    """Every field outside the declared intervention is exactly equal (labels included, never output)."""
    eid = primary["event_id"]
    require(set(derived) - set(CHANGED_FIELDS) == set(primary) - set(CHANGED_FIELDS),
            f"{eid}: variant adds or drops tensor fields")
    for key in set(primary) - set(CHANGED_FIELDS):
        require(_same(primary[key], derived[key]), f"{eid}: unchanged field {key} differs")
    a, b = _np(primary["x"]), _np(derived["x"])
    others = [c for c in range(a.shape[1]) if c != HISTORY_INDEX]
    require(a.shape == b.shape and a.dtype == b.dtype and np.array_equal(a[:, others], b[:, others]),
            f"{eid}: a feature other than column 10 changed")
    pc, dc = primary["forecast_contract"], derived["forecast_contract"]
    allowed = {"history_source_digest", "history_intervention", "signature_source_digest"}
    require(all(_same(pc.get(k), dc.get(k)) for k in (set(pc) | set(dc)) - allowed),
            f"{eid}: a forecast contract field outside the intervention changed")
    pp, dp = primary["history_provenance"], derived["history_provenance"]
    for key in ("issue_time", "availability_cutoff", "excluded_event_id", "history_root"):
        require(pp.get(key) == dp.get(key), f"{eid}: provenance {key} changed")


# ---- variant manifests and gates (A3) -----------------------------------------------------------------------------

def variant_manifest(original, original_sha256, identity, tensors, *, primary_library_digest, variant_library_digest,
                     tensor_manifest_sha256):
    """Original rows byte-for-byte plus ``graph_path``/``graph_sha256`` (decision 7: inherited cohort metadata).

    ``tensors``: {event_id: {"path", "sha256", "parent_sha256"}} for every manifest event.
    ``tensor_manifest_sha256`` is the manifest digest the variant tensors carry in their contract.

    A derived parent manifest (an H3 panel manifest, or any manifest with ``source_manifest_sha256``) is
    accepted: its rows keep every field except ``graph_path``/``graph_sha256``, which must have named exactly the
    parent tensors, and its ``source_manifest_sha256`` must be the digest the tensors carry. A manifest that is
    already a history variant is refused (no crossed interventions).
    """
    require("history_sensitivity" not in original, "Original manifest is already a history variant")
    require(not original.get("locked_test") and not original.get("protected_test") and not original.get("manifest_kind"),
            "Only retrospective manifests are supported here; new-period variants need their own recipe")
    ids = [r["event_id"] for r in original["events"]]
    require(len(set(ids)) == len(ids) and set(tensors) == set(ids), "Variant tensors must cover exactly the manifest IDs")
    derived_parent = "source_manifest_sha256" in original
    if derived_parent:
        require(original["source_manifest_sha256"] == tensor_manifest_sha256,
                "Derived parent manifest names another tensor manifest digest")
        require(all(r.get("graph_sha256") == tensors[r["event_id"]]["parent_sha256"] for r in original["events"]),
                "Derived parent manifest rows name other parent tensors")
    events = [{**row, "graph_path": str(tensors[row["event_id"]]["path"]),
               "graph_sha256": _hex64(tensors[row["event_id"]]["sha256"], "graph_sha256")} for row in original["events"]]
    doc = {k: v for k, v in original.items() if k not in ("events", "manifest_sha256")}
    if identity["kind"] == DELAY_KIND:
        doc["availability_delay_s"] = identity["availability_delay_s"]
    doc.update(
        source_manifest_sha256=tensor_manifest_sha256,
        training_authorized=False, fit_authority="none",
        history_sensitivity={
            "intervention": identity, "original_manifest_sha256": original_sha256,
            "original_manifest_kind": "derived" if derived_parent else "root",
            "original_availability_delay_s": original.get("availability_delay_s", 0),
            "primary_library_digest": primary_library_digest, "variant_library_digest": variant_library_digest,
            "parent_tensor_sha256": {e: tensors[e]["parent_sha256"] for e in sorted(tensors)},
            "row_metadata": "inherited unchanged from the primary query cohort (splits, onsets, issue times and "
                            "label_available_at of the query rows); the variant's history delay governs donor "
                            "availability and the library digest only",
            "use": "frozen inference-only sensitivity; never training, cohort selection, tuning or calibration"},
        events=events)
    doc["manifest_sha256"] = canonical_sha({k: v for k, v in doc.items() if k != "manifest_sha256"})
    return doc


def variant_gate(identity, manifests, *, primary_gate, other_gates=(), spec_sha256=None, code_sha256=None):
    """Separate input gate for one variant: refuses primary and other-variant tensor bytes.

    ``manifests``: [{"path", "sha256", "doc", "delta_s", "tensor_contracts": {event_id: contract}}].
    """
    primary_hashes = {r["sha256"] for m in primary_gate["manifests"] for r in m["inputs"]}
    other_hashes = {r["sha256"] for g in other_gates for m in g["manifests"] for r in m["inputs"]}
    entries = []
    for m in manifests:
        doc = m["doc"]
        require(doc["history_sensitivity"]["intervention"] == identity, "Manifest is bound to another intervention")
        inputs = []
        for row in doc["events"]:
            digest = row["graph_sha256"]
            require(digest not in primary_hashes, f"{row['event_id']}: original primary tensor bytes in a variant gate")
            require(digest not in other_hashes, f"{row['event_id']}: another variant's tensor bytes")
            contract = m["tensor_contracts"][row["event_id"]]
            require(contract.get("history_intervention") == identity,
                    f"{row['event_id']}: tensor contract carries a different intervention")
            require(contract.get("history_source_digest") == doc["history_sensitivity"]["variant_library_digest"],
                    f"{row['event_id']}: tensor library differs from the variant library")
            require(contract.get("manifest_sha256") == doc["source_manifest_sha256"],
                    f"{row['event_id']}: tensor/manifest digest mismatch")
            inputs.append({"event_id": row["event_id"], "path": row["graph_path"], "sha256": digest,
                           "parent_sha256": doc["history_sensitivity"]["parent_tensor_sha256"][row["event_id"]],
                           "forecast_contract": contract})
        entries.append({"path": str(m["path"]), "sha256": m["sha256"], "delta_s": m["delta_s"],
                        "source_manifest_sha256": doc["source_manifest_sha256"],
                        "original_manifest_sha256": doc["history_sensitivity"]["original_manifest_sha256"],
                        "inputs": inputs})
    require(len({e["delta_s"] for e in entries}) == len(entries), "One variant manifest per horizon")
    return {"kind": GATE_KIND, "passed": True, "intervention": identity, "spec_sha256": spec_sha256,
            "code_sha256": code_sha256, "primary_gate_sha256": primary_gate.get("_sha256"),
            "training_authorized": False, "prediction_authorized": False, "test_scoring_authorized": False,
            "fit_authority": "none", "manifests": entries}


# ---- consumer scope (decisions 1 and 2) ---------------------------------------------------------------------------

def _scope_cell(cid, arm_id, parent_ledgers, declared):
    """One declared cell resolved against its parent commitment ledger; nothing is taken from the declaration
    that the ledger states (B-1). Returns (status, facts, parent binding)."""
    ref = declared.get("parent") or {}
    ledger_id, name = ref.get("ledger"), ref.get("name")
    require(isinstance(ledger_id, str) and isinstance(name, str), f"{cid}: parent needs a ledger id and a cell name")
    if ledger_id not in parent_ledgers:
        # The parent ledger does not exist yet (decision 2): a named dependency with declared facts.
        require(isinstance(ref.get("dependency"), str) and ref["dependency"], f"{cid}: a pending parent names its dependency")
        facts = {k: declared.get(k) for k in ("horizon", "seed", "series")}
        require(facts["horizon"] in (30, 60) and isinstance(facts["series"], str), f"{cid}: pending cells declare horizon and series")
        return "pending_parent", facts, {"ledger": ledger_id, "name": name, "dependency": ref["dependency"]}
    require(not {"horizon", "seed", "series", "status"} & set(declared),
            f"{cid}: horizon, seed, series and status come from the parent ledger, never the declaration")
    ledger = parent_ledgers[ledger_id]
    cell = ledger["cells"].get(name)
    require(cell is not None, f"{cid}: {name} is not a cell of parent ledger {ledger_id}")
    facts = {"horizon": cell["horizon"], "seed": cell["seed"], "series": cell["series"]}
    binding = {"ledger": ledger_id, "ledger_sha256": ledger["source"]["sha256"], "name": name, "family": ledger["family"]}
    status = {"final": "final", "failed": "failed", "incomplete": "pending_parent"}[cell["status"]]
    if status == "final":
        binding.update(commitment=_ref(cell["commitment"], f"{cid} parent commitment"),
                       model=_ref(cell["model"], f"{cid} parent model") if cell.get("model") else None)
    elif status == "failed":
        binding["failure_receipt"] = _ref(cell["failure_receipt"], f"{cid} parent failure receipt")
    else:
        binding["dependency"] = f"parent ledger {ledger_id} cell {name} has no terminal completion"
    return status, facts, binding


def _invariant_proof(cid, ledger_cell):
    """B-6: a history-off cell reuses its commitment only with mechanical evidence, never a declaration."""
    proof = (ledger_cell or {}).get("history_off_proof")
    require(isinstance(proof, dict), f"{cid}: no mechanical history-off proof (fit receipt) for an invariant control")
    require(proof.get("history") == "off" and HISTORY_INDEX in proof.get("zeroed_feature_indices", [])
            and set(proof.get("manifest_history_feature_indices", [None])) <= set(proof["zeroed_feature_indices"]),
            f"{cid}: the frozen model does not zero every history feature column")
    require(proof.get("candidate_expansion") is None,
            f"{cid}: the candidate set depends on history (candidate expansion), so it is not invariant")
    _ref(proof.get("fit_receipt"), f"{cid} fit receipt")
    return proof


def consumer_scope(retained_ledger, retained_ledger_sha256, declaration, parent_ledgers):
    """Every retained history consumer x seed x horizon x variant, enumerated from the retained-arm ledger and
    cross-checked cell by cell against the parent commitment ledgers; failures and pending parents kept.

    ``parent_ledgers``: {ledger_id: normalized parent ledger} (``forecast_history_families.normalize``), each
    bound to its source bytes. An arm names its parent ledgers and an optional selector; its non-pending cells
    must equal exactly the selected ledger cells (no invented and no missing cells), every (series, horizon)
    must carry exactly the parent seeds, and every series both horizons.
    """
    require(retained_ledger.get("kind") == "r1_retained_arm_ledger", "Not the R1 retained-arm ledger")
    require(declaration.get("kind") == DECLARATION_KIND, "Not a history consumer declaration")
    require(declaration.get("retained_arm_ledger_sha256") == retained_ledger_sha256,
            "Declaration is bound to another retained-arm ledger")
    for ledger_id, ledger in parent_ledgers.items():
        require(ledger.get("kind") == PARENT_LEDGER_KIND and ledger.get("ledger_id") == ledger_id,
                f"{ledger_id}: not a normalized parent commitment ledger")
        _ref(ledger.get("source"), f"{ledger_id} source")
    ledger_arms = [a["arm_id"] for a in retained_ledger.get("arms", [])]
    require(len(set(ledger_arms)) == len(ledger_arms), "Duplicate retained arm")
    declared = {}
    for arm in declaration["arms"]:
        require(arm["arm_id"] not in declared, f"{arm['arm_id']} declared twice")
        declared[arm["arm_id"]] = arm
    require(set(declared) == set(ledger_arms),
            f"Declaration must classify every retained arm: missing {sorted(set(ledger_arms) - set(declared))}, "
            f"unknown {sorted(set(declared) - set(ledger_arms))}")
    variants = sorted(VARIANTS)
    require(sorted(declaration.get("variants", [])) == variants, f"Exactly the one-factor variants {variants}")
    cells, invariant, aliases, diagnostic, ids, history_cells = [], [], [], [], set(), {}
    used_parents = set()
    alias_arms = []
    for arm_id in ledger_arms:
        arm = declared[arm_id]
        role = arm.get("role")
        require(role in ROLES, f"{arm_id}: role must be one of {ROLES}")
        if arm_id in SENSITIVITY_AXES:
            require(role == "sensitivity_axis" and not arm.get("cells"),
                    f"{arm_id} is an intervention axis; it is never crossed with another")
            continue
        require(role != "sensitivity_axis", f"{arm_id} is not an intervention axis")
        require(isinstance(arm.get("reason"), str) and arm["reason"], f"{arm_id}: classification needs a reason")
        if arm_id in DIAGNOSTIC_AXES:
            require(role == "diagnostic_axis_not_crossed",
                    f"{arm_id} is a diagnostic axis: crossing it with a sensitivity is a forbidden cross-product")
        if role == "diagnostic_axis_not_crossed":
            require(arm_id in DIAGNOSTIC_AXES and not arm.get("cells"), f"{arm_id}: a diagnostic axis has no cells")
            diagnostic.append({"arm_id": arm_id, "reason": arm["reason"]})
            continue
        if arm_id in REQUIRED_CONSUMERS:
            require(role == "history_consumer", f"{arm_id} consumes history (decision 1)")
        if arm_id in NON_CONSUMERS:
            require(role == "no_history", f"{arm_id} consumes no history (decision 1)")
        if role == "no_history":
            require(not arm.get("cells") and not arm.get("parent_ledgers"), f"{arm_id}: a no-history arm has no cells")
            continue
        require(arm.get("cells"), f"{arm_id}: a history consumer must enumerate its cells")
        if arm_id in ALIAS_ARMS:
            alias_arms.append(arm_id)
            continue
        seeds = arm.get("parent_seeds")
        require(seeds is None or (isinstance(seeds, list) and seeds and len(set(seeds)) == len(seeds)),
                f"{arm_id}: parent_seeds must be null (deterministic) or a unique list")
        selectors = arm.get("parent_ledgers") or []
        require(selectors and all(isinstance(s.get("ledger"), str) for s in selectors),
                f"{arm_id}: a history consumer names its parent commitment ledgers")
        # A selector may declare its own parent seeds when one arm joins parent ledgers with different seed sets
        # (R-transfer: neural seeds 0-4, GBDT seed 0). Absent, the arm-level parent_seeds apply unchanged.
        selector_seeds = {}
        for sel in selectors:
            own = sel.get("parent_seeds", seeds) if "parent_seeds" in sel else seeds
            require(own is None or (isinstance(own, list) and own and len(set(own)) == len(own)),
                    f"{arm_id}/{sel['ledger']}: parent_seeds must be null (deterministic) or a unique list")
            require(selector_seeds.setdefault(sel["ledger"], own) == own,
                    f"{arm_id}/{sel['ledger']}: one parent ledger cannot carry two seed sets")
        groups, group_seeds, named = {}, {}, set()
        for cell in arm["cells"]:
            cid = cell["cell_id"]
            require(cid not in ids, f"Duplicate cell {cid}")
            ids.add(cid)
            require(not {"variant", "intervention", "interventions", "alias_of"} & set(cell),
                    f"{cid}: cells declare parents only; variants are never crossed")
            require(cell.get("parent", {}).get("ledger") in {s["ledger"] for s in selectors},
                    f"{cid}: parent ledger is not one the arm names")
            status, facts, binding = _scope_cell(cid, arm_id, parent_ledgers, cell)
            key = (binding["ledger"], binding["name"])
            require(key not in used_parents, f"{cid}: parent cell {key} is consumed twice")
            used_parents.add(key)
            named.add(key)
            ledger_cell = parent_ledgers.get(binding["ledger"], {}).get("cells", {}).get(binding["name"])
            require(cell.get("uses_history") in (True, False), f"{cid}: uses_history must be true or false")
            if ledger_cell is not None:
                require((ledger_cell.get("history") == "off") == (cell["uses_history"] is False),
                        f"{cid}: uses_history contradicts the parent fit's history setting")
            if cell["uses_history"] is False:
                require(status == "final", f"{cid}: an invariant control reuses an existing commitment")
                invariant.append({"cell_id": cid, "arm_id": arm_id, **facts, "parent": binding,
                                  "reuse": "original commitment, labelled invariant; history independence proven "
                                           "mechanically from the frozen fit receipt",
                                  "history_off_proof": _invariant_proof(cid, ledger_cell)})
                continue
            groups.setdefault((facts["series"], facts["horizon"]), []).append(facts["seed"])
            own = selector_seeds[cell["parent"]["ledger"]]
            require(group_seeds.setdefault((facts["series"], facts["horizon"]), own) == own,
                    f"{arm_id}/{facts['series']}/d{facts['horizon']}: one series mixes parent ledgers with different seeds")
            history_cells[cid] = {"arm_id": arm_id, **facts}
            for variant in variants:
                cells.append({"cell_id": f"{variant}/{cid}", "parent_cell_id": cid, "arm_id": arm_id,
                              "variant": variant, "series": facts["series"], "horizon": facts["horizon"],
                              "seed": facts["seed"], "panel": cell.get("panel"),
                              "status": {"final": "planned", "failed": "failed_parent",
                                         "pending_parent": "pending_parent"}[status], "parent": binding})
        for sel in selectors:
            if sel["ledger"] not in parent_ledgers:
                continue
            match = sel.get("select") or {}
            expected = {(sel["ledger"], n) for n, c in parent_ledgers[sel["ledger"]]["cells"].items()
                        if all(c.get("attributes", {}).get(k) == v for k, v in match.items())}
            got = {k for k in named if k[0] == sel["ledger"]}
            require(got == expected, f"{arm_id}: declared cells differ from parent ledger {sel['ledger']}: missing "
                                     f"{sorted(n for _, n in expected - got)[:5]}, invented {sorted(n for _, n in got - expected)[:5]}")
        series = {s for s, _ in groups}
        for name in series:
            require({h for s, h in groups if s == name} == {30, 60}, f"{arm_id}/{name}: both horizons are required")
        for (name, horizon), got in groups.items():
            own = group_seeds[(name, horizon)]
            expected_seeds = [None] if own is None else own
            require(sorted(got, key=str) == sorted(expected_seeds, key=str),
                    f"{arm_id}/{name}/d{horizon}: seeds {got} differ from the parent seeds {expected_seeds}")
    for arm_id in alias_arms:
        arm, rule = declared[arm_id], ALIAS_ARMS[arm_id]
        require(len(arm["cells"]) == rule["cells"], f"{arm_id}: exactly {rule['cells']} alias cells")
        targets = []
        for cell in arm["cells"]:
            cid, target = cell["cell_id"], cell.get("alias_of")
            require(cid not in ids, f"Duplicate cell {cid}")
            ids.add(cid)
            require(set(cell) <= {"cell_id", "alias_of", "uses_history"} and cell.get("uses_history") is True,
                    f"{cid}: an alias cell names only its target; it creates no prediction")
            require(target in history_cells and history_cells[target]["arm_id"] == rule["target_arm"],
                    f"{cid}: alias target must be a history cell of {rule['target_arm']}")
            targets.append(target)
            aliases.append({"cell_id": cid, "arm_id": arm_id, "alias_of": target,
                            "variant_cells": {v: f"{v}/{target}" for v in variants},
                            "rule": "the same frozen fit and the same variant prediction; no duplicate prediction"})
        require(len(set(targets)) == len(targets), f"{arm_id}: alias targets must be distinct")
        facts = [history_cells[t] for t in targets]
        require({f["horizon"] for f in facts} == {30, 60} and len({f["series"] for f in facts}) == 1,
                f"{arm_id}: aliases cover one series at both horizons")
    counts = {}
    for c in cells:
        bucket = counts.setdefault(c["variant"], {}).setdefault(c["arm_id"], {})
        bucket[c["status"]] = bucket.get(c["status"], 0) + 1
    body = {"kind": SCOPE_KIND, "scope_version": 2, "retained_arm_ledger_sha256": retained_ledger_sha256,
            "declaration_sha256": canonical_sha(declaration), "variants": variants,
            "parent_ledgers": {k: {"family": v["family"], "source": v["source"],
                                    **({"seal": v["seal"]} if v.get("seal") else {})}
                               for k, v in sorted(parent_ledgers.items())},
            "rule": "one factor per variant; no delay x withhold x stable-peer combinations; diagnostic axes never "
                    "crossed; zero refits or recalibration; failed parents preserved; pending parents block the "
                    "final batch; cells, seeds and horizons come from the parent commitment ledgers",
            "cells": cells, "invariant_controls": invariant, "aliases": aliases, "diagnostic_axes_not_crossed": diagnostic,
            "counts": counts,
            "totals": {"cells": len(cells), "planned": sum(c["status"] == "planned" for c in cells),
                       "failed_parent": sum(c["status"] == "failed_parent" for c in cells),
                       "pending_parent": sum(c["status"] == "pending_parent" for c in cells),
                       "invariant_controls": len(invariant), "aliases": len(aliases)}}
    return {**body, "scope_sha256": canonical_sha(body)}


def check_scope(scope):
    body = {k: v for k, v in scope.items() if k != "scope_sha256"}
    require(scope.get("kind") == SCOPE_KIND and canonical_sha(body) == scope.get("scope_sha256"),
            "Scope hash does not match its content")
    return scope


# ---- pre-R1 commitment receipt (A5, decision 4) -------------------------------------------------------------------

def _ref(value, what):
    require(isinstance(value, dict) and isinstance(value.get("path"), str), f"{what} needs a path")
    _hex64(value.get("sha256"), f"{what} sha256")
    return {"path": value["path"], "sha256": value["sha256"]}


def frozen_model_ledger(scope, entries, *, variant="withhold"):
    """The exact model/input/seed ledger of one variant: every scoped cell, committed or bound failure.

    ``entries``: {cell_id: {"model", "variant_manifest", "variant_gate"} (refs)} for planned cells.
    """
    check_scope(scope)
    mine = [c for c in scope["cells"] if c["variant"] == variant]
    pending = [c["cell_id"] for c in mine if c["status"] == "pending_parent"]
    require(not pending, f"Missing parent cells are dependencies, never omitted: {pending[:5]}")
    planned = {c["cell_id"] for c in mine if c["status"] == "planned"}
    require(set(entries) == planned, "Ledger must cover exactly the planned cells of the variant")
    rows = []
    for c in sorted(mine, key=lambda c: c["cell_id"]):
        row = {"cell_id": c["cell_id"], "arm_id": c["arm_id"], "series": c["series"], "horizon": c["horizon"],
               "seed": c["seed"], "panel": c["panel"], "status": c["status"], "parent": c["parent"]}
        if c["status"] == "planned":
            e = entries[c["cell_id"]]
            row.update(model=_ref(e["model"], "model") if e.get("model") else None,
                       variant_manifest=_ref(e["variant_manifest"], "variant manifest"),
                       variant_gate=_ref(e["variant_gate"], "variant gate"))
            if c["parent"]["family"] != "baseline":
                require(row["model"] is not None and row["model"] == c["parent"].get("model"),
                        f"{c['cell_id']}: frozen model differs from the parent")
            else:
                require(row["model"] is None and c["parent"].get("model") is None,
                        "A baseline has no learned model")
        else:
            row["failure_receipt"] = _ref(c["parent"]["failure_receipt"], "failure receipt")
        rows.append(row)
    body = {"kind": LEDGER_KIND, "variant": variant, "intervention_kind": VARIANTS[variant][0],
            "scope_sha256": scope["scope_sha256"], "retraining_fits": 0, "calibration_changes": 0, "entries": rows,
            "invariant_controls": [c["cell_id"] for c in scope["invariant_controls"]],
            "aliases": {a["cell_id"]: a["variant_cells"][variant] for a in scope["aliases"]}}
    return {**body, "ledger_sha256": canonical_sha(body)}


def commitment_index(ledger, results):
    """Typed prediction-commitment index; paths and hashes only, ``scores_computed: false``.

    ``results``: {cell_id: {"status": "committed", "predictions", "commitment"} | {"status": "failed",
    "failure_receipt"}}. A planned cell that failed at prediction time is kept as a bound failure.
    """
    require(ledger.get("kind") == LEDGER_KIND and canonical_sha(
        {k: v for k, v in ledger.items() if k != "ledger_sha256"}) == ledger.get("ledger_sha256"), "Ledger hash mismatch")
    require(set(results) == {e["cell_id"] for e in ledger["entries"]}, "Index must cover every ledger cell")
    entries = []
    for e in ledger["entries"]:
        r = results[e["cell_id"]]
        require(not {"score", "scores", "metric", "metrics", "jaccard", "ap"} & set(r), "The index carries no scores")
        if r.get("status") == "committed":
            require(e["status"] == "planned", f"{e['cell_id']}: a failed parent cannot have a commitment")
            entries.append({"cell_id": e["cell_id"], "status": "committed",
                            "predictions": _ref(r["predictions"], "predictions"),
                            "commitment": _ref(r["commitment"], "commitment")})
        else:
            require(r.get("status") == "failed", f"{e['cell_id']}: status must be committed or failed")
            if e["status"] == "failed_parent":
                require(r["failure_receipt"] == e["failure_receipt"], "Failed-parent receipt differs")
            entries.append({"cell_id": e["cell_id"], "status": "failed",
                            "failure_receipt": _ref(r["failure_receipt"], "failure receipt")})
    return {"kind": INDEX_KIND, "index_version": 1, "scores_computed": False, "variant": ledger["variant"],
            "frozen_model_ledger_sha256": ledger["ledger_sha256"], "scope_sha256": ledger["scope_sha256"],
            "entries": entries}


def frozen_model_receipt(spec, spec_sha256, reports, ledger, index, *, library_digest, cohort_event_ids):
    """The gate's frozen-model receipt, with ``results_sha256`` = hash of the typed commitment index."""
    from .forecast_sensitivity_gate import FROZEN_MODEL_KIND, cohort_ids_sha256
    require(ledger["variant"] == "withhold" == index["variant"], "Only R-withhold has a reporting receipt")
    require(index["frozen_model_ledger_sha256"] == ledger["ledger_sha256"], "Index names another ledger")
    require(set(map(int, reports)) == {30, 60}, "Both horizon reports are required")
    return {"kind": FROZEN_MODEL_KIND, "policy_sha256": spec["policy_sha256"], "spec_sha256": spec_sha256,
            "withheld_ids": sorted(spec["withheld_event_ids"]), "retraining_fits": 0,
            "input_impact_report_sha256": {str(h): r["report_sha256"] for h, r in sorted(reports.items())},
            "library_digest": library_digest, "cohort_ids_sha256": cohort_ids_sha256(cohort_event_ids),
            "frozen_model_ledger_sha256": ledger["ledger_sha256"], "results_sha256": canonical_sha(index),
            "results_kind": RECEIPT_RESULTS_KIND, "scores_computed": False,
            "results_meaning": "hash of the canonical typed prediction-commitment index (paths and hashes only); "
                               "the later paired metric report is a separate artifact with its own digest"}


def delay_receipt(variant, ledger, index, *, primary_library_digest, variant_library_digest, cohort_event_ids,
                  variant_gate_sha256):
    """Typed pre-R1 receipt of one delay variant (R-delay900 / R-delay1800); the same commitment meaning as the
    withholding receipt (decision 4), bound to the delayed library instead of a withholding policy.

    Schema ``history_delay_frozen_model_sensitivity`` v1: variant, availability_delay_s, primary and variant library
    digests, the variant input gate, cohort IDs hash, frozen-model ledger hash, ``results_sha256`` = canonical
    hash of the typed commitment index, ``results_kind``, ``scores_computed: false``, ``retraining_fits: 0``.
    No reporting guard consumes it yet: R1 must call ``verify_receipt_bundle`` (shared change, not made here).
    """
    from .forecast_sensitivity_gate import cohort_ids_sha256
    require(VARIANTS.get(variant, ("",))[0] == DELAY_KIND, "A delay receipt needs a delay variant")
    require(ledger["variant"] == variant == index["variant"], "Ledger, index and receipt name different variants")
    require(index["frozen_model_ledger_sha256"] == ledger["ledger_sha256"], "Index names another ledger")
    require(primary_library_digest != variant_library_digest, "A delay variant has its own library digest")
    return {"kind": DELAY_RECEIPT_KIND, "receipt_version": 1, "variant": variant,
            "availability_delay_s": VARIANTS[variant][1], "retraining_fits": 0, "calibration_changes": 0,
            "primary_library_digest": _hex64(primary_library_digest, "primary library digest"),
            "variant_library_digest": _hex64(variant_library_digest, "variant library digest"),
            "variant_input_gate_sha256": _hex64(variant_gate_sha256, "variant gate"),
            "cohort_ids_sha256": cohort_ids_sha256(cohort_event_ids),
            "frozen_model_ledger_sha256": ledger["ledger_sha256"], "results_sha256": canonical_sha(index),
            "results_kind": RECEIPT_RESULTS_KIND, "scores_computed": False,
            "results_meaning": "hash of the canonical typed prediction-commitment index (paths and hashes only); "
                               "the later paired metric report is a separate artifact with its own digest"}


def verify_receipt_commitments(receipt, ledger, index):
    """What the gate cannot check: the receipt's results/ledger hashes ARE the typed commitment index and ledger."""
    require(receipt.get("results_kind") == RECEIPT_RESULTS_KIND and receipt.get("scores_computed") is False,
            "Receipt results are not a pre-R1 commitment index")
    require(index.get("kind") == INDEX_KIND and index.get("scores_computed") is False and index.get("index_version") == 1,
            "Not a typed commitment index")
    require(canonical_sha(index) == receipt.get("results_sha256"), "results_sha256 is not this commitment index")
    body = {k: v for k, v in ledger.items() if k != "ledger_sha256"}
    require(ledger.get("kind") == LEDGER_KIND and canonical_sha(body) == ledger.get("ledger_sha256")
            == receipt.get("frozen_model_ledger_sha256") == index.get("frozen_model_ledger_sha256"),
            "frozen_model_ledger_sha256 is not this ledger")
    require(ledger.get("retraining_fits") == 0 and ledger.get("calibration_changes") == 0, "Ledger claims refits")
    require([e["cell_id"] for e in index["entries"]] == [e["cell_id"] for e in ledger["entries"]],
            "Index and ledger cover different cells")
    return {"committed": sum(e["status"] == "committed" for e in index["entries"]),
            "failed": sum(e["status"] == "failed" for e in index["entries"])}


def verify_receipt_bundle(receipt, ledger, index, scope, *, variant):
    """The cross-binding API the R1 path should call for every history variant (withhold AND delay).

    Checks, beyond ``verify_receipt_commitments``: the receipt kind matches the variant (the withholding gate
    kind for R-withhold, ``DELAY_RECEIPT_KIND`` for a delay), the ledger is the frozen-model ledger of exactly this
    scope and variant, every planned scope cell is committed or a bound prediction failure, every failed parent is
    kept with its receipt, and no pending parent remains. Returns the exact counts.
    """
    from .forecast_sensitivity_gate import FROZEN_MODEL_KIND
    check_scope(scope)
    require(variant in VARIANTS, f"Unknown history variant {variant!r}")
    expected_kind = FROZEN_MODEL_KIND if VARIANTS[variant][0] == WITHHOLD_KIND else DELAY_RECEIPT_KIND
    require(receipt.get("kind") == expected_kind, f"Receipt kind is not the {variant} schema")
    if expected_kind == DELAY_RECEIPT_KIND:
        require(receipt.get("variant") == variant and receipt.get("receipt_version") == 1
                and receipt.get("availability_delay_s") == VARIANTS[variant][1], "Delay receipt names another variant")
    require(ledger.get("variant") == variant and ledger.get("scope_sha256") == scope["scope_sha256"],
            "Ledger belongs to another variant or scope")
    counts = verify_receipt_commitments(receipt, ledger, index)
    reconstructed = frozen_model_ledger(scope, {
        e["cell_id"]: {k: e[k] for k in ("model", "variant_manifest", "variant_gate")}
        for e in ledger["entries"] if e["status"] == "planned"}, variant=variant)
    require(ledger == reconstructed, "Ledger facts differ from the bound consumer scope")
    require(index == commitment_index(ledger, {e["cell_id"]: e for e in index["entries"]}),
            "Index differs from the typed commitment schema")
    mine = sorted(c["cell_id"] for c in scope["cells"] if c["variant"] == variant)
    require([e["cell_id"] for e in ledger["entries"]] == mine, "Ledger does not cover exactly the scoped cells")
    require(not any(c["status"] == "pending_parent" for c in scope["cells"] if c["variant"] == variant),
            "A pending parent remains")
    return {**counts, "failed_parent": sum(e["status"] == "failed_parent" for e in ledger["entries"]),
            "invariant_controls": len(scope["invariant_controls"]), "aliases": len(scope["aliases"])}


# ---- impact queries (A4) ------------------------------------------------------------------------------------------

def impact_queries(rows, events, library, delta_s):
    """``QueryInput``s from manifest rows and prediction-mode inputs (``event_id``, ``asn``) only.

    Single-root primary tensors only: the signature is the library's record, the issue time the manifest's.
    """
    from datetime import timedelta
    from .forecast_history import utc
    from .forecast_history_sensitivity_report import QueryInput
    by_row = {r["event_id"]: r for r in rows}
    queries = []
    for event in events:
        require(not {"y", "target_asns", "curve", "first_s", "n_pos"} & set(event), "Impact queries take inputs only")
        eid = event["event_id"]
        row = by_row[eid]
        issue = utc(row["issue_time"]) if row.get("issue_time") else utc(row["onset"]) + timedelta(seconds=delta_s)
        require(library.by_id[eid].onset + timedelta(seconds=delta_s) == issue,
                f"{eid}: manifest issue time differs from the library onset + horizon")
        queries.append(QueryInput(eid, issue, library.by_id[eid].signature(delta_s),
                                  frozenset(int(a) for a in _np(event["asn"]).tolist())))
    return queries


def h1_topk_impact(library, queries, identity, ks):
    """Separate H1 sidecar: whether the top-K history selection changes under withholding (inputs only)."""
    from .forecast_candidates import expand_from_history
    from .forecast_history_sensitivity import withhold_snapshot
    rows = []
    for q in queries:
        primary = library.snapshot(q.issue_time, exclude_event_id=q.event_id)
        changed = withhold_snapshot(primary, identity["withheld_event_ids"], policy_sha256=identity["policy_sha256"])
        row = {"query_event_id": q.event_id}
        for k in ks:
            _, before = expand_from_history(sorted(q.candidate_asns), primary, k)
            _, after = expand_from_history(sorted(q.candidate_asns), changed, k)
            row[str(k)] = {"selected_changed": before["selected_history_asns"] != after["selected_history_asns"],
                           "added_changed": before["added_asns"] != after["added_asns"]}
        rows.append(row)
    body = {"kind": "history_withholding_h1_topk_impact", "scope": "input_only_no_forecast_scoring",
            "intervention": identity, "library_digest": library.digest, "k_values": sorted(ks),
            "aggregate": {str(k): {"queries": len(rows),
                                   "selected_changed": sum(r[str(k)]["selected_changed"] for r in rows),
                                   "added_changed": sum(r[str(k)]["added_changed"] for r in rows)} for k in ks},
            "rows": rows}
    return {**body, "report_sha256": canonical_sha(body)}
