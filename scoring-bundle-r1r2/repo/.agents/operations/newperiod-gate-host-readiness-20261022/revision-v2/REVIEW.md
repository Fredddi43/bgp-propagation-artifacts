# Review packet: gate host readiness, revision-v2 (round-1 required changes R1-R3)

- Author: claude-opus-5-5, session <SESSION_ID> (`/root/opus_implementation`).
- Base: the round-1 packet one directory up, unchanged:
  - pins adbf072b; review 5a5f3986, verdict 57ac99ea (CHANGES_REQUIRED R1-R3, reviewer 4ba6111c)
  - accepted there: the host facts, the placement design, the 105-file stage closure, the preconditions and the
    exclusive outputs
- Base §1-§3 (host facts, placement, deployment findings) stand unchanged. Base §4 (the run) is superseded by the
  approval shape below.
- **Not done and not authorized:** no host action, placement or run. The R1 v7 preparation is live, and these tools
  now refuse while it is.

## Changes (everything else byte-identical to the base tools, apart from `REPO = HERE.parents[3]`)

**R1, enforced limits** (`host_run.py`; the values are in `LIMITS`).

The test process tree runs with:
- `preexec_fn=limited`: `os.nice(10)`, `RLIMIT_AS` = 8 GiB, `RLIMIT_FSIZE` = 256 MiB and `RLIMIT_CPU` = 3600 s,
  soft = hard
- `OMP/MKL/OPENBLAS/NUMEXPR/POLARS_MAX/RAYON_NUM_THREADS` = 2 in its environment
- the wall timeout of 3600 s kept as the bound for the whole tree

The process that becomes pytest runs a small wrapper first. It records what it actually runs under in
`run/limits-observed.json` and exits 97 unless the values match exactly. Then it `exec`s pytest, so pytest, every
witness child and strace inherit the same limits.

After the run:
- the total size of `run/` (with the synthetic worlds still present) must be ≤ 2 GiB;
- `passed` = pytest rc 0 and size within the bound and limits observed.

**Measured locally** (dev host, 16 cores): the full CODEPASS gate suite, 162 tests, passes under `prlimit --as=4 GiB
--fsize=256 MiB`, `nice -n 10` and all six thread variables at 2, in 283 s. The synthetic worlds used 43 MB. The
8 GiB address-space cap is twice that measured bound. On the 128-core host the thread caps also stop
thread-per-core pools (polars, OpenMP) from inflating the address space.

**R2, coded v7-terminal precondition** (`stage.v7_terminal`, used by both tools):
- The record is `<FORECAST_ROOT>/r1-release-assembly-v7-20261022/control-v1/execution-exit.json`,
  the same `PREPARATION/execution-exit.json` that the evaluation v7 `execute.py` reads.
- It must be a regular file, not a symlink, at most 4 KiB, holding a JSON object with an integer `returncode`.
  It is read only; nothing else under the live root is touched.
- `place.py` checks it before verifying or creating anything, so no hard link is added while v7 is live.
  `host_run.py` checks it first among its preconditions.

**R3, the complete data-like listing** (`data_like_listing`):
- It records every file with a data-like suffix under `sys.prefix` and `sys.base_prefix`, as path and size only,
  and does not follow symlinked directories.
- Walk errors (unreadable directories, failed `lstat`) are recorded with a count and their paths.
- It stops at an explicit cap of 100,000 entries and sets `truncated: true` when it does.
- It is written exclusively to `run/reference-data-like.json`. `result.json` binds its sha256, count, truncation
  flag and walk-error count.

**Root binding (non-blocking N2):** `host_run.py` takes `--root` and refuses unless `--placement` is
`<root>/placement.json`. The approved ROOT is therefore an argument, never derived. Failure cleanup is `rm -rf`
of exactly that approved ROOT.

**Operating rules (non-blocking N1, stated in the `host_run.py` docstring):** the placement venv shares inodes
with the shared venv. Nothing may write into it in place: no pip, no bytecode (`-B` and `PYTHONDONTWRITEBYTECODE`
are set), no chmod or chown.

**A test fix found while doing this:** the base test asserted the shared `.pth`'s `st_nlink` unchanged. That
count is not stable, because uv's cache and other hard-linked copies also link the file; it changed during a local
run. The test now checks the real property: no file in the placement is the original `.pth` inode, and the
original's bytes and inode are unchanged.

## Tests

| Suite | Result |
|---|---|
| `revision-v2/test_host.py` | 39 passed |
| `ruff check` | pass |

The new tests:
- **R2:** the terminal record is refused when absent, a symlink, a string or bool returncode, not JSON, not an
  object, or oversized. Any integer returncode (0 or 1) counts as terminal. `place.py` refuses while v7 is live
  and creates no venv. `host_run.py` refuses (case `v7-live`) before writing anything.
- **R1:** the positive run asserts `limits-observed.json`: `ok` true, AS/FSIZE/CPU exact, nice ≥ base + 10, all six
  thread variables 2. A run whose `run/` exceeds its bound fails, although its tests passed. The limits are
  finite and small.
- **R3:** a synthetic prefix gives exact entries (data-like suffixes only, with sizes), one walk error for an
  unreadable directory, and `truncated` true with cap 1. The positive run binds the listing's sha256, count,
  truncation flag and error count in `result.json`.
- **Root binding:** a `--root` other than the placement's refuses before writing anything.

**Mutation controls** (`mutation_controls.py`; the 10 base cases plus 9 new):

| Mutation | Targeted tests |
|---|---|
| fd check removed | 1 failed |
| strace check removed | 1 failed |
| slurm check removed | 1 failed |
| staged tree not verified (host) | 1 failed |
| editable .pth not checked (host) | 1 failed |
| placement venv not required | 1 failed |
| unreviewed .pth allowed | 1 failed, 3 passed |
| editable shape unchecked (place) | 2 failed, 2 passed |
| stage verify ignores extras | 1 failed, 3 passed |
| data-like files allowed in closure | 3 failed |
| R2 place.py v7 terminal check removed | 1 failed |
| R2 host_run v7 terminal check removed | 1 failed |
| R2 returncode type unchecked | 2 failed, 5 passed |
| R1 limits not applied to the test tree | 1 failed |
| R1 thread caps dropped | 1 failed |
| R1 run size bound ignored | 1 failed |
| R3 walk errors dropped | 1 failed |
| R3 cap silently ignored | 1 failed |
| R3 listing not bound in result | 1 failed |

All 19 guard removals make a targeted test fail.

## Approval shape for the synthetic host run (the reviewer's stated list, filled where already fixed)

- **Tool shas:** `stage.py`, `place.py` and `host_run.py` from `pins.json` here. The tools dir is
  `<RESULTS_ROOT>/nobackup/<PROJECT>/newperiod-gate-host-tools-v2/`.
- **Gate pins:** fedf72b3. The stage-manifest sha is recomputed with these tools at staging time; the closure is
  unchanged at 105 files.
- **ROOT:** `<RESULTS_ROOT>/nobackup/<PROJECT>/newperiod-gate-host-v1`.
- **Source venv:** `<RESULTS_ROOT>/work/<PROJECT>/venv`, editable target `.../work/<PROJECT>/repo/src`.
- **strace and mode:** strace `aebaf212ce84a12208c5fa25f08c892029e6f6949b778da55e071ac145404a1e`, `--full`.
- **v7 precondition and limits:** as coded above.
- **Attempts:** `attempt_limit` 1 and no automatic retry. A failed run keeps its record. A refusal caused by
  strace 6.1 or the host allowlist (N4) is the expected fail-closed outcome and leads to a new revision.
- **Chaining:** `placement_sha256` is taken from `place.py`'s output and recorded before `host_run`.
- **Scope:** synthetic only: no N data, custodian path, access-log write, gate issuance or protected read.
- **Order:** only after R1 v7 is terminal, which the tools now enforce. Then the reviewer judges
  `reference-data-like.json` before any real gate run.
