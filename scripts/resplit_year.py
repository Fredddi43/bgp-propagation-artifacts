"""Re-assign the temporal split of a year's replay selections and manifests (train: month <= split_month) and rebuild the event
sets that exist. Needed for partial years (2026 Jan–Aug: split_month 5), whose selections were written with the default 8.
usage: resplit_year.py <year> <split_month>"""
from __future__ import annotations

import subprocess
import sys

import polars as pl

from bgbench import config

year, m = int(sys.argv[1]), int(sys.argv[2])
INV = config.DATA_ROOT / "inventory" / str(year)
tcol = {"replay_selection.parquet": "first_ts", "leak_replay_selection.parquet": "t0", "withdrawal_replay_selection.parquet": "start",
        "recovery_replay_selection.parquet": "first_ts"}
for f, col in tcol.items():
    p = INV / f
    if not p.exists():
        continue
    d = pl.read_parquet(p)
    if col not in d.columns:
        print("skip", f, "no", col); continue
    d = d.with_columns(split=pl.when(pl.col(col).dt.month() <= m).then(pl.lit("train")).otherwise(pl.lit("test")))
    d.write_parquet(p); print(f, d.group_by("split").len().to_dicts())
for f in ("replay_manifest.tsv", "leak_replay_manifest.tsv", "withdrawal_replay_manifest.tsv", "recovery_replay_manifest.tsv"):
    p = INV / f
    if not p.exists():
        continue
    d = pl.read_csv(p, separator="\t", infer_schema_length=0)
    tc = "t0" if "t0" in d.columns else ("first_ts" if "first_ts" in d.columns else None)
    if tc is None or "split" not in d.columns:
        print("skip", f); continue
    d = d.with_columns(split=pl.when(pl.col(tc).str.slice(5, 2).cast(pl.Int32) <= m).then(pl.lit("train")).otherwise(pl.lit("test")))
    d.write_csv(p, separator="\t"); print(f, d.group_by("split").len().to_dicts())
# rebuild event sets that exist
for tag in ("", "leak", "withdrawal", "recovery"):
    merged = config.DATA_ROOT / ("events_replay" + (f"_{tag}" if tag else ""))
    if merged.exists() and any(merged.glob(f"{year}*")):
        cmd = ["bgbench", "eventset", "--year", str(year)] + (["--tag", tag] if tag else [])
        print("==", " ".join(cmd), flush=True); subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL)
        if not tag:
            subprocess.run(["bgbench", "eventset-vp", "--year", str(year)], check=False, stdout=subprocess.DEVNULL)
print("done")
