"""Revalidate retained events against historical ROAs, with a before/after audit."""
from __future__ import annotations

import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys

import polars as pl

from bgbench import config


def run(year: int) -> dict:
    folder = config.DATA_ROOT / "eventset" / str(year)
    before = pl.read_parquet(folder / "rpki_validity.parquet")
    log = config.WORK_ROOT.parent / "logs" / f"rpki-{year}.log"
    with log.open("w") as output:
        subprocess.run([sys.executable, "scripts/rpki_validity_events.py", str(year)],
                       stdout=output, stderr=subprocess.STDOUT, check=True)
    after = pl.read_parquet(folder / "rpki_validity.parquet")
    merged = before.select("event_id", "validity", "prev_validity").join(
        after.select("event_id", "validity", "prev_validity"), on="event_id", suffix="_new", validate="1:1")
    changed = merged.filter(pl.col("validity") != pl.col("validity_new"))
    previous = merged.filter(pl.col("prev_validity") != pl.col("prev_validity_new"))
    result = {"year": year, "events": merged.height,
              "new_origin_changes": changed.group_by("validity", "validity_new").len().to_dicts(),
              "previous_origin_changes": previous.group_by("prev_validity", "prev_validity_new").len().to_dicts()}
    merged.filter((pl.col("validity") != pl.col("validity_new")) |
                  (pl.col("prev_validity") != pl.col("prev_validity_new"))).write_parquet(folder / "rpki_revalidation_changes.parquet")
    (folder / "rpki_revalidation_changes.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)
    return result


if __name__ == "__main__":
    os.chdir(Path(__file__).resolve().parents[1])
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(run, range(2022, 2027)))
    (config.WORK_ROOT.parent / "rpki-revalidation-complete.json").write_text(json.dumps(results, indent=2) + "\n")
