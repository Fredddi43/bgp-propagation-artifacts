"""Parallel copy/refresh driver. Reads original tensors, writes isolated corrections only."""
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys

from bgbench import config

source = Path(sys.argv[1])
log_dir = Path(sys.argv[2]); log_dir.mkdir(parents=True, exist_ok=True)
if source.resolve() == (config.DATA_ROOT / "tgn").resolve():
    raise ValueError("Input and output tgn directories must differ")


def task(directory):
    relative = directory.relative_to(source)
    target = config.DATA_ROOT / "tgn" / relative
    target.mkdir(parents=True, exist_ok=True)
    name = str(relative).replace("/", "_")
    log = log_dir / ("refresh_" + name + ".log")
    with log.open("w") as stream:
        subprocess.run(["cp", "-a", str(directory) + "/.", str(target)], check=True, stdout=stream, stderr=subprocess.STDOUT)
        year, _, tag = relative.parts[0].partition("_")
        # Stale derived results are quarantined; a successful rerun creates a clean _results.
        results = target / "_results"
        if results.exists():
            archived = target / "_results_before_correction"
            if not archived.exists():
                results.rename(archived)
        command = [sys.executable, str(Path(__file__).with_name("refresh_graph_tensors.py")), year, tag, relative.parts[1][1:-1]]
        subprocess.run(command, check=True, stdout=stream, stderr=subprocess.STDOUT)
    print("DONE", relative, flush=True)
    return str(relative)


dirs = sorted(source.glob("*/d*s"), key=lambda p: (not p.parent.name.endswith("_leak200"), str(p)))
failures = []
with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
    futures = {pool.submit(task, d): d for d in dirs}
    for f in concurrent.futures.as_completed(futures):
        try:
            f.result()
        except Exception as error:
            failures.append({"directory": str(futures[f]), "error": str(error)})
            print("FAILED", futures[f], repr(error), flush=True)
(log_dir / "refresh_failures.json").write_text(json.dumps(failures, indent=2))
if failures:
    raise SystemExit(1)
