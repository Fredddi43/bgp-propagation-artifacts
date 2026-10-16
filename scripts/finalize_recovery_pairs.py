"""Pipeline matched-pair analyses as each corrected transition year becomes ready."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time

from bgbench import config


def main():
    if not os.environ.get("BGBENCH_DATA_ROOT"):
        raise SystemExit("Set an isolated BGBENCH_DATA_ROOT")
    root = config.DATA_ROOT / "eventset"
    logs = config.WORK_ROOT / "logs" / "primary-pairs"
    logs.mkdir(parents=True, exist_ok=True)
    pending, running, finished = set(range(2022, 2027)), {}, []
    while pending or running:
        if (config.WORK_ROOT / "rpki-revalidation-complete.json").exists():
            for year in sorted(pending):
                h = root / f"{year}_hijack_first_transition"
                r = root / f"{year}_recovery_first_transition"
                if not all((p / "summary.json").exists() for p in (h, r)):
                    continue
                command = [sys.executable, str(Path(__file__).parent / "rerun_recovery_corrections.py"), str(year),
                           "--hijack-events", str(h / "events.parquet"), "--recovery-events", str(r / "events.parquet"),
                           "--output-dir", str(r), "--require-matched-definition", "--require-valid-hijack"]
                stream = (logs / f"{year}.log").open("w")
                process = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT,
                                           env={**os.environ, "POLARS_MAX_THREADS": "2", "OPENBLAS_NUM_THREADS": "1"})
                running[year] = (process, stream, command)
                pending.remove(year)
                print(json.dumps({"started_year": year, "pid": process.pid, "command": command}), flush=True)
        for year, (process, stream, command) in list(running.items()):
            if process.poll() is not None:
                stream.close()
                result = {"year": year, "returncode": process.returncode, "command": command}
                finished.append(result)
                print(json.dumps(result), flush=True)
                del running[year]
        if pending or running:
            time.sleep(10)
    (logs / "runs.json").write_text(json.dumps(finished, indent=2) + "\n")
    if any(result["returncode"] for result in finished):
        raise SystemExit(1)
    (config.WORK_ROOT / "primary-pairs-complete.json").write_text(json.dumps(finished, indent=2) + "\n")


if __name__ == "__main__":
    main()
