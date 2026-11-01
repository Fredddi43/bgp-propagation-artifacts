# Attempt-3 host probe, revision 3 (delta for review bc15b17e: D1-D4 + parent owner)

Author: claude-opus-5-5, session <SESSION_ID>. Local only; nothing here has run on the host. `../attempt3-probe/` (0bc9b3a0)
and `../attempt3-probe-r2/` (3b7366f6) are preserved unchanged. Only `probe.py` changed (`delta-probe.diff` against
r2). `test_probe.py` and `mutation_controls.py` changed accordingly (`delta-test_probe.diff`). Nothing else in the
probe was refactored.

## Changes

**D1: owned process groups.** `run_child()` replaces `subprocess.run` for A and B.
- `Popen(..., start_new_session=True, preexec_fn=limits)`, then `communicate(timeout=900)`.
- On `TimeoutExpired`, it calls `killpg(SIGKILL)` and then a bounded `communicate(60)`. If even that times out, it
  kills the direct child and waits at most 60 s.
- A `finally` always sends `killpg(pid, SIGKILL)`, ignoring `ProcessLookupError`.
- It then counts the group's remaining members from the numeric pgrp field of `/proc/<pid>/stat` (parsed after the
  last `)`, so a comm with spaces or parentheses cannot shift it). There is no cmdline match and no pkill.
  - The count waits at most 5 s for live members to go.
  - Each child records `group = {timed_out, survivors, survivors_live}`, where survivors includes zombies. The scratch
    record carries the summed survivors.
- All of this happens before the scan and the rmtree.
- The docstring states the residual limit: a descendant that calls setsid() leaves the group.
- **Zombies, concretely:** a killed grandchild is reparented and reaped by its reaper. Locally the sleeping
  grandchild was `gone` (or at most `Z`) right after the run, and both groups reported survivors 0. I do not assert
  survivors == 0 including zombies on the host: only the live count is under the probe's control. A zombie still
  appears in the total and is reported, not hidden.

**D2: no hang on a B failure, and runner timeouts are recorded.**
- `os.close(w)` sits in a `finally` around B, and the drain thread is `daemon=True`.
- A B timeout no longer raises: `run_child` handles it. If B fails to start, the pipe is closed, the run is recorded as
  `run_error`, the scratch is still scanned and removed, and the exit code is 4.
- Locally, `run()` catches `subprocess.TimeoutExpired` from the runner and still writes `result.json` exclusively:
  `returncode null`, `timed_out true`, the partial stdout capped at 1 MiB with its sha256, and the stderr tail. It then
  refuses. The attempt is final.

**D3: the scan can never skip cleanup.** `SCAN` is a named snippet included verbatim in REMOTE, so its bytes are
tested directly.
- Per-entry `lstat` errors and `os.walk` errors (`onerror`) are recorded: `error_count`, plus the first 20 errors.
- It keeps the totals `entries` and `bytes`, and lists the first 2,000 entries (`truncated`). Counting stops at a hard
  ceiling of 200,000 entries (`ceiling_hit`).
- The whole scan call is in its own `try` inside the `finally`, so rmtree is always attempted, exactly once.
- A failed removal names the leftover path (`scratch.leftover`) and exits 3.

**D4: cwd = SCRATCH.**
- The payload and REMOTE bind `HOME == TMPDIR == cwd == SCRATCH`. A different cwd refuses before the mkdir.
- B reports `trace.cwd_relative`: every cwd-relative open attempt with its result, capped at 500, with a count and a
  truncation flag. That covers `openat`/`openat2` with `AT_FDCWD`, and `open`/`creat` with a relative path.
  - An unfinished call takes the result of its `<... resumed>` line.
  - An unresumed one is reported as `unfinished`.
  - Opens relative to another dirfd are not cwd-relative and are excluded.
- `cwd_top_level_changed` is dropped, both the code and the FULL key.
- The docstring now states the parity limit in place of "cwd as pytest gave the witness child": a repo-root file a
  library would read is ENOENT in the probe. The first attempt is still named, but later library behaviour may
  differ.

**Non-blocking S1 item:** the parent must be owned by the caller (`os.lstat(parent).st_uid == os.getuid()`), before
the mkdir.

## Verification

- **`test_probe.py`: 40 passed.** That is the 27 from r2, adjusted for cwd = SCRATCH and no `cwd_top_level_changed`,
  plus these:
  - **D1:**
    - a child that starts a detached `sleep 60` grandchild: after the run that pid is gone (or a zombie),
      `survivors_live == 0`, and the scratch is removed;
    - A and B each time out (3 s against a 120 s sleep): `timed_out true`, `survivors_live 0`, B `reader_alive false`,
      JSON printed, scratch removed, all well under 60 s.
  - **D2:**
    - B fails to start (no tracer binary): exit 4, `run_error` FileNotFoundError, JSON printed, scratch removed,
      under 60 s;
    - a runner timeout writes `result.json` with `timed_out`, the partial stdout and its sha, refuses, and a second
      run is refused.
  - **D3:**
    - an entry vanishing between walk and lstat is recorded (`error_count 1`), the others are listed, and totals
      exclude it;
    - cap, ceiling and a missing root;
    - a scan that raises inside REMOTE, forced via the walk (caught inside `scan`) or by `scan()` itself raising
      (caught by the outer guard in `finally`), still yields JSON and removal.
  - **D4:**
    - a relative `open("relative-probe-target")` in B is reported with ENOENT;
    - a relative write in A lands in the scratch (listed) and the repo stays untouched;
    - the parser on fixed lines: AT_FDCWD relative, absolute excluded, dirfd excluded, `open`, unfinished/resumed,
      never-resumed, cap and count;
    - a cwd that is not the scratch refuses.
  - **Parent owner:** a scratch under `/tmp` (root-owned, world-writable, so the mkdir alone would succeed) refuses
    before anything is created.
- **`mutation_controls.py`:** the unmutated copy must pass first. The 19 mutations and their results are in
  `evidence-local/mutations.txt`.
  - r2's `relative-file-resolved` mutation is now equivalent and is dropped, with a note. cwd is bound to the scratch,
    outside the repo, so a relative `__file__` cannot resolve into it. The isabs guard stays.
  - D2's protection is two independent guards (the `finally` close and the daemon drain). Removing either alone still
    exits, so the D2 mutation removes both. That combination is the one that hangs.
- ruff: clean.
