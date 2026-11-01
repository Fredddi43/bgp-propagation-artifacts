# v6 final-builder revision B1, plus the bound control candidate (review packet)

- **Author:** claude-opus-5-5, session `f1d352ff-…`, role label `/root/opus_implementation`.
- **Status:**
  - Source staged once; this is terminal.
  - Controls bound locally once.
  - Builder revision B1 is written and tested. No package is built yet.
  - No control stage, no launch, no approval issued.
- **Pins:** `pins.json` in this directory. The frozen packet `../pins.json` d9444877 is unchanged.

## 1. Done under the approvals

- **Source stage.**
  - Ran once, 10:51:01–10:51:12Z, rc 0, `staged: true`, 375 files.
  - Inputs: approval `374f3b58`, review text `4f247d44`, stager `40cd371e`, candidate `dc17cbdd`.
  - Preflight, read-only: the v6 root was absent and there were 0 unblinding markers.
  - Readback, read-only: every remote sha256 equals the candidate map (375/375), all 0444, owner <USER>, no
    symlinks, no `control-v1`.
  - Records:
    - `../staging/staging-record.json` `c010cb25…`
    - `../staging/remote-readback.json` `d95b5a3e…`
    - the stager's own `../source-candidate-v1/stage-intent.json` and `stage-result.json`
  - **Never repeat this stage.**
  - The frozen packet's `test_candidates_are_byte_reproducible` now fails only because those two stager records sit
    in the candidate directory. Every candidate-listed byte is unchanged, and v5 behaved the same way.
- **Bind controls.** `../bind_controls.py` (37fef5a6) ran once with resource approval `0721ff7b` and review text
  `4f247d44`. It produced:
  - **control candidate** `../control-candidate-v1/candidate.json` `91a18ec13dc1e1e285e79833932c7a40f756cd3aff746426604ededcd0fe3814`
  - **control draft** `../control-candidate-v1/draft.json` `c084ddfc5212a870fcd362ade65a634b0460f9ae09d5864b3b2c96ae72a4e609`
    - Its only difference from base draft 549d1448 is `release_resources.review` = `v6/control-v1/resource-review.json`
      0721ff7b.
  - the rest: contract f77a24c3, runtime 57ead7c5, label 59d54832, calibration approval 22381173, review text
    4f247d44.

## 2. Finding B1: the final builder binds the actual start-record capture

`build_execution.py` here (`1d9a137f`; diff against the frozen builder in `build_execution.diff`) differs from the
frozen packet builder (133fc9c5) in three ways:

1. **The start records come from root's read-only capture.**
   - The capture: `workers/opus-takeover-20261021/r1-v5-terminal/actual-start-records/`
     - capture.json d4f4097a (it must name the v5 root and `read_only: true`, and list exactly these two files)
     - `execution-started.json` 04296a3b
     - `launched.json` b37be8c7
   - Each is read by SHA-256 and carried in the evidence as `start_records` {size, sha256, bytes_base64}, like the
     terminal records. Also added: `start_capture_sha256`.
   - `started` is the parsed JSON of those exact bytes, cross-checked against the v5 startup observation 45b5c199
     (spec, approval, memory_before, supervisor pid).
   - The reconstruction `../evidence/v5-start-records.json` is **no longer an input**, so its stale "never hashed"
     provenance does not enter the package. (A test asserts that.)
2. **A CODEPASS precondition (B4).** `checked_order_fix_codepass()` runs inside `assemble()`. It refuses unless
   `reviews/opus-v5fix-round1-verdict.json` has exactly sha 6e3e4ca8, with `verdict: CODEPASS`, `passed: true`,
   candidate custody a0dba7aa and pins 72349710.
3. **Path anchoring.** `HERE` points at the frozen packet, so the package is still built from
   `../control-candidate-v1`, `../execution/code-pins.json` (09bfd8f1) and the frozen wrapper code, into
   `../execution/package/`.

- **Not changed:** spec keys, scope, resources, wrapper code and `execute.failed_v5`. B2 is not implemented.
  - The unchanged host check compares `evidence["started"]` by parsed equality, and the actual bytes satisfy it.
  - The extra `start_records` key is carried as evidence only.
- **The evidence is otherwise byte-equal.** Compared with the frozen builder's evidence, only the two added keys
  differ: staged (17), terminal, started and failure are equal. The spec differs only in `files`, and there only in
  `failed-v5-evidence.json`.

## 3. Approvals still required (B3, B4); none is issued here

1. **Retention**, scope `r1-committed-retrospective-evaluation-v1`. It must be new and bind:
   - draft **c084ddfc…**
   - driver 4573658e…
   - custody a0dba7aa…
   - `labels_authorized` and `scoring_authorized` false
2. **Preparation**, scope `r1-single-pass-metadata-preparation-v1`. It must be new and bind:
   - draft c084ddfc…
   - that retention approval
   - prepare c42e78ac…
   - driver 4573658e…, custody a0dba7aa…
   - `output_dir = …/r1-release-assembly-v6-20261021/control-v1/prepared`
   - `metadata_preparation_authorized: true`
   - false: labels, scoring and automatic retry
   - `fresh_evaluation_reverification_required: true`
3. **Package build (coordinator, once):**
   `.venv/bin/python -B .agents/operations/r1-release-v6-20261021/builder-b1/build_execution.py --control-candidate-sha256 91a18ec1… --code-pins-sha256 09bfd8f1… --retention … --preparation …`
   - This needs a review of this B1 builder first.
4. **Final execution review**, scope `r1-order-fix-metadata-execution-v5`. It must cite the CODEPASS verdict
   **6e3e4ca8** explicitly (`order_fix_code_review_verdict_sha256`), plus the usual fields listed in
   `../REVIEW.md` §6.
   - The "pending" wording in the frozen source candidate and the frozen REVIEW predates that verdict. It is
     superseded by the bound verdict, never silently ignored.

## 4. Verification

```
.venv/bin/python -B -m pytest -q -p no:cacheprovider .agents/operations/r1-release-v6-20261021/builder-b1/test_builder_b1.py
# 5 passed
```

The five tests:
- the evidence equals the frozen builder's except for the two capture keys, with sizes 307/105 and SHAs equal to the
  capture
- the **unchanged** `execute.failed_v5` accepts a predecessor built from this evidence and the captured bytes, and
  refuses when `prepared/spec.json` exists
- the full chain with the **actual** bound controls (draft c084ddfc) passes `launch.check`, and the spec differs from
  the frozen builder's only in the evidence hash
- the CODEPASS precondition refuses a forged verdict
- the frozen packet's pins hold

Ruff is clean. The frozen packet's own tests: 81/82, failing only on the stager-record reproducibility case above.

The capture program 92def8ff is not run.
