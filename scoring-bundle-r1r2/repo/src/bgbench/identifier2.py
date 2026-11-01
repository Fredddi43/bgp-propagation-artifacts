"""Event identifier v2 (ADR-0013 as amended): per-prefix state signals with cross-collector agreement.

Inputs: prefix_events/<collector>/<date>.{origin_changes,new_edges}.parquet (written by ingest-day).
Candidates:
- origin-change candidates: (prefix, new_origin) observed as an origin change at ≥ m collectors within a
  `bin` window (default 5 min). MOAS/hijack/misconfiguration family.
- new-edge candidates: AS adjacency (a, b) first seen in the window at ≥ m collectors within `bin`, and not
  seen on any earlier day of the loaded window (cross-day novelty within the analysis window). Leak family.
Evaluation against Cloudflare Radar labels is per event: a hijack (prefixes, hijacker_asn, min_hijack_ts)
is hit if an origin-change candidate with one of its prefixes and new_origin == hijacker lies within ±slack;
a leak (leak_seg 'a-b-c', min_ts) is hit if a new-edge candidate containing an adjacency of the segment
lies within ±slack. Null model: same test with the candidate timestamps shifted by a random offset.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import polars as pl

from . import config


def _days(start: str, end: str) -> list[str]:
    a, b = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    return [(a + dt.timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]


def load_prefix_events(
    collectors: list[str], start: str, end: str
) -> tuple[pl.DataFrame, pl.DataFrame]:
    root = config.DATA_ROOT / "prefix_events"
    oc, ne = [], []
    for c in collectors:
        for d in _days(start, end):
            f1, f2 = root / c / f"{d}.origin_changes.parquet", root / c / f"{d}.new_edges.parquet"
            if f1.exists():
                oc.append(str(f1))
            if f2.exists():
                ne.append(str(f2))
    if not oc:
        raise FileNotFoundError("no prefix_events for the requested collectors/days")

    def _load(paths: list[str]) -> pl.DataFrame:
        frames = [
            pl.read_parquet(f).with_columns(pl.col("collector").cast(pl.String)) for f in paths
        ]
        return pl.concat(frames, how="diagonal_relaxed") if frames else pl.DataFrame()

    return _load(oc), _load(ne)


def origin_change_candidates(
    OC: pl.DataFrame, min_collectors: int = 2, bin_min: int = 5
) -> pl.DataFrame:
    return (
        OC.with_columns(bin=pl.col("ts").dt.truncate(f"{bin_min}m"))
        .group_by("prefix", "new_origin", "bin")
        .agg(
            n_collectors=pl.col("collector").n_unique(),
            n_peers=pl.struct("collector", "peer_ip").n_unique(),
            first_ts=pl.col("ts").min(),
            prev_origins=pl.col("prev_origin").unique().sort(),
        )
        .filter(pl.col("n_collectors") >= min_collectors)
        .sort("first_ts")
    )


def new_edge_candidates(
    NE: pl.DataFrame, min_collectors: int = 2, bin_min: int = 5
) -> pl.DataFrame:
    if NE.is_empty():
        return NE
    # cross-day novelty within the loaded window: keep an edge's first day only
    first_day = (
        NE.with_columns(day=pl.col("first_ts").dt.date())
        .group_by("a", "b")
        .agg(day0=pl.col("day").min())
    )
    ne = (
        NE.with_columns(day=pl.col("first_ts").dt.date())
        .join(first_day, on=["a", "b"])
        .filter(pl.col("day") == pl.col("day0"))
    )
    return (
        ne.with_columns(bin=pl.col("first_ts").dt.truncate(f"{bin_min}m"))
        .group_by("a", "b", "bin")
        .agg(
            n_collectors=pl.col("collector").n_unique(),
            first_ts=pl.col("first_ts").min(),
            n_msgs=pl.col("n_msgs").sum(),
            example_prefix=(pl.col("example_prefix") if "example_prefix" in NE.columns else pl.col("prefix")).first(),
        )
        .filter(pl.col("n_collectors") >= min_collectors)
        .sort("first_ts")
    )


def _shift(df: pl.DataFrame, col: str, seconds: float, span: tuple | None = None) -> pl.DataFrame:
    """Null model: shift timestamps by `seconds`, wrapping around the analysis window [start, end) so shifted
    candidates stay inside the labelled period (a non-wrapping shift pushes candidates past the end where no
    label can match them and biases the random baseline downward)."""
    shifted = pl.col(col) + pl.duration(seconds=int(seconds))
    if span is not None:
        start, end = span
        total = int((end - start).total_seconds())
        rel = (shifted - pl.lit(start)).dt.total_seconds()
        shifted = pl.lit(start) + pl.duration(seconds=(rel % total))
    return df.with_columns(shifted.alias(col))



def eval_hijacks(cands: pl.DataFrame, hij: pl.DataFrame, slack_min: int = 10) -> dict:
    """hij: Cloudflare hijack rows (prefixes JSON list, hijacker_asn, min_hijack_ts, peer_ip_count)."""
    if cands.is_empty() or hij.is_empty():
        return {"labels": hij.height, "hit": 0, "recall": 0.0, "by_size": []}
    h = (
        hij.select(
            pl.col("prefixes"),
            pl.col("hijacker_asn").cast(pl.UInt32),
            pl.col("min_hijack_ts").alias("t"),
            pl.col("peer_ip_count").cast(pl.Float64).alias("size"),
        )
        .with_columns(pl.col("prefixes").str.json_decode(pl.List(pl.String)))
        .with_row_index("lid")
        .explode("prefixes")
        .rename({"prefixes": "prefix"})
    )
    j = h.join(
        cands.select(
            "prefix", pl.col("new_origin").alias("hijacker_asn"), "first_ts", "n_collectors"
        ),
        on=["prefix", "hijacker_asn"],
        how="inner",
    ).filter((pl.col("first_ts") - pl.col("t")).dt.total_seconds().abs() <= slack_min * 60)
    hit_ids = set(j["lid"].to_list())
    per = h.unique("lid").with_columns(hit=pl.col("lid").is_in(list(hit_ids)))
    by = (
        per.with_columns(
            bucket=pl.when(pl.col("size") >= 50)
            .then(pl.lit("50+"))
            .when(pl.col("size") >= 10)
            .then(pl.lit("10-49"))
            .otherwise(pl.lit("1-9"))
        )
        .group_by("bucket")
        .agg(n=pl.len(), recall=pl.col("hit").mean())
        .sort("bucket")
    )
    return {
        "labels": per.height,
        "hit": len(hit_ids),
        "recall": round(len(hit_ids) / per.height, 3),
        "by_size": by.to_dicts(),
    }


def eval_leaks(cands: pl.DataFrame, leaks: pl.DataFrame, slack_min: int = 10) -> dict:
    """leaks: Cloudflare leak rows (leak_seg 'a-b-c' string, min_ts, peer_count)."""
    if cands.is_empty() or leaks.is_empty():
        return {"labels": leaks.height, "hit": 0}
    l = (
        leaks.select(
            pl.col("leak_seg"),
            pl.col("min_ts").alias("t"),
            pl.col("peer_count").cast(pl.Float64).alias("size"),
        )
        .with_row_index("lid")
        .with_columns(
            seg=pl.col("leak_seg")
            .str.replace_all(r"[\[\]\" ]", "")
            .str.split(",")
            .list.eval(pl.element().cast(pl.UInt32, strict=False))
        )
    )
    # segment adjacencies (a,b) in both directions
    pairs = (
        l.with_columns(
            a=pl.col("seg").list.slice(0, pl.col("seg").list.len() - 1),
            b=pl.col("seg").list.slice(1),
        )
        .explode("a", "b")
        .drop_nulls(["a", "b"])
    )
    both = pl.concat(
        [
            pairs.select("lid", "t", "size", "a", "b"),
            pairs.select("lid", "t", "size", pl.col("b").alias("a"), pl.col("a").alias("b")),
        ]
    )
    j = both.join(
        cands.select("a", "b", "first_ts", "n_collectors"), on=["a", "b"], how="inner"
    ).filter((pl.col("first_ts") - pl.col("t")).dt.total_seconds().abs() <= slack_min * 60)
    hit_ids = set(j["lid"].to_list())
    per = l.with_columns(hit=pl.col("lid").is_in(list(hit_ids)))
    by = (
        per.with_columns(
            bucket=pl.when(pl.col("size") >= 50)
            .then(pl.lit("50+"))
            .when(pl.col("size") >= 10)
            .then(pl.lit("10-49"))
            .otherwise(pl.lit("1-9"))
        )
        .group_by("bucket")
        .agg(n=pl.len(), recall=pl.col("hit").mean())
        .sort("bucket")
    )
    return {
        "labels": per.height,
        "hit": len(hit_ids),
        "recall": round(len(hit_ids) / per.height, 3),
        "by_size": by.to_dicts(),
    }


def run(
    collectors: list[str],
    start: str,
    end: str,
    labels_dir: Path | None,
    min_collectors: int = 2,
    bin_min: int = 5,
    slack_min: int = 10,
    n_random: int = 10,
    seed: int = 0,
) -> dict:
    OC, NE = load_prefix_events(collectors, start, end)
    oc_c = origin_change_candidates(OC, min_collectors, bin_min)
    ne_c = new_edge_candidates(NE, min_collectors, bin_min)
    out_dir = config.DATA_ROOT / "identifier2" / f"{start}_{end}" / f"m{min_collectors}_b{bin_min}"
    out_dir.mkdir(parents=True, exist_ok=True)
    oc_c.with_columns(pl.col("prev_origins").cast(pl.List(pl.String)).list.join(",")).write_parquet(
        out_dir / "origin_change_candidates.parquet"
    )
    if not ne_c.is_empty():
        ne_c.write_parquet(out_dir / "new_edge_candidates.parquet")
    res = {
        "collectors": len(collectors),
        "origin_change_rows": OC.height,
        "new_edge_rows": NE.height,
        "oc_candidates": oc_c.height,
        "oc_candidate_prefixes": oc_c["prefix"].n_unique() if oc_c.height else 0,
        "ne_candidates": ne_c.height if not ne_c.is_empty() else 0,
        "params": {"min_collectors": min_collectors, "bin_min": bin_min, "slack_min": slack_min},
        "out": str(out_dir),
    }
    if labels_dir:
        rng = np.random.default_rng(seed)
        span_s = (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days * 86400 + 86400
        span = (dt.datetime.fromisoformat(start).replace(tzinfo=dt.UTC), dt.datetime.fromisoformat(end).replace(tzinfo=dt.UTC) + dt.timedelta(days=1))
        hf, lf = (
            Path(labels_dir) / "cloudflare_hijacks.parquet",
            Path(labels_dir) / "cloudflare_leaks.parquet",
        )
        if hf.exists():
            hij = pl.read_parquet(hf).with_columns(
                pl.col("min_hijack_ts").str.to_datetime(time_zone="UTC", strict=False)
            )
            hij = _window_labels(hij, "min_hijack_ts", start, end)
            res["hijacks"] = eval_hijacks(oc_c, hij, slack_min)
            res["hijacks_random"] = [
                eval_hijacks(
                    _shift(oc_c, "first_ts", rng.uniform(3600, span_s - 3600), span), hij, slack_min
                )["recall"]
                for _ in range(n_random)
            ]
        if lf.exists() and not ne_c.is_empty():
            leaks = pl.read_parquet(lf).with_columns(
                pl.col("min_ts").str.to_datetime(time_zone="UTC", strict=False)
            )
            leaks = _window_labels(leaks, "min_ts", start, end)
            res["leaks"] = eval_leaks(ne_c, leaks, slack_min)
            res["leaks_random"] = [
                eval_leaks(
                    _shift(ne_c, "first_ts", rng.uniform(3600, span_s - 3600), span), leaks, slack_min
                )["recall"]
                for _ in range(n_random)
            ]
    (out_dir / "summary.json").write_text(json.dumps(res, indent=1, default=str))
    return res


# ---- event-level dedupe + persistent-flapper whitelist ----------------------------------------------
def dedupe_origin_events(
    oc_c: pl.DataFrame, flapper_bins: int = 20, merge_gap_min: int = 60
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Collapse bin-level origin-change candidates into events: consecutive bins of the same (prefix, new_origin)
    closer than merge_gap_min form one event. Pairs with ≥ flapper_bins bins in the window are persistent
    multi-origin prefixes (anycast, multi-origin CDNs) and are whitelisted out. Returns (events, whitelist)."""
    pairs = oc_c.group_by("prefix", "new_origin").agg(bins=pl.len())
    whitelist = pairs.filter(pl.col("bins") >= flapper_bins).select("prefix", "new_origin", "bins")
    kept = oc_c.join(
        whitelist.select("prefix", "new_origin"), on=["prefix", "new_origin"], how="anti"
    ).sort("prefix", "new_origin", "bin")
    gap = (
        (pl.col("bin") - pl.col("bin").shift(1))
        .dt.total_minutes()
        .over("prefix", "new_origin")
        .fill_null(10**9)
    )
    kept = kept.with_columns(new_ev=(gap > merge_gap_min).cast(pl.Int64)).with_columns(
        ev=pl.col("new_ev").cum_sum().over("prefix", "new_origin")
    )
    events = (
        kept.group_by("prefix", "new_origin", "ev")
        .agg(
            first_ts=pl.col("first_ts").min(),
            last_bin=pl.col("bin").max(),
            n_bins=pl.len(),
            max_collectors=pl.col("n_collectors").max(),
            max_peers=pl.col("n_peers").max(),
            prev_origins=pl.col("prev_origins").flatten().unique().sort(),
        )
        .drop("ev")
        .sort("first_ts")
    )
    return events, whitelist


def run_events(
    collectors: list[str],
    start: str,
    end: str,
    labels_dir: Path | None,
    min_collectors: int = 2,
    bin_min: int = 5,
    flapper_bins: int = 20,
    flapper_per_week: bool = True,
    slack_min: int = 10,
    n_random: int = 10,
    seed: int = 0,
) -> dict:
    OC, _ = load_prefix_events(collectors, start, end)
    oc_c = origin_change_candidates(OC, min_collectors, bin_min)
    days = (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days + 1
    # F is specified per week; a month has ~4.3× the bins of a week, so the same absolute F whitelists 4× more
    # (2024 inventory: 7,827 labelled hijacks whitelisted away at a flat F = 50)
    f_eff = max(1, round(flapper_bins * days / 7)) if flapper_per_week else flapper_bins
    events, wl = dedupe_origin_events(oc_c, f_eff)
    out_dir = (
        config.DATA_ROOT
        / "identifier2"
        / f"{start}_{end}"
        / f"m{min_collectors}_b{bin_min}_events_f{flapper_bins}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    events.with_columns(
        pl.col("prev_origins").cast(pl.List(pl.String)).list.join(",")
    ).write_parquet(out_dir / "origin_change_events.parquet")
    wl.write_parquet(out_dir / "flapper_whitelist.parquet")
    res = {
        "bin_candidates": oc_c.height,
        "events": events.height,
        "event_prefixes": events["prefix"].n_unique() if events.height else 0,
        "whitelisted_pairs": wl.height,
        "events_per_day": round(
            events.height
            / max((dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days + 1, 1),
            1,
        ),
        "params": {
            "min_collectors": min_collectors,
            "bin_min": bin_min,
            "flapper_bins": flapper_bins,
        },
        "out": str(out_dir),
    }
    if labels_dir and (Path(labels_dir) / "cloudflare_hijacks.parquet").exists():
        hij = pl.read_parquet(Path(labels_dir) / "cloudflare_hijacks.parquet").with_columns(
            pl.col("min_hijack_ts").str.to_datetime(time_zone="UTC", strict=False)
        )
        hij = _window_labels(hij, "min_hijack_ts", start, end)
        ev_as_cands = events.select(
            "prefix", "new_origin", "first_ts", pl.col("max_collectors").alias("n_collectors")
        )
        rng = np.random.default_rng(seed)
        span_s = ((dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days + 1) * 86400
        span = (dt.datetime.fromisoformat(start).replace(tzinfo=dt.UTC), dt.datetime.fromisoformat(end).replace(tzinfo=dt.UTC) + dt.timedelta(days=1))
        res["hijacks"] = eval_hijacks(ev_as_cands, hij, slack_min)
        res["hijacks_random"] = [
            eval_hijacks(
                _shift(ev_as_cands, "first_ts", rng.uniform(3600, span_s - 3600), span), hij, slack_min
            )["recall"]
            for _ in range(n_random)
        ]
        # how many labelled hijacks were lost to the whitelist?
        h = (
            hij.select(
                pl.col("prefixes").str.json_decode(pl.List(pl.String)),
                pl.col("hijacker_asn").cast(pl.UInt32),
            )
            .with_row_index("lid")
            .explode("prefixes")
            .rename({"prefixes": "prefix"})
        )
        lost = h.join(
            wl.select("prefix", pl.col("new_origin").alias("hijacker_asn")),
            on=["prefix", "hijacker_asn"],
            how="inner",
        )["lid"].n_unique()
        res["hijacks_whitelisted_away"] = lost
    (out_dir / "summary.json").write_text(json.dumps(res, indent=1, default=str))
    return res


def trailing_whitelist(
    collectors: list[str],
    start: str,
    end: str,
    min_collectors: int = 2,
    bin_min: int = 5,
    flapper_bins: int = 20,
) -> pl.DataFrame:
    """Persistent multi-origin pairs from a *trailing* window (e.g. the 4 weeks before the analysis window), so the
    whitelist cannot absorb the events of the window being analysed. Same candidate definition as the analysis."""
    OC, _ = load_prefix_events(collectors, start, end)
    oc_c = origin_change_candidates(OC, min_collectors, bin_min)
    pairs = oc_c.group_by("prefix", "new_origin").agg(
        bins=pl.len(), days=pl.col("bin").dt.date().n_unique()
    )
    return pairs.filter(pl.col("bins") >= flapper_bins).select(
        "prefix", "new_origin", "bins", "days"
    )


def _window_labels(df: pl.DataFrame, ts_col: str, start: str, end: str) -> pl.DataFrame:
    """Restrict a label frame to [start, end + 1 day) — evaluating one month's candidates against a year of
    labels divides recall by twelve (2024 inventory bug, 2026-09-04)."""
    s = dt.datetime.fromisoformat(start).replace(tzinfo=dt.UTC)
    e = dt.datetime.fromisoformat(end).replace(tzinfo=dt.UTC) + dt.timedelta(days=1)
    return df.filter((pl.col(ts_col) >= pl.lit(s)) & (pl.col(ts_col) < pl.lit(e)))


def evaluate_saved_events(start: str, end: str, labels_dir: Path, min_collectors: int = 2, bin_min: int = 5,
                          flapper_bins: int = 50, slack_min: int = 10, n_random: int = 10, seed: int = 0) -> dict:
    """Re-score saved origin-change events (identifier2/<start>_<end>/m*_events_f*/origin_change_events.parquet)
    against labels restricted to the same window, with the circular-shift null model."""
    d = config.DATA_ROOT / "identifier2" / f"{start}_{end}" / f"m{min_collectors}_b{bin_min}_events_f{flapper_bins}"
    events = pl.read_parquet(d / "origin_change_events.parquet")
    hij = pl.read_parquet(Path(labels_dir) / "cloudflare_hijacks.parquet").with_columns(
        pl.col("min_hijack_ts").str.to_datetime(time_zone="UTC", strict=False))
    hij = _window_labels(hij, "min_hijack_ts", start, end)
    ev = events.select("prefix", "new_origin", "first_ts", pl.col("max_collectors").alias("n_collectors"))
    span = (dt.datetime.fromisoformat(start).replace(tzinfo=dt.UTC), dt.datetime.fromisoformat(end).replace(tzinfo=dt.UTC) + dt.timedelta(days=1))
    span_s = (span[1] - span[0]).total_seconds()
    rng = np.random.default_rng(seed)
    res = {"window": f"{start}..{end}", "events": events.height, "labels_in_window": hij.height,
           "hijacks": eval_hijacks(ev, hij, slack_min),
           "hijacks_random": [eval_hijacks(_shift(ev, "first_ts", rng.uniform(3600, span_s - 3600), span), hij, slack_min)["recall"] for _ in range(n_random)]}
    wl = pl.read_parquet(d / "flapper_whitelist.parquet")
    h = (hij.select(pl.col("prefixes").str.json_decode(pl.List(pl.String)), pl.col("hijacker_asn").cast(pl.UInt32)).with_row_index("lid").explode("prefixes").rename({"prefixes": "prefix"}))
    res["hijacks_whitelisted_away"] = h.join(wl.select("prefix", pl.col("new_origin").alias("hijacker_asn")), on=["prefix", "hijacker_asn"], how="inner")["lid"].n_unique()
    (d / "evaluation_windowed.json").write_text(json.dumps(res, indent=1, default=str))
    return res
