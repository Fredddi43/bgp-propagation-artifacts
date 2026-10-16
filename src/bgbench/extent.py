"""Event extent per ADR-0012 from an ingested event window (EVENT_DIR/<name>/<collector>/part-*.parquet).

Announcement wave — an AS is *affected* at time t if, by t, it appeared on any VP-observed AS path of an
announcement for one of the event prefixes that carries the anomalous signature (origin ∈ actors, or
the leaker/amplifier ASN on the path). Membership is per collector (ADR-0004) and pooled for the curve.
Withdrawal wave (path-loss) needs the pre-t₀ RIB and is implemented separately once RIB parsing lands.

Outputs: per-collector membership table (asn, collector, first_seen_ts, via_prefix) and the pooled
growth curve N(t) sampled at 1 s from t₀−window to t₀+2 h, plus extent at the ADR-0012 targets.
"""

from __future__ import annotations

import datetime as dt

import polars as pl

from . import config

TARGETS_S = {"T5m": 300, "T15m": 900, "T60m": 3600, "final_2h": 7200}


def _paths(name: str, collectors: list[str] | None) -> list[str]:
    root = config.EVENT_DIR / name
    cols = collectors or sorted(p.name for p in root.iterdir() if p.is_dir())
    out = []
    for c in cols:
        out += [str(p) for p in sorted((root / c).glob("part-*.parquet"))]
    return out


def anomalous_announcements(
    name: str, prefixes: list[str], actor_asns: list[int], collectors: list[str] | None = None
) -> pl.DataFrame:
    """Announcements for the event prefixes whose path contains any actor ASN (origin or transit)."""
    pat = "(^| )(" + "|".join(str(a) for a in actor_asns) + ")( |$)"
    lf = (
        pl.scan_parquet(_paths(name, collectors))
        .select(
            "ts", "elem_type", "collector", "peer_ip", "peer_asn", "prefix", "as_path", "origin_asn"
        )
        .filter(
            (pl.col("elem_type") == "A")
            & pl.col("prefix").is_in(prefixes)
            & pl.col("as_path").str.contains(pat)
        )
    )
    lf = lf.with_columns(
        hops=pl.col("as_path")
        .str.replace_all(r"[{}]", "")
        .str.split(" ")
        .list.eval(pl.element().cast(pl.UInt32, strict=False))
    )
    lf = lf.filter(pl.col("hops").list.eval(pl.element().is_in(actor_asns)).list.any())
    return lf.select(
        "ts", "collector", "peer_ip", "peer_asn", "prefix", "as_path", "hops", "origin_asn"
    ).collect(engine="streaming")


def membership(
    anom: pl.DataFrame, t0: dt.datetime, actor_asns: list[int] | None = None
) -> pl.DataFrame:
    """Per-collector first time each AS is seen on an anomalous path (announcement-wave membership).
    With actor_asns given, only the hops on the collector side of the first actor occurrence count (the ASes
    that accepted and propagated the anomalous route, plus the actor itself); hops beyond it are the
    legitimate upstream of the route and are not "affected"."""
    if actor_asns:
        first_actor = pl.col("hops").list.eval(pl.element().is_in(actor_asns)).list.arg_max()
        anom = anom.with_columns(hops=pl.col("hops").list.slice(0, first_actor + 1))
    return (
        anom.explode("hops")
        .rename({"hops": "asn"})
        .drop_nulls("asn")
        .group_by("collector", "asn")
        .agg(first_seen=pl.col("ts").min(), via_prefix=pl.col("prefix").first(), n_msgs=pl.len())
        .with_columns(delay_s=(pl.col("first_seen") - pl.lit(t0)).dt.total_microseconds() / 1e6)
        .sort("collector", "first_seen")
    )


def growth_curve(
    mem: pl.DataFrame, t0: dt.datetime, horizon_s: int = 7200, pooled: bool = True
) -> pl.DataFrame:
    """N(t): number of distinct affected ASes seen by time t (pooled across collectors or per collector)."""
    keys = [] if pooled else ["collector"]
    firsts = (
        mem.group_by(*keys, "asn").agg(first=pl.col("first_seen").min())
        if pooled
        else mem.rename({"first_seen": "first"})
    )
    firsts = firsts.with_columns(
        rel_s=((pl.col("first") - pl.lit(t0)).dt.total_microseconds() / 1e6).floor().cast(pl.Int64)
    )
    firsts = firsts.filter(pl.col("rel_s") <= horizon_s)
    counts = firsts.group_by(*keys, "rel_s").agg(n=pl.len()).sort(*keys, "rel_s")
    return counts.with_columns(
        N=pl.col("n").cum_sum().over(keys) if keys else pl.col("n").cum_sum()
    )


def extent_at_targets(mem: pl.DataFrame, t0: dt.datetime) -> dict:
    out = {}
    for label, secs in TARGETS_S.items():
        sub = mem.filter(pl.col("first_seen") <= pl.lit(t0 + dt.timedelta(seconds=secs)))
        out[label] = {
            "asns_pooled": sub["asn"].n_unique(),
            "per_collector": sub.group_by("collector")
            .agg(pl.col("asn").n_unique().alias("n"))
            .sort("collector")
            .to_dicts(),
        }
    return out


def run(
    name: str,
    t0: str,
    prefixes: list[str],
    actor_asns: list[int],
    collectors: list[str] | None = None,
) -> dict:
    t0d = dt.datetime.fromisoformat(t0).replace(tzinfo=dt.UTC)
    anom = anomalous_announcements(name, prefixes, actor_asns, collectors)
    mem = membership(anom, t0d, actor_asns)
    curve = growth_curve(mem, t0d)
    out_dir = config.EVENT_DIR / name / "_extent"
    out_dir.mkdir(parents=True, exist_ok=True)
    anom.drop("hops").write_parquet(out_dir / "anomalous_announcements.parquet", compression="zstd")
    mem.write_parquet(out_dir / "membership.parquet", compression="zstd")
    curve.write_csv(out_dir / "growth_curve_pooled.csv")
    growth_curve(mem, t0d, pooled=False).write_csv(out_dir / "growth_curve_per_collector.csv")
    first_obs = anom["ts"].min()
    return {
        "event": name,
        "t0": t0,
        "first_observation": str(first_obs),
        "observation_lag_s": (first_obs - t0d).total_seconds() if first_obs else None,
        "anomalous_msgs": anom.height,
        "collectors": sorted(anom["collector"].unique().to_list()),
        "persistence_baseline_extent": mem.filter(pl.col("first_seen") <= pl.lit(first_obs))[
            "asn"
        ].n_unique()
        if first_obs
        else 0,
        "extent": extent_at_targets(mem, t0d),
        "out": str(out_dir),
    }


# ---- leak discovery: which prefixes newly transit the leaker? -------------------------------------
def _rib_paths(collectors: list[str] | None, at: dt.datetime) -> pl.LazyFrame:
    """Pre-event RIB rows (collector, peer_ip, prefix, as_path) — latest RIB at/before `at` per collector."""
    frames = []
    root = config.RIB_DIR
    for c in collectors or sorted(
        p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith("_")
    ):
        cands = sorted((root / c).glob("*.parquet"))
        cands = [
            p
            for p in cands
            if dt.datetime.strptime(p.stem, "%Y-%m-%dT%H%M").replace(tzinfo=dt.UTC) <= at
        ]
        if cands:
            frames.append(
                pl.scan_parquet(str(cands[-1])).select("collector", "peer_ip", "prefix", "as_path")
            )
    if not frames:
        raise FileNotFoundError("no pre-event RIBs under RIB_DIR")
    return pl.concat(frames)


def discover_leaked_prefixes(
    name: str, leaker: int, t0: dt.datetime, collectors: list[str] | None = None, min_peers: int = 1
) -> pl.DataFrame:
    """Prefixes for which, after t₀, some (collector, peer) received a path with `leaker` as a *transit*
    hop (not origin) while that (collector, peer)'s pre-event RIB path for the prefix did not contain it.
    Returns one row per (collector, peer_ip, prefix) with first leaked-path time + the path.
    Memory: the cheap regex filter on the path string runs before any list work; the RIB side is
    restricted to the discovered prefixes before joining."""
    pat = rf"(^| ){leaker}( |$)"
    upd = (
        pl.scan_parquet(_paths(name, collectors))
        .select("ts", "elem_type", "collector", "peer_ip", "peer_asn", "prefix", "as_path")
        .filter(
            (pl.col("elem_type") == "A")
            & (pl.col("ts") >= pl.lit(t0))
            & pl.col("as_path").str.contains(pat)
            & ~pl.col("as_path").str.contains(rf"(^| ){leaker}$")
        )  # leaker is transit, not origin
        .group_by("collector", "peer_ip", "peer_asn", "prefix")
        .agg(first_leaked_ts=pl.col("ts").min(), leaked_path=pl.col("as_path").first())
        .collect(engine="streaming")
    )
    if upd.is_empty():
        return upd.with_columns(rib_path=pl.lit(None, pl.String), rib_has_leaker=pl.lit(False))
    prefixes = upd["prefix"].unique().to_list()
    rib = (
        _rib_paths(collectors, t0)
        .filter(pl.col("prefix").is_in(prefixes))
        .with_columns(rib_has_leaker=pl.col("as_path").str.contains(pat))
        .rename({"as_path": "rib_path"})
        .collect(engine="streaming")
    )
    out = upd.join(rib, on=["collector", "peer_ip", "prefix"], how="left").filter(
        pl.col("rib_has_leaker").fill_null(False).not_()
    )
    counts = out.group_by("prefix").agg(n_vp=pl.len())
    keep = counts.filter(pl.col("n_vp") >= min_peers)["prefix"]
    return out.filter(pl.col("prefix").is_in(keep)).sort("first_leaked_ts")


def run_leak(name: str, t0: str, leaker: int, collectors: list[str] | None = None) -> dict:
    t0d = dt.datetime.fromisoformat(t0).replace(tzinfo=dt.UTC)
    leaked = discover_leaked_prefixes(name, leaker, t0d, collectors)
    out_dir = config.EVENT_DIR / name / "_extent"
    out_dir.mkdir(parents=True, exist_ok=True)
    leaked.write_parquet(out_dir / "leaked_prefix_vp.parquet", compression="zstd")
    prefixes = leaked["prefix"].unique().to_list()
    # membership over the discovered prefix set: every AS on a leaked path (announcement wave)
    anom = anomalous_announcements(name, prefixes, [leaker], collectors)
    anom = anom.filter(pl.col("ts") >= pl.lit(t0d))
    mem = membership(anom, t0d, [leaker])  # collector-side hops up to the leaker only
    mem.write_parquet(out_dir / "leak_membership.parquet", compression="zstd")
    growth_curve(mem, t0d).write_csv(out_dir / "leak_growth_curve_pooled.csv")
    # prefix-count growth curve: distinct leaked prefixes over time (pooled)
    pfx_first = leaked.group_by("prefix").agg(first=pl.col("first_leaked_ts").min())
    pfx_first = pfx_first.with_columns(
        rel_s=((pl.col("first") - pl.lit(t0d)).dt.total_microseconds() / 1e6).floor().cast(pl.Int64)
    ).sort("rel_s")
    pfx_curve = (
        pfx_first.group_by("rel_s")
        .agg(n=pl.len())
        .sort("rel_s")
        .with_columns(N=pl.col("n").cum_sum())
    )
    pfx_curve.write_csv(out_dir / "leak_prefix_growth_curve.csv")

    def at(secs):
        lim = t0d + dt.timedelta(seconds=secs)
        return {
            "prefixes": pfx_first.filter(pl.col("first") <= pl.lit(lim)).height,
            "asns_pooled": mem.filter(pl.col("first_seen") <= pl.lit(lim))["asn"].n_unique(),
            "vp_sessions": leaked.filter(pl.col("first_leaked_ts") <= pl.lit(lim))
            .select("collector", "peer_ip")
            .unique()
            .height,
        }

    return {
        "event": name,
        "leaker": leaker,
        "t0": t0,
        "leaked_prefixes_total": len(prefixes),
        "leaked_vp_prefix_rows": leaked.height,
        "collectors_seeing_leak": sorted(leaked["collector"].unique().to_list()),
        "per_collector_prefixes": leaked.group_by("collector")
        .agg(pl.col("prefix").n_unique().alias("n"))
        .sort("collector")
        .to_dicts(),
        "extent": {k: at(v) for k, v in TARGETS_S.items()},
        "out": str(out_dir),
    }


# ---- withdrawal wave / VP route-change (ADR-0012 secondary metric + path-loss membership) ----------
def route_change_and_path_loss(
    name: str, prefixes: list[str], t0: dt.datetime, collectors: list[str] | None = None
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """For every (collector, peer, prefix) that had a pre-event RIB path: the first post-t₀ update that
    withdraws it or replaces it with a different path. Returns
      (vp_changes: one row per (collector, peer_ip, prefix) with change_ts/kind/old/new path,
       path_loss: one row per (collector, asn) = first time an AS on the old path was dropped)."""
    rib = (
        _rib_paths(collectors, t0)
        .filter(pl.col("prefix").is_in(prefixes))
        .rename({"as_path": "rib_path"})
        .collect(engine="streaming")
    )
    upd = (
        pl.scan_parquet(_paths(name, collectors))
        .select("ts", "elem_type", "collector", "peer_ip", "prefix", "as_path")
        .filter(pl.col("prefix").is_in(prefixes) & (pl.col("ts") >= pl.lit(t0)))
        .collect(engine="streaming")
    )
    j = upd.join(rib, on=["collector", "peer_ip", "prefix"], how="inner")
    changed = j.filter((pl.col("elem_type") == "W") | (pl.col("as_path") != pl.col("rib_path")))
    first = (
        changed.sort("ts")
        .group_by("collector", "peer_ip", "prefix")
        .agg(
            change_ts=pl.col("ts").first(),
            kind=pl.col("elem_type").first(),
            old_path=pl.col("rib_path").first(),
            new_path=pl.col("as_path").first(),
        )
    )
    first = first.with_columns(
        delay_s=(pl.col("change_ts") - pl.lit(t0)).dt.total_microseconds() / 1e6
    )
    # path-loss membership: ASes on the old path that are not on the new path (all of them for W)
    pl_rows = (
        first.with_columns(
            old=pl.col("old_path")
            .str.replace_all(r"[{}]", "")
            .str.split(" ")
            .list.eval(pl.element().cast(pl.UInt32, strict=False)),
            new=pl.col("new_path")
            .fill_null("")
            .str.replace_all(r"[{}]", "")
            .str.split(" ")
            .list.eval(pl.element().cast(pl.UInt32, strict=False)),
        )
        .with_columns(lost=pl.col("old").list.set_difference(pl.col("new")))
        .explode("lost")
        .drop_nulls("lost")
        .group_by("collector", "lost")
        .agg(first_lost=pl.col("change_ts").min(), n_prefix_peer=pl.len())
        .rename({"lost": "asn"})
        .with_columns(delay_s=(pl.col("first_lost") - pl.lit(t0)).dt.total_microseconds() / 1e6)
        .sort("collector", "first_lost")
    )
    total_vp_prefix = rib.select("collector", "peer_ip", "prefix").unique().height
    first = first.with_columns(pl.lit(total_vp_prefix).alias("rib_vp_prefix_rows"))
    return first, pl_rows


def run_route_change(
    name: str, t0: str, prefixes: list[str], collectors: list[str] | None = None
) -> dict:
    t0d = dt.datetime.fromisoformat(t0).replace(tzinfo=dt.UTC)
    vp, loss = route_change_and_path_loss(name, prefixes, t0d, collectors)
    out_dir = config.EVENT_DIR / name / "_extent"
    out_dir.mkdir(parents=True, exist_ok=True)
    vp.write_parquet(out_dir / "vp_route_changes.parquet", compression="zstd")
    loss.write_parquet(out_dir / "path_loss_membership.parquet", compression="zstd")
    total = int(vp["rib_vp_prefix_rows"][0]) if vp.height else 0

    def at(secs):
        lim = t0d + dt.timedelta(seconds=secs)
        v = vp.filter(pl.col("change_ts") <= pl.lit(lim))
        return {
            "vp_prefix_changed": v.height,
            "frac_of_rib_rows": round(v.height / total, 4) if total else None,
            "withdrawn": int((v["kind"] == "W").sum()),
            "replaced": int((v["kind"] == "A").sum()),
            "path_loss_asns_pooled": loss.filter(pl.col("first_lost") <= pl.lit(lim))[
                "asn"
            ].n_unique(),
        }

    return {
        "event": name,
        "t0": t0,
        "prefixes": len(prefixes),
        "rib_vp_prefix_rows": total,
        "extent": {k: at(v) for k, v in TARGETS_S.items()},
        "out": str(out_dir),
    }
