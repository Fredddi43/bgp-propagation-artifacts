"""Evaluation path for the ranking-v1 contrasts (PRIMARY-METRIC-REVISION.md, review C3 items B1, B2, B5).

Two populations, two entry points, one shared contrast core:

* ``evaluate_new_period`` is the **only** route that can declare a primary finding. It runs on the
  protected new-period cohort under the one-batch unblinding contract of NEW-PERIOD-PROTOCOL.md:
  the custody seal (``forecast_custody.seal``) must re-verify every retained prediction
  (per arm, seed, horizon and panel) before the custodian's label table is opened, and the label
  table is hash-anchored. It reports the twelve primary AP contrasts (one Holm family), the P@10,
  full-target Jaccard and slice-Jaccard secondary families, the native-candidate whole-system
  C2/C5 pair (its own secondary family) and the median-vs-mean history Jaccard (descriptive).
* ``evaluate_retrospective`` serves the 2025 retrospective (R1) ledger. R1 is temporal-split
  evidence, not a confirmatory holdout (RETROSPECTIVE-RELEASE-SCOPE.md), so nothing it reports
  declares a primary finding; C5/C6 need frozen-2025 arms on new-period inputs and are refused.

Arms are never chosen by the operator. ``derive_*_arms`` map runs to evaluation arms from their
committed metadata (custody ``role`` records, or evaluation-ledger run fields), order seeds by
training seed and require one seed set across learned arms. The hash-bound arm spec must equal
that derivation exactly (``check_arm_spec``).

``verify_r1_authorization`` is the code check of the R1 release preconditions that the
retrospective scoring runs and evaluator require (B5).
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np

# The twelve primary contrasts (PLAN.md §5, NEW-PERIOD-PROTOCOL.md), each at 30 s and 60 s.
PRIMARY_CONTRASTS = {"C1": ("sage_on", "none_on"), "C2": ("sage_on", "online_history"),
                     "C3": ("sage_on", "sage_off"), "C4": ("none_on", "none_off"),
                     "C5": ("frozen_sage_on", "online_history"), "C6": ("frozen_sage_on", "sage_on")}
# Native-candidate history: the labelled whole-system secondary C2/C5 pair (PRIMARY-METRIC-REVISION.md §3).
WHOLE_SYSTEM_CONTRASTS = {"C2-native": ("sage_on", "online_history_native"),
                          "C5-native": ("frozen_sage_on", "online_history_native")}
# Contrasts that exist on the retrospective cohort: no frozen-2025 vs updated split there.
RETROSPECTIVE_CONTRASTS = {k: PRIMARY_CONTRASTS[k] for k in ("C1", "C2", "C3", "C4")}
CONTRAST_FAMILIES = ("primary_ap", "p_at_10", "full_target_jaccard", "slice_jaccard")
HORIZONS = (30, 60)
LEARNED_ARMS = ("sage_on", "none_on", "sage_off", "none_off", "frozen_sage_on")
NEW_PERIOD_ARMS = LEARNED_ARMS + ("online_history", "online_history_native", "history_median")
RETROSPECTIVE_NOTE = ("2025 retrospective (R1): temporal-split evidence, not a confirmatory holdout "
                      "(RETROSPECTIVE-RELEASE-SCOPE.md). Ranking AP/P@10 are reported alongside the 14 "
                      "retrospective contrasts' existing rules; no result here is a primary finding.")
PERSISTENCE_NOTE = "persistence has no ranking (AP = 0); it is the comparator only for Jaccard secondaries"
# Prediction-input status (forecast_manifest.STATUSES, plus inference failures) -> ranking abstention status.
INPUT_ABSTENTIONS = {"unavailable_no_input": "no_input", "source_failure": "technical_failure",
                     "parser_failure": "technical_failure", "inference_failure": "technical_failure",
                     "technical_failure": "technical_failure"}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def hashed_bytes(path):
    """One read of ``path`` and the SHA-256 of exactly those bytes."""
    raw = Path(path).read_bytes()
    return raw, hashlib.sha256(raw).hexdigest()


def bound_json(path, expected_sha256, what):
    """Parse the bytes whose hash was checked (one read; no window between hash and parse)."""
    raw, digest = hashed_bytes(path)
    if not isinstance(expected_sha256, str) or digest != expected_sha256:
        raise ValueError(f"{what} differs from its external hash anchor")
    return json.loads(raw)


# --------------------------------------------------------------------------- shared contrast core

def abstention_counts(per_event):
    """Abstentions of one arm and training seed, by reason (scorer ``ranking_status``), and how many were eligible."""
    from .forecast_ranking import ABSTENTION_STATUSES as RANKING_ABSTENTIONS
    counts = {status: sum(r.get("ranking_status") == status for r in per_event) for status in RANKING_ABSTENTIONS}
    counts["eligible_abstentions"] = sum(bool(r["eligible"]) for r in per_event
                                         if r.get("ranking_status") in RANKING_ABSTENTIONS)
    return counts


def _contrast_families(arms, rows, slice_rules, *, contrasts, declares_primary, repetitions, seed, alpha,
                       whole_system=None, median=False):
    """Compute the contrast families; the caller decides whether ``primary_ap`` is primary.

    Private: only ``evaluate_new_period`` (after the custody seal) passes ``declares_primary=True``.
    ``arms[name][delta]`` is a list over training seeds (one row list for a deterministic arm), each
    aligned with ``rows[delta]``. ``slice_rules`` maps ``str(delta)`` to the frozen issue-time rule,
    or is ``None`` when the slice family cannot be formed (then it is reported as unavailable).
    """
    from .forecast_analysis import incident_day_blocks
    from .forecast_history import in_issue_time_slice
    from .forecast_ranking import holm, paired_bootstrap, ranking_contrast, stratify_by_new_members
    needed = {a for pair in contrasts.values() for a in pair}
    needed |= {a for pair in (whole_system or {}).values() for a in pair}
    if median:
        needed |= {"history_median", "online_history"}
    if set(arms) < needed or any(set(arms[a]) != set(HORIZONS) for a in needed):
        raise ValueError("The one-batch evaluator needs every primary arm at 30 s and 60 s")
    for name, by_delta in arms.items():
        for delta, seeds in by_delta.items():
            for per_event in seeds:
                if [r["event_id"] for r in per_event] != [r["event_id"] for r in rows[delta]]:
                    raise ValueError(f"{name} at {delta} s is not aligned with the evaluation cohort")

    def matrix(seeds, key, mask=None):
        values = np.array([[r[key] for r in per_event] for per_event in seeds], dtype=float)
        return values if mask is None else values[:, mask]

    def slice_mask(delta):
        rule = slice_rules[str(delta)]
        masks = set()
        for name in needed:
            for per_event in arms[name][delta]:
                mask = tuple(in_issue_time_slice(rule, r["issue_time_variables"]) for r in per_event)
                if any("in_issue_time_slice" in r and r["in_issue_time_slice"] != m for r, m in zip(per_event, mask)):
                    raise ValueError("A committed slice flag differs from the frozen slice rule")
                masks.add(mask)
        if len(masks) != 1:
            raise ValueError("Arms disagree on issue-time slice membership")
        return np.array(next(iter(masks)), dtype=bool)

    def slice_decisions(seeds, mask):
        def value(r):
            if "two_threshold_jaccard" in r:
                return r["two_threshold_jaccard"]
            if r.get("decision_rule") == "committed_baseline_decision":
                return r["jaccard"]
            raise ValueError("Learned rows need validation-calibrated slice/remainder decisions")
        return np.array([[value(r) for r in per_event] for per_event in seeds], dtype=float)[:, mask]

    families = {name: {} for name in CONTRAST_FAMILIES}
    whole = {}
    median_report = {}
    eligibility = {}
    for delta in HORIZONS:
        blocks = incident_day_blocks(rows[delta])
        inside = slice_mask(delta) if slice_rules is not None else None
        slice_blocks = None if inside is None else [b for b, keep in zip(blocks, inside) if keep]
        for cid, (left, right) in contrasts.items():
            key = f"{cid}@{delta}"
            a, b = arms[left][delta], arms[right][delta]
            families["primary_ap"][key] = ranking_contrast(a, b, rows[delta], metric="average_precision",
                                                           repetitions=repetitions, seed=seed)
            families["p_at_10"][key] = ranking_contrast(a, b, rows[delta], metric="precision_at", budget=10,
                                                        repetitions=repetitions, seed=seed)
            families["full_target_jaccard"][key] = paired_bootstrap(matrix(a, "jaccard"), matrix(b, "jaccard"), blocks,
                                                                    repetitions=repetitions, seed=seed)
            if inside is not None:
                families["slice_jaccard"][key] = paired_bootstrap(slice_decisions(a, inside),
                                                                  slice_decisions(b, inside), slice_blocks,
                                                                  repetitions=repetitions, seed=seed)
            for family in CONTRAST_FAMILIES:
                if key in families[family]:
                    families[family][key].update(contrast=cid, left=left, right=right, horizon_seconds=delta)
        for cid, (left, right) in (whole_system or {}).items():
            key = f"{cid}@{delta}"
            whole[key] = ranking_contrast(arms[left][delta], arms[right][delta], rows[delta],
                                          metric="average_precision", repetitions=repetitions, seed=seed)
            whole[key].update(contrast=cid, left=left, right=right, horizon_seconds=delta)
        if median:
            mean_j, median_j = matrix(arms["online_history"][delta], "jaccard"), matrix(arms["history_median"][delta], "jaccard")
            median_report[str(delta)] = {
                "mean_extent_jaccard": float(mean_j.mean()), "median_extent_jaccard": float(median_j.mean()),
                "median_minus_mean": paired_bootstrap(median_j, mean_j, blocks, repetitions=repetitions, seed=seed),
                "c2_c5_jaccard_against_median_history": {
                    f"{cid}@{delta}": paired_bootstrap(matrix(arms[contrasts[cid][0]][delta], "jaccard"), median_j,
                                                       blocks, repetitions=repetitions, seed=seed)
                    for cid in ("C2", "C5") if cid in contrasts}}
        reference = contrasts[next(iter(contrasts))][0]
        eligible = [bool(r["eligible"]) for r in arms[reference][delta][0]]
        eligibility[str(delta)] = {
            "events": len(eligible), "eligible_events": sum(eligible),
            "events_without_new_members": len(eligible) - sum(eligible),
            "slice_events": None if inside is None else int(inside.sum()),
            "remainder_events": None if inside is None else int((~inside).sum()),
            # Abstentions by reason, per arm and training seed; they stay in the denominator (AP 0).
            "abstentions": {name: [abstention_counts(per_event) for per_event in by_delta[delta]]
                            for name, by_delta in arms.items()}}
    report = {}
    for family, results in families.items():
        if not results:
            report[family] = {"status": "unavailable", "reason": "no frozen slice rule / slice decisions supplied",
                              "declares_primary_finding": False}
            continue
        adjusted = holm({k: v["p_value"] for k, v in results.items()})
        for k, v in results.items():
            v.update(holm_p_value=adjusted[k], holm_rejects=adjusted[k] <= alpha)
        report[family] = {"contrasts": results, "holm_family_size": len(results), "family_wise_alpha": alpha,
                          "declares_primary_finding": bool(declares_primary and family == "primary_ap")}
    if whole:
        adjusted = holm({k: v["p_value"] for k, v in whole.items()})
        for k, v in whole.items():
            v.update(holm_p_value=adjusted[k], holm_rejects=adjusted[k] <= alpha)
        report["whole_system_ap"] = {
            "contrasts": whole, "holm_family_size": len(whole), "family_wise_alpha": alpha,
            "declares_primary_finding": False,
            "role": "labelled whole-system secondary: native-candidate history (never a primary finding)"}
    stratification = {name: {str(delta): [stratify_by_new_members(per_event) for per_event in seeds]
                             for delta, seeds in by_delta.items()} for name, by_delta in arms.items()}
    result = {"families": report, "eligibility": eligibility, "stratification_by_new_members": stratification,
              "repetitions": repetitions, "rng_seed": seed, "metric_version": "ranking-v1",
              "persistence_note": PERSISTENCE_NOTE}
    if median:
        result["history_median_vs_mean_jaccard"] = {"descriptive_only": True, "horizons": median_report}
    return result


def evaluate_retrospective(arms, rows, slice_rules, *, repetitions=10000, seed=1701, alpha=0.05):
    """R1 report: C1-C4 on AP/P@10/Jaccard, never a primary finding (B1)."""
    if "frozen_sage_on" in arms:
        raise ValueError("frozen-2025 vs updated (C5/C6) exists only on the new-period cohort")
    report = _contrast_families(arms, rows, slice_rules, contrasts=RETROSPECTIVE_CONTRASTS, declares_primary=False,
                                repetitions=repetitions, seed=seed, alpha=alpha,
                                whole_system={"C2-native": WHOLE_SYSTEM_CONTRASTS["C2-native"]}
                                if "online_history_native" in arms else None,
                                median="history_median" in arms)
    report.update(population="retrospective_r1", confirmatory=False, evidence_status=RETROSPECTIVE_NOTE,
                  contrasts_not_applicable={"C5": "needs frozen-2025 arms on new-period inputs",
                                            "C6": "needs frozen-2025 arms on new-period inputs"})
    return report


# --------------------------------------------------------------------------- arm identity (B2)

def check_seed_pairing(seeds_by_arm):
    """``{arm: {delta: [seed, ...]}}`` for learned arms: distinct, identical, sorted seed sets."""
    for delta in HORIZONS:
        sets = {arm: by_delta[delta] for arm, by_delta in seeds_by_arm.items() if delta in by_delta}
        for arm, seeds in sets.items():
            if len(set(seeds)) != len(seeds) or seeds != sorted(seeds):
                raise ValueError(f"{arm} at {delta} s: training seeds must be distinct and ordered")
        if len({tuple(s) for s in sets.values()}) > 1:
            raise ValueError(f"Learned arms at {delta} s do not share one training-seed set: {sets}")
        if sets and len(next(iter(sets.values()))) < 2:
            raise ValueError("Paired seed intervals need at least two training seeds per learned arm")


def _assemble(entries):
    """``entries``: (arm, delta, seed, identifier). Returns ``{arm: {str(delta): [ids by seed]}}``."""
    arms, seeds = {}, {}
    for arm, delta, seed, identifier in entries:
        arms.setdefault(arm, {}).setdefault(int(delta), []).append((int(seed), identifier))
    out = {}
    for arm, by_delta in arms.items():
        out[arm] = {}
        for delta, items in by_delta.items():
            items.sort()
            if arm in LEARNED_ARMS:
                seeds.setdefault(arm, {})[delta] = [s for s, _ in items]
            elif len(items) != 1:
                raise ValueError(f"Deterministic arm {arm} at {delta} s must be exactly one run, got {len(items)}")
            out[arm][str(delta)] = [i for _, i in items]
    check_seed_pairing(seeds)
    return out


def role_arm(role):
    """Evaluation arm of one committed role record, or None if it plays no part in these families."""
    family = role.get("family")
    if family == "neural":
        if role.get("variant") != "core" or role.get("panel") != "reference":
            return None
        if role.get("message_passing") not in ("sage", "none") or role.get("history") not in ("on", "off"):
            raise ValueError(f"Undeclared neural role {role}")
        if role.get("training") == "updated":
            return f"{role['message_passing']}_{role['history']}"
        if role.get("training") == "frozen_2025":
            return "frozen_sage_on" if (role["message_passing"], role["history"]) == ("sage", "on") else None
        raise ValueError(f"Undeclared training period in role {role}")
    if family == "baseline":
        if role.get("panel") != "reference" or role.get("library") != "online":
            return None
        key = (role.get("baseline"), role.get("candidates"))
        return {("history-knn-mean", "matched"): "online_history",
                ("history-knn-mean", "native"): "online_history_native",
                ("history-knn-median", "matched"): "history_median"}.get(key)
    return None


def derive_new_period_arms(custody_spec):
    """Evaluation arms from the frozen custody retention list (every arm's ``role`` is freeze-bound)."""
    entries, seen = [], {}
    for arm in custody_spec["arms"]:
        role = arm.get("role")
        if not isinstance(role, dict):
            continue
        name = role_arm(role)
        if name is None:
            continue
        horizon = role.get("horizon_seconds")
        if horizon not in HORIZONS:
            raise ValueError(f"{arm['arm_id']}: undeclared horizon")
        if name in LEARNED_ARMS and type(role.get("seed")) is not int:
            raise ValueError(f"{arm['arm_id']}: a learned role must name its training seed")
        seed = role["seed"] if name in LEARNED_ARMS else 0
        key = (name, horizon, seed)
        if key in seen:
            raise ValueError(f"Two retained arms claim {key}: {seen[key]} and {arm['arm_id']}")
        seen[key] = arm["arm_id"]
        entries.append((name, horizon, seed, arm["arm_id"]))
    derived = _assemble(entries)
    missing = [a for a in NEW_PERIOD_ARMS if set(derived.get(a, {})) != {"30", "60"}]
    if missing:
        raise ValueError(f"Frozen retention list lacks evaluation arms at both horizons: {missing}")
    return derived


def derive_retrospective_arms(runs, committed_rows=None):
    """Evaluation arms from evaluation-ledger run metadata (retrospective R1)."""
    committed_rows = committed_rows or (lambda run: json.loads(
        (Path(run["prediction_dir"]) / "predictions.json").read_text()))
    entries, configurations = [], set()
    for run in runs:
        family = run.get("model_family")
        if family == "neural":
            if run.get("message_passing") not in ("sage", "none") or run.get("history") not in ("on", "off"):
                raise ValueError(f"Learned run {run['run_id']} lacks declared message passing/history")
            if run.get("configuration_id") is None:
                raise ValueError(f"Learned run {run['run_id']} lacks its configuration ID")
            configurations.add(run["configuration_id"])
            entries.append((f"{run['message_passing']}_{run['history']}", run["horizon_seconds"], run["seed"],
                            run["run_id"]))
        elif family == "gbdt":
            continue  # matched GBDT is its own baseline family, never one of the learned contrast arms
        elif family == "baseline":
            name = {("history-knn-mean", "matched"): "online_history",
                    ("history-knn-mean", "native"): "online_history_native",
                    ("history-knn-median", "matched"): "history_median"}.get((run.get("baseline"),
                                                                              run.get("candidate_protocol")))
            if name is None:
                continue
            rows = committed_rows(run)
            if any(r.get("frozen_at") is not None for r in rows):
                continue  # frozen-library history is a separate secondary, never the online comparator
            entries.append((name, run["horizon_seconds"], 0, run["run_id"]))
        else:
            raise ValueError(f"Run {run['run_id']} has undeclared model family {family!r}")
    if len(configurations) > 1:
        raise ValueError(f"Learned arms mix configurations {sorted(configurations)}; evaluate the selected one only")
    derived = _assemble(entries)
    needed = {a for pair in RETROSPECTIVE_CONTRASTS.values() for a in pair}
    missing = [a for a in sorted(needed) if set(derived.get(a, {})) != {"30", "60"}]
    if missing:
        raise ValueError(f"Evaluation ledger lacks retrospective arms at both horizons: {missing}")
    return derived


def check_arm_spec(spec, derived, population):
    """The hash-bound arm spec must restate the mechanical derivation exactly."""
    if spec.get("kind") != "frozen_evaluation_arm_spec" or spec.get("population") != population:
        raise ValueError(f"Arm spec is not a frozen {population} evaluation arm spec")
    if spec.get("seed_pairing") != "training_seed" or spec.get("online_history") != "history-knn-mean/matched/online":
        raise ValueError("Arm spec must declare training-seed pairing and the matched mean online history")
    if spec.get("arms") != derived:
        raise ValueError("Arm spec differs from the arms derived from committed run metadata")
    return spec


# --------------------------------------------------------------------------- R1 authorization (B5)

R1_WINDOW = {"start": "2025-09-01T00:00:00+00:00", "end": "2026-01-01T00:00:00+00:00"}
R1_PRECONDITIONS = ("sources", "fits", "prediction_commitments", "history_withholding_gate",
                    "new_period_recipes_frozen", "exposure_ledger")


def verify_r1_authorization(path, expected_sha256, *, evaluation_ledger_sha256):
    """Refuse retrospective test scoring unless the R1 release preconditions are recorded and bound.

    The receipt names the evaluation ledger it authorizes, the six preconditions of
    RETROSPECTIVE-RELEASE-SCOPE.md each with hash-verified evidence, the retained-arm ledger and
    an independent review. No helper here creates such a receipt.
    """
    receipt = bound_json(path, expected_sha256, "R1 release authorization")
    if (receipt.get("kind") != "r1_release_authorization" or receipt.get("passed") is not True
            or receipt.get("development_frozen") is not True or receipt.get("released_window") != R1_WINDOW):
        raise ValueError("R1 release authorization is not a passed, development-frozen R1 window receipt")
    if receipt.get("evaluation_ledger_sha256") != evaluation_ledger_sha256:
        raise ValueError("R1 release authorization names a different evaluation ledger")
    preconditions = receipt.get("preconditions") or {}
    if set(preconditions) != set(R1_PRECONDITIONS):
        raise ValueError(f"R1 authorization must record exactly the preconditions {R1_PRECONDITIONS}")
    evidence = [(name, item) for name, item in preconditions.items()]
    evidence += [("retained_arm_ledger", receipt.get("retained_arm_ledger")),
                 ("independent_review", receipt.get("independent_review"))]
    for name, item in evidence:
        if not isinstance(item, dict) or (name in preconditions and item.get("satisfied") is not True):
            raise ValueError(f"R1 precondition not satisfied: {name}")
        if not item.get("path") or sha(item["path"]) != item.get("sha256"):
            raise ValueError(f"R1 evidence missing or changed: {name}")
    from .forecast_protocol import utc
    if utc(receipt["authorized_utc"]) > datetime.now(timezone.utc):
        raise ValueError("R1 authorization time is in the future")
    return expected_sha256


# --------------------------------------------------------------------------- new-period custodian path (B1)

def _jaccard(truth, predicted):
    union = truth | predicted
    if not union:
        raise ValueError("Empty target and prediction: Jaccard undefined on a scorable event")
    return len(truth & predicted) / len(union)


def check_committed_inputs(row, inputs, candidates):
    """A committed row's seeds (and, for matched candidates, its candidate list in order) equal the
    custodian-exported issue-time input (M4); native history candidates must contain every seed."""
    eid = row["event_id"]
    if inputs is None:
        raise ValueError(f"{eid}: no custodian input to check the committed row against")
    seeds = sorted(set(map(int, inputs["seed_asns"])))
    if sorted(set(map(int, row.get("seed_asns", [])))) != seeds:
        raise ValueError(f"{eid}: committed seeds differ from the custodian input")
    committed = [int(a) for a in row["candidate_asns"]]
    if candidates == "matched":
        if committed != [int(a) for a in inputs["asn"]]:
            raise ValueError(f"{eid}: committed candidates differ from the custodian input graph (matched protocol)")
    elif candidates == "native":
        if not set(seeds) <= set(committed) or len(set(committed)) != len(committed):
            raise ValueError(f"{eid}: native candidates must be distinct and include every input seed")
    else:
        raise ValueError(f"{eid}: undeclared candidate protocol {candidates!r}")


def check_rows_label_free(predictions, manifest_rows, *, baseline, inputs, candidates="matched",
                          issue_time=None, slice_rule=None):
    """Every check of ``per_event_rows`` that needs no label, over all reference events (E1).

    Run before the one-time marker so that a failure here never consumes the single label opening:
    coverage of the reference population, committed seeds/candidates against the custodian input,
    a well-formed ranking (scored against an empty target), empty abstentions, committed
    slice/remainder decisions where the slice family needs them, and slice membership.
    Returns ``{event_id: committed row}``.
    """
    from .forecast_history import in_issue_time_slice
    from .forecast_ranking import event_ranking_metrics
    by_id = {r["event_id"]: r for r in predictions}
    if len(by_id) != len(predictions) or set(by_id) != {m["event_id"] for m in manifest_rows}:
        raise ValueError("Committed predictions do not cover the reference population exactly")
    for meta in manifest_rows:
        eid = meta["event_id"]
        row = by_id[eid]
        status = meta.get("input_status", "available")
        seeds = set(map(int, row.get("seed_asns", [])))
        if status == "available":
            check_committed_inputs(row, inputs.get(eid), candidates)
            scores = row["ranking_scores"] if baseline else row["probabilities"]
            event_ranking_metrics(row["candidate_asns"], scores, [], seeds)
            set(map(int, row["predicted_asns"]))
        elif status not in INPUT_ABSTENTIONS or row.get("candidate_asns") or row.get("predicted_asns"):
            raise ValueError(f"{eid}: an abstention ranks and predicts nothing")
        if issue_time is not None:
            if eid not in issue_time:
                raise ValueError(f"{eid}: no issue-time variables")
            if slice_rule is not None and not baseline and status == "available":
                if "slice_predicted_asns" not in row:
                    raise ValueError(f"{eid}: learned rows need committed slice/remainder decisions")
                set(map(int, row["slice_predicted_asns"]))
            if slice_rule is not None:
                in_issue_time_slice(slice_rule, issue_time[eid])
    return by_id


def per_event_rows(predictions, manifest_rows, labels, *, baseline, inputs, candidates="matched",
                   issue_time=None, slice_rule=None):
    """Score one committed arm on the scorable reference events (custodian only).

    ``labels[event_id]`` is ``{"target_status": "scorable" | "censored", "target_asns": [...]}``.
    ``inputs[event_id]`` is the custodian-exported issue-time input (``asn``, ``seed_asns``) every
    available committed row is checked against (``check_committed_inputs``). Censored events are left
    out of every metric and counted by the caller. Rows are returned in the order of the scorable
    reference events.
    """
    from .forecast_history import in_issue_time_slice
    from .forecast_ranking import event_ranking_metrics
    by_id = check_rows_label_free(predictions, manifest_rows, baseline=baseline, inputs=inputs,
                                  candidates=candidates, issue_time=issue_time, slice_rule=slice_rule)
    out = []
    for meta in manifest_rows:
        eid = meta["event_id"]
        label = labels[eid]
        if label["target_status"] == "censored":
            continue
        if label["target_status"] != "scorable":
            raise ValueError(f"Undeclared target status for {eid}")
        row = by_id[eid]
        status = meta.get("input_status", "available")
        truth = set(map(int, label["target_asns"]))
        seeds = set(map(int, row.get("seed_asns", [])))
        if status == "available":
            check_committed_inputs(row, inputs.get(eid), candidates)
            scores = row["ranking_scores"] if baseline else row["probabilities"]
            ranking = event_ranking_metrics(row["candidate_asns"], scores, truth, seeds)
            predicted = set(map(int, row["predicted_asns"]))
        else:
            if status not in INPUT_ABSTENTIONS or row.get("candidate_asns") or row.get("predicted_asns"):
                raise ValueError(f"{eid}: an abstention ranks and predicts nothing")
            # Explicit abstention penalty (NEW-PERIOD-PROTOCOL.md): AP 0 on an eligible event,
            # no-input and technical failures kept apart.
            ranking = event_ranking_metrics([], [], truth, seeds, status=INPUT_ABSTENTIONS[status])
            predicted = set()
        result = {"event_id": eid, "average_precision": ranking["average_precision"],
                  "precision_at": ranking["precision_at"], "recall_at": ranking["recall_at"],
                  "new_members": ranking["new_members"], "eligible": ranking["eligible"],
                  "coverage_ceiling": ranking["coverage_ceiling"], "ranking_status": ranking["status"],
                  "metric_version": ranking["metric_version"], "jaccard": _jaccard(truth, predicted),
                  "input_status": status, "seed_asns": sorted(seeds)}
        if baseline:
            result["decision_rule"] = "committed_baseline_decision"
        if issue_time is not None:
            variables = issue_time[eid]
            result["issue_time_variables"] = variables
            if slice_rule is not None and not baseline and status == "available":
                if "slice_predicted_asns" not in row:
                    raise ValueError(f"{eid}: learned rows need committed slice/remainder decisions")
                result["two_threshold_jaccard"] = _jaccard(truth, set(map(int, row["slice_predicted_asns"])))
            elif slice_rule is not None and not baseline:
                result["two_threshold_jaccard"] = result["jaccard"]
            if slice_rule is not None:
                result["in_issue_time_slice"] = in_issue_time_slice(slice_rule, variables)
        out.append(result)
    return out


# New-period window (NEW-PERIOD-PROTOCOL.md): starts 1 September 2026 and ends on 16 October 2026, or on
# 1 December 2026 when the binding extension decision extends it. The two end dates are the protocol's
# (forecast_campaign.EXTENSION_RULE; a test keeps them equal), never the decision file's own copy of its rule.
NEW_PERIOD_START = "2026-09-01T00:00:00+00:00"
NEW_PERIOD_ENDS = {False: "2026-10-16", True: "2026-12-01"}


def _instant(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


UNBLINDED_PREFIX = "unblinded-"


def _marker_for(seal, seal_sha256):
    """Content-keyed one-time marker (E2): beside the sealed retention list, named by the seal's hash.

    Every byte-identical copy of a seal names the same retention list (``spec_path``) and has the same
    hash, so every copy maps to this one marker wherever the copy lies.
    """
    return Path(seal["spec_path"]).parent / f"{UNBLINDED_PREFIX}{seal_sha256}.json"


def unblinded_marker(seal_path):
    """The one-time marker of the seal at ``seal_path`` (written immediately before the single label opening)."""
    raw, digest = hashed_bytes(seal_path)
    return _marker_for(json.loads(raw), digest)


def refuse_second_opening(seal, seal_sha256):
    """Refuse when this seal's content, or another seal of the same retention list, was already unblinded.

    Markers live beside the retention list; one that records this seal hash or this retention-list
    hash (a fresh seal of the same list is the same batch) refuses the run.
    """
    marker = _marker_for(seal, seal_sha256)
    if marker.exists():
        raise ValueError(f"Labels of this sealed batch were already opened once ({marker}); no second opening")
    for other in sorted(marker.parent.glob(f"{UNBLINDED_PREFIX}*.json")):
        try:
            record = json.loads(other.read_bytes())
        except (OSError, ValueError) as error:
            raise ValueError(f"Unreadable unblinding marker {other}; refusing a possible second opening") from error
        if record.get("seal_sha256") == seal_sha256 or record.get("custody_spec_sha256") == seal["spec_sha256"]:
            raise ValueError(f"Labels of this sealed batch were already opened once ({other}); no second opening")
    return marker


def evaluation_window(decision):
    """``[start, end)`` of the new-period cohort from a binding extension decision (M3, E4).

    A non-binding (configuration pseudo-seed) rehearsal carries no end date and is refused. The end
    date must be the protocol's for the decision's ``extend`` flag (``NEW_PERIOD_ENDS``); the rule the
    decision file carries is not trusted to say what that is.
    """
    end = decision.get("evaluation_end_exclusive")
    if decision.get("binding") is not True or decision.get("test_data_read") is not False or end is None:
        raise ValueError("The new-period cohort needs a binding extension decision (five-seed sizing)")
    if decision.get("extend") not in (True, False) or end != NEW_PERIOD_ENDS[decision["extend"]]:
        raise ValueError("Extension decision window is not the one the protocol prescribes for its extend flag")
    return _instant(NEW_PERIOD_START), _instant(end)


def _torch_load(raw):
    import io
    import torch
    return torch.load(io.BytesIO(raw), map_location="cpu", weights_only=False)


def _as_list(value):
    return [int(v) for v in (value.tolist() if hasattr(value, "tolist") else value)]


def default_input_loader(raw):
    """Custodian-exported label-free input (forecast_train export-inputs): event ID, candidates, seeds."""
    event = _torch_load(raw)
    return {"event_id": event["event_id"], "asn": _as_list(event["asn"]), "seed_asns": _as_list(event["seed_asns"])}


def default_checkpoint_identity(raw):
    """Training identity recorded in a forecast_train checkpoint: seed, history and message passing."""
    checkpoint = _torch_load(raw)
    return {"seed": checkpoint["receipt"]["seed"], "history": checkpoint["history"],
            "message_passing": checkpoint["settings"].get("message_passing")}


def _bound_bytes(path, expected_sha256, what):
    raw = Path(path).read_bytes()
    if not isinstance(expected_sha256, str) or hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError(f"{what} differs from its sealed hash at read time: {path}")
    return raw


def evaluate_new_period(seal_path, expected_seal_sha256, arm_spec_path, expected_arm_spec_sha256,
                        labels_path, expected_labels_sha256, out, *, extension_decision_path,
                        expected_extension_decision_sha256, access_log, slice_rules_path=None,
                        expected_slice_rules_sha256=None, issue_time_tables=None, repetitions=10000,
                        seed=1701, alpha=0.05, input_loader=default_input_loader,
                        checkpoint_identity=default_checkpoint_identity):
    """The single new-period batch release for the ranking-v1 families (custodian only).

    Order is the contract. Before any label byte: the anchors (the seal and the custody spec are each
    read once and hashed from those bytes), the content-keyed one-time marker check, the arm identity
    and the arm spec's bindings (slice rule, issue-time tables, extension decision, evaluation end date,
    repetitions, alpha, bootstrap seed) are checked; the cohort window comes from the binding extension
    decision and the protocol's end dates; ``authorize_outcome_join`` re-verifies every retained
    prediction against the seal and must report the anchored seal and custody-spec hashes; every file
    used later is re-hashed as it is read (predictions against the seal, manifests, models and custodian
    inputs against the frozen arm); each learned checkpoint's training seed/history/message passing must
    equal its role; and every label-free row check of the scorer runs here (coverage, committed seeds and
    matched candidates against the custodian inputs, well-formed rankings, empty abstentions, committed
    slice decisions, slice membership, one reference cohort and one seed set per horizon). Only then is
    the one-time ``unblinded`` marker written (a second opening is refused), ``access_log`` called and the
    label table opened. ``issue_time_tables[str(delta)]`` is an optional ``{path, sha256}`` table of
    input-only issue-time variables; with the frozen slice rules it enables the slice-Jaccard family,
    otherwise that family is reported unavailable.
    """
    from . import forecast_custody
    out = Path(out)
    if out.exists():
        raise ValueError("Evaluation output already exists")
    if not callable(access_log):
        raise ValueError("The custodian access log is mandatory before the label read")
    seal = bound_json(seal_path, expected_seal_sha256, "One-batch seal")
    marker = refuse_second_opening(seal, expected_seal_sha256)
    spec = bound_json(arm_spec_path, expected_arm_spec_sha256, "Frozen arm spec")
    custody_raw, custody_sha256 = hashed_bytes(seal["spec_path"])
    if custody_sha256 != seal["spec_sha256"] or spec.get("custody_spec_sha256") != seal["spec_sha256"]:
        raise ValueError("Arm spec is not bound to the sealed retention list")
    custody = json.loads(custody_raw)
    derived = derive_new_period_arms(custody)
    check_arm_spec(spec, derived, "new_period")
    tables = {str(d): item["sha256"] for d, item in (issue_time_tables or {}).items()} or None
    bindings = {"slice_rules_sha256": expected_slice_rules_sha256, "issue_time_tables": tables,
                "extension_decision_sha256": expected_extension_decision_sha256, "repetitions": repetitions,
                "alpha": alpha, "bootstrap_seed": seed}
    for key, value in bindings.items():
        if key not in spec or spec[key] != value:
            raise ValueError(f"Arm spec does not bind {key} to the supplied value")
    slice_rules = None
    if slice_rules_path is not None:
        slice_rules = bound_json(slice_rules_path, expected_slice_rules_sha256, "Frozen slice rule")["horizons"]
    issue_time = {}
    for delta, item in (issue_time_tables or {}).items():
        table = bound_json(item["path"], item["sha256"], "Issue-time variable table")
        if table.get("input_only") is not True:
            raise ValueError("Issue-time variables must come from exported inputs only")
        issue_time[str(delta)] = table["events"]
    if slice_rules is not None and set(issue_time) != {"30", "60"}:
        raise ValueError("Slice family needs the issue-time variables of both horizons")
    decision = bound_json(extension_decision_path, expected_extension_decision_sha256, "Extension decision")
    start, end = evaluation_window(decision)
    if spec.get("evaluation_end_exclusive") != decision["evaluation_end_exclusive"]:
        raise ValueError("Arm spec does not bind evaluation_end_exclusive to the extension decision's end date")
    authorization = forecast_custody.authorize_outcome_join(seal_path)
    if (authorization.get("seal_sha256") != expected_seal_sha256
            or authorization.get("spec_sha256") != custody_sha256):
        raise ValueError("One-batch seal changed between its anchored read and the outcome-join check")
    records = {a["arm_id"]: a for a in custody["arms"]}
    sealed = {a["arm_id"]: a for a in seal["arms"]}
    used = {i for by_delta in derived.values() for ids in by_delta.values() for i in ids}
    if not used <= set(authorization["authorized_arm_ids"]):
        raise ValueError("An evaluation arm is outside the authorized sealed batch")
    # ---- everything below up to the label read is label-free and re-hashed as it is read ----
    loaded, inputs_by_manifest, files = {}, {}, {}
    cohorts, seed_rows = {}, {}
    for arm_id in sorted(used):
        record, role = records[arm_id], records[arm_id]["role"]
        delta = int(role["horizon_seconds"])
        manifest_raw = _bound_bytes(record["manifest_path"], record["manifest_sha256"], "Frozen manifest")
        manifest = json.loads(manifest_raw)
        if manifest.get("delta_s") != delta:
            raise ValueError(f"{arm_id}: manifest horizon {manifest.get('delta_s')!r} differs from its role ({delta} s)")
        reference = sorted((r for r in manifest["events"] if r.get("split") == "test"), key=lambda r: r["event_id"])
        outside = [r["event_id"] for r in reference if not start <= _instant(r["onset"]) < end]
        if outside:
            raise ValueError(f"{arm_id}: cohort events outside the decided window [{start}, {end}): {outside[:5]}")
        cohort = [(r["event_id"], r["incident_id"], r["onset"], r.get("input_status", "available")) for r in reference]
        if cohorts.setdefault(delta, cohort) != cohort:
            raise ValueError(f"Arms at {delta} s disagree on the reference cohort")
        if record["manifest_sha256"] not in inputs_by_manifest:
            inputs = {}
            for row in reference:
                if row.get("input_status", "available") != "available":
                    continue
                event = input_loader(_bound_bytes(row["input_path"], row["input_sha256"], "Custodian input"))
                if event["event_id"] != row["event_id"]:
                    raise ValueError(f"Custodian input identity differs: {row['event_id']}")
                inputs[row["event_id"]] = event
            inputs_by_manifest[record["manifest_sha256"]] = inputs
        inputs = inputs_by_manifest[record["manifest_sha256"]]
        if role["family"] == "neural":
            identity = checkpoint_identity(_bound_bytes(record["model_path"], record["model_sha256"], "Frozen model"))
            if (identity.get("seed") != role["seed"] or identity.get("history") != role["history"]
                    or identity.get("message_passing") != role["message_passing"]):
                raise ValueError(f"{arm_id}: checkpoint training identity {identity} differs from its role")
        else:
            _bound_bytes(record["model_path"], record["model_sha256"], "Frozen model")
        predictions = json.loads(_bound_bytes(record["predictions_path"], sealed[arm_id]["predictions_sha256"],
                                              "Sealed predictions"))
        candidates = "matched" if role["family"] == "neural" else role.get("candidates")
        # Every label-free check of per_event_rows, over all reference events (E1).
        by_id = check_rows_label_free(predictions, reference, baseline=role["family"] == "baseline", inputs=inputs,
                                      candidates=candidates, issue_time=issue_time.get(str(delta)),
                                      slice_rule=None if slice_rules is None else slice_rules[str(delta)])
        seeds = tuple(tuple(sorted(set(map(int, by_id[r["event_id"]].get("seed_asns", []))))) for r in reference)
        if seed_rows.setdefault(delta, seeds) != seeds:
            raise ValueError(f"Arms at {delta} s do not share the issue-time input seeds")
        loaded[arm_id] = (reference, predictions, candidates, delta)
        files[arm_id] = {"manifest_sha256": record["manifest_sha256"], "model_sha256": record["model_sha256"],
                         "predictions_sha256": sealed[arm_id]["predictions_sha256"],
                         "commitment_sha256": sealed[arm_id]["commitment_sha256"]}
    # ---- label access starts here (custodian only, once per sealed batch) ----
    with marker.open("x") as stream:
        json.dump({"unblinded_utc": datetime.now(timezone.utc).isoformat(), "seal_sha256": expected_seal_sha256,
                   "custody_spec_sha256": custody_sha256, "seal_path": str(Path(seal_path).resolve()),
                   "arm_spec_sha256": expected_arm_spec_sha256, "labels_sha256": expected_labels_sha256,
                   "out": str(out.resolve())}, stream, indent=2)
    access_log(labels_path, "new-period one-batch evaluation: label join after seal")
    label_table = bound_json(labels_path, expected_labels_sha256, "Custodian label table")
    if label_table.get("kind") != "custodian_label_table":
        raise ValueError("Labels must be the custodian label table")
    arms, rows, censoring = {}, {}, {}
    for name, by_delta in derived.items():
        arms[name] = {}
        for delta_key, ids in by_delta.items():
            delta = int(delta_key)
            labels = label_table["horizons"][delta_key]
            seeds = []
            for arm_id in ids:
                reference, predictions, candidates, _ = loaded[arm_id]
                if {r["event_id"] for r in reference} != set(labels):
                    raise ValueError("Label table does not cover the reference population exactly")
                scored = per_event_rows(predictions, reference, labels,
                                        baseline=records[arm_id]["role"]["family"] == "baseline",
                                        inputs=inputs_by_manifest[records[arm_id]["manifest_sha256"]],
                                        candidates=candidates, issue_time=issue_time.get(delta_key),
                                        slice_rule=None if slice_rules is None else slice_rules[delta_key])
                seeds.append(scored)
                order = [{"event_id": r["event_id"], "incident_id": r["incident_id"], "onset": r["onset"]}
                         for r in reference if labels[r["event_id"]]["target_status"] == "scorable"]
                if rows.setdefault(delta, order) != order:
                    raise ValueError("Arms disagree on the scorable reference cohort")
                censoring[delta_key] = {"reference_events": len(reference),
                                        "censored_events": len(reference) - len(order), "scorable_events": len(order)}
            arms[name][delta] = seeds
    for delta in HORIZONS:
        seed_sets = {tuple(tuple(r["seed_asns"]) for r in per_event)
                     for by_delta in arms.values() for per_event in by_delta[delta]}
        if len(seed_sets) != 1:
            raise ValueError(f"Arms at {delta} s do not share the issue-time input seeds")
    report = _contrast_families(arms, rows, slice_rules, contrasts=PRIMARY_CONTRASTS, declares_primary=True,
                                repetitions=repetitions, seed=seed, alpha=alpha,
                                whole_system=WHOLE_SYSTEM_CONTRASTS, median=True)
    report.update(population="new_period", confirmatory=True, censoring=censoring,
                  seal_sha256=expected_seal_sha256, custody_spec_sha256=seal["spec_sha256"],
                  arm_spec_sha256=expected_arm_spec_sha256, labels_sha256=expected_labels_sha256,
                  slice_rules_sha256=expected_slice_rules_sha256, issue_time_tables_sha256=tables,
                  extension_decision_sha256=expected_extension_decision_sha256, alpha=alpha,
                  evaluation_window={"start": start.isoformat(), "end_exclusive": end.isoformat()},
                  unblinded_marker=str(marker), files=files,
                  authorized_arm_ids=authorization["authorized_arm_ids"],
                  arms=derived, source_sha256=sha(__file__),
                  unblinding_contract=("predictions sealed per arm/seed/horizon/panel, re-verified and re-hashed "
                                       "at read time before the single label join"))
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return report
