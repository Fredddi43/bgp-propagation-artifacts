# Review packet: N input gate launcher, revision-v2 (round-1 R1, plus N3)

- Author: claude-opus-5-5, session <SESSION_ID> (`/root/opus_implementation`).
- Base: the launcher one directory up, unchanged. Pins 1c92db00; round-1 review/verdict 9ff02f13:
  CHANGES_REQUIRED (R1 only), reviewer 4ba6111c. Everything not listed below is byte-identical in behaviour, and
  base REVIEW.md §1-§2 still describe it.
- Nothing ran on the host. No approval is claimed.

## Changes

**R1, the evaluation contract's interpreter anchor restored:**
- The spec must carry `python_executable` (the resolved interpreter, e.g. miniforge `python3.12`) and
  `python_sha256` (`checked_spec`). Missing or malformed values refuse.
- `gate_execute.placement()` refuses unless `str(Path(sys.executable).resolve()) == spec['python_executable']`
  and `sha(sys.executable) == spec['python_sha256']`. The placement venv's `bin/python` is a symlink into the
  shared interpreter, so this binds the binary that actually runs.
- `launch.py`'s REMOTE transport program asserts the same two equalities before any stage or launch action, as
  the evaluation v7 `launch.py` does.

**N3:** `checked_gate_phase` refuses unless both the witness phase's stages and the gate plan's horizons are
exactly `{'30', '60'}`. That gives an explicit refusal instead of a KeyError.

**N1, wording only, no new caps:** `as_bytes`, `fsize_bytes` and `cpu_seconds` are set by the exact phase
approval. The code requires them to be positive integers. Only `nice ≥ 10`, `threads ≤ 4` and
`wall_seconds ≤ 4 h` are bounded in code. The base REVIEW's phrase "within the coded caps" is corrected here
accordingly.

**N2, not implemented:** a host free-memory or disk-headroom check. The rlimits bound the process tree, but host
headroom is not checked; this stays a stated limitation for the real-run approval.

## Tests

| Suite | Result |
|---|---|
| `test_launch.py` | 43 passed |
| `ruff check` | pass |

The base tests are adapted only for depth and the two new spec fields. New tests:
- **R1 (spec):** refusals for another `python_sha256`, another `python_executable`, and a missing anchor.
- **R1 (transport):** `launch.py`'s REMOTE program runs locally from the placement venv against a package
  directory, with only the host and user strings patched. Under the exact interpreter it stages the phase root
  (`stage-complete.json`, read-only files). With another interpreter sha or path it refuses with an
  AssertionError and stages nothing.
- **N3:** a gate plan naming only horizon 30 refuses before any stage.

**Mutation controls** (the base 12 plus 2):

| Mutation | Targeted tests |
|---|---|
| unresolved references accepted | 1 failed |
| author may approve | 1 failed |
| phase flags unchecked | 1 failed |
| limits unchecked | 1 failed, 1 passed |
| staged closure unchecked | 1 failed |
| placement venv not required | 1 failed, 1 passed |
| inherited descriptor allowed | 1 failed |
| plan tracer/roots unchecked | 1 failed |
| output outside phase root allowed | 1 failed |
| gate binding unchecked | 4 failed |
| witness exit unchecked | 1 failed |
| interpreter anchor removed | 2 failed, 2 passed |
| horizon set unchecked | 1 failed |
| first failure does not stop the phase | 1 failed |

All 14 guard removals make a targeted test fail. With the worker's interpreter anchor removed, the two transport cases still refuse, because the REMOTE program checks the anchor too (both checks restored, as in the evaluation contract).
