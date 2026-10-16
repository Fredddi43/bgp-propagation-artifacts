"""Sprint 3 step 2: leak *events* from the classified first-seen triples (leakcheck4 output).

A leak event = one leaker AS `a` whose valley-free-violating triples (x, a, b) appear at ≥ min_collectors collectors,
merged over consecutive 5-min bins (gap ≤ merge_bins). t₀ = first triple, extent proxies: distinct upstream x
(who accepted the leak), distinct b (where it was learned from), example prefixes, message count. Matched to the
Cloudflare leak labels by leaker ASN (leak_seg[1]) within ±slack.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import polars as pl

from . import config


def load_classified(start: str, end: str, m: int = 2) -> pl.DataFrame:
    f = config.DATA_ROOT / "identifier2" / f"{start}_{end}" / f"leakcheck4_m{m}" / "new_triples_classified.parquet"
    return pl.read_parquet(f)


def build_events(cl: pl.DataFrame, min_collectors: int = 2, min_msgs: int = 3, merge_bins: int = 1, mode: str = "leak_like") -> pl.DataFrame:
    c = cl.filter(pl.col("leak_like")) if mode == "leak_like" else cl.filter(pl.col("leak_like") | ~pl.col("in_known") | ~pl.col("out_known"))
    c = c.filter(pl.col("n_collectors") >= min_collectors)
    per_bin = (c.group_by("a", "bin").agg(t0=pl.col("first_ts").min(), t_last=pl.col("first_ts").max(), n_triples=pl.len(),
                                          n_collectors=pl.col("n_collectors").max(), n_msgs=pl.col("n_msgs").sum(),
                                          n_upstreams=pl.col("x").n_unique(), n_sources=pl.col("b").n_unique(),
                                          n_prefixes=pl.col("example_prefix").n_unique(), example_prefix=pl.col("example_prefix").first(),
                                          example_path=pl.col("example_path").first())
                 .sort("a", "bin"))
    # merge consecutive bins of the same leaker (gap ≤ merge_bins × 5 min) into one event
    per_bin = per_bin.with_columns(gap=(pl.col("bin") - pl.col("bin").shift(1).over("a")).dt.total_minutes())
    per_bin = per_bin.with_columns(new_event=(pl.col("gap").is_null() | (pl.col("gap") > 5 * merge_bins)).cast(pl.Int32))
    per_bin = per_bin.with_columns(event_no=pl.col("new_event").cum_sum().over("a"))
    ev = (per_bin.group_by("a", "event_no").agg(t0=pl.col("t0").min(), t_last=pl.col("t_last").max(), bins=pl.len(),
                                                n_triples=pl.col("n_triples").sum(), n_collectors=pl.col("n_collectors").max(),
                                                n_msgs=pl.col("n_msgs").sum(), n_upstreams=pl.col("n_upstreams").max(), n_sources=pl.col("n_sources").max(),
                                                n_prefixes=pl.col("n_prefixes").max(), example_prefix=pl.col("example_prefix").first(),
                                                example_path=pl.col("example_path").first())
            .filter(pl.col("n_msgs") >= min_msgs)
            .with_columns(duration_min=(pl.col("t_last") - pl.col("t0")).dt.total_minutes(),
                          event_id=pl.col("t0").dt.strftime("%Y%m%dT%H%M%S") + pl.lit("_leak_") + pl.col("a").cast(pl.String))
            .drop("event_no").sort("t0"))
    return ev


def match_labels(ev: pl.DataFrame, labels_dir: Path, start: str, end: str, slack_min: int = 10) -> tuple[pl.DataFrame, dict]:
    from .labels import load_cf_leaks

    lk = load_cf_leaks(labels_dir)
    if lk is None:                                   # no leak labels for this year: events unlabelled, recall undefined
        ev_lab = ev.with_columns(labelled=pl.lit(False), label_peer_count=pl.lit(None, dtype=pl.Int64))
        return ev_lab, {"events": ev_lab.height, "labelled_events": 0, "labels": 0, "labels_hit": 0, "label_recall_by_peer_count": [],
                        "events_by_collectors": ev_lab.group_by("n_collectors").agg(n=pl.len(), labelled=pl.col("labelled").mean()).sort("n_collectors").head(9).to_dicts(),
                        "duration_min_p50": float(ev_lab["duration_min"].median()) if ev_lab.height else None,
                        "duration_min_p90": float(ev_lab["duration_min"].quantile(0.9)) if ev_lab.height else None,
                        "n_upstreams_p50": float(ev_lab["n_upstreams"].median()) if ev_lab.height else None,
                        "n_prefixes_p50": float(ev_lab["n_prefixes"].median()) if ev_lab.height else None, "leak_labels": "none"}
    s = dt.datetime.fromisoformat(start).replace(tzinfo=dt.UTC); e = dt.datetime.fromisoformat(end).replace(tzinfo=dt.UTC) + dt.timedelta(days=1)
    lk = lk.filter((pl.col("min_ts") >= pl.lit(s)) & (pl.col("min_ts") < pl.lit(e)))
    leaker = [int(x) for x in (re.sub(r"[\[\]\" ]", "", v).split(",")[1] if len(re.sub(r"[\[\]\" ]", "", v).split(",")) >= 2 else "0" for v in lk["leak_seg"].to_list())]
    lk = lk.with_columns(pl.Series("leaker", leaker, dtype=pl.UInt32), pl.col("peer_count").cast(pl.Int64))
    j = ev.join(lk.select("leaker", pl.col("min_ts").alias("label_ts"), "peer_count", pl.col("id").alias("label_id")), left_on="a", right_on="leaker", how="left")
    j = j.with_columns(hit=((pl.col("t0") - pl.col("label_ts")).dt.total_seconds().abs() <= slack_min * 60).fill_null(False))
    ev_lab = j.group_by(ev.columns).agg(labelled=pl.col("hit").any(), label_peer_count=pl.col("peer_count").filter(pl.col("hit")).max()).sort("t0")
    # label-side recall by peer_count bucket
    lab_hit = lk.join(ev.select("a", "t0"), left_on="leaker", right_on="a", how="left").with_columns(
        hit=((pl.col("t0") - pl.col("min_ts")).dt.total_seconds().abs() <= slack_min * 60).fill_null(False)).group_by("id", "peer_count").agg(hit=pl.col("hit").any())
    rec = (lab_hit.with_columns(b=pl.when(pl.col("peer_count") < 10).then(pl.lit("1-9")).when(pl.col("peer_count") < 50).then(pl.lit("10-49")).otherwise(pl.lit("50+")))
                  .group_by("b").agg(n=pl.len(), recall=pl.col("hit").mean()).sort("b").to_dicts())
    summ = {"events": ev_lab.height, "labelled_events": int(ev_lab["labelled"].sum()), "labels": lk.height, "labels_hit": int(lab_hit["hit"].sum()),
            "label_recall_by_peer_count": rec,
            "events_by_collectors": ev_lab.group_by("n_collectors").agg(n=pl.len(), labelled=pl.col("labelled").mean()).sort("n_collectors").head(9).to_dicts(),
            "duration_min_p50": float(ev_lab["duration_min"].median()), "duration_min_p90": float(ev_lab["duration_min"].quantile(0.9)),
            "n_upstreams_p50": float(ev_lab["n_upstreams"].median()), "n_prefixes_p50": float(ev_lab["n_prefixes"].median())}
    return ev_lab, summ


def run(start: str, end: str, labels_dir: Path, min_collectors: int = 2, min_msgs: int = 3, mode: str = "leak_like") -> dict:
    cl = load_classified(start, end)
    ev = build_events(cl, min_collectors, min_msgs, mode=mode)
    ev_lab, summ = match_labels(ev, labels_dir, start, end)
    out = config.DATA_ROOT / "leak_events" / f"{start}_{end}"; out.mkdir(parents=True, exist_ok=True)
    ev_lab.write_parquet(out / f"events_{mode}_m{min_collectors}.parquet")
    summ |= {"window": [start, end], "mode": mode, "min_collectors": min_collectors, "min_msgs": min_msgs}
    (out / f"summary_{mode}_m{min_collectors}.json").write_text(json.dumps(summ, indent=1, default=str))
    return summ
