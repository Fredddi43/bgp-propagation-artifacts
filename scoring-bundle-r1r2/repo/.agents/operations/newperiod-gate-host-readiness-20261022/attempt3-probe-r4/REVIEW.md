# Attempt-3 host probe, revision 4 (after the failed r3 run)

Author: claude-opus-5-5, session <SESSION_ID>. LOCAL proposal only; nothing here has run on the host. The r1, r2 and r3
packets are preserved and committed (c12d12d).

## What the approved r3 run did (2026-10-22T14:12:03Z-14:12:09Z, approval 3803dde6, once)

- **Result:** local rc 1, remote rc 1, empty stdout. Records: `../attempt3-probe-r3/probe-records/` (intent 42374087,
  result 6549d400) and outcome `../attempt3-probe-r3/coordination/run-outcome.json` d7046ab9.
- **Where it stopped:** remote line 20, `assert stat.S_ISDIR(...) and stat.S_IMODE(info.st_mode)==0o700 and
  info.st_uid==os.getuid()`, immediately after `os.mkdir(scratch, 0o700)`.
  - Every earlier check passed: identity, the placed package shas, the tracer sha aebaf212, HOME == TMPDIR == cwd ==
    scratch, the parent being real and owned by the caller, and the scratch being absent.
- **Cause:** `<CLUSTER_STORAGE>` is setgid (Slurm skill §5: group `<CLUSTER_GROUP>`, setgid). A new directory inherits S_ISGID, and
  `S_IMODE` includes that bit, so the mode was 0o2700.
  - Reproduced locally with the exact r3 REMOTE under a setgid parent: rc 1, empty stdout, AssertionError at this
    check, and a leftover directory with mode 0o2700.
  - The host directory's mode was not read: no further host read is authorized.
- **Consequences:**
  - The check sat before the cleanup `try/finally`, so the empty scratch
    `<RESULTS_ROOT>/nobackup/<PROJECT>/newperiod-probe-scratch-v1` is left on the host. It is
    reported only: not removed, never reused.
  - Neither child ran, so **there is no F1/F2 data**. F1 (which reader or alias) and F2 (which outside path) are as
    unknown as before.
- **A gap in review:** the reviews (and I) checked that every refusal came before the mkdir. They did not check that
  every check after it sat inside the cleanup block.

## The r4 change (`delta-probe.diff` against r3; nothing else changed)

1. The post-mkdir check moves to the top of the main `try`, so a failure there is `run_error`: the scratch is still
   scanned and removed, the JSON prints, and the exit code is 4. It now compares the permission bits
   (`mode & 0o777 == 0o700`), the directory type and the owner. The setgid bit is allowed and recorded as
   `scratch_mode = {octal, setgid}`, a new key in FULL.
2. `SCRATCH` becomes `.../newperiod-probe-scratch-v2`. The v1 leftover must never be reused, and r4's
   "scratch absent" check would refuse it anyway.
3. The docstring states both changes.

## Not in r4 (a separate decision)

Removing the v1 leftover would be one more host write. It could be a one-line `rmdir` of exactly that path (it fails
unless the directory is empty), under its own approval. It is not added to the probe.

## Verification

- **`test_probe.py`: 43 passed.** That is the 40 from r3 plus three:
  - the scratch path is v2, and v1 appears nowhere in the payload;
  - **setgid parent** (the host failure reproduced): mode 0o2700 is accepted, `setgid` is recorded, both children
    run, and the scratch is removed;
  - **a failing post-mkdir check** (forced): exit 4, `run_error` with the check's message, no child run, and the
    scratch still removed.
- `mutation_controls.py`: the unmutated copy passes, then 22/22 mutations are detected (`evidence-local/mutations.txt`). Three new r4 mutations: the strict `S_IMODE`
  comparison, the check moved back before the cleanup block, and the v1 path.
- ruff: clean.

## What a successful r4 run would and would not settle (unchanged from r3)

- **A (import time):** whether the host lacks a listed reader or holds an outside alias. It cannot see stage-time
  lazy imports.
- **B (import and start-up under strace):** opens outside the roots, and cwd-relative attempts. It cannot see
  audit-time opens, a repo-root file read through the cwd (ENOENT here), or descendants that call setsid().
