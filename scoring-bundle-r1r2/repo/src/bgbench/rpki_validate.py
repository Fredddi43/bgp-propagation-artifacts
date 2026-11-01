"""RFC 6811 origin validation against the RIPE daily ROA archive (rpki/roas/<day>.parquet). Shared by the validity scripts."""
from __future__ import annotations

import datetime as dt
import ipaddress
from collections import defaultdict

import polars as pl

from . import config

_roa_cache: dict[str, dict | None] = {}


def roas_for(day: str):
    """ROA table {prefix: [(max_len, asn)]} for a day, or the nearest earlier day within a week; None if no archive. One day cached."""
    if day in _roa_cache:
        return _roa_cache[day]
    _roa_cache.clear()
    f = config.DATA_ROOT / "rpki" / "roas" / f"{day}.parquet"
    if not f.exists():
        d0 = dt.date.fromisoformat(day)
        for k in range(1, 8):
            g = config.DATA_ROOT / "rpki" / "roas" / f"{(d0 - dt.timedelta(days=k)).isoformat()}.parquet"
            if g.exists():
                f = g
                break
        else:
            _roa_cache[day] = None
            return None
    tab = defaultdict(list)
    for p, ml, a in pl.read_parquet(f).select("prefix", "max_len", "asn").iter_rows():
        tab[p].append((int(ml), int(a)))
    _roa_cache[day] = tab
    return tab


def validity(prefix: str, origin: int, tab) -> tuple[str, int, str]:
    """(state, n_covering, reason): valid | invalid | unknown; reason invalid_length (a ROA names the origin but its maxLength
    is shorter) vs invalid_asn (no ROA names the origin)."""
    net = ipaddress.ip_network(prefix, strict=False)
    covering = 0
    valid = False
    asn_match_too_long = False
    # RFC 6811 section 2: coverage is prefix containment, independent of
    # maxLength. A covered but too-specific announcement is Invalid, not
    # NotFound. Include /0; there is no family-specific minimum ROA length.
    for plen in range(net.prefixlen, -1, -1):
        sup = net if plen == net.prefixlen else net.supernet(new_prefix=plen)
        for ml, a in tab.get(str(sup), ()):
            covering += 1
            if net.prefixlen <= ml:
                if a == origin and a != 0:
                    valid = True
            elif a == origin:
                asn_match_too_long = True
    state = "valid" if valid else ("invalid" if covering else "unknown")
    reason = "" if state != "invalid" else ("invalid_length" if asn_match_too_long else "invalid_asn")
    return state, covering, reason


def validate_day(task: tuple[str, list[dict]]) -> list[dict]:
    """Process-pool worker: load one historical ROA snapshot for all day's events."""
    day, events = task
    tab = roas_for(day)
    out = []
    for event in events:
        if tab is None:
            state, count, reason, previous = "no_roa_data", 0, "", "no_roa_data"
        else:
            state, count, reason = validity(event["prefix"], int(event["new_origin"]), tab)
            previous = (validity(event["prefix"], int(event["prev_origin"]), tab)[0]
                        if event["prev_origin"] is not None else "unknown_prev")
        out.append({"event_id": event["event_id"], "validity": state, "n_covering": count,
                    "invalid_reason": reason, "prev_validity": previous, "split": event["split"]})
    return out
