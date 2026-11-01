# Attempt-3 host probe, revision 2 (delta for review 48e0231b)

Author: claude-opus-5-5, session <SESSION_ID>. Local only. Nothing here has run on the host. The original packet
`../attempt3-probe/` (pins 0bc9b3a0) is preserved unchanged. The evidence analysis there still stands; the reviewer
agreed with it. Scope unchanged: `newperiod-attempt3-host-probe-v1`, one attempt.

## Changes, by finding (`probe.py` is the only tool file; `test_probe.py` grows)

**P1: HOME/TMPDIR pointed at a removed directory.**

The fix follows the root's correction of the suggested `/tmp` path: on <BATCH_HOST>, host writes are allowed only
under `<CLUSTER_STORAGE>/<PROJECT_STORAGE>{results,models}`.

- **The scratch directory.**
  - `SCRATCH = <RESULTS_ROOT>/nobackup/<PROJECT>/newperiod-probe-scratch-v1`. It lies outside the
    preserved attempt-3 placement and outside the shared venv tree.
  - It is the same class as attempt 3's `<PLACEMENT>/run/tmp`: an existing, writable directory on `<CLUSTER_STORAGE>`, outside
    every reference root and system path. Only the exact path differs, and the docstring says so.
- **Before A and B, REMOTE:**
  - asserts HOME == TMPDIR == SCRATCH, that the parent is a real, non-symlinked directory, and that SCRATCH is
    absent;
  - then calls `os.mkdir(SCRATCH, 0o700)` and checks it is a directory with mode 0700 owned by the caller.
- **A and B** run with that HOME/TMPDIR, and with `cwd=<PLACEMENT>/repo`.
  - That is the cwd pytest gave the attempt-3 witness child: `test_gate.witness_run` passes no `cwd`, and
    `host_run.py` ran pytest in `root/'repo'`.
  - The repo root itself is not a reference root, so a cwd-relative open is part of the F2 parity.
  - The old probe ran in the ssh login directory.
- **After A and B (in `finally`):**
  - a bounded listing of SCRATCH: relative path, type and size, no content, at most 2,000 entries, with a truncation
    flag;
  - then `shutil.rmtree(SCRATCH)`, which touches only the directory this run created, and an explicit check that it
    is gone;
  - whether the cwd's top-level entries (name and mtime) changed.
- **In B,** an outside open under SCRATCH is shown as `$SCRATCH/...`.
- **`limits()`** now adds RLIMIT_FSIZE 256 MiB (host_run LIMITS) next to nice 10, RLIMIT_AS 8 GiB and RLIMIT_CPU 600 s.
- **Failure handling.**
  - A refusal before the mkdir (scratch exists, wrong tracer or package sha, symlinked parent, HOME/TMPDIR not the
    scratch) creates nothing and prints nothing. A pre-existing SCRATCH is never touched.
  - An exception in A or B is recorded as `run_error`; the listing and removal still run, and the exit code is 4.
  - A failed removal is recorded (`scratch.removed false` plus the error), and the exit code is 3.
  - Locally, `run()` writes `evidence/probe.json` whenever the output parses with the expected keys, even on a
    non-zero exit. It still refuses afterwards, so the evidence is kept and the attempt is marked failed. There is
    no retry.

**P2: tracer identity.**
- `payload()` binds `strace` `/usr/bin/strace` and `strace_sha256` `aebaf212…` (the attempt-3 tracer).
- REMOTE asserts `x["strace"] == syscall_trace.STRACE` and the sha before anything is created.
- The output carries `tracer` = `syscall_trace.tracer_identity()` (path, sha256, version). It is taken before the
  mkdir, so a failing `strace -V` leaves nothing behind.

**P3: placed code beyond the two checked files.**
- After `install_readers`, A reports `repo_modules`: the sha256 of every loaded module file under `<PLACEMENT>/repo`.
- **Two corrections found while testing this:**
  - The witness and the modules it loads by spec (`cni`, `boundary`, …) are not in `sys.modules`, so A walks
    `[aw, modules bound in aw's namespace, *sys.modules]`.
  - A relative `__file__` (one module has `_classes.py`) is never resolved against the cwd. Before this fix it was
    misattributed to the repo and made A fail locally.
- Files under the interpreter prefixes are excluded; locally the venv sits inside the repo.
- Also `interpreter`: `realpath(sys.executable)`, `sys.prefix`, `sys.base_prefix`.
- Reporting only, not a gate.

**P4: honest wording.**
- The docstring now states the exact write boundary:
  - host: only SCRATCH, created, listed and removed;
  - a library write elsewhere is not prevented, only bounded by RLIMIT_FSIZE, and a change in the cwd's top level is
    reported;
  - local: `probe-records/{intent,result}.json` and `evidence/probe.json`, exclusive.
- It also states A's inference limit, next to B's:
  - A is import-time only. The witness child also ran stages pins..marker before `readers`.
  - So "install_readers ok" localizes F1 to stage-time imports; it does not clear it.

**N1:** `trace.reader_alive` = `reader.is_alive()` after the 60 s join.

## Verification

- **`test_probe.py`: 27 passed.**
  - 11 approval cases.
  - The payload: scratch under `<RESULTS_ROOT>`, not under the placement, not `/tmp`, not the shared
    venv tree; tracer aebaf212; fsize 256 MiB; cwd is the placement repo.
  - Run-once with records.
  - Five failure cases: rc, shape, scratch-not-removed, run-error, and rc 0 but not removed. Partial evidence is kept
    exactly when the shape allows.
  - The local mirror run:
    - `install_readers` ok, nothing missing, no outside aliases;
    - `repo_modules` holds the witness at its CODEPASS sha, `custodian_newperiod_inputs.py`, `forecast_train.py` and
      `boundary.py`, with no venv files;
    - interpreter, `reader_alive` false, tracer sha;
    - the scratch is removed and the cwd is unchanged.
  - Library-style writes (a `tempfile.mkstemp` file, `$HOME/.cache/lib`) land in the scratch, are listed and are
    removed.
  - Cleanup failure (a 0500 subdirectory): the JSON still prints, `removed` is false, the error is
    `PermissionError`, exit 3.
  - Five refusals before anything is created: scratch exists (its content is preserved), tracer sha, symlinked
    parent, witness sha, TMPDIR not the scratch.
  - RLIMIT_FSIZE is applied: a 2 MiB write under a lowered 1 MiB cap fails child A, the scratch is still removed and
    the evidence still prints.
- `mutation_controls.py`: the unmutated copy passes, then 10/10 mutations are detected (`evidence-local/mutations.txt`):
  no tracer sha check, scratch reuse (`makedirs(exist_ok)` without the absence assert), no RLIMIT_FSIZE, no cleanup,
  no `reader_alive`, HOME not bound to the scratch, cleanup failure exiting 0, no witness-namespace modules, relative
  `__file__` resolved against the cwd, evidence not kept on failure.
  - Dropping only the absence assert is an equivalent mutant, because `os.mkdir` is exclusive anyway.
  - For the scratch-exists test the pre-existing directory is made 0700 by the caller, so the mode/owner check
    cannot mask a missing exclusivity check.
- ruff: clean.
