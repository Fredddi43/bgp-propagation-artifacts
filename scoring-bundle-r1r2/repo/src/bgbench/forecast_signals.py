"""Causal candidate signals from continuous announcements and withdrawals.

This is a deterministic development trigger, not an attack classifier. It keeps
active per-session origin state and a warm-up edge dictionary. First observations
of a prefix are not origin changes; withdrawals erase active origin state. An
unseen directed edge becomes eligible only when first observed after warm-up.
Collector agreement is emitted at the threshold-crossing clock, never backdated.
"""
from __future__ import annotations

from collections import Counter

from .forecast_protocol import utc
from .forecast_trigger import CollectorAgreement, TriggerConfig


def simple_path(value):
    """Reject ambiguous AS sets; remove only adjacent prepending duplicates."""
    if value is None or any(c in str(value) for c in "{}(),"):
        return None
    try:
        asns = [int(x) for x in str(value).split()]
    except ValueError:
        return None
    if not asns or any(a < 1 or a >= 2**32 for a in asns):
        return None
    return tuple(a for i, a in enumerate(asns) if i == 0 or asns[i - 1] != a)


class CausalPathSignals:
    def __init__(self, *, evaluation_start, config=TriggerConfig()):
        self.start = utc(evaluation_start)
        self.config = config
        self.agreement = CollectorAgreement(config)
        self.active_origin = {}
        self.edge_first = {}
        self.last_clock = None
        self.counts = Counter()

    def push(self, row):
        observed = utc(row["ts"])
        available = utc(row["arrival_at"]) if self.config.clock == "arrival_time" else observed
        if available < observed or (self.last_clock is not None and available < self.last_clock):
            raise ValueError("Raw stream must be ordered by valid availability timestamps")
        self.last_clock = available
        self.counts["raw_messages"] += 1
        collector, peer, prefix = str(row["collector"]), str(row["peer_ip"]), str(row["prefix"])
        # peer_asn is part of session identity: ASN reassignment cannot inherit
        # an earlier peer's active route merely because its address is reused.
        session_key = collector, peer, int(row["peer_asn"]), prefix
        kind = str(row["elem_type"]).upper()
        if kind in ("W", "WITHDRAWAL"):
            self.active_origin.pop(session_key, None)
            self.counts["withdrawals"] += 1
            return []
        if kind not in ("A", "ANNOUNCEMENT"):
            self.counts["unsupported_message_type"] += 1
            return []
        path = simple_path(row.get("as_path"))
        if path is None:
            # An ambiguous announcement replaces the active route, so keeping
            # the preceding known origin would manufacture a later transition.
            self.active_origin.pop(session_key, None)
            self.counts["ambiguous_or_missing_path"] += 1
            return []
        previous = self.active_origin.get(session_key)
        self.active_origin[session_key] = path[-1]
        signals = []
        base = {"collector": collector, "observed_at": observed,
                **({"arrival_at": available} if self.config.clock == "arrival_time" else {})}
        if previous is not None and previous != path[-1] and available >= self.start:
            signals.append({**base, "kind": "origin_change", "prefix": prefix,
                            "new_origin": path[-1]})
        for a, b in set(zip(path, path[1:])):
            first = self.edge_first.setdefault((a, b), available)
            if first >= self.start and (available - first).total_seconds() <= self.config.agreement_window_s:
                signals.append({**base, "kind": "edge_candidate", "a": a, "b": b})
        emitted = []
        for signal in sorted(signals, key=lambda s: (s["kind"], str(s))):
            self.counts[signal["kind"] + "_signals"] += 1
            event = self.agreement.push(signal)
            if event:
                emitted.append(event)
                self.counts[event["kind"] + "_triggers"] += 1
        return emitted

    def reset_peer(self, collector, peer_ip, peer_asn):
        """Explicit session reset when the transport supplies one; never infer it."""
        key = str(collector), str(peer_ip), int(peer_asn)
        for entry in [k for k in self.active_origin if k[:3] == key]:
            del self.active_origin[entry]
        self.counts["explicit_peer_resets"] += 1
