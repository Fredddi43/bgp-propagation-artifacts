# Review packet: gate host readiness, revision-v3 (runtime hook admitted by exact hash; final-eval terminal record)

- Author: claude-opus-5-5, session <SESSION_ID> (`/root/opus_implementation`).
- Base: revision-v2 (pins 7cbdf2ff, CODEPASS), unchanged. These files are copies with the deltas below.
- Trigger: attempt 2 is terminal at S4 (result d2e45ef2, reviewer assessment ada45289). The shared venv carries
  virtualenv's `_virtualenv.pth`.
- Captured once, read-only, under approval 931aa472: `runtime-capture-v1/evidence/runtime-capture.json` 99e15e99,
  result-ready 72005fba.
- **Nothing is placed, staged or run.** The R1 final evaluation (supervisor 317830) is live and untouched. No
  approval is claimed.

## The captured hook (read as text only; never imported or executed)

| File | Size | sha256 | Content |
|---|---|---|---|
| `_virtualenv.pth` | 18 B | 69ac3d8f… | exactly `import _virtualenv` |
| `_virtualenv.py` | 5246 B | cfb3db86… | stock virtualenv runtime patch, described below |

What `_virtualenv.py` does:
- At module level it imports `contextlib`, `os` and `sys`, all standard library. It reads no file, and its only
  `os` use is `os.path.abspath(__file__)`. It does not touch `sys.path`.
- It inserts one `_Finder` at `sys.meta_path[0]`. `find_spec` returns `None` for every name except
  `distutils.dist` and `setuptools.dist`.
- For those two only, it lazily imports `threading`, `functools.partial` and `importlib.util.find_spec` (all
  standard library), delegates to the normal finder, and wraps the loader to patch
  `Distribution.parse_config_files`. The patch makes `install` prefix and path options stay inside the venv.
- **Effect on the gate:** one extra finder on each import, which returns `None` unless a distutils/setuptools
  module is imported. No non-stdlib module is imported, so the reviewer's condition for a further capture is not
  met. Every file it touches is under `sys.prefix`/`sys.base_prefix`, the witness's reference roots.

## Deltas

**1. Exact admission of the hook (`place.py`):**
- `REVIEWED_HOOK` = `{'_virtualenv.pth': 69ac3d8f…, '_virtualenv.py': cfb3db86…}`. These are two literal names
  with no pattern; a test binds them to the capture evidence.
- `checked_source_venv` admits `KNOWN_PTH`, plus `_virtualenv.pth` only when `REVIEWED_HOOK` is set.
- When `_virtualenv.pth` is present, `checked_hook` requires both files to be regular files, not symlinks, at
  exactly the reviewed sha.
- Any other `.pth` still refuses, including `_virtualenv2.pth` and `_virtualenv_extra.pth`.
- The editable `.pth` check is unchanged.

**2. Binding the executed hook code to the reviewed source (`place.py`):**
- Python reads an existing `__pycache__/*.pyc` even under `-B`. So a reviewed `.py` hash alone does not fix what
  runs: a stale or altered cache with a matching header would execute instead.
- The placement therefore does not hard-link `site-packages/__pycache__/_virtualenv.*.pyc` (it records them in
  `runtime_hook_cache_skipped`). It re-checks the hook in the placement, and refuses if any such cache was linked.
- Under `-B` and `PYTHONDONTWRITEBYTECODE` the placement compiles the reviewed source in memory and writes
  nothing.
- No shared file is touched: these are skipped links, not deletions.

**3. Re-check at run time (`host_run.py`):** `checked_placement` requires all of the following, or refuses before
writing:
- the placement's `.pth` set ⊆ `KNOWN_PTH` plus the hook;
- the hook is present exactly when `placement.json` records it;
- the recorded hook equals `REVIEWED_HOOK`;
- the bytes match;
- no hook `.pyc` exists.

**Limitation:** the venv's own interpreter runs `site` before `host_run` starts, so the hook has already been
imported when the check runs. The binding that counts is `place.py`'s, under the base interpreter at S4; this
re-check only detects a later change.

**4. R1 final-evaluation terminal record (`stage.py`, `place.py`, `host_run.py`):**
- `EVAL_EXIT` = `…/r1-release-assembly-v7-20261022/evaluation-control-v1/execution-exit.json`.
- `eval_terminal()` is as strict as `v7_terminal()` (both use the shared `terminal_record`): a regular non-symlink
  file of at most 4 KiB with an integer returncode.
- `place.py` and `host_run.py` require both records before anything else. So no hard link or run happens while
  the final evaluation is live.

Unchanged: the stage closure (manifest 3e01aed8, 105 files), gate pins fedf72b3, the limits, the data-like listing,
the strace binding and every v2 guard.

## Tests

| Suite | Result |
|---|---|
| `test_host.py` | 61 passed (208 s) |
| `ruff check` | pass |

The tests are the 39 revision-v2 tests (fixtures extended for the second record and the hook constants), plus:
- **Binding:** `REVIEWED_HOOK` equals the capture evidence, the approval is 931aa472, and there are exactly two
  names.
- **Real captured bytes,** written as data: they pass `checked_hook`, and one changed byte refuses.
- **Admission matrix:** a positive case and 7 refusals: unreviewed constant, `.pth` bytes, module bytes, module
  missing, module symlink, a second hook `.pth`, a prefix lookalike.
- **Placement with the hook and a poisoned cache:**
  - first proves the source venv really executes the poisoned `.pyc` (flag `poison`);
  - then the placement skips it, links the reviewed module (same inode), runs the reviewed source (flag `source`),
    and writes no `.pyc`.
- **Placement without the hook** records `runtime_hook: null`.
- **`host_run` refusals with the hook** (no `run/` created): an added `.pyc`, a tools hook that differs, changed
  hook bytes, and hook bytes swapped after placement for other bytes the tools would accept (only the
  placement-record binding notices that one).
- **`host_run` smoke** with the reviewed hook in place passes.
- **Final evaluation:** `place.py` refuses while it is live and creates nothing; `host_run` refuses (case
  `eval-live`); strict record checks (absent, string or bool returncode).

**Mutation controls:** all 27 detected (the 19 v2 cases, 3 anchors updated for the v3 text, plus 8 v3 cases).
- 24 come from the full run on the previous test revision.
- 3 were re-run after two test fixes: the `v7-live` case now has a valid final-eval record, and the
  `swapped-reviewed` case was added. The other 24 targeted tests did not change.
- `mutation_controls.py [names…]` runs a subset.

| v3 mutation | Targeted tests |
|---|---|
| final-eval check removed (place) | 1 failed |
| final-eval check removed (host) | 1 failed |
| hook admitted without its bytes | 4 failed, 4 passed |
| wildcard hook admission | 2 failed |
| symlinked hook accepted | 1 failed |
| hook bytecode linked | 1 failed |
| host bytecode re-check removed | 1 failed |
| host hook binding removed | 1 failed, 1 passed |
| (v2) host_run v7 terminal check removed | 1 failed (was undetected before the `v7-live` fix) |

## Proposed future attempt 3 (not requested for approval now; needs the R1 final evaluation's terminal proof first)

**Paths:**
- Fresh ROOT `<RESULTS_ROOT>/nobackup/<PROJECT>/newperiod-gate-host-v3`.
- Tools dir `<RESULTS_ROOT>/nobackup/<PROJECT>/newperiod-gate-host-tools-v3`.
- Local stage `/tmp/newperiod-gate-host-stage-v3`.
- Evidence `revision-v3/evidence-synthetic-v3`.
- The attempt-2 ROOT (`newperiod-gate-host-v1`) and `newperiod-gate-host-tools-v2` are preserved as they are.

**Steps:** the same as approval-v2 plus addendum-1, with the revision-v3 tools and these paths.

**Preconditions:**
- P0 adds `evaluation-control-v1/execution-exit.json` with an integer returncode, and the supervisor 317830 is
  gone. The tools also enforce the record.
- The preflight is re-run with the new paths.

It needs a new exact approval. Attempts 1 and 2 stay recorded. No automatic retry, no cleanup.
