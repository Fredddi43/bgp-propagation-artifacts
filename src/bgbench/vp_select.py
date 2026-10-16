"""Vantage-point selection heuristic (ADR-0014) from BGPKit daily peer-stats.

Score collectors by full-feed IPv4 peers and unique peer ASNs; pick greedily by marginal coverage of
peer ASNs not yet covered (MVP-style redundancy avoidance, without reproducing MVP's scoring).
"""

from __future__ import annotations

import bz2
import datetime as dt
import json
from pathlib import Path

import httpx
import polars as pl

from . import config

BASE = "https://data.bgpkit.com"
FULL_FEED_V4 = 700_000  # a 2024 full IPv4 table is ~950k prefixes; partial feeds are far below


def collectors(client: httpx.Client) -> list[dict]:
    r = client.get(f"{BASE}/commons/collectors.json")
    r.raise_for_status()
    body = r.json()
    return body if isinstance(body, list) else body.get("collectors", body.get("data", []))


def peer_stats(client: httpx.Client, collector: str, day: dt.date) -> pl.DataFrame | None:
    epoch = int(dt.datetime(day.year, day.month, day.day, tzinfo=dt.UTC).timestamp())
    url = f"{BASE}/peer-stats/{collector}/{day:%Y/%m}/peer-stats_{collector}_{day:%Y-%m-%d}_{epoch}.bz2"
    r = client.get(url)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    body = json.loads(bz2.decompress(r.content))
    rows = [
        {
            "collector": collector,
            "peer_ip": ip,
            "peer_asn": p.get("asn"),
            "n_connected_asns": p.get("num_connected_asns"),
            "n_v4": p.get("num_v4_pfxs"),
            "n_v6": p.get("num_v6_pfxs"),
        }
        for ip, p in body.get("peers", {}).items()
    ]
    return pl.DataFrame(rows) if rows else None


def collect(day: dt.date, only: list[str] | None = None) -> pl.DataFrame:
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        cols = only or sorted({c.get("name") or c.get("id") for c in collectors(client)} - {None})
        frames = []
        for c in cols:
            df = peer_stats(client, c, day)
            if df is not None:
                frames.append(df)
    return pl.concat(frames) if frames else pl.DataFrame()


def score_and_select(ps: pl.DataFrame, k: int = 10) -> tuple[pl.DataFrame, list[dict]]:
    ps = ps.with_columns(full_v4=pl.col("n_v4") >= FULL_FEED_V4)
    per = (
        ps.group_by("collector")
        .agg(
            peers=pl.len(),
            full_feed_v4=pl.col("full_v4").sum(),
            peer_asns=pl.col("peer_asn").n_unique(),
            full_feed_asns=pl.col("peer_asn").filter(pl.col("full_v4")).n_unique(),
            v6_peers=(pl.col("n_v6") > 0).sum(),
        )
        .sort("full_feed_asns", descending=True)
    )
    ff_sets = {
        c: set(ps.filter((pl.col("collector") == c) & pl.col("full_v4"))["peer_asn"].to_list())
        for c in per["collector"]
    }
    all_sets = {
        c: set(ps.filter(pl.col("collector") == c)["peer_asn"].to_list()) for c in per["collector"]
    }
    covered_ff, covered_all, picks = set(), set(), []
    for step in range(min(k, len(ff_sets))):
        best, best_gain = None, (-1, -1)
        picked = {p["collector"] for p in picks}
        for c, ffs in ff_sets.items():
            if c in picked:
                continue
            gain = (len(ffs - covered_ff), len(all_sets[c] - covered_all))
            if gain > best_gain:
                best, best_gain = c, gain
        if best is None or best_gain == (0, 0):
            break
        covered_ff |= ff_sets[best]
        covered_all |= all_sets[best]
        picks.append(
            {
                "step": step + 1,
                "collector": best,
                "new_full_feed_asns": best_gain[0],
                "new_peer_asns": best_gain[1],
                "cum_full_feed_asns": len(covered_ff),
                "cum_peer_asns": len(covered_all),
                "redundancy": round(1 - best_gain[0] / max(len(ff_sets[best]), 1), 3),
            }
        )
    return per, picks


def run(day: str, k: int = 10, out_dir: Path | None = None) -> dict:
    d = dt.date.fromisoformat(day)
    ps = collect(d)
    out_dir = out_dir or (config.DATA_ROOT / "vp_selection" / day)
    out_dir.mkdir(parents=True, exist_ok=True)
    ps.write_parquet(out_dir / "peer_stats.parquet")
    per, picks = score_and_select(ps, k)
    per.write_csv(out_dir / "per_collector.csv")
    pl.DataFrame(picks).write_csv(out_dir / "greedy_selection.csv")
    return {
        "day": day,
        "collectors": per.height,
        "peers": ps.height,
        "picks": picks,
        "out": str(out_dir),
    }
