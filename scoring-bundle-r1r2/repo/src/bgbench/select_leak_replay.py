"""Sprint 3 step 4: the slow-regime replay set from the leak-event inventory (`bgbench leak-events`).

Selection (default): every Cloudflare-labelled leak event seen at ≥ label_collectors collectors, plus the top_k events by
n_collectors × n_msgs. For each event the leaked adjacencies are recovered from the classified triples of its month:
the violating triples of leaker `a` within [t₀ − 1 min, t_last + 5 min] give the source ASes b (route learned from)
and upstreams x (exported to). Manifest columns: event_id, kind=leak, a, sources (b1|b2|…), t0, split, reason.
"""
from __future__ import annotations

import polars as pl

from . import config


def select(year: int = 2024, top_k: int = 400, label_collectors: int = 3, min_collectors: int = 3) -> pl.DataFrame:
    root = config.DATA_ROOT / "leak_events"
    months = sorted(p for p in root.iterdir() if p.name.startswith(str(year)))
    rows = []
    for m in months:
        ev = pl.read_parquet(m / "events_leak_like_m2.parquet")
        cl = pl.read_parquet(config.DATA_ROOT / "identifier2" / m.name / "leakcheck4_m2" / "new_triples_classified.parquet").filter(pl.col("leak_like"))
        ev = ev.with_columns(score=pl.col("n_collectors").cast(pl.Float64) * pl.col("n_msgs").cast(pl.Float64).log1p())
        lab = ev.filter(pl.col("labelled") & (pl.col("n_collectors") >= label_collectors)).with_columns(reason=pl.lit("labelled"))
        top = ev.filter(pl.col("n_collectors") >= min_collectors).sort("score", descending=True).head(max(1, top_k // len(months))).with_columns(reason=pl.lit("top"))
        sel = pl.concat([lab, top], how="diagonal_relaxed").unique("event_id", keep="first")
        for e in sel.iter_rows(named=True):
            t = cl.filter((pl.col("a") == e["a"]) & (pl.col("first_ts") >= pl.lit(e["t0"]) - pl.duration(minutes=1))
                          & (pl.col("first_ts") <= pl.lit(e["t_last"]) + pl.duration(minutes=5)))
            rows.append({**e, "sources": "|".join(str(b) for b in sorted(set(t["b"].to_list()))) or str(e["a"]),
                         "upstreams": "|".join(str(x) for x in sorted(set(t["x"].to_list()))), "kind": "leak",
                         "split": "train" if e["t0"].month <= config.SPLIT_MONTH else "test"})
    return pl.DataFrame(rows).sort("t0")


def run(year: int = 2024, top_k: int = 400, label_collectors: int = 3, min_collectors: int = 3) -> dict:
    sel = select(year, top_k, label_collectors, min_collectors)
    out_dir = config.DATA_ROOT / "inventory" / str(year); out_dir.mkdir(parents=True, exist_ok=True)
    sel.write_parquet(out_dir / "leak_replay_selection.parquet")
    man = out_dir / "leak_replay_manifest.tsv"
    sel.select("event_id", "kind", pl.col("a").cast(pl.Int64), "sources", "upstreams",
               pl.col("t0").dt.strftime("%Y-%m-%dT%H:%M:%S").alias("t0"), "split", "reason").write_csv(man, separator="\t")
    return {"selected": sel.height, "labelled": int((sel["reason"] == "labelled").sum()), "top": int((sel["reason"] == "top").sum()),
            "train": int((sel["split"] == "train").sum()), "test": int((sel["split"] == "test").sum()),
            "n_msgs_p50": float(sel["n_msgs"].median()), "manifest": str(man)}
