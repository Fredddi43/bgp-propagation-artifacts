"""Wait for corrected RPKI labels, then refresh all dependent retained analyses."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from bgbench import config


def stop_preliminary(pid: int):
    proc = Path(f"/proc/{pid}")
    if not proc.exists():
        return
    command = (proc / "cmdline").read_bytes().replace(b"\0", b" ")
    if b"rerun_rov_corrections.py frontier" not in command:
        raise RuntimeError(f"PID {pid} is not the known preliminary frontier driver")
    children = subprocess.check_output(["ps", "--ppid", str(pid), "-o", "pid="], text=True).split()
    os.kill(pid, signal.SIGTERM)
    for child in children:
        try:
            os.kill(int(child), signal.SIGTERM)
        except ProcessLookupError:
            pass


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--preliminary-pid", type=int)
    ap.add_argument("--resume-failed",action="store_true")
    ap.add_argument("--ready-marker", default="rpki-revalidation-complete.json")
    ap.add_argument("--completion-marker", default="post-rpki-analyses-complete.json")
    ap.add_argument("--log-name", default="post-rpki")
    args = ap.parse_args()
    if not os.environ.get("BGBENCH_DATA_ROOT"):
        raise SystemExit("Set an isolated BGBENCH_DATA_ROOT")
    marker = config.WORK_ROOT / args.ready_marker
    while not marker.exists():
        time.sleep(10)
    readiness = json.loads(marker.read_text())
    print(json.dumps({"source_ready": readiness}), flush=True)
    if args.preliminary_pid:
        stop_preliminary(args.preliminary_pid)
    scripts = Path(__file__).parent
    logs = config.WORK_ROOT / "logs" / args.log_name
    logs.mkdir(parents=True, exist_ok=True)
    tasks = [("frontier-final", [sys.executable, str(scripts / "rerun_rov_corrections.py"), "frontier", "--workers", "19"])]
    for year in range(2022, 2027):
        tasks.append((f"later-validity-{year}", [sys.executable, str(scripts / "later_validity.py"), str(year)]))
        flags = [] if year == 2022 else ["--exclude-reason", "rpki_invalid_sample", "--suffix", "_labelled"]
        tasks.append((f"per-vp-{year}", [sys.executable, str(scripts / "per_vp_by_validity.py"), str(year), *flags]))
    for year in (2024, 2025):
        tasks.append((f"radar-rpki-{year}", [sys.executable, str(scripts / "radar_rpki_agreement.py"), str(year)]))
    tasks.append(("per-vp-duration-final", [sys.executable, str(scripts / "rerun_per_vp_duration.py"), "--workers", "10"]))
    def run(task):
        name, command = task
        log = logs / f"{name}.log"
        with log.open("w") as stream:
            result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT,
                                    env={**os.environ, "POLARS_MAX_THREADS": "2", "OPENBLAS_NUM_THREADS": "1"})
        result = {"name": name, "command": command, "returncode": result.returncode, "log": str(log)}
        print(json.dumps(result), flush=True)
        return result
    previous=[]
    if args.resume_failed:
        previous=json.loads((logs/'runs.json').read_text())
        failed={r['name'] for r in previous if r['returncode']}
        tasks=[(name,cmd+(['--retry-failed'] if name=='per-vp-duration-final' else [])) for name,cmd in tasks if name in failed]
        (logs/'runs-before-retry.json').write_text(json.dumps(previous,indent=2)+'\n')
    with ThreadPoolExecutor(max_workers=14) as pool:
        results = [r for r in previous if not r['returncode']] + list(pool.map(run, tasks))
    (logs / "runs.json").write_text(json.dumps(results, indent=2) + "\n")
    if any(result["returncode"] for result in results):
        raise SystemExit(1)
    (config.WORK_ROOT / args.completion_marker).write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
