"""One causal, graph-independent history library for forecasting experiments.

Forecasting consumers use ``snapshot`` to retrieve historical labels. Availability
is the later of the two-hour target boundary and recorded label-availability time.
The library scope is explicit; graph eligibility and train/test membership never
determine whether a completed event is part of history.

This in-process loader owns source labels and is for retrospective/custodian
processing. A protected evaluation must expose only matured snapshots through
the custodian boundary, never hand this entire object to model developers.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import polars as pl

from .forecast_protocol import available_at_expr, check_timestamp_precision

HISTORY_VERSION = 3
HISTORY_FEATURE_INDICES = (10,)
# First signature offset, in seconds after onset (DECISION-LOG.md, 2026-10-18 protocol revision). It was 0 s. Under
# the whole-second availability rule a RIS record stamped at onset becomes available at onset + 1 s, so an s = 0
# count was zero for every RIS onset and nonzero for every RouteViews onset: it encoded the onset collector type.
# 1 s is the first instant at which both collector types can contribute.
SIGNATURE_FIRST_OFFSET_S = 1


def signature_offsets(delta_s: float) -> tuple[float, float, float]:
    """The three onset-relative instants (seconds) at which the history signature counts available members."""
    return (SIGNATURE_FIRST_OFFSET_S, delta_s / 2, delta_s)


def utc(value) -> datetime:
    value = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if not isinstance(value, datetime):
        raise ValueError(f"Expected an event timestamp, got {value!r}")
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


@dataclass(frozen=True)
class HistoryEvent:
    event_id: str
    onset: datetime
    available_at: datetime
    target_asns: frozenset[int]
    # Canonical first membership times, pooled only within the declared panel.
    first_seen: tuple[tuple[int, datetime], ...]
    # Input availability times (forecast_protocol.available_at per collector, then pooled). The
    # signature is an issue-time input, so it counts members by availability; None = raw first_seen.
    first_available: tuple[tuple[int, datetime], ...] | None = None
    _signature_cache: dict = field(default_factory=dict, compare=False, hash=False, repr=False)

    def signature(self, delta_s: float) -> np.ndarray:
        """Candidate-independent onset signature, including nongraph events."""
        if delta_s in self._signature_cache:
            return self._signature_cache[delta_s]
        times = self.first_seen if self.first_available is None else self.first_available
        counts = [sum(t <= self.onset + timedelta(seconds=s) for _, t in times)
                  for s in signature_offsets(delta_s)]
        result = np.log1p(np.asarray(counts, dtype=np.float64))
        result.flags.writeable = False
        self._signature_cache[delta_s] = result
        return result


@dataclass(frozen=True)
class HistorySnapshot:
    events: tuple[HistoryEvent, ...]
    participation: dict[int, int]
    provenance: dict


class CompletedEventLibrary:
    def __init__(self, events, *, family: str, collectors: tuple[str, ...] | None = None, sources=(),
                 signature_collectors=None, target_collectors=None):
        events = tuple(events)
        if len({e.event_id for e in events}) != len(events):
            raise ValueError("Duplicate event IDs in history library")
        if any(e.available_at < e.onset + timedelta(seconds=7200) for e in events):
            raise ValueError("History labels cannot mature before the two-hour boundary")
        self.events = tuple(sorted(events, key=lambda e: (e.available_at, e.event_id)))
        self.by_id = {e.event_id: e for e in events}
        self.sources = list(sources)
        self.scope = {"version": HISTORY_VERSION, "family": family,
                      "collectors": sorted(collectors) if collectors is not None else "pooled",
                      "target_horizon_seconds": 7200}
        if signature_collectors is not None or target_collectors is not None:
            self.scope.update(collectors="separate_signature_and_target_panels",
                              signature_collectors=sorted(signature_collectors) if signature_collectors is not None else "pooled",
                              target_collectors=sorted(target_collectors) if target_collectors is not None else "pooled",
                              history_service="common_reference_labels_after_maturity",
                              event_universe="all_successful_reference_family_events")
        records_digest = hashlib.sha256()
        for event in sorted(events, key=lambda e: e.event_id):
            records_digest.update(json.dumps([event.event_id, event.onset.isoformat(), event.available_at.isoformat(),
                                              sorted(event.target_asns),
                                              [(a, t.isoformat()) for a, t in event.first_seen],
                                              *([[(a, t.isoformat()) for a, t in event.first_available]]
                                                if event.first_available is not None else [])], sort_keys=True).encode())
        self.digest = hashlib.sha256(json.dumps({**self.scope, "sources": self.sources,
                                                "records_sha256": records_digest.hexdigest()}, sort_keys=True).encode()).hexdigest()
        self._available = 0
        self._counts = Counter()

    def snapshot(self, issue_time, *, exclude_event_id=None, frozen_at=None) -> HistorySnapshot:
        cutoff = min(utc(issue_time), utc(frozen_at)) if frozen_at is not None else utc(issue_time)
        # Monotone issue-time iteration is linear in historical memberships;
        # out-of-order callers are safe and reset the incremental accumulator.
        if self._available and self.events[self._available - 1].available_at > cutoff:
            self._available, self._counts = 0, Counter()
        while self._available < len(self.events) and self.events[self._available].available_at <= cutoff:
            self._counts.update(self.events[self._available].target_asns)
            self._available += 1
        events = tuple(e for e in self.events[:self._available] if e.event_id != exclude_event_id)
        counts = self._counts.copy()
        excluded = self.by_id.get(exclude_event_id)
        if excluded is not None and excluded.available_at <= cutoff:
            counts.subtract(excluded.target_asns)
        counts = {a: n for a, n in counts.items() if n > 0}
        ids_hash = hashlib.sha256("\n".join(e.event_id for e in events).encode()).hexdigest()
        provenance = {**self.scope, "source_digest": self.digest,
                      "issue_time": utc(issue_time).isoformat(), "availability_cutoff": cutoff.isoformat(),
                      "library_events": len(events), "library_event_ids_sha256": ids_hash,
                      "excluded_event_id": exclude_event_id}
        return HistorySnapshot(events, counts, provenance)

    @classmethod
    def from_eventsets(cls, data_root: Path, years, family: str, *, collectors=None, availability_delay_s: float = 0,
                       signature_collectors=None, target_collectors=None):
        """Load every successful family event, irrespective of size or graph support.

        Missing membership is an error, never a silent reduction of history.
        Missing years likewise fail rather than imply an empty earlier library.
        """
        panel = tuple(sorted(set(collectors))) if collectors is not None else None
        separate_panels = signature_collectors is not None or target_collectors is not None
        if separate_panels and collectors is not None:
            raise ValueError("Use legacy collectors or separate signature/target panels, not both")
        signature_panel = tuple(sorted(set(signature_collectors))) if signature_collectors is not None else panel
        target_panel = tuple(sorted(set(target_collectors))) if target_collectors is not None else panel
        if panel == ():
            raise ValueError("An explicit collector panel must not be empty")
        if signature_panel == () or target_panel == ():
            raise ValueError("Explicit signature/target panels must not be empty")
        if availability_delay_s < 0:
            raise ValueError("Availability delay must be nonnegative")
        events, sources = [], [{"availability_delay_s": availability_delay_s}]
        replay_root = data_root / (f"events_replay_{family}" if family else "events_replay")
        for year in sorted(set(map(int, years))):
            path = data_root / "eventset" / (f"{year}_{family}" if family else str(year)) / "events.parquet"
            sources.append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
            table = pl.read_parquet(path).filter(pl.col("error").is_null())
            for row in table.iter_rows(named=True):
                if row.get("t0_obs") is None:
                    raise ValueError(f"Successful history event has no onset: {row['event_id']}")
                onset = utc(row["t0_obs"])
                member_path = replay_root / row["event_id"] / "membership.parquet"
                raw_members = pl.read_parquet(member_path)
                members = raw_members.filter(pl.col("collector").is_in(signature_panel)) if signature_panel is not None else raw_members
                check_timestamp_precision(members, ts_column="first_seen")
                members = (members.with_columns(available=available_at_expr("first_seen"))
                           .group_by("asn").agg(first=pl.col("first_seen").min(), available=pl.col("available").min()))
                ready = tuple(sorted((int(a), utc(t)) for a, t in members.select("asn", "available").iter_rows()))
                members = members.select("asn", "first")
                if target_panel == signature_panel:
                    target_members = members
                else:
                    target_members = raw_members.filter(pl.col("collector").is_in(target_panel)) if target_panel is not None else raw_members
                    target_members = target_members.group_by("asn").agg(first=pl.col("first_seen").min())
                first = tuple(sorted((int(a), utc(t)) for a, t in members.iter_rows()))
                boundary = onset + timedelta(seconds=7200)
                # A collector-only system cannot learn the identity/zero size
                # of an event it never observed anywhere in its target window.
                if not separate_panels and panel is not None and not any(t <= boundary for _, t in first):
                    continue
                available = max(boundary, utc(row["label_available_at"])) if row.get("label_available_at") else boundary + timedelta(seconds=availability_delay_s)
                events.append(HistoryEvent(str(row["event_id"]), onset, available,
                                           frozenset(int(a) for a, t in target_members.iter_rows() if utc(t) <= boundary), first,
                                           ready))
                sources.append({"path": str(member_path), "sha256": hashlib.sha256(member_path.read_bytes()).hexdigest()})
        return cls(events, family=family, collectors=panel, sources=sources,
                   signature_collectors=signature_panel if separate_panels else None,
                   target_collectors=target_panel if separate_panels else None)


def history_issue_time(event: dict, library: CompletedEventLibrary, cutoff_s: float) -> datetime:
    """Issue time of a history arm's query event (TARGET-CONSISTENCY-POLICY.md v6).

    Single root (the graph provenance names no ``history_root``): the library's own record of the
    event, onset + cutoff, exactly as before. Split root: the library holds the history root's
    original observed record, whose onset can differ from the data-root event the graph was built
    from, so the issue time is the graph's provenance issue time, which the builder took from the
    data root and the gated loader checks against the manifest onset.
    """
    provenance = event.get("history_provenance") or {}
    if provenance.get("history_root") is None:
        return library.by_id[event["event_id"]].onset + timedelta(seconds=cutoff_s)
    if not provenance.get("issue_time"):
        raise ValueError(f"Split-root history query has no recorded issue time: {event['event_id']}")
    return utc(provenance["issue_time"])


def history_query(event: dict, library: CompletedEventLibrary, cutoff_s: float):
    """``(issue_time, own signature, history_root or None)`` of a history arm's query event.

    Single root: both from the library's record of the event (unchanged behaviour). Split root: the
    library supplies only neighbours and participation; the event's own issue-time signature is the
    graph's ``history_signature``, which the builder computed from the data root.
    """
    issue_time = history_issue_time(event, library, cutoff_s)
    root = (event.get("history_provenance") or {}).get("history_root")
    if root is None:
        return issue_time, library.by_id[event["event_id"]].signature(cutoff_s), None
    if event.get("history_signature") is None:
        raise ValueError(f"Split-root history query needs the graph's own issue-time signature: {event['event_id']}")
    signature = np.asarray(event["history_signature"], dtype=np.float64)
    if signature.shape != (3,) or not np.isfinite(signature).all():
        raise ValueError(f"Invalid graph issue-time signature: {event['event_id']}")
    return issue_time, signature, str(root)


def graph_history_provenance(snapshot: HistorySnapshot, event: dict) -> dict:
    """The history provenance the graph ``event`` must record when it was built against ``snapshot``.

    Single root: exactly ``snapshot.provenance``. Split root: the builder (tgn_data.build_split) adds the
    history root and ``signature_source_digest``, the digest of the data-root library that supplied the
    event's own issue-time signature. That digest must be present and, where the graph's forecast
    contract is at hand, equal to the contract's.
    """
    provenance = event.get("history_provenance") or {}
    root = provenance.get("history_root")
    if root is None:
        return snapshot.provenance
    digest = provenance.get("signature_source_digest")
    if not isinstance(digest, str) or not digest:
        raise ValueError(f"Split-root graph records no signature source digest: {event['event_id']}")
    contract = event.get("forecast_contract")
    if isinstance(contract, dict) and contract.get("signature_source_digest") != digest:
        raise ValueError(f"Graph signature source digest differs from its forecast contract: {event['event_id']}")
    return {**snapshot.provenance, "history_root": str(root), "signature_source_digest": digest}


HISTORY_SIZE_STATISTICS = ("mean", "median")


def issue_time_slice_variables(history_signature, seed_asns) -> dict:
    """The two declared issue-time slice variables of one event (PRIMARY-METRIC-REVISION.md §4.1).

    ``history_signature`` is the event's own issue-time signature, log1p of the members
    available by ``signature_offsets(delta)`` (1 s, delta/2, delta; graphs built before the
    2026-10-18 revision stored 0 s as the first point). Only the last two points are read here,
    so both generations give the same variables. Early growth is the count added in the second half of
    the observation window; seeds at issue is the number of distinct input seeds at delta.
    """
    counts = np.rint(np.expm1(np.asarray(history_signature, dtype=np.float64))).astype(np.int64)
    if counts.shape != (3,):
        raise ValueError("Issue-time signature must have three points")
    return {"early_growth": int(counts[2] - counts[1]), "seeds_at_issue": len(set(map(int, seed_asns)))}


def in_issue_time_slice(rule: dict, variables: dict) -> bool:
    """Membership under a frozen slice rule ``{"variable", "cut"}``."""
    if rule.get("variable") not in ("early_growth", "seeds_at_issue") or not isinstance(rule.get("cut"), int):
        raise ValueError("Slice rule needs a declared variable and an integer cut")
    return variables[rule["variable"]] >= rule["cut"]


def predict_history(snapshot: HistorySnapshot, signature: np.ndarray, candidate_asns,
                    seed_asns, *, delta_s: float, k: int = 20, size: str = "mean", return_scores: bool = False):
    """KNN extent and global participation ranking from exactly one snapshot.

    ``size`` is the extent statistic over the k nearest past events: ``mean`` is the declared
    baseline (unchanged behaviour); ``median`` is the separately pre-registered
    history-kNN-median arm (PRIMARY-METRIC-REVISION.md §4.3). With ``return_scores`` a third
    value is returned: the issue-time participation count of every non-seed candidate, which is
    the ranking score itself (ties are left to the evaluator, never broken by ASN).
    """
    if k < 1:
        raise ValueError("k must be positive")
    if size not in HISTORY_SIZE_STATISTICS:
        raise ValueError(f"History extent statistic must be one of {HISTORY_SIZE_STATISTICS}")
    statistic = np.mean if size == "mean" else np.median
    seeds = set(map(int, seed_asns))
    if snapshot.events:
        signatures = np.stack([e.signature(delta_s) for e in snapshot.events])
        scale = signatures.std(axis=0) + 1e-9
        nearest = np.argsort(np.square((signatures - signature) / scale).sum(axis=1), kind="stable")[:k]
        extent = max(float(len(seeds)), float(statistic([len(snapshot.events[i].target_asns) for i in nearest])))
    else:
        extent = float(len(seeds))
    candidates = set(map(int, candidate_asns)) - seeds
    ranked = sorted(candidates, key=lambda a: (-snapshot.participation.get(a, 0), a))
    prediction = seeds | set(ranked[:max(0, round(extent - len(seeds)))])
    if return_scores:
        return prediction, extent, {a: int(snapshot.participation.get(a, 0)) for a in ranked}
    return prediction, extent
