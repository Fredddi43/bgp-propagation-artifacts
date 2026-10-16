"""Parity check for the Rust writer (#25): parse the same MRT files with both engines and compare."""

import sys
import tempfile
import time
from pathlib import Path

import polars as pl
import pyarrow.parquet as pq

from bgbench.parse import _rust_hour, parse_file

files = sys.argv[2:]
collector = sys.argv[1]
with tempfile.TemporaryDirectory() as td:
    t0 = time.time()
    n_rust = _rust_hour(files, collector, Path(td) / "rust.parquet")
    t1 = time.time()
    tables = [parse_file(f, collector)[0] for f in files]
    import pyarrow as pa

    pq.write_table(
        pa.concat_tables(tables).sort_by("ts"), Path(td) / "py.parquet", compression="zstd"
    )
    t2 = time.time()
    r = pl.read_parquet(Path(td) / "rust.parquet")
    p = pl.read_parquet(Path(td) / "py.parquet")
    print(
        f"rust {n_rust} rows in {t1 - t0:.1f}s | python {p.height} rows in {t2 - t1:.1f}s | speedup x{(t2 - t1) / max(t1 - t0, 1e-9):.1f}"
    )
    print("schemas equal:", r.schema == p.schema)
    print("rust:", r.schema)
    print("py:  ", p.schema)
    for col in (
        "ts",
        "elem_type",
        "peer_ip",
        "peer_asn",
        "prefix",
        "as_path",
        "origin_asn",
        "next_hop",
        "aggr_asn",
        "aggr_ip",
    ):
        a = r[col].cast(pl.String) if r.schema[col] != pl.String else r[col]
        b = p[col].cast(pl.String) if p.schema[col] != pl.String else p[col]
        eq = a.sort().to_list() == b.sort().to_list()
        print(f"{col:12s} equal-as-multiset: {eq}")
    def ms(df, col):
        return sorted("|".join(map(str, v)) if v is not None else "" for v in df[col].to_list())
    print("origin_asns equal-as-multiset:", ms(r, "origin_asns") == ms(p, "origin_asns"))
    print("communities equal-as-multiset:", ms(r, "communities") == ms(p, "communities"))
    # row-level: join on (ts, peer_ip, prefix, elem_type, as_path) and compare communities per row
    key = ["ts", "peer_ip", "prefix", "elem_type", "as_path"]
    rr = r.with_columns(pl.col("elem_type").cast(pl.String), c=pl.col("communities").list.join("|")).group_by(key).agg(pl.col("c").sort())
    pp = p.with_columns(pl.col("elem_type").cast(pl.String), c=pl.col("communities").list.join("|")).group_by(key).agg(pl.col("c").sort())
    j = rr.join(pp, on=key, how="inner", suffix="_py")
    print("row-keyed communities mismatches:", j.filter(pl.col("c") != pl.col("c_py")).height, "of", j.height)
