#!/usr/bin/env python3
"""Determinism check: the per-cell sidecar files of two independent build runs must be byte-identical.

Compares the events/sets parquet digests recorded in each run's done records (and re-hashes the files of the
final run), for every cell both runs built.
"""
import hashlib
import json
import sys
from pathlib import Path

WORK = Path("<FORECAST_ROOT>/r1-rank-sidecar-20261101/work")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    first, final = WORK / "run1" / "done", WORK / "done"
    same = differ = only_final = rehash_bad = 0
    differing = []
    for record_path in sorted(final.glob("*.json")):
        record = json.loads(record_path.read_text())
        if record.get("files"):
            for kind in ("events", "sets"):
                if sha(record["files"][kind]["path"]) != record["files"][kind]["sha256"]:
                    rehash_bad += 1
        old_path = first / record_path.name
        if not old_path.exists():
            only_final += 1
            continue
        old = json.loads(old_path.read_text())
        if not (old.get("files") and record.get("files")):
            continue
        keys = ("events", "sets")
        if all(old["files"][k]["sha256"] == record["files"][k]["sha256"] for k in keys) and \
                old.get("per_event_sha256_reproduced") == record.get("per_event_sha256_reproduced"):
            same += 1
        else:
            differ += 1
            differing.append(record["cell_id"])
    result = {"cells_identical": same, "cells_differing": differ, "differing": differing[:20],
              "cells_only_in_final_run": only_final, "final_run_rehash_mismatches": rehash_bad}
    print(json.dumps(result, indent=2))
    return 1 if differ or rehash_bad else 0


if __name__ == "__main__":
    sys.exit(main())
