"""Parity check for in-worker side tables (#27): the merged tables written by `ingest-day --keep-parquet` versus
the streaming scans over the kept hourly Parquet.  usage: parity_side_tables.py <collector> <date>"""

import sys
import time

import polars as pl

from bgbench import config
from bgbench.aggregate import minute_signals
from bgbench.prefix_events import new_edges, new_triples, origin_changes

collector, date = sys.argv[1], sys.argv[2]
day = config.PARQUET_DIR / collector / date
pe = config.DATA_ROOT / "prefix_events" / collector
t0 = time.time()
agg_s, oc_s, ne_s, nt_s = minute_signals(day), origin_changes(day), new_edges(day), new_triples(day)
print(f"scan tables in {time.time() - t0:.1f}s")
agg_m = pl.read_parquet(config.AGG_DIR / collector / f"{date}.parquet")
oc_m = pl.read_parquet(pe / f"{date}.origin_changes.parquet")
ne_m = pl.read_parquet(pe / f"{date}.new_edges.parquet")
nt_m = pl.read_parquet(pe / f"{date}.new_triples.parquet")

base = ["minute", "n_ann", "n_wd", "n_prefixes", "n_peers", "n_origins", "n_paths"]
a = agg_s.select(base).sort("minute")
b = agg_m.select(base).sort("minute")
print("minutes: scan", a.height, "merged", b.height, "equal:", a.equals(b))
if not a.equals(b):
    print(a.join(b, on="minute", suffix="_m").filter(pl.any_horizontal([pl.col(c) != pl.col(c + "_m") for c in base[1:]])).head())

k = ["ts", "peer_ip", "peer_asn", "prefix", "prev_origin", "new_origin", "as_path"]
a = oc_s.select(k).sort(k)
b = oc_m.select(k).sort(k)
print("origin_changes: scan", a.height, "merged", b.height, "equal:", a.equals(b))
if not a.equals(b):
    print("only scan:", a.join(b, on=k, how="anti").height, "only merged:", b.join(a, on=k, how="anti").height)
    print(a.join(b, on=k, how="anti").head(3)); print(b.join(a, on=k, how="anti").head(3))

for name, s, m, keys in (("new_edges", ne_s, ne_m, ["a", "b"]), ("new_triples", nt_s, nt_m, ["x", "a", "b"])):
    j = s.join(m, on=keys, how="full", suffix="_m", coalesce=True)
    miss = j.filter(pl.col("first_ts").is_null() | pl.col("first_ts_m").is_null()).height
    dts = j.filter(pl.col("first_ts") != pl.col("first_ts_m")).height
    dn = j.filter(pl.col("n_msgs") != pl.col("n_msgs_m")).height
    dex = j.filter(pl.col("example_prefix") != pl.col("example_prefix_m")).height
    print(f"{name}: scan {s.height} merged {m.height} | keys missing on one side {miss} | first_ts diff {dts} | n_msgs diff {dn} | example_prefix diff (ties allowed) {dex}")
    print("  dtypes equal:", s.schema == m.schema, "" if s.schema == m.schema else (s.schema, m.schema))
print("oc dtypes equal:", oc_s.schema == oc_m.schema, "" if oc_s.schema == oc_m.schema else (oc_s.schema, oc_m.schema))
print("agg dtypes equal (base cols):", agg_s.select(base).schema == agg_m.select(base).schema, agg_s.select(base).schema, agg_m.select(base).schema)
