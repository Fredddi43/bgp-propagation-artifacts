"""Stable-peer sensitivity R-stable / N-stable: source derivation, exact membership parity and R1 linkage.

PEER-CHURN.md (frozen 639-identity selection), HISTORY-SENSITIVITY-EXECUTION-DECISIONS.md decisions 5 and 6, and
REVIEW-PACKET-STABLE-PEER-EXECUTION.md. Proposed for independent review; nothing here authorizes a source
derivation, graph build, prediction or score. Pure functions; I/O lives in ``scripts/stage_stable_peer_inputs.py``
(data root) and ``scripts/forecast_stable_peer_campaign.py`` (manifests, gate, audit, linkage, recipe).

* Selection: the frozen peer identities ``(collector, peer_ip, peer_asn)``, re-hashed with the protocol-pack rule
  and pinned. IPv4/IPv6 addresses are compared as ``ipaddress`` values (canonical text); IPv4-mapped IPv6 and
  unparsable addresses are refused rather than merged.
* Rows: a pure row filter on the event's own anomalous rows. Row order and every duplicate occurrence are kept.
* Membership: ``extent.membership`` (the replay rule) for keys, first_seen, via_prefix and n_msgs, with two
  recorded source conventions made explicit (REVIEW-PACKET-STABLE-PEER-EXECUTION.md §2):
  - ``delay_s`` is integer microseconds after the event's *recorded* clock (``summary.t0`` for summaries written
    before d4a79db, which carry no ``measurement_onset``; otherwise ``summary.first_observation``) times 1e-6,
    computed here in Python so it no longer depends on Polars' SIMD division path;
  - for 2025 events whose source occurrences were restored, ``via_prefix`` comes from the hash-bound pre-repair
    rows (the order the canonical value was computed on) while ``n_msgs`` comes from the restored rows, exactly
    as the reviewed metadata producer composed the canonical file.
* Parity is per logical column with no tolerance: delay_s must equal the recorded clock in integer microseconds
  and be bit-equal to one of the two IEEE results the historical arithmetic produced (``m * 1e-6`` or ``m / 1e6``).
* Clock: every stable event keeps the primary ``first_observation`` (issue time = primary onset + delta) and the
  primary two-hour boundary. The stable target is rebuilt from stable rows only.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
from datetime import UTC, datetime, timedelta

STABLE_SELECTION_SHA256 = "7ebedd6e32dd64b6de53425fcadc358a211cce29207cf9e025464f2bdb1eff77"
STABLE_SELECTION_FILE_SHA256 = "47d759c1abd3b01119dc76296cd136e1014444a56911fd562ddc09ace91d961d"
STABLE_PEER_COUNT = 639
REFERENCE_PANEL = ("route-views.linx", "route-views2", "route-views3", "rrc00", "rrc01",
                   "rrc03", "rrc12", "rrc15", "rrc20", "rrc25")
ROW_COLUMNS = ("ts", "collector", "peer_ip", "peer_asn", "prefix", "as_path", "origin_asn")
MEMBERSHIP_COLUMNS = ("collector", "asn", "first_seen", "via_prefix", "n_msgs", "delay_s")
TARGET_HORIZON_S = 7200
HORIZONS_S = (30, 60)
DELAY_CONVENTION = "integer microseconds after the recorded clock times 1e-6 (Python float)"
INPUT_STATUSES = ("stable_input", "certified_no_stable_input")
COVERAGE_CLASSES = ("complete", "inherited_primary_incomplete")
# How a completed event with incomplete primary coverage and no stable rows is treated. Only "refuse" is
# implemented; any other treatment is a scientific choice for the reviewer (packet seam S3).
INCOMPLETE_EMPTY_POLICIES = ("refuse",)
STAGE_KIND = "stable_peer_data_root_receipt"
GATE_KIND = "stable_peer_input_gate"
LINKAGE_KIND = "stable_peer_r1_target_linkage"
RECIPE_KIND = "stable_peer_newperiod_recipe"


def sensitivity() -> dict:
    """The intervention identity, bound to the selection digest pinned at call time."""
    return {"axis": "R-stable", "kind": "stable_peer_identity_filter",
            "selection_sha256": STABLE_SELECTION_SHA256, "retraining_fits": 0}


class StablePeerError(ValueError):
    pass


class SourceError(StablePeerError):
    """Missing, unreadable, inconsistent or incompletely covered source: never an empty event."""


def require(ok, message, error=StablePeerError):
    if not ok:
        raise error(message)


def canonical_sha(doc) -> str:
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def ids_sha256(ids) -> str:
    return hashlib.sha256("\n".join(sorted(ids)).encode()).hexdigest()


def utc(value) -> datetime:
    value = datetime.fromisoformat(value) if isinstance(value, str) else value
    require(isinstance(value, datetime), f"Expected a timestamp, got {value!r}")
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


# ---- selection -------------------------------------------------------------------------------------------------

def normalize_peer_ip(value) -> str:
    """Canonical text of an IPv4/IPv6 peer address; refuses blanks, garbage and IPv4-mapped IPv6."""
    require(isinstance(value, str) and value.strip() == value and value, f"Invalid peer address {value!r}")
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise StablePeerError(f"Unparsable peer address {value!r}") from exc
    require(not (address.version == 6 and address.ipv4_mapped is not None),
            f"IPv4-mapped peer address {value!r} needs an explicit reviewed identity rule")
    return address.compressed


def peer_key(collector, peer_ip, peer_asn):
    require(isinstance(collector, str) and collector, f"Invalid collector {collector!r}")
    require(isinstance(peer_asn, int) and not isinstance(peer_asn, bool) and peer_asn > 0, f"Invalid peer ASN {peer_asn!r}")
    return collector, normalize_peer_ip(peer_ip), int(peer_asn)


def load_selection(doc, *, expected_sha256=None, expected_count=None, panel=REFERENCE_PANEL) -> frozenset:
    """The frozen identities; the inner digest is recomputed with the protocol-pack rule (sha256_json(peers))."""
    expected_sha256 = expected_sha256 or STABLE_SELECTION_SHA256
    expected_count = expected_count or STABLE_PEER_COUNT
    peers = doc.get("peers") if isinstance(doc, dict) else None
    require(isinstance(peers, dict), "Not a stable-peer selection")
    require(canonical_sha(peers) == doc.get("sha256") == expected_sha256, "Stable-peer selection digest differs")
    require(set(peers) <= set(panel), f"Selection collectors outside the reference panel: {sorted(set(peers) - set(panel))}")
    keys = [peer_key(c, ip, asn) for c, rows in peers.items() for ip, asn in rows]
    require(len(keys) == len(set(keys)) == expected_count, "Selection identities are not the frozen unique set")
    require(not any(ip in ("0.0.0.0", "::") or asn == 0 for _, ip, asn in keys), "Placeholder identity in selection")
    return frozenset(keys)


# ---- rows and membership --------------------------------------------------------------------------------------

def filter_stable_rows(rows, peers):
    """Keep exactly the rows of selected identities, in source order, with every duplicate occurrence."""
    import polars as pl
    require(set(ROW_COLUMNS) <= set(rows.columns), "Anomalous rows lack the replay row columns", SourceError)
    sessions = rows.select("collector", "peer_ip", "peer_asn").unique()
    keep, invalid = set(), set()
    for c, ip, a in sessions.iter_rows():
        try:
            key = peer_key(c, ip, a)
        except StablePeerError:
            # An invalid identity cannot be silently discarded if either usable
            # identity component points at a selected session on this collector.
            normalized = None
            try:
                address = ipaddress.ip_address(ip)
                normalized = str(address.ipv4_mapped or address) if address.version == 6 else str(address)
            except (ValueError, TypeError):
                pass
            ambiguous = any(pc == c and (pa == a or pi == normalized or pi == ip) for pc, pi, pa in peers)
            require(not ambiguous, "Invalid selected peer identity is ambiguous", SourceError)
            invalid.add((c, ip, a))
            continue
        if key in peers:
            keep.add((c, ip, a))
    identities = list(rows.select("collector", "peer_ip", "peer_asn").iter_rows())
    filtered = rows.filter(pl.Series([key in keep for key in identities], dtype=pl.Boolean))
    stats = {"rows_in": rows.height, "rows_kept": filtered.height, "sessions_in": sessions.height,
             "sessions_kept": len(keep), "invalid_unselected_sessions": len(invalid),
             "invalid_unselected_rows": sum(key in invalid for key in identities)}
    return filtered, stats


def with_hops(rows):
    """replay_day.measure_event's hop parsing (UInt32, braces removed)."""
    import polars as pl
    return rows.with_columns(hops=pl.col("as_path").str.replace_all(r"[{}]", "").str.split(" ")
                             .list.eval(pl.element().cast(pl.UInt32, strict=False)))


def recorded_delay_clock(summary) -> datetime:
    """The clock the canonical delay_s was measured from (see module docstring)."""
    key = "t0" if "measurement_onset" not in summary else "first_observation"
    require(summary.get(key), f"Summary has no {key}", SourceError)
    return utc(summary[key])


def _micros(when, clock) -> int:
    return (utc(when) - clock) // timedelta(microseconds=1)


def empty_membership():
    import polars as pl
    return pl.DataFrame(schema={"collector": pl.String, "asn": pl.UInt32, "first_seen": pl.Datetime("us", "UTC"),
                                "via_prefix": pl.String, "n_msgs": pl.UInt32, "delay_s": pl.Float64})


def derive_membership(rows, *, onset, actor, delay_clock, prefix_rows=None):
    """Canonical membership of ``rows``; ``prefix_rows`` (restored events) supplies via_prefix only."""
    import polars as pl

    from .extent import membership
    require(isinstance(actor, int) and actor > 0, "Membership needs the event actor ASN")
    if not rows.height:
        require(prefix_rows is None or not prefix_rows.height, "Pre-repair rows exist where restored rows are empty",
                SourceError)
        return empty_membership()
    table = membership(with_hops(rows), utc(onset), [actor]).drop("delay_s")
    if prefix_rows is not None:
        require(prefix_rows.height > 0, "Restored rows have no pre-repair counterpart", SourceError)
        old = membership(with_hops(prefix_rows), utc(onset), [actor]).select("collector", "asn", "first_seen", "via_prefix")
        joined = table.drop("via_prefix").join(old, on=["collector", "asn"], how="full", coalesce=True,
                                               suffix="_pre_repair")
        require(joined.height == table.height == old.height
                and joined["first_seen"].equals(joined["first_seen_pre_repair"]),
                "Pre-repair and restored rows disagree on members or first_seen", SourceError)
        table = joined.drop("first_seen_pre_repair")
    delays = [_micros(f, utc(delay_clock)) * 1e-6 for f in table["first_seen"].to_list()]
    table = table.with_columns(pl.col("n_msgs").cast(pl.UInt32), pl.Series("delay_s", delays, dtype=pl.Float64))
    return table.select(MEMBERSHIP_COLUMNS).sort("collector", "first_seen", "asn")


def logical_parity(derived, stored, *, delay_clock) -> dict:
    """Exact logical-row comparison of two membership tables; physical Parquet encoding is irrelevant."""
    keyed = [t.select(MEMBERSHIP_COLUMNS).sort("collector", "asn") for t in (derived, stored)]
    report = {"rows_equal": keyed[0].height == keyed[1].height, "differing_columns": []}
    if report["rows_equal"]:
        for column in ("collector", "asn", "first_seen", "via_prefix", "n_msgs"):
            if not keyed[0][column].equals(keyed[1][column]):
                report["differing_columns"].append(column)
        if "collector" not in report["differing_columns"] and "asn" not in report["differing_columns"]:
            clock = utc(delay_clock)
            for (_, d), (f, s) in zip(keyed[0].select("first_seen", "delay_s").iter_rows(),
                                      keyed[1].select("first_seen", "delay_s").iter_rows()):
                m = _micros(f, clock)
                if round(s * 1e6) != m or s not in (m * 1e-6, m / 1e6) or round(d * 1e6) != m:
                    report["differing_columns"].append("delay_s")
                    break
    report["passed"] = report["rows_equal"] and not report["differing_columns"]
    return report


# ---- coverage, clock and input status --------------------------------------------------------------------------

def coverage_class(summary) -> str:
    """Archive coverage of a successful primary event; missing coverage is never certified empty."""
    require(not summary.get("error") and summary.get("first_observation"), "Not a successful observed event", SourceError)
    gaps = summary.get("measurement_missing_archive_blocks") or {}
    require(not any(gaps.values()), "Successful event records missing archive blocks", SourceError)
    parts, expected = summary.get("collectors_with_parts"), summary.get("expected_collectors")
    require(isinstance(parts, int) and isinstance(expected, int) and 0 < parts <= expected == len(REFERENCE_PANEL),
            "Summary does not record collector-part coverage", SourceError)
    return "complete" if parts == expected else "inherited_primary_incomplete"


def check_empty_allowed(coverage, rows_kept, *, policy="refuse"):
    require(policy in INCOMPLETE_EMPTY_POLICIES, f"Unsupported incomplete-empty policy {policy!r}")
    if rows_kept == 0 and coverage != "complete":
        raise SourceError("No stable rows on an event with incomplete archive coverage: missing coverage is not an "
                          "empty stable target (reviewed treatment required, packet seam S3)")


def input_status(stable_membership, onset, delta_s, *, coverage="complete", missing_collectors=None, peers=None) -> dict:
    """Issue-time stable input (seeds by the availability rule); zero seeds is the declared abstention."""
    from .forecast_protocol import admit_available
    require(delta_s in HORIZONS_S, f"Unsupported horizon {delta_s}")
    issue = utc(onset) + timedelta(seconds=delta_s)
    admitted = admit_available(stable_membership, issue, ts_column="first_seen") if stable_membership.height else stable_membership
    seeds = len(set(admitted["asn"].to_list())) if admitted.height else 0
    require(coverage in ("complete", "inherited_primary_incomplete"), "Unknown coverage class")
    missing = None if missing_collectors is None else sorted(set(missing_collectors))
    if missing is not None:
        require(set(missing) <= set(REFERENCE_PANEL), "Unknown missing collector")
    can_certify = coverage == "complete" or (bool(missing) and peers is not None
                                            and not any(c in missing for c, _, _ in peers))
    status = INPUT_STATUSES[0] if seeds else INPUT_STATUSES[1] if can_certify else "source_failure"
    return {"issue_time": issue.isoformat(), "status": status, "stable_seed_count": seeds,
            "coverage": coverage, "partial_observation": coverage != "complete",
            "missing_collectors": missing,
            "failure_reason": "missing coverage may hide selected stable input" if status == "source_failure" else None}


# ---- stable summary and event table ----------------------------------------------------------------------------

# Primary summary keys a stable summary keeps verbatim: identity, actor, clock, window and coverage.
SUMMARY_INHERITED = ("event_id", "kind", "prefix", "new_origin", "leaker", "sources", "upstreams", "t0",
                     "collectors_with_parts", "expected_collectors", "first_observation", "observation_lag_s",
                     "measurement_onset", "measurement_planned_window_end", "measurement_followup_within_planned_window")
# Counts of the unfiltered pass that staged anomalous rows cannot reproduce for a peer subset.
SUMMARY_NOT_DERIVABLE = ("rows_with_adjacency", "sessions_carrying_prefix")


def stable_summary(primary, rows, membership, *, provenance) -> dict:
    """Successful-event summary for the stable root; the clock is the primary one, counts are stable-only."""
    import polars as pl

    from .extent import TARGETS_S
    onset = utc(primary["first_observation"])
    summary = {k: primary[k] for k in SUMMARY_INHERITED if k in primary}
    firsts = membership.group_by("asn").agg(first=pl.col("first_seen").min()) if membership.height else None
    vp = rows.group_by("collector", "peer_ip").agg(first=pl.col("ts").min()) if rows.height else None

    def at(seconds):
        limit = onset + timedelta(seconds=seconds)
        members = membership.filter(pl.col("first_seen") <= pl.lit(limit)) if membership.height else membership
        return {"asns_pooled": members["asn"].n_unique() if members.height else 0,
                "vp_sessions": vp.filter(pl.col("first") <= pl.lit(limit)).height if vp is not None else 0,
                "per_collector_asns": members.group_by("collector").agg(pl.col("asn").n_unique().alias("n"))
                .sort("collector").to_dicts() if members.height else []}
    summary.update(
        anomalous_msgs=rows.height, leaked_prefixes=rows["prefix"].n_unique() if rows.height else None,
        collectors_seeing=sorted(rows["collector"].unique().to_list()) if rows.height else [],
        sessions_switched_to_new_origin=vp.height if vp is not None else 0,
        extent={k: at(v) for k, v in TARGETS_S.items()},
        persistence_extent_asns=firsts.filter(pl.col("first") <= pl.lit(onset)).height if firsts is not None else 0,
        **{k: None for k in SUMMARY_NOT_DERIVABLE},
        stable_peer={**provenance, "clock": "primary first_observation and two-hour boundary, unchanged",
                     "not_derivable_fields": list(SUMMARY_NOT_DERIVABLE)})
    return summary


# Event-table columns inherited from the primary (identity, selection, split, clock and source status). They must
# equal the rebuilt values where eventset.build_table recomputes them from the stable summaries.
TABLE_INHERITED = ("event_id", "split", "reason", "labelled", "max_collectors", "n_msgs", "duration_min", "a",
                   "error", "observation_lag_s", "t0_obs", "trigger_lag_s", "wave_prefixes")
TABLE_NOT_DERIVABLE = ("sessions_carrying",)


def table_column_role(name) -> str:
    if name in TABLE_INHERITED or name.startswith("measurement_"):
        return "inherited"
    if name in TABLE_NOT_DERIVABLE:
        return "not_derivable"
    if name in ("anomalous_msgs", "t90_s", "sessions_switched", "collectors_seeing", "leaked_prefixes") \
            or name.startswith(("set_", "asns_", "vp_")):
        return "stable_derived"
    raise StablePeerError(f"Event-table column {name!r} has no declared stable-peer role")


def merge_stable_table(primary, rebuilt):
    """Primary schema and row order; inherited columns checked equal, label columns from the stable rebuild.

    ``rebuilt`` (eventset.build_table on the stable root) holds the successful events only. Primary source
    failures have no staged files: their rows are inherited unchanged and must carry no derived values.
    """
    import polars as pl
    roles = {c: table_column_role(c) for c in primary.columns}
    require(primary["event_id"].n_unique() == primary.height, "Duplicate primary event IDs")
    failed = primary["error"].is_not_null()
    require(sorted(rebuilt["event_id"].to_list()) == sorted(primary.filter(~failed)["event_id"].to_list()),
            "Stable event table population differs from the primary successful events")
    if "error" in rebuilt.columns:
        require(rebuilt["error"].null_count() == rebuilt.height, "Stable rebuild turned an event into a failure")
    for column, role in roles.items():
        if role != "inherited":
            require(primary.filter(failed)[column].null_count() == int(failed.sum()),
                    f"Primary failure rows carry derived values in {column}")
    joined = primary.select("event_id").join(rebuilt, on="event_id", how="left", maintain_order="left")
    ok = (~failed).to_list()
    out = {}
    for column, role in roles.items():
        if role == "inherited":
            if column in rebuilt.columns and column not in ("event_id", "error"):
                left, right = primary[column].to_list(), joined[column].to_list()
                for keep, a, b in zip(ok, left, right):
                    if not keep:
                        continue
                    same = (a is None and b is None) or (a is not None and b is not None and (
                        _utc_equal(a, b) if column == "t0_obs" else a == b))
                    require(same, f"Stable rebuild changed inherited column {column}")
            out[column] = primary[column]
        elif role == "not_derivable":
            out[column] = pl.Series(column, [None] * primary.height, dtype=primary.schema[column])
        else:
            require(column in rebuilt.columns or primary[column].null_count() == primary.height,
                    f"Stable rebuild lacks derived column {column}")
            values = joined[column] if column in rebuilt.columns else primary[column]
            out[column] = values.cast(primary.schema[column], strict=True).alias(column)
    return pl.DataFrame(out).select(primary.columns)


def _utc_equal(a, b) -> bool:
    return utc(a) == utc(b)


# ---- manifests, gate, linkage and new-period recipe -------------------------------------------------------------

def stable_manifest(original, original_sha256, *, stage_receipt_sha256, tensors, abstentions, delta_s):
    """Primary rows (clock, splits, incidents) with stable graphs; certified abstentions listed separately.

    ``tensors``: {event_id: {"path", "sha256"}} for every built event; ``abstentions``: {event_id: input-status}.
    Built events plus abstentions must be exactly the primary IDs.
    """
    require(original.get("delta_s") == delta_s and not original.get("locked_test") and "source_manifest_sha256" not in original,
            "Stable manifests derive from the primary retrospective manifest of the same horizon")
    ids = [r["event_id"] for r in original["events"]]
    require(not set(tensors) & set(abstentions) and set(tensors) | set(abstentions) == set(ids),
            "Stable tensors and certified abstentions must partition the primary IDs")
    require(all(a.get("status") == "certified_no_stable_input" for a in abstentions.values()),
            "Only certified no-input events may be abstentions")
    rows = [{**r, "graph_path": str(tensors[r["event_id"]]["path"]), "graph_sha256": tensors[r["event_id"]]["sha256"]}
            for r in original["events"] if r["event_id"] in tensors]
    doc = {k: v for k, v in original.items() if k not in ("events", "manifest_sha256")}
    doc.update(source_manifest_sha256=original_sha256, training_authorized=False, fit_authority="none",
               stable_peer={**sensitivity(), "stage_receipt_sha256": stage_receipt_sha256,
                            "population_ids_sha256": ids_sha256(ids),
                            "abstentions": {e: abstentions[e] for e in sorted(abstentions)},
                            "row_metadata": "inherited unchanged from the primary manifest (onsets, issue times, "
                                            "splits, incidents); the target is the stable-peer target in each tensor",
                            "use": "frozen inference-only sensitivity scored against its own stable target"},
               events=rows)
    doc["manifest_sha256"] = canonical_sha({k: v for k, v in doc.items() if k != "manifest_sha256"})
    return doc


def stable_gate(manifests, *, primary_gate, stable_library_digest, code_sha256):
    """Separate input gate: refuses primary tensor bytes and any tensor whose library is not the stable one.

    ``manifests``: [{"path", "sha256", "doc", "delta_s", "tensor_contracts": {event_id: contract}}].
    """
    primary_hashes = {r["sha256"] for m in primary_gate["manifests"] for r in m["inputs"]}
    entries = []
    for m in manifests:
        doc = m["doc"]
        require(doc.get("stable_peer", {}).get("selection_sha256") == STABLE_SELECTION_SHA256, "Not a stable-peer manifest")
        inputs = []
        for row in doc["events"]:
            contract = m["tensor_contracts"][row["event_id"]]
            require(row["graph_sha256"] not in primary_hashes, f"{row['event_id']}: primary tensor bytes in the stable gate")
            require(contract.get("history_source_digest") == stable_library_digest,
                    f"{row['event_id']}: tensor library is not the stable library")
            require(contract.get("manifest_sha256") == doc["source_manifest_sha256"],
                    f"{row['event_id']}: tensor/manifest digest mismatch")
            require(not contract.get("history_intervention"), f"{row['event_id']}: crossed with a history intervention")
            inputs.append({"event_id": row["event_id"], "path": row["graph_path"], "sha256": row["graph_sha256"],
                           "forecast_contract": contract})
        entries.append({"path": str(m["path"]), "sha256": m["sha256"], "delta_s": m["delta_s"],
                        "source_manifest_sha256": doc["source_manifest_sha256"],
                        "abstentions_sha256": canonical_sha(doc["stable_peer"]["abstentions"]), "inputs": inputs})
    require(sorted(e["delta_s"] for e in entries) == list(HORIZONS_S), "One stable manifest per horizon (30 s, 60 s)")
    return {"kind": GATE_KIND, "passed": True, "sensitivity": sensitivity(), "code_sha256": code_sha256,
            "primary_gate_sha256": primary_gate.get("_sha256"), "stable_library_digest": stable_library_digest,
            "training_authorized": False, "prediction_authorized": False, "test_scoring_authorized": False,
            "fit_authority": "none", "manifests": entries}


def r1_target_linkage(*, stage_receipt, stage_receipt_sha256, audit, audit_sha256, gate_sha256, manifests,
                      commitment_index_sha256=None, gate=None):
    """Hash-bound record the R1 retention spec and verify-before-join barrier need (decision 6). No scores.

    ``manifests``: {delta_s: (doc, sha256)}. The scorer must read targets only from the gated stable tensors and
    must refuse any ordinary full-panel target for R-stable.
    """
    require(stage_receipt.get("kind") == STAGE_KIND and stage_receipt.get("passed") is True, "Stable data root not passed")
    require(audit.get("passed") is True and audit.get("stage_receipt_sha256") == stage_receipt_sha256,
            "Independent stable audit has not passed for this data root")
    require(set(manifests) == set(HORIZONS_S), "Linkage requires both horizons")
    require(gate is not None and gate.get("kind") == GATE_KIND and gate.get("passed") is True,
            "Linkage needs the passed stable gate")
    require({m["delta_s"]: m["sha256"] for m in gate["manifests"]} == {d: v[1] for d, v in manifests.items()}
            and len(gate["manifests"]) == 2, "Linkage gate manifests differ")
    audited = audit.get("audited_event_ids")
    require(isinstance(audited, list) and len(audited) == len(set(audited))
            and ids_sha256(audited) == audit.get("event_ids_sha256"), "Audit needs exact covered IDs")
    population = {}
    for delta, (doc, digest) in sorted(manifests.items()):
        block = doc["stable_peer"]
        require(block["stage_receipt_sha256"] == stage_receipt_sha256, "Manifest bound to another data root")
        built = sorted(r["event_id"] for r in doc["events"] if r["split"] == "test")
        abstained = sorted(e for e, v in block["abstentions"].items() if v["split"] == "test")
        require(set(built) | set(abstained) <= set(audited), "Audit omits test IDs or abstentions")
        population[str(delta)] = {"manifest_sha256": digest, "test_built_ids_sha256": ids_sha256(built),
                                  "abstention_ids_sha256": ids_sha256(abstained),
                                  "population_ids_sha256": block["population_ids_sha256"]}
    return {"kind": LINKAGE_KIND, "sensitivity": sensitivity(), "stage_receipt_sha256": stage_receipt_sha256,
            "stable_target_source": {"data_root": stage_receipt["output_root"],
                                     "event_tables_sha256": stage_receipt["event_tables_sha256"],
                                     "membership_digest": stage_receipt["membership_digest"]},
            "independent_audit_sha256": audit_sha256, "input_gate_sha256": gate_sha256, "population": population,
            "prediction_commitment_index_sha256": commitment_index_sha256,
            "scoring_rule": {"target": "stable-peer target in the gated stable tensors only",
                             "full_panel_target_substitution": "forbidden",
                             "abstention": "empty prediction, count 0, kept in the denominator",
                             "secondary": "restrict to IDs with stable input",
                             "issue_clock": "primary onset + delta", "horizon_s": TARGET_HORIZON_S},
            "scores_computed": False}


def newperiod_recipe(*, core_recipe_sha256, code_sha256):
    """N-stable: the same frozen selection and rules inside new-period custody, executed only after R1."""
    return {"kind": RECIPE_KIND, "sensitivity": sensitivity(), "selection_file_sha256": STABLE_SELECTION_FILE_SHA256,
            "newperiod_core_recipe_sha256": core_recipe_sha256, "code_sha256": code_sha256,
            "rules": {"identity": "(collector, canonical peer IP, peer ASN), IPv4-mapped refused",
                      "rows": "pure row filter, order and duplicate occurrences kept",
                      "membership": "extent.membership with the recorded delay clock; no pre-repair prefix source "
                                    "exists for new-period events unless custody records one",
                      "clock": "primary new-period onset + delta, primary two-hour boundary",
                      "abstention": "zero stable seeds at issue time, complete coverage only",
                      "library": "the new-period original observed history library rebuilt from the same peers",
                      "coverage": "incomplete coverage with no stable rows is a source failure (seam S3)"},
            "models": {"learned": ["sage_on", "none_on"], "seeds": [0, 1, 2, 3, 4], "horizons_s": list(HORIZONS_S),
                       "baselines": ["persistence", "online_history"], "fits": 0},
            "execution": "after R1, inside new-period custody, after the sealed snapshot; not before",
            "executed": False}
