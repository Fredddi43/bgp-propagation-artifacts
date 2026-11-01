# v8 post-evaluation candidate (LOCAL, constants-only re-pin)

Author: claude-opus-5-5, session <SESSION_ID> (/root/opus_implementation). Code only. Nothing here was captured, staged,
approved or run against the host. This covers the 13 post-evaluation tools the final inventory (8bcced6d) left
pending. It is separate from `v8-postprep-candidate` (67414ab7, under review), which it does not modify.

## Layout

This packet sits beside `r1-posteval-verification-20261022` at the same depth. So every `HERE`/`PACKET`/`OPS`
relation in the tools is byte-identical to v7, and no layout edit is needed. `build_posteval.py` regenerates every
tool from the reviewed v7 bytes. Each source must equal the package sha in its frozen v7 sub-packet `pins.json`, and
each of those seven pins files is itself pinned by sha:

| v7 pins | sha | bound by |
|---|---|---|
| `pins.json` (census, requests) | f2b223ee | `reviews/opus-verifier-review.txt` |
| `k2c/pins.json` | 57e6dc3d | `reviews/opus-k2c-approval.json` |
| `verifier-r2/pins.json` | 2a861eb0 | `reviews/opus-verifier-r2-review.txt` (CODEPASS) |
| `adapter-r2/pins.json` | 5eb25c10 | `reviews/opus-classd-transport-approval.json` |
| `classd-host/pins.json` | bffe254e | `reviews/opus-classd-transport-approval.json` |
| `vrun-host/pins.json` | 198fa9d3 | `reviews/opus-vrun-host-review.txt` |
| `d2-host-r2/pins.json` | 51de6bd3 | `reviews/opus-d2-host-r2-review.txt` (CODEPASS, code only) |

## What changes, per file (`diff-*.diff`; `planned.json` is the machine-readable inventory)

| File | Change |
|---|---|
| `requests.py` | v8 eval root; final spec sha -> `__V8_EXECUTION_SPEC_SHA256_AFTER_BUILD__` |
| `census.py` | v8 eval root; `SUPERVISOR_PID` -> `'__V8_EVALUATION_SUPERVISOR_PID_AFTER_LAUNCH__'` (resolves to an int literal) |
| `k2c/test_k2c.py` | held capture A from the v8 held directory; spec prefix check -> full equality with the spec marker |
| `verifier-r2/run_verify.py` | v8 eval root; final spec, spec/seal/ledger, R1 authorization -> markers; driver -> O1 33011eed |
| `verifier-r2/test_verify.py` | the staged-equal oracle source -> the v8 source tree (only the driver differs from v7) |
| `adapter-r2/adapter.py` | source manifest -> v8 6a9a325f; `VERIFIER_PINS_SHA256` -> the new verifier pins (cascade) |
| `adapter-r2/run_adapter.py` | spec/seal/ledger -> markers; disclosure text says v8 manifest |
| `adapter-r2/test_adapter.py` | v8 source tree, v8 manifest, v8 held captures; spec prefix -> full equality with the marker |
| `classd-host/stage_code.py` | fresh `r1-posteval-classd-v8-20261022`; `PINS` -> the new adapter/verifier pins (cascade) |
| `classd-host/phases.py` | fresh dest; seal path spec -> marker; v8 spec/ledger paths |
| `classd-host/test_host_phases.py` | same dest name in a temp path; seal path spec -> marker |
| `vrun-host/vrun.py` | fresh dest; v8 spec/ledger paths, seal spec -> marker; `CODE_SHAS` (cascade); docstring |
| `d2-host-r2/d2.py` | `V7` -> `V8` root (source tree + manifest); fresh dest; `HELD` -> v8 held dir; `CODE_SHAS` (cascade) |
| byte-identical | `verify_r1.py`, `extract_k2c.py`, `request-k2c.json`, `test_capture.py`, `test_vrun.py`, `test_d2.py` |
| generated | `verifier-r2/pins.json`, `adapter-r2/pins.json` (package shas of the re-pinned files) |

**Known v8 values used:**
- O1 33011eed, manifest 6a9a325f, the v8 source tree.
- The v8 held-capture directory `v8-postprep-candidate/tools/transition/evidence`, where capture A/B are to be
  written.
- The fresh host directory.
- Unchanged and still valid: manifests 45865cdf/f885a805, slice rules 0291d789, arm spec, population, forecast_train
  ebf066a2, scoring 740bf610, custody 409e1171.
- The v8 source manifest differs from v7 only in the driver; a test checks this.

**`verify_r1.py` is kept byte-identical (CODEPASS 5ed5229f).** Its docstring cites addendum-1's source list
("driver 4573658e"). That is a historical citation and stays true, and keeping the bytes keeps every check of them
valid. The inventory had listed that line for re-pinning; this is the decision not to.

## Pending identities and the one resolution interface

Six markers, each listed in `MARKERS`, with `planned.json` showing them per file:
- spec / seal / ledger (after the preparation);
- the final evaluation execution spec (final_build spec step);
- the R1 authorization receipt;
- the evaluation supervisor pid (launch receipt).

`build_posteval.py --resolve R.json OUT` writes the complete resolved packet. It requires all six and nothing else:
64-hex values, or decimal digits for the pid.

**Order:** edits -> resolution -> verifier pins -> `adapter.VERIFIER_PINS_SHA256` -> adapter pins -> `stage_code.PINS`
and the `CODE_SHAS` of `vrun.py` / `d2.py`. So the shas the transport and both host jobs check are of the resolved
bytes. All six values exist once the v8 evaluation is launched, so one resolution then, and its review, covers every
later step.

## Dependency order after the v8 evaluation (unchanged from v7, `reviews/opus-ordering-addendum-1.json`)

Each step needs its own exact approval and is one attempt with no retry.

1. **Resolution:** `--resolve`, then review of the resolved diff.
2. **Transport:** class (d)/(b) code transport T1/T2 with the same reviewed `stage_code.py` program and procedure,
   to the fresh `r1-posteval-classd-v8-20261022`. This may happen while the evaluation runs, as in v7.
   - The v7 `r1-posteval-classd-v1` on the host is not reused. Its five files bind v7 actuals, the v7 manifest and
     the v7 pins, so their shas differ from the v8 bytes. It stays untouched.
3. **K1 census, then K2a**, after the evaluation is terminal.
4. **Three lanes after K2a, which may run concurrently:**
   - L1: K2b -> extract -> K2c -> K3.
   - L2: D0 -> D1 -> F.
   - L3: vrun script -> exact run approval -> submit.
5. **D2** (labels + predictions, class (d)) needs its own approval after D1's measured bytes.

## Verification

- `test_posteval.py`: 22 passed.
  - Regeneration and line-by-line diff purity (static and cascade edits); the byte-identical files.
  - No v7 identity outside three declared history lines; roots and destinations.
  - The v8-vs-v7 source manifest check; the marker set; five resolution refusals.
  - A resolved build has no markers, an int pid and a consistent cascade.
  - **Unresolved:** each re-pinned suite runs, and the failures are exactly the tests that need the not-yet-captured
    v8 held metadata: 1 k2c test, 9 adapter tests on the held fixture, and test_d2 collection. Everything else passes:
    - test_capture 34;
    - test_verify 76, whose staged-equal oracle now runs against the O1 driver;
    - test_host_phases 31;
    - test_vrun 28;
    - the other adapter tests 31.
  - **Resolved rehearsal:** an overlay mirror of the repo holds the held v7 capture A/B metadata relocated onto the v8
    control paths, at the v8 held directory. spec/seal/ledger are resolved from it, and the other three markers are
    synthetic. All seven suites pass there with the v7 counts (34/5/76/40/31/28/47 = 261). This is not v8 evidence.
- `mutation_controls.py`: the unmutated copy passes, then 12/12 generator mutations are detected (`evidence/mutations.txt`). They cover the v7 dest, driver and manifest, all four stale cascade shas, the pid pattern and the pid literal, ignored resolution, the v7 held dir, and a non-pending spec.
- ruff: clean.
