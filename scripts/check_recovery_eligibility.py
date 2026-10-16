"""Quantify recovery-cohort changes after origin revalidation, without reselecting."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import polars as pl

from bgbench import config


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--original-data", type=Path, required=True)
    ap.add_argument("--wait-for-rpki", action="store_true")
    args = ap.parse_args()
    if args.wait_for_rpki:
        while not (config.WORK_ROOT / "rpki-revalidation-complete.json").exists():
            time.sleep(10)
    result = {}
    def eligible(file):
        return set(pl.read_parquet(file).filter((pl.col("validity") == "invalid") & (pl.col("prev_validity") == "valid"))["event_id"])
    for year in range(2022, 2027):
        old = eligible(args.original_data / "eventset" / str(year) / "rpki_validity.parquet")
        new = eligible(config.DATA_ROOT / "eventset" / str(year) / "rpki_validity.parquet")
        links = pl.read_parquet(config.DATA_ROOT / "inventory" / str(year) / "recovery_replay_selection.parquet").select("event_id", "hijack_id").unique()
        excluded = links.filter(~pl.col("hijack_id").is_in(sorted(new)))
        result[str(year)] = {"original_eligible_origin_events": len(old), "corrected_eligible_origin_events": len(new),
                             "new_eligible_hijacks": sorted(new - old), "no_longer_eligible_hijacks": sorted(old - new),
                             "frozen_selected_links": links.height, "frozen_links_no_longer_eligible": excluded.to_dicts()}
    output = config.WORK_ROOT / "recovery-eligibility-corrections.json"
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
