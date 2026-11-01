"""Per-prefix state signals for the event identifier (ADR-0013 v2), computed per collector-day from the
hourly Parquet before it is discarded (ADR-0011 aggregates-only pass).

Two compact tables:
- origin_changes: for each (peer_ip, prefix), every announcement whose origin ASN differs from that peer's
  previously observed origin for the prefix within the day (first observation of the day is not a change
  unless it differs from the last origin of the previous day — cross-day state is not carried; v2 caveat).
- new_edges: every (asn_a, asn_b) adjacency seen for the first time this collector-day, with the first
  timestamp, peer and prefix. Cross-day novelty is resolved later against a rolling edge set.
Plus per-minute counts of both, joined into the aggregate table by the caller.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl


def origin_changes(day_dir: Path) -> pl.DataFrame:
    """Two-stage so a 100M-row day never sits in memory: (1) streaming group-by → prefixes announced with ≥ 2
    distinct origins at this collector today (an origin change at any peer requires that); (2) sort-based
    per-(peer, prefix) change detection on that small subset only."""
    src = pl.scan_parquet(str(day_dir / "part-*.parquet")).filter(
        (pl.col("elem_type") == "A") & pl.col("origin_asn").is_not_null()
    )
    multi = (
        src.group_by("prefix")
        .agg(n=pl.col("origin_asn").n_unique())
        .filter(pl.col("n") >= 2)
        .select("prefix")
        .collect(engine="streaming")
    )
    if multi.is_empty():
        return pl.DataFrame(
            schema={
                "ts": pl.Datetime("us", "UTC"),
                "collector": pl.String,
                "peer_ip": pl.String,
                "peer_asn": pl.UInt32,
                "prefix": pl.String,
                "prev_origin": pl.UInt32,
                "new_origin": pl.UInt32,
                "as_path": pl.String,
            }
        )
    sub = (
        src.filter(pl.col("prefix").is_in(multi["prefix"].implode()))
        .select("ts", "collector", "peer_ip", "peer_asn", "prefix", "origin_asn", "as_path")
        .collect(engine="streaming")
    )
    return (
        sub.sort("peer_ip", "prefix", "ts", maintain_order=True)   # stable: same-second announcements keep MRT order (as the side tables do)
        .with_columns(prev_origin=pl.col("origin_asn").shift(1).over("peer_ip", "prefix"))
        .filter(
            pl.col("prev_origin").is_not_null() & (pl.col("prev_origin") != pl.col("origin_asn"))
        )
        .select(
            "ts",
            pl.col("collector").cast(pl.String),
            "peer_ip",
            "peer_asn",
            "prefix",
            "prev_origin",
            pl.col("origin_asn").alias("new_origin"),
            "as_path",
        )
    )


def _exploded_edges(day_dir: Path) -> pl.LazyFrame:
    return (
        pl.scan_parquet(str(day_dir / "part-*.parquet"))
        .filter(
            (pl.col("elem_type") == "A")
            & pl.col("as_path").is_not_null()
            & ~pl.col("as_path").str.contains(r"[{}]")
        )
        .select("ts", pl.col("collector").cast(pl.String), "prefix", "as_path")
        .with_columns(
            hops=pl.col("as_path")
            .str.split(" ")
            .list.eval(pl.element().cast(pl.UInt32, strict=False))
        )
        .with_columns(
            a=pl.col("hops").list.slice(0, pl.col("hops").list.len() - 1),
            b=pl.col("hops").list.slice(1),
        )
        .select("ts", "collector", "prefix", "as_path", "a", "b")
        .explode("a", "b")
        .filter(
            pl.col("a").is_not_null() & pl.col("b").is_not_null() & (pl.col("a") != pl.col("b"))
        )
    )


def new_edges(day_dir: Path) -> pl.DataFrame:
    """Distinct AS adjacencies first seen this collector-day. Two streaming passes: (1) group-by (a, b) → first_ts,
    n_msgs (cheap); (2) inner join on (a, b, ts == first_ts) → the example prefix/path of the first announcement
    carrying the edge (needed by the valley-free leak check). An ordered group-by with string first() over the
    ~500 M exploded rows of a big collector-day does not stream and OOMs."""
    edges = (
        _exploded_edges(day_dir)
        .group_by("collector", "a", "b")
        .agg(first_ts=pl.col("ts").min(), n_msgs=pl.len())
        .collect(engine="streaming")
    )
    ex = (
        _exploded_edges(day_dir)
        .join(
            edges.select("a", "b", pl.col("first_ts").alias("ts")).lazy(),
            on=["a", "b", "ts"],
            how="inner",
        )
        .group_by("a", "b")
        .agg(example_prefix=pl.col("prefix").first(), example_path=pl.col("as_path").first())
        .collect(engine="streaming")
    )
    return edges.join(ex, on=["a", "b"], how="left").sort("first_ts")


def minute_counts(oc: pl.DataFrame, ne: pl.DataFrame) -> pl.DataFrame:
    """Per collector-minute: prefixes with an origin change, distinct new origins, first-seen edges."""
    a = (
        oc.with_columns(minute=pl.col("ts").dt.truncate("1m"))
        .group_by("collector", "minute")
        .agg(
            n_origin_change_pfx=pl.col("prefix").n_unique().cast(pl.UInt32),
            n_origin_change_peers=pl.col("peer_ip").n_unique().cast(pl.UInt16),
            n_new_origins=pl.col("new_origin").n_unique().cast(pl.UInt32),
        )
    )
    b = (
        ne.with_columns(minute=pl.col("first_ts").dt.truncate("1m"))
        .group_by("collector", "minute")
        .agg(n_new_edges=pl.len().cast(pl.UInt32))
    )
    return a.join(b, on=["collector", "minute"], how="full", coalesce=True).sort("minute")


def _exploded_triples(day_dir: Path) -> pl.LazyFrame:
    """(x, a, b) consecutive hop triples of every announced path; x is collector-side of a, b is origin-side."""
    return (pl.scan_parquet(str(day_dir / "part-*.parquet"))
              .filter((pl.col("elem_type") == "A") & pl.col("as_path").is_not_null() & ~pl.col("as_path").str.contains(r"[{}]"))
              .select("ts", pl.col("collector").cast(pl.String), "prefix", "as_path")
              .with_columns(hops=pl.col("as_path").str.split(" ").list.eval(pl.element().cast(pl.UInt32, strict=False)))
              .filter(pl.col("hops").list.len() >= 3)
              .with_columns(x=pl.col("hops").list.slice(0, pl.col("hops").list.len() - 2),
                            a=pl.col("hops").list.slice(1, pl.col("hops").list.len() - 2),
                            b=pl.col("hops").list.slice(2))
              .select("ts", "collector", "prefix", "as_path", "x", "a", "b")
              .explode("x", "a", "b")
              .filter(pl.col("x").is_not_null() & pl.col("a").is_not_null() & pl.col("b").is_not_null()
                      & (pl.col("x") != pl.col("a")) & (pl.col("a") != pl.col("b"))))


def new_triples(day_dir: Path) -> pl.DataFrame:
    """Identifier v4 (ADR-0018): distinct (x, a, b) triples first seen this collector-day, with first_ts, n_msgs
    and the example prefix/path — the unit the valley-free leak check classifies (a learned from b, exported to x).
    Two streaming passes like new_edges()."""
    tri = (_exploded_triples(day_dir).group_by("collector", "x", "a", "b")
             .agg(first_ts=pl.col("ts").min(), n_msgs=pl.len()).collect(engine="streaming"))
    ex = (_exploded_triples(day_dir)
            .join(tri.select("x", "a", "b", pl.col("first_ts").alias("ts")).lazy(), on=["x", "a", "b", "ts"], how="inner")
            .group_by("x", "a", "b").agg(example_prefix=pl.col("prefix").first(), example_path=pl.col("as_path").first())
            .collect(engine="streaming"))
    return tri.join(ex, on=["x", "a", "b"], how="left").sort("first_ts")


# ---------------------------------------------------------------------------------------------------------------
# In-worker extraction (issue #27): the parse worker already holds one hour of the day sorted by ts in memory, so
# it computes the per-hour pieces of every table above there and writes them as small "side tables" to RAM. The
# main process merges 24 of them instead of re-reading the day's Parquet three times (that second pass was ~30 %
# of an ingest job). Semantics are identical to the scan-based functions, which stay for backfills from kept Parquet.
# ---------------------------------------------------------------------------------------------------------------

_SIDE_KINDS = ("minutes", "prefix_origins", "oc_changes", "oc_boundary", "edges", "triples", "violations")


def _hops(df: pl.DataFrame) -> pl.DataFrame:
    """Announcements with a clean (no AS-set) path → rid, ts, peer_ip, prefix, as_path, hops[u32]; rid indexes the ts order."""
    return (
        df.filter((pl.col("elem_type") == "A") & pl.col("as_path").is_not_null() & ~pl.col("as_path").str.contains(r"[{}]"))
        .select("ts", "peer_ip", "prefix", "as_path")
        .with_row_index("rid")
        .with_columns(hops=pl.col("as_path").str.split(" ").list.eval(pl.element().cast(pl.UInt32, strict=False)))
    )


def _first_seen(exploded: pl.DataFrame, keys: list[str], paths: pl.DataFrame) -> pl.DataFrame:
    """Group consecutive-hop tuples: first_ts, n_msgs and the example prefix/path of the earliest message.
    `exploded` is in ts order (it derives from the ts-sorted hour), so first() is the earliest occurrence."""
    g = exploded.group_by(keys, maintain_order=False).agg(
        first_ts=pl.col("ts").first(), n_msgs=pl.len().cast(pl.UInt32), rid=pl.col("rid").first()
    )
    return (
        g.join(paths.select("rid", "prefix", "as_path"), on="rid", how="left")
        .rename({"prefix": "example_prefix", "as_path": "example_path"})
        .drop("rid")
    )


def hour_side_tables(df: pl.DataFrame, side_dir: Path, hour: str, rel_path: Path | None = None) -> None:
    """Compute and write the per-hour side tables for one ts-sorted hour of one collector-day.
    rel_path: CAIDA relationship Parquet (u, v, kind) of the month → also the identifier-v5 `violations` table."""
    side_dir.mkdir(parents=True, exist_ok=True)

    def w(kind: str, t: pl.DataFrame) -> None:
        t.write_parquet(side_dir / f"part-{hour}.{kind}.parquet", compression="zstd", compression_level=1)

    # 1. per-minute signals (minutes never straddle hours → per-hour tables concatenate exactly)
    w(
        "minutes",
        df.with_columns(minute=pl.col("ts").dt.truncate("1m"))
        .group_by("minute")
        .agg(
            n_ann=(pl.col("elem_type") == "A").sum().cast(pl.UInt32),
            n_wd=(pl.col("elem_type") == "W").sum().cast(pl.UInt32),
            n_prefixes=pl.col("prefix").n_unique().cast(pl.UInt32),
            n_peers=pl.col("peer_ip").n_unique().cast(pl.UInt16),
            n_origins=pl.col("origin_asn").drop_nulls().n_unique().cast(pl.UInt32),
            n_paths=pl.col("as_path").drop_nulls().n_unique().cast(pl.UInt32),
        ),
    )
    # 2./3./4. origin changes: distinct (prefix, origin) pairs; within-hour changes; per-(peer, prefix) hour boundary
    ann = df.filter((pl.col("elem_type") == "A") & pl.col("origin_asn").is_not_null()).select(
        "ts", "peer_ip", "peer_asn", "prefix", "origin_asn", "as_path"
    )
    w("prefix_origins", ann.select("prefix", "origin_asn").unique())
    seq = ann.sort("peer_ip", "prefix", "ts", maintain_order=True).with_columns(
        prev_origin=pl.col("origin_asn").shift(1).over("peer_ip", "prefix")
    )
    w(
        "oc_changes",
        seq.filter(pl.col("prev_origin").is_not_null() & (pl.col("prev_origin") != pl.col("origin_asn"))).select(
            "ts", "peer_ip", "peer_asn", "prefix", "prev_origin", pl.col("origin_asn").alias("new_origin"), "as_path"
        ),
    )
    w(
        "oc_boundary",
        seq.group_by("peer_ip", "prefix", maintain_order=True).agg(
            peer_asn=pl.col("peer_asn").first(),
            first_origin=pl.col("origin_asn").first(),
            first_ts=pl.col("ts").first(),
            first_path=pl.col("as_path").first(),
            last_origin=pl.col("origin_asn").last(),
        ).with_columns(hour=pl.lit(hour)),
    )
    del seq, ann
    # 5./6. first-seen edges (a, b) and triples (x, a, b) of clean paths
    paths = _hops(df)
    slim = paths.select("rid", "ts", "hops")
    paths = paths.drop("hops")            # the list column is only needed in `slim`; keep the example lookup table small
    e = (
        slim.with_columns(a=pl.col("hops").list.slice(0, pl.col("hops").list.len() - 1), b=pl.col("hops").list.slice(1))
        .select("rid", "ts", "a", "b")
        .explode("a", "b")
        .filter(pl.col("a").is_not_null() & pl.col("b").is_not_null() & (pl.col("a") != pl.col("b")))
    )
    w("edges", _first_seen(e, ["a", "b"], paths))
    del e
    t = (
        slim.filter(pl.col("hops").list.len() >= 3)
        .with_columns(
            x=pl.col("hops").list.slice(0, pl.col("hops").list.len() - 2),
            a=pl.col("hops").list.slice(1, pl.col("hops").list.len() - 2),
            b=pl.col("hops").list.slice(2),
        )
        .select("rid", "ts", "x", "a", "b")
        .explode("x", "a", "b")
        .filter(
            pl.col("x").is_not_null() & pl.col("a").is_not_null() & pl.col("b").is_not_null()
            & (pl.col("x") != pl.col("a")) & (pl.col("a") != pl.col("b"))
        )
    )
    w("triples", _first_seen(t, ["x", "a", "b"], paths))
    # 7. identifier v5: prefixes traversing a valley-violating triple this hour (a learned from provider/peer b and
    #    exported to provider/peer x), per (x, a, b, prefix): first_ts, n_msgs, n_peers. Novelty is resolved by the
    #    consumer across days; here every violating (triple, prefix) of the hour is recorded.
    if rel_path is not None:
        rel = pl.read_parquet(rel_path).with_columns(pl.col("u").cast(pl.UInt32), pl.col("v").cast(pl.UInt32))
        # classify the hour's *distinct* triples (~10⁵) against CAIDA, then keep only the exploded rows on violating ones
        # (joining the ~10⁷ exploded rows directly doubled the ingest time in the petest run)
        bad = (t.select("x", "a", "b").unique()
                 .join(rel.rename({"u": "a", "v": "b", "kind": "learned_from"}), on=["a", "b"], how="inner")
                 .join(rel.rename({"u": "a", "v": "x", "kind": "exported_to"}), on=["a", "x"], how="inner")
                 .filter(pl.col("learned_from").is_in(["provider", "peer"]) & pl.col("exported_to").is_in(["provider", "peer"])))
        v = (t.join(bad, on=["x", "a", "b"], how="inner")
               .join(paths.select("rid", "peer_ip", "prefix"), on="rid", how="left")
               .group_by("x", "a", "b", "prefix")
               .agg(first_ts=pl.col("ts").first(), n_msgs=pl.len().cast(pl.UInt32), n_peers=pl.col("peer_ip").n_unique().cast(pl.UInt16),
                    learned_from=pl.col("learned_from").first(), exported_to=pl.col("exported_to").first()))
        w("violations", v)


def _side(side_dir: Path, kind: str) -> pl.LazyFrame:
    files = sorted(side_dir.glob(f"part-*.{kind}.parquet"))
    if not files:
        raise FileNotFoundError(f"no {kind} side tables in {side_dir}")
    return pl.concat([pl.scan_parquet(str(f)) for f in files], how="vertical_relaxed")


def _merge_first_seen(side_dir: Path, kind: str, keys: list[str], collector: str) -> pl.DataFrame:
    return (
        _side(side_dir, kind)
        .sort("first_ts")
        .group_by(keys, maintain_order=True)
        .agg(
            first_ts=pl.col("first_ts").first(),
            n_msgs=pl.col("n_msgs").sum().cast(pl.UInt32),
            example_prefix=pl.col("example_prefix").first(),
            example_path=pl.col("example_path").first(),
        )
        .with_columns(collector=pl.lit(collector))
        .select("collector", *keys, "first_ts", "n_msgs", "example_prefix", "example_path")
        .sort("first_ts")
        .collect()
    )


def merge_violations(side_dir: Path, collector: str) -> pl.DataFrame | None:
    """Identifier v5 day table: per (x, a, b, prefix) first_ts, n_msgs (sum), n_peers (max over hours). None if absent."""
    if not list(side_dir.glob("part-*.violations.parquet")):
        return None
    return (
        _side(side_dir, "violations")
        .sort("first_ts")
        .group_by(["x", "a", "b", "prefix"], maintain_order=True)
        .agg(first_ts=pl.col("first_ts").first(), n_msgs=pl.col("n_msgs").sum().cast(pl.UInt32), n_peers=pl.col("n_peers").max(),
             learned_from=pl.col("learned_from").first(), exported_to=pl.col("exported_to").first())
        .with_columns(collector=pl.lit(collector))
        .select("collector", "x", "a", "b", "prefix", "first_ts", "n_msgs", "n_peers", "learned_from", "exported_to")
        .sort("first_ts")
        .collect()
    )


def merge_side_tables(side_dir: Path, collector: str) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Merge the per-hour side tables of one collector-day → (minute_signals, origin_changes, new_edges, new_triples)
    with exactly the schemas of aggregate.minute_signals / origin_changes / new_edges / new_triples."""
    agg = (
        _side(side_dir, "minutes")
        .with_columns(collector=pl.lit(collector))
        .select("collector", "minute", "n_ann", "n_wd", "n_prefixes", "n_peers", "n_origins", "n_paths")
        .sort("collector", "minute")
        .collect()
    )
    # origin changes = within-hour changes ∪ changes across consecutive observed hours of the same (peer, prefix).
    # The boundary table is restricted to prefixes announced with ≥ 2 distinct origins today (as the scan does).
    multi = (
        _side(side_dir, "prefix_origins").unique().group_by("prefix").len().filter(pl.col("len") >= 2).select("prefix").collect()
    )
    oc_cols = ["ts", "collector", "peer_ip", "peer_asn", "prefix", "prev_origin", "new_origin", "as_path"]
    inner = _side(side_dir, "oc_changes").with_columns(collector=pl.lit(collector)).select(oc_cols).collect()
    if multi.is_empty():
        boundary = inner.clear()
    else:
        boundary = (
            _side(side_dir, "oc_boundary")
            .filter(pl.col("prefix").is_in(multi["prefix"].implode()))
            .sort("peer_ip", "prefix", "hour")
            .with_columns(prev_last=pl.col("last_origin").shift(1).over("peer_ip", "prefix"))
            .filter(pl.col("prev_last").is_not_null() & (pl.col("prev_last") != pl.col("first_origin")))
            .select(
                pl.col("first_ts").alias("ts"),
                pl.lit(collector).alias("collector"),
                "peer_ip",
                "peer_asn",
                "prefix",
                pl.col("prev_last").alias("prev_origin"),
                pl.col("first_origin").alias("new_origin"),
                pl.col("first_path").alias("as_path"),
            )
            .collect()
        )
    oc = pl.concat([inner, boundary], how="vertical_relaxed").sort("peer_ip", "prefix", "ts")
    ne = _merge_first_seen(side_dir, "edges", ["a", "b"], collector)
    nt = _merge_first_seen(side_dir, "triples", ["x", "a", "b"], collector)
    return agg, oc, ne, nt


def violations_from_parquet(day_dir: Path, collector: str, rel_path: Path) -> pl.DataFrame:
    """Identifier v5 day table from kept hourly Parquet (backfill for beacon-week days): run the per-hour side-table
    computation for the violations only, into a temporary side dir, then merge."""
    import shutil
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="vio_", dir=str(day_dir.parent)))
    try:
        rel = pl.read_parquet(rel_path).with_columns(pl.col("u").cast(pl.UInt32), pl.col("v").cast(pl.UInt32))
        for part in sorted(day_dir.glob("part-*.parquet")):
            hour = part.stem.split("-")[1]
            df = pl.read_parquet(part).with_columns(pl.col("collector").cast(pl.String))
            paths = _hops(df)
            slim = paths.select("rid", "ts", "hops")
            paths = paths.drop("hops")
            t = (slim.filter(pl.col("hops").list.len() >= 3)
                     .with_columns(x=pl.col("hops").list.slice(0, pl.col("hops").list.len() - 2),
                                   a=pl.col("hops").list.slice(1, pl.col("hops").list.len() - 2), b=pl.col("hops").list.slice(2))
                     .select("rid", "ts", "x", "a", "b").explode("x", "a", "b")
                     .filter(pl.col("x").is_not_null() & pl.col("a").is_not_null() & pl.col("b").is_not_null()
                             & (pl.col("x") != pl.col("a")) & (pl.col("a") != pl.col("b"))))
            bad = (t.select("x", "a", "b").unique()
                     .join(rel.rename({"u": "a", "v": "b", "kind": "learned_from"}), on=["a", "b"], how="inner")
                     .join(rel.rename({"u": "a", "v": "x", "kind": "exported_to"}), on=["a", "x"], how="inner")
                     .filter(pl.col("learned_from").is_in(["provider", "peer"]) & pl.col("exported_to").is_in(["provider", "peer"])))
            v = (t.join(bad, on=["x", "a", "b"], how="inner").join(paths.select("rid", "peer_ip", "prefix"), on="rid", how="left")
                   .group_by("x", "a", "b", "prefix")
                   .agg(first_ts=pl.col("ts").first(), n_msgs=pl.len().cast(pl.UInt32), n_peers=pl.col("peer_ip").n_unique().cast(pl.UInt16),
                        learned_from=pl.col("learned_from").first(), exported_to=pl.col("exported_to").first()))
            v.write_parquet(tmp / f"part-{hour}.violations.parquet", compression="zstd", compression_level=1)
        out = merge_violations(tmp, collector)
        return out if out is not None else pl.DataFrame()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
