# S0: synthetic-only host timing on <BATCH_HOST> (LOCAL packet; nothing run on the host)

- Author: claude-opus-5-5, session <SESSION_ID>.
- Root has approved S0 for local preparation. **Host execution needs an exact independent approval**, and root then
  routes it.
- **Purpose:** replace the budget's unmeasured host-speed assumption (`HOST_FACTOR` 0.45-1.0 in
  `recovery-serial-d1-r2/budget.py`) with host measurements. They are taken on the same synthetic structures and
  frozen functions the local budget already used. The result feeds a later budget revision; this packet changes no
  budget.

## What runs (one program, one ssh, one attempt)

`s0_program.py` is read from stdin by the shared venv python with `-I -B` on <BATCH_HOST> (the evaluation host;
execute.py refuses Slurm). Exact remote command (`s0.py check`):

```
cd / && OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 POLARS_MAX_THREADS=1 exec nice -n 10 timeout -k 30 1800 bash -c 'ulimit -v 25165824 && ulimit -t 1800 && exec <RESULTS_ROOT>/work/<PROJECT>/venv/bin/python -I -B -'
```

**Measurements.** Every payload is generated in memory from fixed seeds. Each function below is the frozen staged v7
code, imported read-only from `B/r1-release-assembly-v7-20261022/source`.

| Part | Measures |
|---|---|
| scale | `check_forecast_rows` plain, under `tracemalloc.start(1)` and `json.loads`, at 300 / 900 / 1800 candidates × 3,543 events (35 / 103 / 205 MB); plus the traced-peak ratio |
| score | `score_membership` per cell at 300 / 1200 candidates |
| bootstrap | `evaluate_retrospective` + `retrospective_14` at R1 scale (3,543 events per horizon, 46 arm cells), **200 and 1000 repetitions** (both valid; 50 is refused by the frozen code) |
| decode | sha256 of 512 MiB; `torch.load` of a 23 MB event container |
| metadata | CPU model, nproc, load average before/after, versions, elapsed, max RSS |

## Containment (enforced in the program, not by convention)

**The audit hook is installed before numpy/torch/staged code are imported:**
- `open` is allowed only for reads under the interpreter prefixes, the staged v7 source tree, `/proc`, `/sys`,
  `/dev/null|urandom`, `/etc/localtime`, `/usr/share/zoneinfo` and the system lib dirs;
- any write mode is refused;
- refused events: fork/exec/spawn/subprocess, sockets, kill, remove/rename/mkdir/chmod, shutil copy/move/rmtree.

**Further guards:**
- Before any work, the program refuses unless it runs as <USER> on <BATCH_HOST>, outside Slurm, isolated, with
  all five thread variables = 1.
- **Remote writes: none.** cwd is `/`, there are no output files, and `-B` means no bytecode. The result is stdout
  only.
- So no cleanup is needed, and none is authorized.

**Caps:**
- wall 1800 s, then SIGKILL after 30 s;
- CPU 1800 s (`ulimit -t`);
- address space 24 GiB (`ulimit -v`);
- nice 10;
- single-threaded numeric libraries.

**Never touched:** no Slurm, no install, no shared-venv write, no audit or launcher change. No real prediction, label,
tensor, per-event, seal, ledger or report file can be opened.

## Local evidence (same program, host/user/source path substituted)

- `evidence/local-run.json` and `evidence/local-run-binding.json` record the program sha and the substitutions.
- It completes in about 88 s on the laptop with max RSS about 2.7 GiB, so the caps leave large margins.
- Expected host time: a few minutes.

## Coexistence with the live v7 evaluation

- The v7 worker is pinned to CPUs 0-3; host load is about 1.2 of 128.
- S0 is one nice-10 thread with at most 24 GiB address space.
- It reads no v7 file and changes nothing the evaluation reads.
- If v7 reaches its memory gate while S0 runs, its fresh `MemAvailable` check needs about 905 GiB; about 1,512 GiB
  was observed available. S0 cannot move that materially.
- Running before or after v7 ends is equivalent for timing purposes. Root chooses.

## Run tooling (`s0.py`) and tests (`test_s0.py`: 36 passed; ruff clean)

**`s0.py run --approval A --approval-sha256 H`:**
- It requires an independent approval binding:
  - scope `r1-s0-host-timing-v1`;
  - `tool_sha256`, `program_sha256`, host and the exact `remote_command`;
  - `attempt_limit` 1 and retry false;
  - data read, remote write, Slurm and install all false.
- It writes `run-records/intent.json` exclusively, sends one ssh with the program on stdin, and writes
  `run-records/result.json` exclusively (rc, stdout ≤ 1 MiB, stderr tail, parsed document).
- Any failure is preserved and never retried.

**Tests:**
- the audit allows code and metadata reads;
- the audit refuses seal, report, tensor and home reads, any write mode or write flags, and 7 side-effect events;
- the real program refuses a wrong host and multithreaded libraries (run as subprocesses);
- the exact remote command contains no write or install verbs;
- 9 approval refusals;
- one attempt with records, the program on stdin, and failure recorded and never retried (rc / garbage / kind);
- no ssh without an exact approval.
