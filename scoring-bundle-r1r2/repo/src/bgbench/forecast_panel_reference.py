"""Derive reference10 availability from the two audited H3 panel ledgers.

The panel union is exactly the reference collector set. Unioning their issue-time
seed sets therefore gives the reference seeds; shared collectors and clocks must
agree exactly. Only existing label-free metadata is consumed. No graph, forecast,
label, cohort freeze or scoring operation is performed here.
"""
from __future__ import annotations

import datetime as dt
import json

from . import forecast_h3_commitments as h3
from . import forecast_panel_scoring as scoring

require = scoring.require
SCOPE = "h3-reference-metadata-union-v1"
CERTIFYING = frozenset({"reported_complete_day", "identified_day_gaps_outside_current_and_predecessor_window"})


def encoded(doc):
    return (json.dumps(doc, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def digest(doc):
    return scoring.sha256_bytes(encoded(doc))


def utc(value):
    parsed = dt.datetime.fromisoformat(value)
    require(parsed.tzinfo is not None, "Input clock must have a timezone")
    return parsed.astimezone(dt.UTC)


def derive(horizon, ids, panels, *, manifest_sha256, metadata_sha256):
    """Consume independently bound documents, checked by the CLI before this pure operation.

    Each panel supplies its metadata build entry, availability, status ledger,
    coverage extract and their byte hashes. The CLI also reruns frozen check_build.
    """
    require(horizon in h3.HORIZONS and set(panels) == set(h3.PANELS), "Both panels and a declared horizon required")
    require(len(ids) == len(set(ids)) and scoring.population_sha256(ids) == scoring.REFERENCE_POPULATION_SHA256
            and len(ids) == scoring.REFERENCE_EVENTS, "Reference population differs")
    require(set().union(*map(set, h3.PANELS.values())) == set(h3.REFERENCE), "Panels do not cover reference10")
    source_rows, bindings = {}, {}
    coverage_receipt = None
    for arm, item in panels.items():
        ledger, coverage, availability = item["ledger"], item["coverage"], item["availability"]
        hashes = item["hashes"]
        require(ledger.get("contains_labels") is False and ledger.get("panel") == arm
                and ledger.get("delta_s") == horizon, "Wrong input ledger")
        require(ledger.get("input_collectors") == list(h3.PANELS[arm])
                and ledger.get("reference_collectors") == list(h3.REFERENCE), "Ledger collector set differs")
        require(coverage.get("panel_name") == arm and coverage.get("panel") == list(h3.PANELS[arm])
                and coverage.get("delta_s") == horizon
                and coverage["manifest"]["sha256"] == manifest_sha256, "Coverage build differs")
        require(set(coverage["certifying_day_statuses"]) == CERTIFYING, "Coverage certification policy differs")
        require(scoring._hex64(coverage.get("receipt_sha256")), "Missing original coverage binding")
        if coverage_receipt is None:
            coverage_receipt = coverage["receipt_sha256"]
        require(coverage["receipt_sha256"] == coverage_receipt, "Panels use different coverage sources")
        translated = h3.translate_availability(ledger, coverage, arm, ids,
                                               ledger_sha256=hashes["ledger"], coverage_sha256=hashes["coverage"])
        require(availability["rows"] == translated, "Availability is not the ledger translation")
        audit = scoring.panel_audit(arm, horizon, item["build"], availability, hashes["availability"],
                                    ledger, hashes["ledger"])
        scoring.check_availability(availability, arm, horizon, ids,
                                   availability_sha256=hashes["availability"], audit=audit)
        source_rows[arm] = {row["event_id"]: row for row in ledger["events"]}
        require(len(source_rows[arm]) == len(ledger["events"]), "Duplicate ledger event")
        bindings[arm] = dict(hashes)
    ledger_rows, coverage_rows = [], {}
    for eid in ids:
        collectors, day_evidence, seeds = {}, {}, set()
        onset = issue = None
        for arm in h3.PANELS:
            row = source_rows[arm][eid]
            evidence = panels[arm]["coverage"]["events"][eid]
            row_onset, row_issue = utc(row["onset"]), utc(row["issue_time"])
            require(row_issue - row_onset == dt.timedelta(seconds=horizon), "Issue clock differs from horizon")
            require(utc(evidence["observed_onset"]) == row_onset, "Coverage onset differs")
            if onset is None:
                onset, issue = row_onset, row_issue
            require((row_onset, row_issue) == (onset, issue), "Panel clocks differ")
            seeds.update(scoring._asns(row["input_seed_asns"], "Panel seeds"))
            for collector in h3.PANELS[arm]:
                facts = row["collectors"][collector]
                statuses = sorted(set(evidence["day_evidence"].get(collector, [])))
                missing_part = collector in evidence["missing_retained_part_collectors"]
                proof = {"day_statuses": statuses, "missing_retained_part": missing_part}
                if collector in collectors:
                    require(collectors[collector] == facts and day_evidence[collector] == proof,
                            f"Overlapping collector evidence differs: {eid}: {collector}")
                require(facts["status"] in ("observed", "empty", "missing"), "Unknown reference collector status")
                count = facts.get("messages_by_issue")
                require(type(count) is int and count >= 0, "Invalid issue-time message count")
                require((count > 0) == (facts["status"] == "observed"), "Observation status/count disagree")
                if facts["status"] == "empty":
                    require(not missing_part and statuses and set(statuses) <= CERTIFYING,
                            "Empty collector lacks source completeness evidence")
                collectors[collector], day_evidence[collector] = dict(facts), proof
        require(set(collectors) == set(h3.REFERENCE), "Reference collector coverage incomplete")
        missing = sorted(c for c, r in collectors.items() if r["status"] == "missing")
        require(seeds or not missing, "Reference source failure cannot become no-input abstention")
        available = bool(seeds)
        ledger_rows.append({"event_id": eid, "onset": onset.isoformat(), "issue_time": issue.isoformat(),
                            "status": "available" if available else "unavailable_no_input",
                            "forecast_available": available, "abstention_policy": None if available else h3.ABSTENTION,
                            "partial_panel_input": bool(missing), "input_seed_asns": sorted(seeds),
                            "collectors": collectors, "input_collectors": list(h3.REFERENCE),
                            "reference_collectors": list(h3.REFERENCE)})
        coverage_rows[eid] = day_evidence
    common = {"scope": SCOPE, "contains_labels": False, "horizon_seconds": horizon,
              "metadata_ledger_sha256": metadata_sha256, "reference_manifest_sha256": manifest_sha256,
              "source_bindings": bindings}
    ledger = {**common, "panel": "reference", "delta_s": horizon, "events": ledger_rows,
              "derivation": "union of issue-time seeds; exact agreement of overlapping collector records and clocks"}
    coverage = {**common, "kind": "h3_reference_coverage_union", "original_coverage_receipt_sha256": coverage_receipt,
                "collectors": list(h3.REFERENCE), "events": coverage_rows}
    ledger_sha, coverage_sha = digest(ledger), digest(coverage)
    rows, partial, no_input, missing_map = [], [], [], {}
    for row in ledger_rows:
        eid = row["event_id"]
        gaps = sorted(c for c, facts in row["collectors"].items() if facts["status"] == "missing")
        if gaps:
            partial.append(eid)
            missing_map[eid] = gaps
        if not row["forecast_available"]:
            no_input.append(eid)
        rows.append({"event_id": eid, "status": "available" if row["forecast_available"] else "no_input",
                     "ledger_status": row["status"], "input_window_complete": not gaps, "parse_status": "ok",
                     "input_seed_asns": row["input_seed_asns"], "coverage_audit_sha256": coverage_sha,
                     "input_status_ledger_sha256": ledger_sha, "partial_panel_input": bool(gaps),
                     "panel_missing_collectors": gaps})
    availability = {**common, "panel": "reference", "reference_event_ids_sha256": scoring.population_sha256(ids),
                    "rows": rows}
    audit = {**common, "kind": scoring.AUDIT_KIND, "arm": "reference", "collectors": list(h3.REFERENCE),
             "availability_sha256": digest(availability), "coverage_audit_sha256": coverage_sha,
             "input_status_ledger_sha256": ledger_sha, "partial_event_ids": partial,
             "missing_collectors": missing_map, "no_input_event_ids": no_input,
             "seed_asns_sha256": scoring.canonical_sha256({r["event_id"]: r["input_seed_asns"] for r in rows})}
    scoring.check_availability(availability, "reference", horizon, ids,
                               availability_sha256=digest(availability), audit=audit)
    return {"input-status-ledger.json": ledger, "coverage-union.json": coverage,
            "availability.json": availability, "audit.json": audit}
