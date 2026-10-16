"""Sprint-2 steps 4–5: replay one selected event — ingest its window on the pass collectors, extract the
announcement-wave labels (ADR-0012) and growth curves, keep only the derived tables (ADR-0011).

For an origin-change event (prefix, new_origin, t₀): anomalous announcements = announcements of `prefix`
(exact) whose origin is `new_origin` inside the window; membership = every AS on those paths (all hops are on
the collector side of the origin), per collector; growth curves for ASes and VP sessions; extents at ADR-0012
horizons; observation lag = first anomalous announcement − t₀ (t₀ = the identifier's first_ts).
Output: events_replay/<event_id>/{anomalous.parquet, membership.parquet, curve_asn.csv, curve_vp.csv, summary.json}.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import polars as pl

from . import config
from .broker import search
from .extent import TARGETS_S, growth_curve, membership
from .fetch import fetch_all
from .parse import parse_day

PASS_COLLECTORS = ["rrc25", "rrc00", "rrc12", "rrc01", "route-views3", "rrc03", "route-views2", "rrc20", "rrc15", "route-views.linx"]


def replay_event(event_id: str, prefix: str, new_origin: int, t0: dt.datetime, collectors: list[str] | None = None,
                 before_h: int = 1, after_h: int = 3, workers: int = 16, procs: int = 4) -> dict:
    collectors = collectors or PASS_COLLECTORS
    out_dir = config.DATA_ROOT / "events_replay" / event_id
    if (out_dir / "summary.json").exists():
        return json.loads((out_dir / "summary.json").read_text())
    out_dir.mkdir(parents=True, exist_ok=True)
    start, end = t0 - dt.timedelta(hours=before_h), t0 + dt.timedelta(hours=after_h)
    shm = config.shm_dir() / "replay" / event_id
    parts: list[str] = []
    fetched = {}
    try:
        for c in collectors:
            items = search(c, start, end, "updates")
            res = fetch_all(items, shm / c, workers=workers)
            ok = [r.path for r in res if r.path]
            fetched[c] = (len(ok), len(items))
            if ok:
                stats = parse_day(ok, c, shm / f"pq_{c}", procs=procs, delete_raw=True)
                parts += [str(p) for p in sorted((shm / f"pq_{c}").glob("part-*.parquet"))]
        if not parts:
            summary = {"event_id": event_id, "error": "no data fetched", "fetched": fetched}
            (out_dir / "summary.json").write_text(json.dumps(summary))
            return summary
        anom = (pl.scan_parquet(parts)
                  .filter((pl.col("elem_type") == "A") & (pl.col("prefix") == prefix) & (pl.col("origin_asn") == new_origin) & pl.col("as_path").is_not_null())
                  .select("ts", pl.col("collector").cast(pl.String), "peer_ip", "peer_asn", "prefix", "as_path", "origin_asn")
                  .with_columns(hops=pl.col("as_path").str.replace_all(r"[{}]", "").str.split(" ").list.eval(pl.element().cast(pl.UInt32, strict=False)))
                  .collect(engine="streaming"))
        # everything the prefix did in the window (any origin) — for the VP-side "did this peer switch" metric
        all_pfx = (pl.scan_parquet(parts).filter(pl.col("prefix") == prefix)
                     .select("ts", pl.col("collector").cast(pl.String), "peer_ip", "elem_type", "origin_asn").collect(engine="streaming"))
        mem = membership(anom, t0, [new_origin]) if anom.height else pl.DataFrame(schema={"collector": pl.String, "asn": pl.UInt32, "first_seen": pl.Datetime("us", "UTC"), "via_prefix": pl.String, "n_msgs": pl.UInt32, "delay_s": pl.Float64})
        first_obs = anom["ts"].min() if anom.height else None
        # curves
        curve_asn = growth_curve(mem, t0) if mem.height else pl.DataFrame()
        vp_first = (anom.group_by("collector", "peer_ip").agg(first=pl.col("ts").min())
                        .with_columns(rel_s=((pl.col("first") - pl.lit(t0)).dt.total_microseconds() / 1e6).floor().cast(pl.Int64)).sort("rel_s")) if anom.height else pl.DataFrame()
        curve_vp = vp_first.group_by("rel_s").agg(n=pl.len()).sort("rel_s").with_columns(N=pl.col("n").cum_sum()) if vp_first.height else pl.DataFrame()
        # VP sessions that carried the prefix at all in the window vs those that switched to the new origin
        sessions_any = all_pfx.select("collector", "peer_ip").unique().height
        sessions_new = anom.select("collector", "peer_ip").unique().height if anom.height else 0
        def at(secs: int) -> dict:
            lim = t0 + dt.timedelta(seconds=secs)
            m = mem.filter(pl.col("first_seen") <= pl.lit(lim)) if mem.height else mem
            v = vp_first.filter(pl.col("first") <= pl.lit(lim)).height if vp_first.height else 0
            return {"asns_pooled": m["asn"].n_unique() if m.height else 0, "vp_sessions": v,
                    "per_collector_asns": (m.group_by("collector").agg(pl.col("asn").n_unique().alias("n")).sort("collector").to_dicts() if m.height else [])}
        summary = {
            "event_id": event_id, "prefix": prefix, "new_origin": int(new_origin), "t0": t0.isoformat(),
            "window": [start.isoformat(), end.isoformat()], "fetched": fetched,
            "first_observation": first_obs.isoformat() if first_obs else None,
            "observation_lag_s": (first_obs - t0).total_seconds() if first_obs else None,
            "anomalous_msgs": anom.height, "collectors_seeing": sorted(anom["collector"].unique().to_list()) if anom.height else [],
            "sessions_carrying_prefix": sessions_any, "sessions_switched_to_new_origin": sessions_new,
            "extent": {k: at(v) for k, v in TARGETS_S.items()},
            "persistence_extent_asns": mem.filter(pl.col("first_seen") <= pl.lit(first_obs))["asn"].n_unique() if (mem.height and first_obs) else 0,
        }
        anom.drop("hops").write_parquet(out_dir / "anomalous.parquet", compression="zstd")
        mem.write_parquet(out_dir / "membership.parquet", compression="zstd")
        if curve_asn.height:
            curve_asn.write_csv(out_dir / "curve_asn.csv")
        if curve_vp.height:
            curve_vp.write_csv(out_dir / "curve_vp.csv")
        (out_dir / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
        return summary
    finally:
        config.release_shm(shm)
