"""Parallel MRT download into a RAM directory (ADR-0011). RouteViews single-stream is ~2 MB/s,
RIS ~9 MB/s; both scale near-linearly with streams up to 32+ (measured 2026-09-03)."""

from __future__ import annotations

import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import httpx

from .broker import BrokerItem


@dataclass
class FetchResult:
    item: BrokerItem
    path: Path | None
    size: int
    error: str | None = None


BACKOFF_S = (2, 5, 15, 45, 90, 180, 300, 300, 300, 300, 300, 300)   # RouteViews drops connections under load, and on 2026-09-16 was
# unreachable (No route to host) in windows longer than the old ~6 min budget; 12 attempts now span ~40 min

# Compute nodes have no IPv6 route. httpx's local_address="0.0.0.0" (below) makes the connect to an AAAA answer fail with
# [Errno 97] and move on to the A answer, but when the resolver hands back AAAA records only, or orders them so the last
# error is the v6 one, the whole file is reported as a ConnectError. Filter the resolver answers to IPv4 process-wide
# (2026-09-16: 2024 recovery replay lost 12 collector-days to this in one evening on two different nodes).
_getaddrinfo = socket.getaddrinfo


def _getaddrinfo_v4(*args, **kwargs):
    res = _getaddrinfo(*args, **kwargs)
    v4 = [r for r in res if r[0] == socket.AF_INET]
    return v4 or res


socket.getaddrinfo = _getaddrinfo_v4


def _fetch_one(client: httpx.Client, item: BrokerItem, dest: Path, retries: int = len(BACKOFF_S)) -> FetchResult:
    path = dest / item.filename
    last = ""
    for attempt in range(retries):
        try:
            with client.stream("GET", item.url) as r:
                if r.status_code == 404:
                    return FetchResult(item, None, 0, "404")
                r.raise_for_status()
                if "pch.net" in item.url and "text/html" in r.headers.get("content-type", ""):
                    return FetchResult(item, None, 0, "404")        # PCH serves its web app with 200 for missing files
                with open(path, "wb") as f:
                    f.writelines(r.iter_bytes(1 << 20))
            size = path.stat().st_size
            if item.exact_size and size != item.exact_size:
                last = f"size {size} != exact_size {item.exact_size}"
                path.unlink(missing_ok=True)
                continue
            if size == 0:
                last = "empty file"
                path.unlink(missing_ok=True)
                continue
            return FetchResult(item, path, size)
        except (httpx.HTTPError, OSError) as e:
            last = f"{type(e).__name__}: {e}"
            path.unlink(missing_ok=True)
            time.sleep(BACKOFF_S[min(attempt, len(BACKOFF_S) - 1)])
    return FetchResult(item, None, 0, last or "failed")


def fetch_all(items: list[BrokerItem], dest: Path, workers: int = 32) -> list[FetchResult]:
    dest.mkdir(parents=True, exist_ok=True)
    if items and "routeviews" in items[0].url:
        workers = min(workers, 8)      # RouteViews: 32 streams × 120 jobs disconnects; 8 streams still saturate a 15-min file

    results: list[FetchResult] = []
    limits = httpx.Limits(max_connections=workers + 4, max_keepalive_connections=workers)
    with (
        httpx.Client(
            timeout=httpx.Timeout(120, connect=30),
            limits=limits,
            follow_redirects=True,
            headers={"User-Agent": "bgbench/0.1 (research)"},
            # force IPv4: compute nodes have no IPv6 route and RouteViews resolves to AAAA → [Errno 97]
            transport=httpx.HTTPTransport(local_address="0.0.0.0", retries=2),
        ) as client,
        ThreadPoolExecutor(max_workers=workers) as ex,
    ):
        futs = [ex.submit(_fetch_one, client, it, dest) for it in items]
        for f in as_completed(futs):
            results.append(f.result())
    results.sort(key=lambda r: r.item.ts_start)
    return results
