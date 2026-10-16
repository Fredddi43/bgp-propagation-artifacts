"""Forged-path hijack candidates (ADR-0003/0012 class never separated): a route whose origin is legitimate but whose path carries a
never-before-seen adjacency *next to the origin* (the ROV-evading pattern: the hijacker prepends the legitimate origin). From the
per-collector-day edge tables (prefix_events/<collector>/<day>.new_edges.parquet — "first seen this collector-day", so a
steady-state edge reappears every midnight): an edge (a, b) is *novel* on a day if it appears at no collector in the preceding
WINDOW days (rolling set over all ten collectors), b is the path's origin (last hop), a is not a CAIDA neighbour of b in that month,
the edge is seen at ≥ min_collectors collectors the same day, and the prefix's origin did not change that day (not a MOAS). The
first WINDOW days of the year only warm the window. Reports monthly counts, the RPKI validity of the origin (would ROV have
stopped an origin hijack of this prefix — i.e. was forging worth it), and samples. Measurement only: no external label exists.
usage: forged_path_candidates.py <year> [min_collectors]"""
from __future__ import annotations

import datetime as dt
import ipaddress
import json
import sys
from collections import defaultdict

import polars as pl

from bgbench import config
from bgbench.leakcheck import rel_parquet

year = int(sys.argv[1]); min_coll = int(sys.argv[2]) if len(sys.argv) > 2 else 2
COLL = ["rrc25", "rrc00", "rrc12", "rrc01", "route-views3", "rrc03", "route-views2", "rrc20", "rrc15", "route-views.linx"]
PE = config.DATA_ROOT / "prefix_events"
nb_cache: dict[str, set] = {}


def neighbours(month: str) -> set:
    if month not in nb_cache:
        nb_cache.clear()
        d = pl.read_parquet(rel_parquet(month), columns=["u", "v"])
        nb_cache[month] = set(zip(d["u"].to_list(), d["v"].to_list())) | set(zip(d["v"].to_list(), d["u"].to_list()))
    return nb_cache[month]


roa_cache: dict[str, dict] = {}


def roas(day: str):
    if day not in roa_cache:
        roa_cache.clear(); tab = defaultdict(list)
        f = config.DATA_ROOT / "rpki" / "roas" / f"{day}.parquet"
        if f.exists():
            for p, ml, a in pl.read_parquet(f).select("prefix", "max_len", "asn").iter_rows():
                tab[p].append((int(ml), int(a)))
        roa_cache[day] = tab
    return roa_cache[day]


def validity(prefix: str, origin: int, tab) -> str:
    try:
        net = ipaddress.ip_network(prefix, strict=False)
    except ValueError:
        return "unknown"
    cov = 0; ok = False
    for plen in range(net.prefixlen, (8 if net.version == 4 else 16) - 1, -1):
        sup = net if plen == net.prefixlen else net.supernet(new_prefix=plen)
        for ml, a in tab.get(str(sup), ()):
            if net.prefixlen <= ml:
                cov += 1; ok = ok or a == origin
    return "valid" if ok else "invalid" if cov else "unknown"


WINDOW = 14
rows = []
d0 = dt.date(year, 1, 1) - dt.timedelta(days=WINDOW)
seen_by_day: dict[str, set] = {}
for k in range(366 + WINDOW):
    day = d0 + dt.timedelta(days=k)
    if day.year > year:
        break
    ds = day.isoformat(); month = ds[:7].replace("-", "")
    frames = []
    for c in COLL:
        f = PE / c / f"{ds}.new_edges.parquet"
        if f.exists():
            frames.append(pl.read_parquet(f, columns=["collector", "a", "b", "first_ts", "n_msgs", "example_prefix", "example_path"]))
    if not frames:
        continue
    e = pl.concat(frames)
    todays = set(zip(e["a"].cast(pl.Int64).to_list(), e["b"].cast(pl.Int64).to_list()))
    recent = set().union(*[v for d_, v in seen_by_day.items() if d_ < ds]) if seen_by_day else set()
    seen_by_day[ds] = todays
    for old in [d_ for d_ in seen_by_day if d_ < (day - dt.timedelta(days=WINDOW)).isoformat()]:
        del seen_by_day[old]
    if day.year != year or len(seen_by_day) <= 1:
        continue
    e = e.filter(~pl.struct(pl.col("a").cast(pl.Int64), pl.col("b").cast(pl.Int64)).map_elements(lambda r: (r["a"], r["b"]) in recent, return_dtype=pl.Boolean))
    if e.is_empty():
        continue
    # origin-adjacent: b is the last hop of the example path (the origin), a its neighbour on the path
    e = e.with_columns(pl.col("example_path").str.replace_all(r"[{}]", "").str.split(" ").list.last().cast(pl.Int64, strict=False).alias("origin"))
    e = e.filter(pl.col("b").cast(pl.Int64) == pl.col("origin"))
    if e.is_empty():
        continue
    # not a MOAS that day: the prefix has no origin change recorded at any collector
    oc = []
    for c in COLL:
        f = PE / c / f"{ds}.origin_changes.parquet"
        if f.exists():
            oc.append(pl.read_parquet(f, columns=["prefix"]))
    changed = set(pl.concat(oc)["prefix"].to_list()) if oc else set()
    nbs = neighbours(month)
    agg = (e.group_by("a", "b").agg(collectors=pl.col("collector").n_unique(), msgs=pl.col("n_msgs").sum(), first=pl.col("first_ts").min(), prefix=pl.col("example_prefix").first(), path=pl.col("example_path").first())
             .filter(pl.col("collectors") >= min_coll))
    tab = roas(ds)
    for r in agg.iter_rows(named=True):
        a, b = int(r["a"]), int(r["b"])
        if (a, b) in nbs or r["prefix"] in changed:
            continue
        rows.append({"day": ds, "a": a, "origin": b, "collectors": r["collectors"], "msgs": int(r["msgs"]), "prefix": r["prefix"], "path": r["path"], "origin_validity": validity(r["prefix"], b, tab)})
    if k % 30 == 0:
        print(ds, "candidates so far", len(rows), flush=True)
d = pl.DataFrame(rows)
out_dir = config.DATA_ROOT / "inventory" / str(year); d.write_parquet(out_dir / "forged_path_candidates.parquet")
summ = {"year": year, "min_collectors": min_coll, "novelty_window_days": WINDOW, "candidates": d.height, "distinct_origins": int(d["origin"].n_unique()) if d.height else 0,
        "by_month": {m: n for m, n in d.with_columns(pl.col("day").str.slice(0, 7).alias("m")).group_by("m").len().sort("m").iter_rows()} if d.height else {},
        "origin_validity": {v: n for v, n in d.group_by("origin_validity").len().iter_rows()} if d.height else {},
        "collectors_p50": float(d["collectors"].median()) if d.height else None, "msgs_p50": float(d["msgs"].median()) if d.height else None,
        "sample": d.sort("msgs", descending=True).head(10).to_dicts() if d.height else []}
print(json.dumps(summ, indent=1, default=str)); (out_dir / "forged_path_candidates.json").write_text(json.dumps(summ, indent=1, default=str))
