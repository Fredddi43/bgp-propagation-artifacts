#!/usr/bin/env python3
"""Write the array job script and print/execute the sbatch for one family spec. Normal use: run with --dry-run on <BATCH_HOST>
(writes the .sbatch into the shared work dir, prints the command), then submit that exact command with
`ssh <SUBMIT_HOST> '<command>'` under `flock -w 1800 <AGENT_TMP>/bgb-launch.lock`; check `sacct -j ID -X -n` after 60 s.

Never --export=NONE (cancelled by the cluster); --export=NIL. Jobs: partition cpu, real -o/-e files, no requeue.
"""
import argparse
import json
import re
import shlex
import subprocess
from pathlib import Path

# origin parallel-inference env (r3 successor, ROOT-approved q34): the sbatch line uses
# --export=NIL and the script runs `exec env -i ...`, so these MUST be set inside the job script.
# Injected only for specs of family "origin" (their runner is the parallel successor; the
# history/stable pinned runners never read these names). "$SLURM_CPUS_PER_TASK" is expanded by
# bash to the task's CPU count == the cpus the runner re-binds from the live allocation. A spec
# may record the same table in spec["parallel_env"] (make_g2_plan.py does); when present it must
# equal these values, and values may only use shell-safe characters.
PARALLEL_ENV_DEFAULTS = {"BGBENCH_PARALLEL_WORKERS": "$SLURM_CPUS_PER_TASK",
                         "BGBENCH_PARALLEL_THREADS": "1",
                         "BGBENCH_PARALLEL_CUSTODY_LOAD": "1"}
ENV_VALUE_RE = re.compile(r"\A(?:\$SLURM_CPUS_PER_TASK|[0-9]+)\Z")


def parallel_env(spec):
    """The literal KEY=VALUE assignments to append to the cleared job environment (origin only)."""
    if spec.get("family") != "origin":
        return []
    claimed = spec.get("parallel_env")
    if claimed is not None and claimed != PARALLEL_ENV_DEFAULTS:
        raise SystemExit(f"spec parallel_env {claimed} differs from the required {PARALLEL_ENV_DEFAULTS}")
    for key, value in PARALLEL_ENV_DEFAULTS.items():
        if not ENV_VALUE_RE.fullmatch(value):
            raise SystemExit(f"parallel env {key}={value}: only digits or $SLURM_CPUS_PER_TASK are allowed")
    return [f"{k}={v}" for k, v in sorted(PARALLEL_ENV_DEFAULTS.items())]


def script(py, exec_path, spec, cpus, singleton=False, extra_env=(), literal_env=()):
    env = ["PATH=/usr/bin:/bin", "LANG=C.UTF-8", *extra_env] + [f"{k}={cpus}" for k in
                                                    ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "POLARS_MAX_THREADS")]
    inherited = " ".join(f'{k}="${{{k}:?}}"' for k in ("SLURM_JOB_ID", "SLURM_JOB_PARTITION", "SLURM_CPUS_PER_TASK", "SLURM_MEM_PER_NODE"))
    literals = " ".join(literal_env)      # unquoted on purpose: bash expands $SLURM_CPUS_PER_TASK here
    return ("#!/bin/bash\nset -eu\nexec env -i " + shlex.join(env) + ((" " + literals) if literals else "")
            + " " + inherited + ' SLURM_RESTART_COUNT="${SLURM_RESTART_COUNT:-0}" '
            + shlex.join([py, "-I", "-B", str(exec_path), "--spec", str(spec)])
            + ("" if singleton else ' --index "$SLURM_ARRAY_TASK_ID"') + "\n")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--spec", type=Path, required=True)
    p.add_argument("--python", required=True, help="private science venv python on the cluster")
    p.add_argument("--exec", type=Path, default=Path(__file__).with_name("g2_exec.py"))
    p.add_argument("--cpus", type=int, required=True)
    p.add_argument("--mem-mib", type=int, required=True)
    p.add_argument("--wall", required=True, help="Slurm time, e.g. 04:00:00")
    p.add_argument("--concurrency", type=int, default=64, help="array %% cap; every G2 spec passes an explicit "
                     "capacity-based value (RESOURCE-POLICY.md: as high as capacity allows)")
    p.add_argument("--job-name", required=True)
    p.add_argument("--singleton", action="store_true", help="one job, no array (R2: the runner refuses SLURM_ARRAY_TASK_ID); spec needs one template wall_seconds")
    p.add_argument("--export-env", action="append", default=[], help="KEY=VALUE put into the cleared job environment (R2: CUSTODIAN_ACCESS_LOG)")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv)
    a.spec = a.spec.resolve()
    spec = json.loads(a.spec.read_bytes())
    h, m, sec = (int(x) for x in a.wall.split("-")[-1].split(":"))
    limit = (int(a.wall.split("-")[0]) * 86400 if "-" in a.wall else 0) + h * 3600 + m * 60 + sec
    for arm in ([] if a.singleton else spec["arms"]):   # the runner turns template wall_seconds into a SIGALRM: it must fit the allocation
        wall = json.loads(Path(arm["template"]["path"]).read_bytes())["resources"]["wall_seconds"]
        if wall > limit:
            raise SystemExit(f"{arm['arm_id']}: template wall_seconds {wall} exceeds --wall {a.wall}")
    work = Path(spec["work"])
    work.mkdir(parents=True, exist_ok=True)
    job = work / f"{a.job_name}.sbatch"
    job.write_text(script(a.python, a.exec, a.spec, a.cpus, a.singleton, a.export_env, parallel_env(spec)))
    job.chmod(0o755)
    n = 1 if a.singleton else len(spec["arms"])
    cmd = ["sbatch", "--parsable", "--export=NIL", "--partition=cpu", f"--cpus-per-task={a.cpus}", f"--mem={a.mem_mib}M",
           f"--time={a.wall}", "--no-requeue", f"--job-name={a.job_name}", *([] if a.singleton else [f"--array=0-{n - 1}%{a.concurrency}"]),
           f"--output={work}/{a.job_name}-{'%j' if a.singleton else '%A_%a'}.out", f"--error={work}/{a.job_name}-{'%j' if a.singleton else '%A_%a'}.err", str(job)]
    print(shlex.join(cmd))
    if not a.dry_run:
        print(subprocess.run(cmd, check=True, capture_output=True, text=True).stdout.strip())


if __name__ == "__main__":
    main()
