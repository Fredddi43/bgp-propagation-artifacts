"""Leak recall ceiling diagnostic (#26): for every Cloudflare leak in a window with *kept* hourly Parquet (beacon week
2024-06-10..16, 10 collectors), did any of our vantage points carry a path with the leak segment at all, and did the
leak check v4 hit it?  usage: leak_visibility.py <start> <end> <labels_dir> <classified_triples.parquet> <out_dir>"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import polars as pl

from bgbench import config

SLACK = dt.timedelta(minutes=10)
COLLECTORS = ["rrc25", "rrc00", "rrc12", "rrc01", "route-views3", "rrc03", "route-views2", "rrc20", "rrc15", "route-views.linx"]


def _seg(s: str) -> list[int]:
    return [int(x) for x in re.sub(r"[\[\]\" ]", "", s).split(",") if x]


PARTS: Path | None = None   # set in main(); per collector-day results are written here so a timeout keeps partial work


def scan_day(collector: str, date: str, leaks: list[dict]) -> list[dict]:
    """Rows carrying any leak segment adjacency within the leak's window, at this collector-day."""
    part = PARTS / f"{collector}_{date}.json" if PARTS else None
    if part and part.exists():
        return json.loads(part.read_text())
    day_dir = config.PARQUET_DIR / collector / date
    if not list(day_dir.glob("part-*.parquet")):
        return []
    asns = sorted({int(l["leak_asn"]) for l in leaks})
    t0 = min(l["t_lo"] for l in leaks); t1 = max(l["t_hi"] for l in leaks)
    # hour by hour (bounded memory, predictable time): keep rows whose hop set intersects the leaker set — one split per
    # row instead of one substring scan per leaker (a regex alternation / per-ASN contains over 100 M rows took > 1 h)
    frames = []
    for part in sorted(day_dir.glob("part-*.parquet")):
        try:
            with open(part, "rb") as fh:
                fh.seek(-4, 2)
                if fh.read(4) != b"PAR1":
                    print(f"[skip] truncated parquet {part}", file=sys.stderr); continue
        except OSError:
            continue
        h = (pl.scan_parquet(str(part))
               .filter((pl.col("elem_type") == "A") & pl.col("as_path").is_not_null()
                       & (pl.col("ts") >= pl.lit(t0)) & (pl.col("ts") <= pl.lit(t1)))
               .select("ts", "peer_ip", "as_path")
               .with_columns(hops=pl.col("as_path").str.replace_all(r"[{}]", "").str.split(" ").list.eval(pl.element().cast(pl.UInt32, strict=False)))
               .filter(pl.col("hops").list.eval(pl.element().is_in(asns)).list.any())
               .select("ts", "peer_ip", "as_path")
               .collect())
        if h.height:
            frames.append(h)
    df = pl.concat(frames) if frames else pl.DataFrame(schema={"ts": pl.Datetime("us", "UTC"), "peer_ip": pl.String, "as_path": pl.String})
    out = []
    for l in leaks:
        seg = l["seg"]; L = l["leak_asn"]
        sub = df.filter((pl.col("ts") >= pl.lit(l["t_lo"])) & (pl.col("ts") <= pl.lit(l["t_hi"])))
        if sub.is_empty():
            continue
        # route flows b → leaker → a, so the path string reads "... a L b ..."
        pairs = [(seg[i], seg[i + 1]) for i in range(len(seg) - 1)]
        pair_pat = "|".join(rf"(^| ){a} {b}( |$)" for a, b in pairs)
        full_pat = rf"(^| ){' '.join(map(str, seg))}( |$)"
        m_pair = sub.filter(pl.col("as_path").str.contains(pair_pat))
        m_full = sub.filter(pl.col("as_path").str.contains(full_pat))
        m_leaker = sub.filter(pl.col("as_path").str.contains(rf"(^| ){L}( |$)"))
        out.append({"id": l["id"], "collector": collector, "peers_leaker": m_leaker["peer_ip"].n_unique(),
                    "peers_pair": m_pair["peer_ip"].n_unique(), "peers_full": m_full["peer_ip"].n_unique(),
                    "first_full_ts": m_full["ts"].min().isoformat() if m_full.height else None})
    if part:
        part.write_text(json.dumps(out))
    return out


def _set_parts(p: Path) -> None:
    global PARTS
    PARTS = p


def main(start: str, end: str, labels_dir: str, classified: str, out_dir: str) -> None:
    s = dt.datetime.fromisoformat(start).replace(tzinfo=dt.UTC); e = dt.datetime.fromisoformat(end).replace(tzinfo=dt.UTC) + dt.timedelta(days=1)
    lk = pl.read_parquet(Path(labels_dir) / "cloudflare_leaks.parquet").with_columns(
        pl.col("min_ts").str.to_datetime(time_zone="UTC", strict=False), pl.col("max_ts").str.to_datetime(time_zone="UTC", strict=False))
    lk = lk.filter((pl.col("min_ts") >= pl.lit(s)) & (pl.col("min_ts") < pl.lit(e)))
    leaks = []
    for r in lk.to_dicts():
        seg = _seg(r["leak_seg"])
        if len(seg) < 2:
            continue
        leaks.append({"id": r["id"], "leak_asn": int(r["leak_asn"]), "seg": seg, "peer_count": int(r["peer_count"]),
                      "t_lo": r["min_ts"] - SLACK, "t_hi": (r["max_ts"] or r["min_ts"]) + SLACK, "min_ts": r["min_ts"]})
    days = sorted({(l["t_lo"] + dt.timedelta(days=k)).date().isoformat() for l in leaks for k in range(0, 2)})
    days = [d for d in days if start <= d <= end]
    tasks = []
    for c in COLLECTORS:
        for d in days:
            dl = [l for l in leaks if l["t_lo"].date().isoformat() <= d <= l["t_hi"].date().isoformat()]
            if dl:
                tasks.append((c, d, dl))
    global PARTS
    PARTS = Path(out_dir) / "parts"; PARTS.mkdir(parents=True, exist_ok=True)
    rows = []
    # spawn, not fork: the parent has already used polars (labels), and a forked child inherits a dead rayon pool and
    # hangs forever — which is why three earlier runs of this script produced no output at all
    import multiprocessing as mp

    with ProcessPoolExecutor(max_workers=8, mp_context=mp.get_context("spawn"), initializer=_set_parts, initargs=(PARTS,)) as ex:
        for res in ex.map(scan_day, *zip(*tasks)):
            rows.extend(res)
    vis = pl.DataFrame(rows, schema={"id": pl.String, "collector": pl.String, "peers_leaker": pl.Int64, "peers_pair": pl.Int64,
                                     "peers_full": pl.Int64, "first_full_ts": pl.String}).with_columns(
        pl.col("first_full_ts").str.to_datetime(time_zone="UTC", strict=False)) if rows else None
    per = pl.DataFrame({"id": [l["id"] for l in leaks], "peer_count": [l["peer_count"] for l in leaks], "min_ts": [l["min_ts"] for l in leaks],
                        "leak_asn": [l["leak_asn"] for l in leaks], "seg": [",".join(map(str, l["seg"])) for l in leaks]})
    if vis is not None:
        agg = vis.group_by("id").agg(collectors_pair=(pl.col("peers_pair") > 0).sum(), peers_pair=pl.col("peers_pair").sum(),
                                    collectors_full=(pl.col("peers_full") > 0).sum(), peers_full=pl.col("peers_full").sum(),
                                    collectors_leaker=(pl.col("peers_leaker") > 0).sum(), first_full_ts=pl.col("first_full_ts").min())
        per = per.join(agg, on="id", how="left")
    per = per.fill_null(0)
    # hit by the leak check v4 (classified first-seen triples of the month): a segment pair as (a,b) or (x,a) within ±slack
    cl = pl.read_parquet(classified).select(pl.col("x").cast(pl.UInt32), pl.col("a").cast(pl.UInt32), pl.col("b").cast(pl.UInt32), "first_ts")
    edges = pl.concat([cl.select("a", "b", "first_ts"), cl.select(pl.col("x").alias("a"), pl.col("a").alias("b"), "first_ts")])
    hits = set()
    for l in leaks:
        pairs = {(l["seg"][i], l["seg"][i + 1]) for i in range(len(l["seg"]) - 1)}
        pairs |= {(b, a) for a, b in pairs}
        pairs_df = pl.DataFrame({"a": [a for a, _ in pairs], "b": [b for _, b in pairs]}, schema={"a": pl.UInt32, "b": pl.UInt32})
        m = edges.join(pairs_df, on=["a", "b"], how="inner").filter(
            (pl.col("first_ts") - pl.lit(l["min_ts"])).dt.total_seconds().abs() <= SLACK.total_seconds())
        if m.height:
            hits.add(l["id"])
    per = per.with_columns(hit=pl.col("id").is_in(list(hits)))
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    per.write_parquet(out / "leak_visibility.parquet")
    def bucket(col: str) -> list[dict]:
        return (per.with_columns(b=pl.when(pl.col(col) == 0).then(pl.lit("0")).when(pl.col(col) <= 2).then(pl.lit("1-2")).otherwise(pl.lit("3+")))
                   .group_by("b").agg(n=pl.len(), recall=pl.col("hit").mean()).sort("b").to_dicts())
    summ = {"window": [start, end], "leaks": per.height, "hit_total": int(per["hit"].sum()),
            "visible_pair_any_collector": int((per["collectors_pair"] > 0).sum()), "visible_full_segment_any_collector": int((per["collectors_full"] > 0).sum()),
            "leaker_seen_any_collector": int((per["collectors_leaker"] > 0).sum()),
            "recall_by_collectors_carrying_pair": bucket("collectors_pair"), "recall_by_collectors_carrying_full_segment": bucket("collectors_full"),
            "recall_by_cloudflare_peer_count": (per.with_columns(b=pl.when(pl.col("peer_count") < 10).then(pl.lit("1-9")).when(pl.col("peer_count") < 50).then(pl.lit("10-49")).otherwise(pl.lit("50+")))
                                                  .group_by("b").agg(n=pl.len(), recall=pl.col("hit").mean(), visible_pair=(pl.col("collectors_pair") > 0).mean()).sort("b").to_dicts())}
    (out / "summary.json").write_text(json.dumps(summ, indent=1, default=str))
    print(json.dumps(summ, indent=1, default=str))


if __name__ == "__main__":
    main(*sys.argv[1:6])
