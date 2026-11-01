# Tier-1 metadata capture program — code-only check packet

- **Author:** claude-opus-5-5, session `f1d352ff-…`, role label `/root/opus_implementation`.
- **Scope:** `../reviews/opus-tier1-capture-approval.json` `b81fa37c…`, review text `04e6b9ea…`, verdict
  `APPROVED_SCOPE_CONDITIONAL_ON_PROGRAM_CHECK`. Only tier 1, only the 7 approved files.
- **Status:** written and tested on synthetic files only. **Not run.**
  - No ssh, no remote read, no capture.
  - It may run only after this program passes an independent code-only check and root routes the run.
- **Exact bytes:** `pins.json`.

## Files

| File | Role |
|---|---|
| `remote.py` | Piped to `python3 -I -B -` on <BATCH_HOST>. Stdlib only. Embeds the 7 approved (path, sha256, limit) entries and the 20 MiB total limit. |
| `capture.py` | Local driver. Makes one ssh call, verifies the returned bytes, writes once, records the content checks. |
| `test_capture.py` | 20 synthetic tests. No ssh. |

## Mapping to the approval

**Host and transport**
- `capture.ARGV = ["ssh", "-o", "BatchMode=yes", "<BATCH_HOST>", "python3 -I -B -"]`, with the program bytes on
  stdin. The test fake asserts this exact argv and input.
- No Slurm. The remote program refuses unless all of these hold:
  - user `<USER>`
  - hostname `<BATCH_HOST>`
  - no `SLURM_JOB_ID`
  - `sys.flags.isolated` and `dont_write_bytecode`
- Off the approved host it refuses with empty stdout, which a test checks in a subprocess.

**Allowlist**
- `remote.ALLOWLIST` holds exactly the 7 approved paths, SHAs and limits: 1 MiB for the receipts and the slice rule,
  4 MiB for each union. `TOTAL_LIMIT` is 20 MiB.
- `capture.checked_inputs` will not run unless:
  - the approval and review hashes match
  - the program hash matches `--program-sha256`
  - the program's embedded allowlist and total limit equal the approval's
- A test shows that one changed limit refuses.

**Per-file remote checks, in order**
1. `os.path.isabs(p)` and `os.path.realpath(p) == p`. Tests cover a symlinked file, a symlinked parent directory and
   a relative path.
2. `os.open(p, O_RDONLY|O_NOFOLLOW|O_CLOEXEC|O_NONBLOCK)`. A test shows that a final-component symlink refuses even
   if the realpath check were bypassed.
   - **Disclosed addition:** `O_NONBLOCK` is not in the approval text. It only stops a FIFO from blocking the open,
     which the FIFO test proves, and it has no effect on regular files.
3. `fstat` must be `S_ISREG`. Tests cover a FIFO and a directory.
4. `0 < st_size <= limit`, then the running total `<= 20 MiB`. Tests cover the limit, an empty file and the total.
5. Read up to `st_size+1` bytes, require exactly `st_size`, and require that `fstat` (ino, size, mtime, ctime) did not
   change across the read. Tests cover a file larger than `st_size` and a simulated change.
6. `sha256` equals the approved digest, then the bytes decode as UTF-8 JSON with a top-level object. Tests cover a
   wrong hash, non-UTF-8, non-JSON and a JSON array.

**Failure behaviour**
- Any refusal aborts the **whole** capture: stdout stays empty and stderr carries
  `CaptureRefused <check>:<index>`, never file content.
- `capture()` has no partial return path.
- **Remote writes:** none. A test scans the remote program's AST:
  - imports are exactly `base64, hashlib, json, os, pwd, socket, stat, sys`
  - `os.*` calls are exactly `path.isabs, path.realpath, open, fstat, read, close, getuid, environ.get`
  - there is no builtin `open`, `exec`, `eval`, `compile` or `__import__`
  - Combined with `-B`, nothing is written: no files, temp files or bytecode.

**Local writes and attempts**
- Everything goes into `output/` with exclusive create:
  - `attempt-N-intent.json`, written before ssh, containing the argv, the program, approval and review hashes, and
    the start time
  - `attempt-N-result.json`, written after ssh, containing the rc, the stdout size and hash, a stderr tail, and the
    timestamps
  - and only after local re-verification (exact path set, sha256, size within limit, total, JSON object):
    `capture.json.gz` (`{path, sha256, size, raw_base64}`, gzip mtime 0) and `content-checks.json`
- One attempt only.
  - A second attempt is possible only when attempt 1 recorded `returncode 255` with 0 stdout bytes, and only once.
  - An intent without a result counts as uncertain and is never rerun.
  - Every refusal is terminal and records stay preserved.
  - Tests cover each of these cases.

**Content checks**
- These are the approval's three rules, recorded as found and never repaired (`repaired: false`):
  - **receipts:** `kind == "history_delay_frozen_model_sensitivity"` and `scores_computed is False`. The kind constant
    is `forecast_history_variants.DELAY_RECEIPT_KIND` in the staged source.
  - **slice rule:** `fit_outcomes_used is False` and the horizons keys are `{"30","60"}`.
  - **unions:** `passed is True`, `labels_read is False` and `prediction_values_decoded is False`.
- A failed check is a predicted guard failure. A test shows it is recorded and not fixed.

**Not authorized here and not implemented:** tier 2, the secondary authorization ca099b49, any listing, labels,
predictions, tensors, checkpoints, scores, remote writes, staging or execution. The program reads nothing else.

## Verification

```
.venv/bin/python -B -m pytest -q -p no:cacheprovider .agents/operations/r1-preparation-failure-v5-20261021/tier1-capture/test_capture.py
# 20 passed
.venv/bin/ruff check .agents/operations/r1-preparation-failure-v5-20261021/tier1-capture/
# All checks passed
```

## Run command (only after the code check passes and root routes it)

```
.venv/bin/python -B .agents/operations/r1-preparation-failure-v5-20261021/tier1-capture/capture.py --program-sha256 <remote.py sha256 from pins.json>
```

A clean capture is a **prediction** for guards 1821–1824, part of 1834–1840, and 1870. It is never a pass; only the
next full run proves those guards.
