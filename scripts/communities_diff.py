"""Show rows where the Rust writer and the Python parser format `communities` differently (#25)."""
import sys, tempfile
from pathlib import Path
import polars as pl, pyarrow as pa, pyarrow.parquet as pq
from bgbench.parse import _rust_hour, parse_file
collector, files = sys.argv[1], sys.argv[2:]
with tempfile.TemporaryDirectory() as td:
    _rust_hour(files, collector, Path(td) / "r.parquet")
    pq.write_table(pa.concat_tables([parse_file(f, collector)[0] for f in files]).sort_by("ts"), Path(td) / "p.parquet")
    key = ["ts", "peer_ip", "prefix", "elem_type", "as_path"]
    r = pl.read_parquet(Path(td) / "r.parquet").with_columns(pl.col("elem_type").cast(pl.String), c=pl.col("communities").list.join("|")).group_by(key).agg(pl.col("c").sort())
    p = pl.read_parquet(Path(td) / "p.parquet").with_columns(pl.col("elem_type").cast(pl.String), c=pl.col("communities").list.join("|")).group_by(key).agg(pl.col("c").sort())
    j = r.join(p, on=key, how="inner", suffix="_py").filter(pl.col("c") != pl.col("c_py"))
    pl.Config.set_fmt_str_lengths(400); pl.Config.set_tbl_width_chars(400)
    print(j.height, "mismatching row-keys")
    for row in j.head(6).to_dicts():
        print("rust:", row["c"]); print("py:  ", row["c_py"]); print()
