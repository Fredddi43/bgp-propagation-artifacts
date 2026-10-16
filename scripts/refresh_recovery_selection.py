"""Refresh recovery eligibility after RPKI correction, preserving the prior links."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys

import polars as pl

from bgbench import config


def refresh(year: int) -> dict:
    root = config.DATA_ROOT / "inventory" / str(year)
    file = root / "recovery_replay_selection.parquet"
    before = root / "recovery_replay_selection.before-correction.parquet"
    if not before.exists():
        shutil.copy2(file, before)
        shutil.copy2(root / "recovery_replay_manifest.tsv", root / "recovery_replay_manifest.before-correction.tsv")
    old = pl.read_parquet(before)
    subprocess.run([sys.executable, str(Path(__file__).with_name("select_recovery_replay.py")), str(year)], check=True)
    new = pl.read_parquet(file)
    old_links = set(old.select("event_id", "hijack_id").iter_rows())
    new_links = set(new.select("event_id", "hijack_id").iter_rows())
    report = {"year": year, "old_links": len(old_links), "new_links": len(new_links),
              "added_links": sorted(new_links - old_links), "removed_links": sorted(old_links - new_links),
              "old_recovery_events": old["event_id"].n_unique(), "new_recovery_events": new["event_id"].n_unique(),
              "old_hijack_events": old["hijack_id"].n_unique(), "new_hijack_events": new["hijack_id"].n_unique()}
    (root / "recovery_selection_changes.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report), flush=True)
    return report


if __name__ == "__main__":
    refresh(int(sys.argv[1]))
