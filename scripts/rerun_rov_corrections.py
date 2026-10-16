"""Rerun retained RoVista variants in parallel, preserving each declared population.

Run against an isolated BGBENCH_DATA_ROOT, after staging existing summary JSONs.
Usage: python scripts/rerun_rov_corrections.py frontier|recovery --workers 5
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
    ap.add_argument("kind", choices=["frontier", "recovery"])
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--years", nargs="+", type=int, default=list(range(2022, 2027)))
    add_pair_arguments(ap)
    args = ap.parse_args()
    prefix = "rov_frontier" if args.kind == "frontier" else "rov_summary"
    script = Path(__file__).parent / ("rov_frontier.py" if args.kind == "frontier" else "recovery_rov.py")
    tasks = []
    for year in args.years:
        directory = config.DATA_ROOT / "eventset" / (str(year) if args.kind == "frontier" else f"{year}_recovery")
        for path in sorted(directory.glob(f"{prefix}*.json")):
            old = json.loads(path.read_text())
            command = [sys.executable, str(script), str(year), "--suffix", path.stem[len(prefix):]]
            for key in ("threshold", "freeze_date", "min_total", "only_reason", "exclude_reason"):
                if key in old and old[key] is not None and (args.kind == "frontier" or key not in ("threshold", "min_total")):
                    command += ["--" + key.replace("_", "-"), str(old[key])]
            if args.kind == "recovery":
                command += pair_cli_options(args)
            tasks.append((path, command))
    logs = config.WORK_ROOT / "logs" / f"rov-{args.kind}"
    logs.mkdir(parents=True, exist_ok=True)
    def run(task):
        path, command = task
        log = logs / f"{path.parent.name}-{path.stem}.log"
        with log.open("w") as stream:
            proc = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT,
                                  env={**os.environ, "POLARS_MAX_THREADS": "2", "OPENBLAS_NUM_THREADS": "1"})
        return {"output": str(path), "command": command, "returncode": proc.returncode, "log": str(log)}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(run, tasks))
    (logs / ("runs-" + "-".join(map(str, args.years)) + ".json")).write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2), flush=True)
    if any(r["returncode"] for r in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
