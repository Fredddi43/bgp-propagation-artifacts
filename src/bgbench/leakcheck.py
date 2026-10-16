"""Identifier v3 leak signal: valley-free check of first-seen AS adjacencies against CAIDA relationships.

For a first-seen edge (a, b) on its example path [peer … x, a, b, y … origin] the route flows b → a (b exported
to a). The classic route leak (RFC 7908 types 1–4) is an AS exporting a route learned from a provider or peer to
another provider or peer. With CAIDA rel: 'a provider of b' (-1) or 'peer' (0):
  - the AS under test is `a` if it received from `b` and exports to `x`: leak if rel(b→a) ∈ {provider→customer? no}
Concretely, for the triple (x, a, b): a learned the route from b and exported it to x.
  learned_from_kind = provider if b is a's provider, peer if peer, customer if b is a's customer
  exported_to_kind  = provider if x is a's provider, peer if peer, customer if x is a's customer
  valley-free violation (leak by a) ⇔ learned_from_kind ∈ {provider, peer} AND exported_to_kind ∈ {provider, peer}.
Edges absent from CAIDA are 'unknown' (novel adjacency) and are reported separately.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from .diffusion import load_asgraph


def rel_parquet(month: str) -> Path:
    """Relationship table cached as Parquet next to the CAIDA file (ingest workers read it; downloads CAIDA if needed)."""
    from . import config

    p = config.DATA_ROOT / "graphs" / f"{month}01.rel.parquet"
    if not p.exists():
        relationship_table(month).write_parquet(p)
    return p


def relationship_table(month: str) -> pl.DataFrame:
    """Directed rows (u, v, kind_of_v_for_u): 'provider' | 'customer' | 'peer'."""
    g = load_asgraph(month)
    import numpy as np

    rows = []
    for M, kind in ((g.c2p, "provider"), (g.p2c, "customer"), (g.p2p, "peer")):
        coo = M.tocoo()
        rows.append(
            pl.DataFrame(
                {
                    "u": g.asns[coo.row].astype(np.int64),
                    "v": g.asns[coo.col].astype(np.int64),
                    "kind": [kind] * len(coo.row),
                }
            )
        )
    return pl.concat(rows).unique(["u", "v"])


def classify_new_edges(ne: pl.DataFrame, month: str) -> pl.DataFrame:
    """Add learned_from / exported_to kinds and a `leak_like` flag to first-seen-edge rows (needs example_path)."""
    rel = relationship_table(month)
    d = ne.with_columns(
        hops=pl.col("example_path")
        .str.split(" ")
        .list.eval(pl.element().cast(pl.Int64, strict=False))
    )
    # position of a in hops (a is collector-side of b)
    idx = []
    for hops, a in zip(d["hops"].to_list(), d["a"].to_list()):
        try:
            idx.append(hops.index(int(a)))
        except (ValueError, TypeError):
            idx.append(None)
    d = d.with_columns(pl.Series("ia", idx, dtype=pl.Int64))
    d = d.with_columns(
        x=pl.when(pl.col("ia") > 0)
        .then(pl.col("hops").list.get(pl.col("ia") - 1, null_on_oob=True))
        .otherwise(None),
        a64=pl.col("a").cast(pl.Int64),
        b64=pl.col("b").cast(pl.Int64),
    )
    d = d.join(
        rel.rename({"u": "a64", "v": "b64", "kind": "learned_from"}), on=["a64", "b64"], how="left"
    ).join(rel.rename({"u": "a64", "v": "x", "kind": "exported_to"}), on=["a64", "x"], how="left")
    d = d.with_columns(
        edge_known=pl.col("learned_from").is_not_null(),
        leak_like=pl.col("learned_from").is_in(["provider", "peer"])
        & pl.col("exported_to").is_in(["provider", "peer"]),
    )
    return d.drop("hops", "a64", "b64")


def eval_leaks_v3(
    classified: pl.DataFrame,
    leaks: pl.DataFrame,
    slack_min: int = 10,
    require_leak_like: bool = True,
) -> dict:
    """Cloudflare leak rows (leak_seg JSON list [a,b,c] or 'a-b-c', min_ts, peer_count): hit if a first-seen edge
    of the segment (either direction) that is leak_like (or unknown) lies within ±slack."""
    from .identifier2 import eval_leaks

    cands = (
        classified.filter(pl.col("leak_like") | ~pl.col("edge_known"))
        if require_leak_like
        else classified
    )
    cands = cands.select("a", "b", "first_ts", pl.lit(1).alias("n_collectors"))
    return eval_leaks(cands, leaks, slack_min)


# ------------------------------------------------------------------------------------------------------------------
# Identifier v4 (ADR-0018, #26): the same valley-free test on first-seen *triples* (x, a, b) — the unit that actually
# carries the leak semantics (a learned the route from b and exported it to x), with no example-path parsing needed.
# ------------------------------------------------------------------------------------------------------------------


def load_new_triples(collectors: list[str], start: str, end: str) -> pl.DataFrame:
    from . import config
    from .identifier2 import _days

    root = config.DATA_ROOT / "prefix_events"
    files = [root / c / f"{d}.new_triples.parquet" for c in collectors for d in _days(start, end)]
    files = [f for f in files if f.exists()]
    if not files:
        return pl.DataFrame()
    return pl.concat(
        [pl.read_parquet(f).with_columns(pl.col("collector").cast(pl.String)) for f in files], how="diagonal_relaxed"
    )


def triple_candidates(NT: pl.DataFrame, min_collectors: int = 2, bin_min: int = 5) -> pl.DataFrame:
    """Cross-day novelty within the loaded window (a triple's first day only), binned, ≥ min_collectors agreeing."""
    if NT.is_empty():
        return NT
    keys = ["x", "a", "b"]
    first_day = NT.with_columns(day=pl.col("first_ts").dt.date()).group_by(keys).agg(day0=pl.col("day").min())
    nt = NT.with_columns(day=pl.col("first_ts").dt.date()).join(first_day, on=keys).filter(pl.col("day") == pl.col("day0"))
    return (
        nt.with_columns(bin=pl.col("first_ts").dt.truncate(f"{bin_min}m"))
        .group_by(*keys, "bin")
        .agg(
            n_collectors=pl.col("collector").n_unique(),
            first_ts=pl.col("first_ts").min(),
            n_msgs=pl.col("n_msgs").sum(),
            example_prefix=pl.col("example_prefix").first(),
            example_path=pl.col("example_path").first(),
        )
        .filter(pl.col("n_collectors") >= min_collectors)
        .sort("first_ts")
    )


def classify_triples(cand: pl.DataFrame, month: str) -> pl.DataFrame:
    """learned_from = rel(a, b), exported_to = rel(a, x); leak_like ⇔ both ∈ {provider, peer}; *_known flags."""
    rel = relationship_table(month)
    d = cand.with_columns(x64=pl.col("x").cast(pl.Int64), a64=pl.col("a").cast(pl.Int64), b64=pl.col("b").cast(pl.Int64))
    d = d.join(rel.rename({"u": "a64", "v": "b64", "kind": "learned_from"}), on=["a64", "b64"], how="left").join(
        rel.rename({"u": "a64", "v": "x64", "kind": "exported_to"}), on=["a64", "x64"], how="left"
    )
    return d.with_columns(
        in_known=pl.col("learned_from").is_not_null(),
        out_known=pl.col("exported_to").is_not_null(),
        leak_like=pl.col("learned_from").is_in(["provider", "peer"]) & pl.col("exported_to").is_in(["provider", "peer"]),
    ).drop("x64", "a64", "b64")


def eval_leaks_v4(classified: pl.DataFrame, leaks: pl.DataFrame, slack_min: int = 10, mode: str = "leak_like") -> dict:
    """Match Cloudflare leak segments against the two adjacencies (a, b) and (x, a) of each candidate triple.
    mode: 'all' | 'leak_like' | 'leak_like_or_unknown' (unknown = either adjacency absent from CAIDA)."""
    from .identifier2 import eval_leaks

    if mode == "leak_like":
        c = classified.filter(pl.col("leak_like"))
    elif mode == "leak_like_or_unknown":
        c = classified.filter(pl.col("leak_like") | ~pl.col("in_known") | ~pl.col("out_known"))
    else:
        c = classified
    if c.is_empty():
        return {"labels": leaks.height, "hit": 0, "candidates": 0}
    edges = pl.concat(
        [
            c.select("a", "b", "first_ts", "n_collectors"),
            c.select(pl.col("x").alias("a"), pl.col("a").alias("b"), "first_ts", "n_collectors"),
        ]
    )
    res = eval_leaks(edges, leaks, slack_min)
    res["candidates"] = c.height
    return res


# ------------------------------------------------------------------------------------------------------------------
# Identifier v5: prefix-level valley violations. A leak event = a leaker AS a whose violating triples start carrying
# prefixes they did not carry before (cross-day first-seen (x, a, b, prefix) within the window), grouped per 5-min bin.
# ------------------------------------------------------------------------------------------------------------------


def load_violations(collectors: list[str], start: str, end: str) -> pl.DataFrame:
    from . import config
    from .identifier2 import _days

    root = config.DATA_ROOT / "prefix_events"
    files = [root / c / f"{d}.violations.parquet" for c in collectors for d in _days(start, end)]
    files = [f for f in files if f.exists()]
    if not files:
        return pl.DataFrame()
    return pl.concat([pl.read_parquet(f).with_columns(pl.col("collector").cast(pl.String)) for f in files], how="diagonal_relaxed")


def violation_events(V: pl.DataFrame, min_collectors: int = 2, min_prefixes: int = 1, bin_min: int = 5, warmup_days: int = 7) -> pl.DataFrame:
    """Events from newly violating (triple, prefix) pairs: first day in the window per (x, a, b, prefix) — the first
    `warmup_days` of the window only seed the state and emit no events — then per leaker a and bin: prefixes, collectors,
    msgs, peers, distinct sources b and upstreams x."""
    if V.is_empty():
        return V
    keys = ["x", "a", "b", "prefix"]
    first = V.group_by(keys).agg(first_ts=pl.col("first_ts").min())
    day0 = first["first_ts"].min().date() if first.height else None
    new = (V.join(first.rename({"first_ts": "first_ts_win"}), on=keys)
             .filter(pl.col("first_ts").dt.date() == pl.col("first_ts_win").dt.date())        # rows of the first day
             .filter(pl.col("first_ts_win").dt.date() >= pl.lit(day0) + pl.duration(days=warmup_days)))
    return (new.with_columns(bin=pl.col("first_ts").dt.truncate(f"{bin_min}m"))
               .group_by("a", "bin")
               .agg(t0=pl.col("first_ts").min(), n_prefixes=pl.col("prefix").n_unique(), n_collectors=pl.col("collector").n_unique(),
                    n_msgs=pl.col("n_msgs").sum(), n_peers=pl.col("n_peers").max(), n_sources=pl.col("b").n_unique(), n_upstreams=pl.col("x").n_unique(),
                    example_prefix=pl.col("prefix").first())
               .filter((pl.col("n_collectors") >= min_collectors) & (pl.col("n_prefixes") >= min_prefixes))
               .sort("t0"))


def eval_leaks_v5(ev: pl.DataFrame, leaks: pl.DataFrame, slack_min: int = 10) -> dict:
    """Label recall by leaker ASN (leak_seg[1]) within ±slack, overall and by Cloudflare peer_count bucket."""
    import re

    if ev.is_empty() or leaks.is_empty():
        return {"labels": leaks.height, "hit": 0}
    leaker = []
    for v in leaks["leak_seg"].to_list():
        seg = re.sub(r"[\[\]\" ]", "", v).split(",")
        leaker.append(int(seg[1]) if len(seg) >= 2 and seg[1] else 0)
    lk = leaks.with_columns(pl.Series("leaker", leaker, dtype=pl.UInt32), pl.col("peer_count").cast(pl.Int64)).with_row_index("lid")
    j = lk.join(ev.select(pl.col("a").cast(pl.UInt32).alias("leaker"), "t0"), on="leaker", how="left").with_columns(
        hit=((pl.col("t0") - pl.col("min_ts")).dt.total_seconds().abs() <= slack_min * 60).fill_null(False))
    per = j.group_by("lid", "peer_count").agg(hit=pl.col("hit").any())
    by = (per.with_columns(b=pl.when(pl.col("peer_count") < 10).then(pl.lit("1-9")).when(pl.col("peer_count") < 50).then(pl.lit("10-49")).otherwise(pl.lit("50+")))
             .group_by("b").agg(n=pl.len(), recall=pl.col("hit").mean()).sort("b").to_dicts())
    return {"labels": per.height, "hit": int(per["hit"].sum()), "recall": round(float(per["hit"].mean()), 4), "by_size": by}
