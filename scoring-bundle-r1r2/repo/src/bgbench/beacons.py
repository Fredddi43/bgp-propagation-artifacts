"""RIS Routing Beacons (AS12654) — registry for the post-2024-02-01 set and the AGGREGATOR decoder.

Source: docs/research/2026-09-03-slice-candidates-and-beacons.md §2 (fetched from RIPE, 2026-09-03).
Schedule (standard beacons): announce 00/04/08/12/16/20 UTC, withdraw 02/06/10/14/18/22 UTC.
Fast-paced beacon (RRC03 only): announce XX:00/:20/:40, withdraw XX:10/:30/:50.
Every beacon announcement carries AGGREGATOR = (64512 + announcement_id<<k | seq, 10.x.y.z) where
x.y.z is a 24-bit big-endian count of seconds since midnight UTC on the 1st of the month.
Anchors are permanent and carry no tag. ⚠️ Before 2024-02-01 the set, the anycast roles and the
IPv6 tagging were different — do not apply this registry to 2023 data.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

BEACON_ORIGIN_ASN = 12654
REBUILT_ON = datetime(2024, 2, 1, tzinfo=UTC)


@dataclass(frozen=True)
class Beacon:
    prefix: str
    kind: str  # "beacon" | "anchor" | "fast" | "rpki_valid" | "rpki_invalid" | "rpki_unknown" | "longprefix"
    setup: str  # "rrcNN" for per-RRC pairs; "multihop"/"ripe"/"apnic"/"arin"/"lacnic"/"afrinic"; "rrc03-fast"; "rpki"; "longprefix"
    origin_rrcs: tuple[str, ...]
    announcement_ids: tuple[int, ...]  # parallel to origin_rrcs; 0 where not meaningful
    family: int  # 4 | 6


def _pairs(rrc: str, v6b: str, v4b: str | None, v6a: str, v4a: str | None) -> list[Beacon]:
    out = [Beacon(v6b, "beacon", rrc, (rrc,), (0,), 6), Beacon(v6a, "anchor", rrc, (rrc,), (0,), 6)]
    if v4b:
        out.append(Beacon(v4b, "beacon", rrc, (rrc,), (0,), 4))
    if v4a:
        out.append(Beacon(v4a, "anchor", rrc, (rrc,), (0,), 4))
    return out


_PER_RRC = [
    ("rrc00", "2001:7fb:fe00::/48", None, "2001:7fb:ff00::/48", None),
    ("rrc01", "2001:7fb:fe01::/48", "84.205.65.0/24", "2001:7fb:ff01::/48", "84.205.81.0/24"),
    ("rrc03", "2001:7fb:fe03::/48", "84.205.67.0/24", "2001:7fb:ff03::/48", "84.205.83.0/24"),
    ("rrc04", "2001:7fb:fe04::/48", None, "2001:7fb:ff04::/48", None),
    ("rrc05", "2001:7fb:fe05::/48", None, "2001:7fb:ff05::/48", None),
    ("rrc06", "2001:7fb:fe06::/48", None, "2001:7fb:ff06::/48", None),
    ("rrc07", "2001:7fb:fe07::/48", None, "2001:7fb:ff07::/48", None),
    ("rrc10", "2001:7fb:fe0a::/48", None, "2001:7fb:ff0a::/48", None),
    ("rrc11", "2001:7fb:fe0b::/48", None, "2001:7fb:ff0b::/48", None),
    ("rrc12", "2001:7fb:fe0c::/48", "84.205.76.0/24", "2001:7fb:ff0c::/48", "84.205.92.0/24"),
    ("rrc13", "2001:7fb:fe0d::/48", None, "2001:7fb:ff0d::/48", None),
    ("rrc14", "2001:7fb:fe0e::/48", None, "2001:7fb:ff0e::/48", None),
    ("rrc15", "2001:7fb:fe0f::/48", None, "2001:7fb:ff0f::/48", None),
    ("rrc16", "2001:7fb:fe10::/48", None, "2001:7fb:ff10::/48", None),
    ("rrc18", "2001:7fb:fe12::/48", None, "2001:7fb:ff12::/48", None),
    ("rrc19", "2001:7fb:fe13::/48", None, "2001:7fb:ff13::/48", None),
    ("rrc20", "2001:7fb:fe14::/48", None, "2001:7fb:ff14::/48", None),
    ("rrc21", "2001:7fb:fe15::/48", None, "2001:7fb:ff15::/48", None),
    ("rrc22", "2001:7fb:fe16::/48", None, "2001:7fb:ff16::/48", None),
    ("rrc23", "2001:7fb:fe17::/48", None, "2001:7fb:ff17::/48", None),
    ("rrc24", "2001:7fb:fe18::/48", None, "2001:7fb:ff18::/48", None),
    ("rrc25", "2001:7fb:fe20::/48", None, "2001:7fb:ff20::/48", None),
    ("rrc26", "2001:7fb:fe19::/48", None, "2001:7fb:ff19::/48", None),
]

_ANYCAST = [  # (setup, v6 beacon, v4 beacon, v6 anchor, v4 anchor, ((rrc, id), ...))
    (
        "multihop",
        "2001:7fb:ee00::/48",
        "84.205.64.0/24",
        "2001:7fb:ef00::/48",
        "84.205.80.0/24",
        (("rrc00", 0), ("rrc25", 1)),
    ),
    (
        "ripe",
        "2001:7fb:ee01::/48",
        "84.205.69.0/24",
        "2001:7fb:ef01::/48",
        "84.205.85.0/24",
        (
            ("rrc04", 0),
            ("rrc05", 1),
            ("rrc07", 2),
            ("rrc10", 3),
            ("rrc13", 4),
            ("rrc18", 5),
            ("rrc20", 6),
            ("rrc21", 7),
            ("rrc22", 8),
            ("rrc26", 9),
        ),
    ),
    (
        "apnic",
        "2001:7fb:ee02::/48",
        "84.205.70.0/24",
        "2001:7fb:ef02::/48",
        "84.205.86.0/24",
        (("rrc06", 0), ("rrc23", 1)),
    ),
    (
        "arin",
        "2001:7fb:ee03::/48",
        "84.205.75.0/24",
        "2001:7fb:ef03::/48",
        "84.205.91.0/24",
        (("rrc11", 0), ("rrc14", 1), ("rrc16", 2)),
    ),
    (
        "lacnic",
        "2001:7fb:ee04::/48",
        "93.175.153.0/24",
        "2001:7fb:ef04::/48",
        "93.175.152.0/24",
        (("rrc15", 0), ("rrc24", 1)),
    ),
    (
        "afrinic",
        "2001:7fb:ee05::/48",
        "84.205.82.0/24",
        "2001:7fb:ef05::/48",
        "84.205.88.0/24",
        (("rrc19", 0),),
    ),
]


def registry() -> list[Beacon]:
    out: list[Beacon] = []
    for r in _PER_RRC:
        out += _pairs(*r)
    for setup, v6b, v4b, v6a, v4a, ids in _ANYCAST:
        rrcs = tuple(r for r, _ in ids)
        aids = tuple(i for _, i in ids)
        out += [
            Beacon(v6b, "beacon", setup, rrcs, aids, 6),
            Beacon(v4b, "beacon", setup, rrcs, aids, 4),
            Beacon(v6a, "anchor", setup, rrcs, aids, 6),
            Beacon(v4a, "anchor", setup, rrcs, aids, 4),
        ]
    out += [
        Beacon("2001:7fb:ff02::/48", "fast", "rrc03-fast", ("rrc03",), (0,), 6),
        Beacon("84.205.66.0/24", "fast", "rrc03-fast", ("rrc03",), (0,), 4),
        Beacon("2001:7fb:fd02::/48", "rpki_valid", "rpki", ("rrc03",), (0,), 6),
        Beacon("93.175.146.0/24", "rpki_valid", "rpki", ("rrc03",), (0,), 4),
        Beacon("2001:7fb:fd03::/48", "rpki_invalid", "rpki", ("rrc03",), (0,), 6),
        Beacon("93.175.147.0/24", "rpki_invalid", "rpki", ("rrc03",), (0,), 4),
        # rpki_unknown == the rrc03 anchor pair (already listed as anchors)
        Beacon(
            "2001:7fb:fb01:100::/56",
            "longprefix",
            "longprefix",
            ("rrc04", "rrc06", "rrc11", "rrc15", "rrc19"),
            (0, 1, 2, 3, 4),
            6,
        ),
        Beacon(
            "93.175.154.0/25",
            "longprefix",
            "longprefix",
            ("rrc04", "rrc06", "rrc11", "rrc15", "rrc19"),
            (0, 1, 2, 3, 4),
            4,
        ),
        Beacon(
            "2001:7fb:fb01:200::/64",
            "longprefix",
            "longprefix",
            ("rrc04", "rrc06", "rrc11", "rrc15", "rrc19"),
            (0, 1, 2, 3, 4),
            6,
        ),
        Beacon(
            "93.175.154.128/28",
            "longprefix",
            "longprefix",
            ("rrc04", "rrc06", "rrc11", "rrc15", "rrc19"),
            (0, 1, 2, 3, 4),
            4,
        ),
    ]
    return out


BY_PREFIX: dict[str, Beacon] = {b.prefix: b for b in registry()}
BEACON_PREFIXES: frozenset[str] = frozenset(BY_PREFIX)
SCHEDULED_PREFIXES: frozenset[str] = frozenset(
    b.prefix for b in registry() if b.kind in ("beacon", "fast")
)


def decode_aggregator(
    aggr_asn: int | None, aggr_ip: str | None, ts: datetime
) -> tuple[datetime | None, int | None]:
    """Return (origination_time_utc, raw_10bit_field) from a beacon's AGGREGATOR attribute, or (None, None).

    ts is the observation time; it selects the month the 24-bit second counter is relative to.
    Observation lag can straddle a month boundary in the first seconds of a month: if the decoded
    time would be > 1 h in the future, decode against the previous month instead.
    """
    if aggr_ip is None or aggr_asn is None or not (64512 <= aggr_asn < 64512 + 1024):
        return None, None
    try:
        ip = ipaddress.ip_address(aggr_ip)
    except ValueError:
        return None, None
    if ip.version != 4 or ip.packed[0] != 10:
        return None, None
    x, y, z = ip.packed[1], ip.packed[2], ip.packed[3]
    secs = (x << 16) | (y << 8) | z
    month_start = ts.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    orig = month_start + timedelta(seconds=secs)
    if orig > ts + timedelta(hours=1):
        prev = (month_start - timedelta(days=1)).replace(day=1)
        orig = prev + timedelta(seconds=secs)
    return orig, aggr_asn - 64512


def scheduled_withdraw_after(announce_slot: datetime, kind: str) -> datetime:
    """Scheduled withdrawal instant for the cycle that began at announce_slot."""
    return announce_slot + (timedelta(minutes=10) if kind == "fast" else timedelta(hours=2))


def announce_slot_for(ts: datetime, kind: str) -> datetime:
    """The scheduled announcement instant of the cycle containing observation ts."""
    if kind == "fast":
        m = (ts.minute // 20) * 20
        return ts.replace(minute=m, second=0, microsecond=0)
    h = (ts.hour // 4) * 4
    return ts.replace(hour=h, minute=0, second=0, microsecond=0)


def withdraw_slot_for(ts: datetime, kind: str) -> datetime:
    """The scheduled withdrawal instant at or before observation ts (withdraw phase of the cycle).
    Withdrawal messages (incl. path-hunting stragglers) are attributed to this instant, and the cycle
    they belong to is the announce slot 2 h (or 10 min) earlier."""
    if kind == "fast":
        m = ((ts.minute - 10) // 20) * 20 + 10
        base = ts.replace(minute=0, second=0, microsecond=0)
        return base + timedelta(minutes=m) if m >= 0 else base - timedelta(minutes=10)
    h = ((ts.hour - 2) // 4) * 4 + 2
    base = ts.replace(hour=0, minute=0, second=0, microsecond=0)
    return base + timedelta(hours=h) if h >= 0 else base - timedelta(hours=2)
