"""Sprint-2 step 3: rank identifier-v2 origin-change events for replay selection.

Per event (prefix, new_origin, first_ts…): visibility (max collectors / peers), duration (n_bins × bin),
flip-back (the reverse change new→prev seen within 2 h ⇒ MOAS/transient rather than hand-over), prefix length,
and whether a Cloudflare hijack label matches (prefix + hijacker + ±10 min). Score = a simple monotone
combination for ordering; the stratification for the ~2,000 replay events is a research decision, so the output
is the full ranked table plus the marginal distributions needed to make it.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import polars as pl

from . import config


def load_year_events(year: int, tag: str = "m2_b5_events_f50") -> pl.DataFrame:
    root = config.DATA_ROOT / "identifier2"
    frames = []
    for d in sorted(root.glob(f"{year}-*_{year}-*")):
        f = d / tag / "origin_change_events.parquet"
        if f.exists():
            frames.append(pl.read_parquet(f).with_columns(month=pl.lit(d.name[:7])))
    if not frames:
        raise FileNotFoundError("no monthly event tables")
    return pl.concat(frames, how="diagonal_relaxed")


def add_flipback(ev: pl.DataFrame, within_h: int = 2) -> pl.DataFrame:
    """flip_back = the *next* event on the same prefix (forward as-of join, within `within_h`) changes the origin
    to one of this event's previous origins. Nearest-neighbour approximation of "reverted within 2 h"; avoids the
    per-prefix self-join that OOMs on prefixes with thousands of events."""
    base = ev.select("prefix", "new_origin", "prev_origins", "first_ts").sort("first_ts")
    nxt = (ev.select("prefix", pl.col("new_origin").alias("rev_new"), (pl.col("first_ts") - pl.duration(microseconds=1)).alias("rev_ts"))
             .sort("rev_ts"))
    # strictly later: shift the candidate timestamps by 1 µs so an event does not match itself
    j = base.join_asof(nxt, left_on="first_ts", right_on="rev_ts", by="prefix", strategy="forward",
                       tolerance=f"{within_h}h", allow_exact_matches=False)
    j = j.with_columns(
        flip_back=pl.col("rev_new").is_not_null()
        & pl.col("prev_origins").str.split(",").list.contains(pl.col("rev_new").cast(pl.String))
    ).select("prefix", "new_origin", "first_ts", "flip_back")
    return ev.join(j, on=["prefix", "new_origin", "first_ts"], how="left").with_columns(pl.col("flip_back").fill_null(False))


def add_labels(ev: pl.DataFrame, labels_dir: Path, slack_min: int = 10) -> pl.DataFrame:
    f = labels_dir / "cloudflare_hijacks.parquet"
    raw = pl.read_parquet(f) if f.exists() else pl.DataFrame()
    if raw.height == 0 or "min_hijack_ts" not in raw.columns:
        # Radar publishes no events before 2023: no labelled stratum, every event unlabelled (2022 extension, 2026-09-15)
        return ev.with_columns(lab_peers=pl.lit(None, dtype=pl.Float64), lab_conf=pl.lit(None, dtype=pl.Float64), labelled=pl.lit(False))
    hij = (raw
             .with_columns(pl.col("min_hijack_ts").str.to_datetime(time_zone="UTC", strict=False))
             .select(pl.col("prefixes").str.json_decode(pl.List(pl.String)), pl.col("hijacker_asn").cast(pl.UInt32).alias("new_origin"),
                     pl.col("min_hijack_ts").alias("lab_ts"), pl.col("peer_ip_count").cast(pl.Float64, strict=False).alias("lab_peers"),
                     pl.col("confidence_score").cast(pl.Float64, strict=False).alias("lab_conf"))
             .explode("prefixes").rename({"prefixes": "prefix"}))
    j = (ev.select("prefix", "new_origin", "first_ts").join(hij, on=["prefix", "new_origin"], how="inner")
           .filter((pl.col("first_ts") - pl.col("lab_ts")).dt.total_seconds().abs() <= slack_min * 60)
           .group_by("prefix", "new_origin", "first_ts").agg(lab_peers=pl.col("lab_peers").max(), lab_conf=pl.col("lab_conf").max())
           .with_columns(labelled=pl.lit(True)))
    return ev.join(j, on=["prefix", "new_origin", "first_ts"], how="left").with_columns(pl.col("labelled").fill_null(False))


def rank(ev: pl.DataFrame) -> pl.DataFrame:
    ev = ev.with_columns(
        plen=pl.col("prefix").str.extract(r"/(\d+)$").cast(pl.Int32),
        family=pl.when(pl.col("prefix").str.contains(":")).then(6).otherwise(4),
        duration_min=pl.col("n_bins") * 5,
        n_prev=pl.col("prev_origins").str.split(",").list.len(),
    )
    # monotone score: visibility first, then duration, then not-a-flipback
    return ev.with_columns(
        score=(pl.col("max_collectors").cast(pl.Float64) * 10 + pl.col("max_peers").cast(pl.Float64)
               + pl.col("duration_min").clip(0, 120) / 12 - pl.col("flip_back").cast(pl.Float64) * 5)
    ).sort("score", descending=True)


def summarize(ev: pl.DataFrame) -> dict:
    q = lambda c, p: float(ev[c].quantile(p)) if ev.height else None  # noqa: E731
    by_coll = ev.group_by("max_collectors").agg(n=pl.len(), labelled=pl.col("labelled").sum()).sort("max_collectors")
    return {
        "events": ev.height, "labelled": int(ev["labelled"].sum()), "flip_back": int(ev["flip_back"].sum()),
        "ipv6_share": round(float((ev["family"] == 6).mean()), 3),
        "max_peers_p50_p90_p99": [q("max_peers", .5), q("max_peers", .9), q("max_peers", .99)],
        "duration_min_p50_p90": [q("duration_min", .5), q("duration_min", .9)],
        "by_max_collectors": by_coll.to_dicts(),
        "labelled_by_collectors": ev.filter(pl.col("labelled")).group_by("max_collectors").len().sort("max_collectors").to_dicts(),
        "events_ge5_collectors": int((ev["max_collectors"] >= 5).sum()),
        "events_ge8_collectors": int((ev["max_collectors"] >= 8).sum()),
        "events_ge5_collectors_not_flipback_ge15min": int(((ev["max_collectors"] >= 5) & ~ev["flip_back"] & (ev["duration_min"] >= 15)).sum()),
    }


def run(year: int, labels_dir: Path) -> dict:
    ev = load_year_events(year)
    ev = add_flipback(ev)
    ev = add_labels(ev, labels_dir)
    ev = rank(ev)
    out_dir = config.DATA_ROOT / "inventory" / str(year)
    out_dir.mkdir(parents=True, exist_ok=True)
    ev.write_parquet(out_dir / "events_ranked.parquet", compression="zstd")
    s = summarize(ev)
    s["out"] = str(out_dir)
    import json
    (out_dir / "summary.json").write_text(json.dumps(s, indent=1, default=str))
    return s
