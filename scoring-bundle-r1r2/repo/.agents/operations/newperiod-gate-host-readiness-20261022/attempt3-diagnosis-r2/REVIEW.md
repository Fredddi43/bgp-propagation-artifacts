# Attempt-3 diagnosis capture r2 (log only)

Author: claude-opus-5-5, session <SESSION_ID>. Local only; nothing here was run against the host.

## What happened to capture attempt 1

- Approval 32713e9b (tool af607ccf, pins 65793501), run ONCE on root's routing, 2026-10-22.
- Result: local rc 1, remote rc 1, stdout empty. Remote traceback: `<string>` line 19 `AssertionError`, which is
  `assert os.path.isdir(chain0) and not os.path.islink(chain0)` (the program starts with a newline).
- So the log was opened and matched 4dc9e76f (that assert carries a message and comes first). chain0 is absent, not a
  directory, or a symlink. Nothing was captured and nothing was written on the host.
- Records preserved: `../attempt3-diagnosis/capture-records/` (intent 62dd595c, result 05b46c89) and
  `../attempt3-diagnosis/coordination/capture-outcome.json`. No retry.

## Cause (found locally, after the fact)

`revision-v3-round2/host_run.py` line 217 runs `shutil.rmtree(out / 'basetemp', ignore_errors=True)` after every run.
chain0 and both witness traces were therefore expected to be gone. The attempt-1 design (my DIAGNOSIS.md) required a
chain0 listing; that was an author error, and the review did not catch it either. The raw traces cannot be recovered.

## r2

`capture_diag.py` reads `run/pytest.log` alone: O_NOFOLLOW regular file, 64 MiB cap, refused unless its sha256 is
4dc9e76f. New scope `newperiod-attempt3-diagnosis-capture-v2`, so the attempt-1 approval cannot be reused; records go
to this directory, never to the attempt-1 records. One attempt, no retry, no host write.

What the log can and cannot settle: the first failing test asserts `result.returncode == 0, result.stderr`, so the
witness's stderr is in the log. A `TraceError` (H-a) or strace's own message (H-d) shows directly there. A refusal
naming a path separates a host system path (H-b) from a synthetic-world data path (H-c), **if** the witness names the
path in its message. Without the raw trace, a fix may still need a new synthetic host run (attempt 4) that keeps its
traces. That is a separate reviewed decision.

## Verification

`test_capture_diag.py`: 23 passed (12 approval cases, including the v1 scope, tool and payload; payload is the log
alone; one attempt with records; failure is final for rc / log-sha / extra key; the remote program run locally reads
exactly the log and refuses a sha mismatch, a symlink, oversize, a missing file and a directory). ruff clean.
