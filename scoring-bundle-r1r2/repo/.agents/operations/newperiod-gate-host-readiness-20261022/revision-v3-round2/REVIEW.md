# Review packet: gate host readiness revision-v3, round 2 (C1 only). LOCAL; nothing placed or run.

- Author: claude-opus-5-5, session <SESSION_ID> (`/root/opus_implementation`).
- Base: revision-v3, pins f4c297b7 (its bytes are preserved). Verdict bfb1b3e3: CHANGES_REQUIRED, C1 only, reviewer
  4ba6111c.
- Nothing is placed, staged or run. The R1 final evaluation (supervisor 317830) is live and untouched. No approval
  is claimed.

## Change (C1; no other code byte changes)

`place.py` has one new import (`stat`) and one new helper, `_fd_sha256`. `checked_hook` uses that helper:
- one `os.open(path, O_RDONLY | O_NOFOLLOW)`;
- `fstat` → `S_ISREG`;
- sha256 of the bytes read from that same descriptor;
- `close` in `finally`.

Any `OSError` or non-regular file gives `None`, so it refuses with the same
`ValueError('Runtime hook differs from its reviewed bytes: <name>')`. The earlier `is_symlink()` / `is_file()` /
`read_bytes()` sequence, which can be swapped between check and read, is gone.

`stage.py` and `host_run.py` are byte-identical to revision-v3. `host_run` calls `place.checked_hook`, so it gets
the same read.

## Tests

| Suite | Result |
|---|---|
| `test_host.py` | 62 passed (213 s): the 61 of v3 plus T1 |
| `ruff check` | pass |

**T1:** `test_checked_hook_refuses_a_symlink_to_the_reviewed_bytes_even_if_the_symlink_check_is_fooled`.
- `_virtualenv.py` is a symlink to a file holding exactly the reviewed bytes.
- `Path.is_symlink` is monkeypatched to answer False.
- `checked_hook` refuses (ELOOP from `O_NOFOLLOW`).
- Control: the same bytes as a regular file pass.

**Mutations,** re-run for the changed hook code:

| Mutation | Targeted tests |
|---|---|
| M1: hook read reverted to `path.read_bytes()` (the v3 line) | 1 failed (T1) |
| `O_NOFOLLOW` dropped (replaces the v3 "symlinked hook accepted" case, whose anchor no longer exists) | 2 failed |
| hook admitted without its bytes | 4 failed, 4 passed |
| wildcard hook admission | 2 failed |

The other 23 v3 cases are unchanged in code and in their targeted tests.

## Non-blocking items, carried as a PROPOSED attempt-3 preflight (`preflight_probe_v3.sh`, not run)

This is the reviewer's "not required as code" (b) plus NB1, as read-only checks:
- the fresh v3 ROOT and tools dir are absent;
- H1-H3 as in attempt 2;
- `sitecustomize.py` / `usercustomize.py` are absent in the source site-packages, and `sitecustomize.py` is absent
  under the base prefix;
- the final evaluation's `execution-exit.json` is a small regular file with its content recorded;
- `/proc/317830` is absent;
- no process has the exact control-root `execute.py`, `supervise.py` or `run.sh` path as an argv element.

The argv scan is pure bash with no subprocess, so no process carries a marker path in its own argv. A local sanity
run found exactly the planted exact-path sleeper and not its `.bak` lookalike.

**Not requested now:** the attempt-3 approval. It needs the final evaluation's terminal proof first.
