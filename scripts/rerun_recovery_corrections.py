"""Recompute retained pair, overlap and ROV variants after a corrected year's replay.

BGBENCH_DATA_ROOT must point at an isolated correction directory containing the
old summaries, so their filenames and declared populations can be preserved.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys

from bgbench import config
from bgbench.paired_analysis import add_pair_arguments, pair_cli_options


def main():
    if not os.environ.get("BGBENCH_DATA_ROOT"):
        raise SystemExit("Set BGBENCH_DATA_ROOT to the isolated correction directory")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("year", type=int)
    ap.add_argument("--workers", type=int, default=3)
    add_pair_arguments(ap)
    args = ap.parse_args()
    root = Path(__file__).parent
    directory = config.DATA_ROOT / "eventset" / f"{args.year}_recovery"
    logs = config.WORK_ROOT / "logs" / f"recovery-analyses-{args.year}"
    logs.mkdir(parents=True, exist_ok=True)
    tasks = []
    for path in sorted(directory.glob("pairs_summary*.json")):
        suffix = path.stem.removeprefix("pairs_summary")
        if suffix not in ("", "_labelled", "_stratum"):
            raise ValueError(f"Unknown pair population suffix: {suffix}")
        flags = [] if not suffix else ["--exclude-reason" if suffix == "_labelled" else "--only-reason", "rpki_invalid_sample"]
        for script in ("recovery_pairs_full", "recovery_overlap"):
            tasks.append((f"{script}{suffix}", [sys.executable, str(root / f"{script}.py"), str(args.year), "--suffix", suffix, *flags, *pair_cli_options(args)]))
    tasks.append(("rov-variants", [sys.executable, str(root / "rerun_rov_corrections.py"), "recovery", "--years", str(args.year), "--workers", "2", *pair_cli_options(args)]))
    def run(task):
        name, command = task
        log = logs / f"{name}.log"
        with log.open("w") as stream:
            result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT,
                                    env={**os.environ, "POLARS_MAX_THREADS": "2", "OPENBLAS_NUM_THREADS": "1"})
        return {"name": name, "command": command, "returncode": result.returncode, "log": str(log)}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(run, tasks))
    (logs / "runs.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2), flush=True)
    if any(r["returncode"] for r in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
