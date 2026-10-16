"""Beacon propagation analysis (sprint-1 week 1). From the parsed Parquet, extract every element
touching a RIS beacon prefix, decode the AGGREGATOR origination time, and compute per-(collector,
peer) observation delay for announcements and withdrawals. Output: one Parquet of beacon observations
+ a per-VP summary. ⚠️ UPDATE files only — RIB dumps land on the announcement instants (ADR-0015)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import polars as pl

from . import config
from .beacons import (
    BY_PREFIX,
    SCHEDULED_PREFIXES,
    announce_slot_for,
    decode_aggregator,
    scheduled_withdraw_after,
    withdraw_slot_for,
)


def _days(start: str, end: str) -> list[str]:
    a, b = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    return [(a + dt.timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]


def extract_observations(collectors: list[str], start: str, end: str) -> pl.DataFrame:
    """All A/W elements for scheduled beacon prefixes, with decoded origination + scheduled slots."""
    paths = []
    for c in collectors:
        for d in _days(start, end):
            paths += [str(p) for p in sorted((config.PARQUET_DIR / c / d).glob("part-*.parquet"))]
    if not paths:
        raise FileNotFoundError("no parquet parts for the requested collectors/days")
    df = (
        pl.scan_parquet(paths)
        .filter(pl.col("prefix").is_in(list(SCHEDULED_PREFIXES)))
        .select(
            "ts",
            "elem_type",
            "collector",
            "peer_ip",
            "peer_asn",
            "prefix",
            "as_path",
            "origin_asn",
            "aggr_asn",
            "aggr_ip",
        )
        .collect()
    )
    kinds = {p: b.kind for p, b in BY_PREFIX.items()}
    setups = {p: b.setup for p, b in BY_PREFIX.items()}
    df = df.with_columns(
        kind=pl.col("prefix").replace_strict(kinds, default="?"),
        setup=pl.col("prefix").replace_strict(setups, default="?"),
    )
    # decode AGGREGATOR per row (announcements only carry it)
    origs, fields = [], []
    for ts, asn, ip in zip(df["ts"].to_list(), df["aggr_asn"].to_list(), df["aggr_ip"].to_list()):
        o, f = decode_aggregator(asn, ip, ts.replace(tzinfo=dt.UTC) if ts.tzinfo is None else ts)
        origs.append(o)
        fields.append(f)
    df = df.with_columns(
        orig_ts=pl.Series(origs, dtype=pl.Datetime("us", "UTC")),
        aggr_field=pl.Series(fields, dtype=pl.Int32),
    )
    # scheduled slot for the cycle each observation belongs to
    slots, wds = [], []
    for ts, kind, et in zip(df["ts"].to_list(), df["kind"].to_list(), df["elem_type"].to_list()):
        ts = ts.replace(tzinfo=dt.UTC) if ts.tzinfo is None else ts
        if et == "W":
            # attribute withdrawals to the scheduled withdraw instant at/before ts; cycle = its announce slot
            w = withdraw_slot_for(ts, kind)
            s = w - (dt.timedelta(minutes=10) if kind == "fast" else dt.timedelta(hours=2))
        else:
            s = announce_slot_for(ts, kind)
            w = scheduled_withdraw_after(s, kind)
        slots.append(s)
        wds.append(w)
    df = df.with_columns(
        slot_ts=pl.Series(slots, dtype=pl.Datetime("us", "UTC")),
        sched_wd_ts=pl.Series(wds, dtype=pl.Datetime("us", "UTC")),
    )
    # delays: announcements vs decoded origination (true t0); withdrawals vs scheduled withdraw instant
    df = df.with_columns(
        delay_s=pl.when(pl.col("elem_type") == "A")
        .then((pl.col("ts") - pl.col("orig_ts")).dt.total_microseconds() / 1e6)
        .otherwise((pl.col("ts") - pl.col("sched_wd_ts")).dt.total_microseconds() / 1e6),
        slot_delay_s=(pl.col("ts") - pl.col("slot_ts")).dt.total_microseconds() / 1e6,
    )
    return df.sort("prefix", "collector", "peer_ip", "ts")


def first_observation_per_cycle(obs: pl.DataFrame) -> pl.DataFrame:
    """For each (prefix, cycle slot, collector, peer): first A and first W seen → the propagation delay
    that matters for forecasting (ADR-0012 t₀ = ground truth vs first observation)."""
    a = (
        obs.filter(pl.col("elem_type") == "A")
        .group_by("prefix", "kind", "setup", "slot_ts", "collector", "peer_ip", "peer_asn")
        .agg(
            first_a_ts=pl.col("ts").min(),
            orig_ts=pl.col("orig_ts").min(),
            a_delay_s=pl.col("delay_s").min(),
            n_a=pl.len(),
        )
    )
    w = (
        obs.filter(pl.col("elem_type") == "W")
        .group_by("prefix", "slot_ts", "collector", "peer_ip")
        .agg(first_w_ts=pl.col("ts").min(), w_delay_s=pl.col("delay_s").min(), n_w=pl.len())
    )
    out = a.join(w, on=["prefix", "slot_ts", "collector", "peer_ip"], how="left")
    # A VP whose *first* announcement of the cycle arrives ~2 h after origination never saw the
    # propagation wave: it only learned the prefix through path exploration at withdrawal time.
    # Flag it so propagation-delay statistics exclude it (it is a visibility fact, not a delay).
    out = out.with_columns(exploration_only=pl.col("a_delay_s") > 3600)
    return out.sort("prefix", "slot_ts", "collector", "peer_ip")


def per_vp_summary(cycles: pl.DataFrame) -> pl.DataFrame:
    cycles = cycles.filter(~pl.col("exploration_only"))
    return (
        cycles.group_by("collector", "kind", "setup")
        .agg(
            n_cycles=pl.col("slot_ts").n_unique(),
            n_peers=pl.col("peer_ip").n_unique(),
            a_delay_p50=pl.col("a_delay_s").quantile(0.5),
            a_delay_p90=pl.col("a_delay_s").quantile(0.9),
            a_delay_max=pl.col("a_delay_s").max(),
            w_delay_p50=pl.col("w_delay_s").quantile(0.5),
            w_delay_p90=pl.col("w_delay_s").quantile(0.9),
            frac_cycles_with_w=(pl.col("first_w_ts").is_not_null().mean()),
        )
        .sort("collector", "kind", "setup")
    )


def run(collectors: list[str], start: str, end: str, out_dir: Path | None = None) -> dict:
    out_dir = out_dir or (config.BEACON_DIR / f"{start}_{end}")
    out_dir.mkdir(parents=True, exist_ok=True)
    obs = extract_observations(collectors, start, end)
    cyc = first_observation_per_cycle(obs)
    summ = per_vp_summary(cyc)
    obs.write_parquet(out_dir / "observations.parquet", compression="zstd")
    cyc.write_parquet(out_dir / "cycles.parquet", compression="zstd")
    summ.write_parquet(out_dir / "per_vp_summary.parquet", compression="zstd")
    summ.write_csv(out_dir / "per_vp_summary.csv")
    return {
        "observations": obs.height,
        "cycles": cyc.height,
        "vps": summ.height,
        "out": str(out_dir),
    }


def visibility(collectors: list[str], start: str, end: str) -> pl.DataFrame:
    """Per beacon-registry prefix (all kinds incl. anchors and the RPKI triple): how many (collector, peer)
    sessions ever carried it in the window, and how many collectors. Anchors are the collector-artefact
    control (permanent, untagged); valid/invalid/unknown differ only by ROA → their session counts are a
    direct ROV-deployment measurement among RIS peers."""
    from .beacons import BEACON_PREFIXES

    paths = []
    for c in collectors:
        for d in _days(start, end):
            paths += [str(p) for p in sorted((config.PARQUET_DIR / c / d).glob("part-*.parquet"))]
    df = (
        pl.scan_parquet(paths)
        .filter(pl.col("prefix").is_in(list(BEACON_PREFIXES)) & (pl.col("elem_type") == "A"))
        .group_by("prefix")
        .agg(
            sessions=pl.struct("collector", "peer_ip").n_unique(),
            collectors=pl.col("collector").n_unique(),
            peer_asns=pl.col("peer_asn").n_unique(),
            n_ann=pl.len(),
        )
        .collect(engine="streaming")
    )
    kinds = {p: b.kind for p, b in BY_PREFIX.items()}
    setups = {p: b.setup for p, b in BY_PREFIX.items()}
    fam = {p: b.family for p, b in BY_PREFIX.items()}
    return df.with_columns(
        kind=pl.col("prefix").replace_strict(kinds, default="?"),
        setup=pl.col("prefix").replace_strict(setups, default="?"),
        family=pl.col("prefix").replace_strict(fam, default=0),
    ).sort("kind", "setup", "family")


# ---- #24 follow-ups: RIB-based visibility (anchors control + RPKI triple), full-feed peer join ----------
def rib_visibility(at: dt.datetime, collectors: list[str] | None = None) -> pl.DataFrame:
    """Sessions carrying each registry prefix in the RIB dumps at/before `at` (RIB_DIR/<collector>/*.parquet).
    The right instrument for permanent prefixes (anchors, RPKI triple) that UPDATE files under-count."""
    from .beacons import BEACON_PREFIXES
    from .extent import _rib_paths

    rib = (
        _rib_paths(collectors, at)
        .filter(pl.col("prefix").is_in(list(BEACON_PREFIXES)))
        .group_by("prefix")
        .agg(
            sessions=pl.struct("collector", "peer_ip").n_unique(),
            collectors=pl.col("collector").n_unique(),
            peer_asns=pl.col("as_path")
            .str.extract(r"^(\d+)")
            .cast(pl.Int64, strict=False)
            .n_unique(),
        )
        .collect(engine="streaming")
    )
    kinds = {p: b.kind for p, b in BY_PREFIX.items()}
    setups = {p: b.setup for p, b in BY_PREFIX.items()}
    fam = {p: b.family for p, b in BY_PREFIX.items()}
    return rib.with_columns(
        kind=pl.col("prefix").replace_strict(kinds, default="?"),
        setup=pl.col("prefix").replace_strict(setups, default="?"),
        family=pl.col("prefix").replace_strict(fam, default=0),
    ).sort("kind", "setup", "family")


def rov_meter(vis: pl.DataFrame) -> dict:
    """RPKI triple from RIB visibility: sessions carrying invalid / valid / unknown per family."""
    out = {}
    for fam in (4, 6):
        v = {
            r["kind"]: r["sessions"]
            for r in vis.filter(
                (pl.col("family") == fam) & pl.col("kind").str.starts_with("rpki")
            ).to_dicts()
        }
        # unknown = the rrc03 anchor pair
        unk_pfx = "84.205.83.0/24" if fam == 4 else "2001:7fb:ff03::/48"
        unk = vis.filter(pl.col("prefix") == unk_pfx)["sessions"]
        v["rpki_unknown"] = int(unk[0]) if unk.len() else None
        if v.get("rpki_valid"):
            v["invalid_over_valid"] = round(v.get("rpki_invalid", 0) / v["rpki_valid"], 3)
        out[f"ipv{fam}"] = v
    return out


def full_feed_join(
    cycles: pl.DataFrame, peer_stats_path: Path, threshold_v4: int = 700_000
) -> pl.DataFrame:
    """Attach a full-feed flag per (collector, peer_ip) from a BGPKit peer-stats snapshot (vp_selection/<day>/peer_stats.parquet)."""
    ps = pl.read_parquet(peer_stats_path).select(pl.col("collector").cast(pl.String), "peer_ip", "n_v4", "n_v6")
    ps = ps.with_columns(full_feed=(pl.col("n_v4") >= threshold_v4) | (pl.col("n_v6") >= 150_000))
    cycles = cycles.with_columns(pl.col("collector").cast(pl.String))
    return cycles.join(
        ps.select("collector", "peer_ip", "full_feed"), on=["collector", "peer_ip"], how="left"
    ).with_columns(pl.col("full_feed").fill_null(False))


def per_vp_summary_by_feed(cycles: pl.DataFrame) -> pl.DataFrame:
    c = (
        cycles.filter(~pl.col("exploration_only"))
        if "exploration_only" in cycles.columns
        else cycles
    )
    return (
        c.group_by("full_feed", "kind")
        .agg(
            sessions=pl.struct("collector", "peer_ip").n_unique(),
            cycles=pl.len(),
            a_delay_p50=pl.col("a_delay_s").quantile(0.5),
            a_delay_p90=pl.col("a_delay_s").quantile(0.9),
            w_delay_p50=pl.col("w_delay_s").quantile(0.5),
            w_delay_p90=pl.col("w_delay_s").quantile(0.9),
            frac_cycles_with_w=pl.col("first_w_ts").is_not_null().mean(),
        )
        .sort("full_feed", "kind")
    )
