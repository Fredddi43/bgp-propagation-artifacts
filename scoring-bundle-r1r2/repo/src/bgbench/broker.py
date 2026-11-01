"""BGPKit broker v3 client — the authoritative MRT file index (ADR-0015 completeness check)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

from .config import BROKER_URL


@dataclass(frozen=True)
class BrokerItem:
    collector: str
    data_type: str  # "updates" | "rib"
    ts_start: datetime
    ts_end: datetime
    url: str
    rough_size: int
    exact_size: int

    @property
    def filename(self) -> str:
        return self.url.rsplit("/", 1)[-1]


def _parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=UTC)


def search(
    collector: str,
    start: datetime,
    end: datetime,
    data_type: str = "updates",
    page_size: int = 1000,
    client: httpx.Client | None = None,
) -> list[BrokerItem]:
    """All broker items for one collector in [start, end). Handles pagination.
    Collectors named "pch.<site>" are Packet Clearing House IXP route collectors (no broker): one gzip'd MRT update
    file per minute at downloads.pch.net (verified 2026-09-09; 390 collectors, 2018–2026, CC BY-SA 3.0)."""
    if collector.startswith("pch."):
        return pch_items(collector, start, end, data_type)
    own = client is None
    client = client or httpx.Client(timeout=60)
    items: list[BrokerItem] = []
    page = 1
    try:
        while True:
            r = client.get(
                BROKER_URL,
                params={
                    "collector_id": collector,
                    "data_type": data_type,
                    "ts_start": int(start.timestamp()),
                    "ts_end": int(end.timestamp()),
                    "page": page,
                    "page_size": page_size,
                },
            )
            r.raise_for_status()
            body = r.json()
            if body.get("error"):
                raise RuntimeError(f"broker error: {body['error']}")
            for d in body["data"]:
                items.append(
                    BrokerItem(
                        collector=d["collector_id"],
                        data_type=d["data_type"],
                        ts_start=_parse_ts(d["ts_start"]),
                        ts_end=_parse_ts(d["ts_end"]),
                        url=d["url"],
                        rough_size=int(d.get("rough_size") or 0),
                        exact_size=int(d.get("exact_size") or 0),
                    )
                )
            if page * page_size >= int(body["total"]):
                break
            page += 1
    finally:
        if own:
            client.close()
    # broker's ts_end is exclusive-ish; keep only files whose window starts inside [start, end)
    items = [i for i in items if start <= i.ts_start < end]
    items.sort(key=lambda i: i.ts_start)
    return items


def day_window(date: str) -> tuple[datetime, datetime]:
    d = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC)
    return d, d + timedelta(days=1)


PCH_BASE = "https://downloads.pch.net/files/BGP_Routing_Data"


def pch_host(collector: str) -> str:
    """'pch.decix-dus.fra' → 'route-collector.decix-dus.fra.pch.net'."""
    return f"route-collector.{collector[4:]}.pch.net"


def pch_items(collector: str, start: datetime, end: datetime, data_type: str = "updates") -> list[BrokerItem]:
    from datetime import timedelta

    host = pch_host(collector)
    items: list[BrokerItem] = []
    if data_type == "updates":
        t = start.replace(second=0, microsecond=0)
        while t < end:
            url = f"{PCH_BASE}/MRT_BGP_UPDATES/{host}/{t:%Y/%m/%d}/{host}-mrt-bgp-updates-{t:%Y-%m-%d-%H-%M}.gz"
            items.append(BrokerItem(collector=collector, data_type="updates", ts_start=t, ts_end=t + timedelta(minutes=1), url=url, rough_size=0, exact_size=0))
            t += timedelta(minutes=1)
    else:                                         # daily RIB snapshot (BGP_ROUTES_V4, one file per day)
        d = start.replace(hour=0, minute=0, second=0, microsecond=0)
        while d < end:
            url = f"{PCH_BASE}/BGP_ROUTES_V4/{host}/{d:%Y/%m/%d}/{host}-ipv4_bgp_routes.{d:%Y.%m.%d}.gz"
            items.append(BrokerItem(collector=collector, data_type="rib", ts_start=d, ts_end=d + timedelta(days=1), url=url, rough_size=0, exact_size=0))
            d += timedelta(days=1)
    return items
