# v8 post-preparation candidate (LOCAL, constants-only re-pin)

Author: claude-opus-5-5, session <SESSION_ID> (/root/opus_implementation). Code only: nothing here was captured, staged,
approved or run against the host. The v8 preparation (spec caafc95d; supervisor 469425, worker 469426; launched
2026-10-22 12:18:42Z) was still running when this was frozen.

## What it covers

The post-preparation critical path, from the v8 preparation terminal up to the evaluation launch:

| Step | Tool (under `tools/`) | Source (reviewed v7 bytes) |
|---|---|---|
| terminal status | `transition/terminal_status.sh` | v7 transition 00afa179 |
| capture A/B requests, `fill` | `transition/transition.py` (+ `test_transition.py`, frozen `source-fit-bridge.json`, `capture-request-a.json`) | v7 transition 45a48bb5 / 61923472 |
| v7 -> v8 draft step | reused unchanged: `v8-assembly-r3/check_transition_v8.py` ceeafd8c, already run locally (exit 0) | `evidence/check-transition-v8.json` |
| U2 masked seal check | reused unchanged: `v8-assembly-r2/check_u2.py` dc4e8144 (A1 CODEPASS) | arguments in `u2-bindings.json` |
| eval package | `evaluation/*`, rendered from the CODEPASS r2 launcher template | r2 pins 64d0f7a7, render.py f30ac6b5 |
| U3 B8 transport | `final-staging/stage_b8.py` | v7 final staging 784555dc |
| receipt -> spec -> package | `final-staging/final_build.py` (+ `test_final.py`) | 32231a91 / b16adc33 |
| eval status, pre-stage probe | `final-staging/eval_status.sh`, `final-staging/status/pre_stage_probe.sh` | 3b554b4f / 044afc5b (launch-proof) |

`build_post.py` regenerates every file. Each edit is an exact `(kind, old, new, count)` replacement on sha-bound v7
bytes (`edits()`); the diffs are in `diff-*.diff`.

## The deltas

- **root**: v7 assembly root and B8 destination -> `r1-release-assembly-v8-20261022`, `r1-b8-evidence-v8-20261022`.
- **layout**: the tools live in this packet: `OPS = HERE.parents[3]`; `EVAL`, `TRANSITION` point at `../evaluation`,
  `../transition`.
- **bind**: v8 preparation spec caafc95d, draft d0f95301, launcher 87457a2a, source manifest 6a9a325f; the rendered
  eval package pins c250dda7 (`EVAL_PINS` in transition and final_build); v8 pids 469425/469426.
- **chain** (the one non-constant change, flagged by the final inventory note): the bridge's draft chain gets the v8
  draft, and the v7 -> v8 step alone may also change `/release_driver_sha256` and
  `/probability_calibration/approval/{path,sha256}` (`V8_STEP`). Earlier steps keep the old rule. Their exact
  values are checked by `check_transition_v8.py`, not by the bridge.
- **pending**: identities that exist only after a successful preparation, its captures and the reviewer's B8 records
  are explicit `__V8_*__` markers (`MARKERS`, `planned.json` lists them per file). They are filled only by
  `build_post.py --resolve R.json OUT`, which requires every marker, only markers, each a 64-hex value, and changes
  nothing but marker text. Unresolved, `final_build.bound` and `stage_b8.checked_files` refuse.
- **label**: v7 -> v8 in docstrings, messages, kind strings (capture requests, bridge, fill summary, B8 kinds
  `r1_v8_b8_{sources,fits}_assessment_v1`), module and test names.

## Evaluation package

The r2 template rendered with `ASSEMBLY_DIR r1-release-assembly-v8-20261022`, `ASSEMBLY_LABEL v8`,
`WALLTIME_SECONDS 113 * 3600`, `CPU_SECONDS 452 * 3600`. The generator refuses unless those equal budget-r4
(a084cfe1): walltime 406800 s, CPU 1627200 s, supervisor timeout 406800 + 300 = 407100 s. The spec template is the
v7 one with exactly `files`, `launcher_sha256`, `root`, `output`, `resources.walltime_seconds` and
`source_manifest_sha256` rebound; the approval template differs only in `launcher_sha256`; the R1-authorization
template is byte-identical (7f67f584). Every prepared ref stays null.

The rendered `execute.py` keeps the template comment "authored the v6/v7 preparation"; its `AUTHOR_SESSIONS` already
lists 065d2f16, the v8 author, so the check is unchanged (template bytes are CODEPASS; not edited).

## Verification

- `test_post.py`: 19 passed. Includes regeneration, line-by-line diff purity, no v7 identity outside two declared
  history lines, template field sets, the V8_STEP rules, marker set and refusals, and a **resolved rehearsal**: the
  held v7 capture-A/B metadata relocated onto the v8 control paths, run through the v8 `fill`, all markers resolved
  (two SYNTHETIC B8 test documents), then the re-pinned `test_final.py` runs there: 54 passed.
- `tools/transition/test_transition.py` (re-pinned): 22 passed.
- `mutation_controls.py`: unmutated copy passes, then 12/12 generator mutations detected (`evidence/mutations.txt`).
- ruff: all checks passed.

## Not covered (deferred, still pending)

- The 13 post-evaluation tools in the final inventory (requests, census, k2c test, verifier-r2 x3, adapter-r2 x3,
  classd x2, vrun, d2). They need the v8 evaluation spec, R1 authorization and supervisor pid, and their pins cascade
  (verifier pins -> adapter `VERIFIER_PINS_SHA256` -> classd). They run only after a successful evaluation.
- **Inventory gap found:** final-inventory's identity list misses the v7 actuals in `final_build.py` `BOUND`
  (50ee2213, 57294d8c, 2b4c3945, 7d4eb589), the B8 assessment shas (1cbbaf52, ad06ef94) and the approval template
  529c95a7. This candidate re-pins all of them (pending markers); the test's identity list includes them.

## Order after a successful preparation (each step needs its own exact approval)

1. capture A (`transition.py request-a`, capture tool f19d1066) -> capture B (`request-b`) -> `fill`.
2. U2 `check_u2.py` with the captured seal; the draft step is already checked.
3. reviewer B8 assessments -> `build_post.py --resolve` -> review of the resolved diff -> `stage_b8.py`.
4. receipt/review -> `final_build.py spec` -> approval -> `final_build.py package` -> stage/launch once.

A failed preparation stops this chain: `checked_a` refuses any non-zero return code, and nothing here retries.
