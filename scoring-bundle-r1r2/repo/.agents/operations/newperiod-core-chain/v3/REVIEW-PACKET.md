# N-core v3 — code-only independent review

Author: `gpt-6-astra`, `/root/impact_consumer_review`, 20 October 2026.
This package is a prospective local candidate. No remote access, staging, submission, N execution, protected input, model/forecast/outcome read, or R1 operation was performed to create it.

## Exact change

Preserve the reviewed v2 package byte-for-byte. v3 carries:

- A new package-relative operator runner and fresh `core-chain-v3` root; the existing sealed-core and core campaign output destinations stay unchanged and must remain absent before first execution.
- Exact `gpt-6-astra` / `openai/gpt-6-astra` and Claude Opus reviewer identities, per current policy. Require a separate identified reviewer from both the v3 author and inherited v2 author. Reject known author aliases, case/whitespace/trailing-slash disguises, empty identities and ambiguous root aliases.
- Explicit bare `--export=ALL` for chain admission/submission and GPU admission/submission. All three chain hash anchors precede `sbatch` as environment assignments. GPU jobs retain the exact ledger path/hash positional arguments. The CLI export option overrides inherited `SBATCH_EXPORT`; it never constructs a comma-list export.
- A package-local copy of `scripts/forecast_gpu_placement.py`, derived from exact original SHA `1bba8bf940d8ecea6b83be4c4ee2e9cd0c6cec1a6342dde03a374285a1efae33`. Its sole difference is the added `--export=ALL` argument in `fit_command`. The original placement source and frozen fit job are not edited.

All scientific/model/runtime/resource/cell parameters remain identical to v2: marker `f1fae1f7…`, recipe `1071f730…`, training snapshot `dae04f85…`, 40 configuration-3 fits, eight horizon/control profiles, 20+20 waves, RTX8000/240G/4 CPUs/12 h and the first-wave at-most-200-GiB RSS gate. Every completion remains bound to run, prepared ledger and snapshot; all return codes must be integer zero. CPU seal/prepare remains 4 CPUs/32768 MiB/6 h. No fallback, retry, calibration change or additional scientific operation.

## R1 and execution boundary

The builder reads only exact local v2 metadata and produces a `passed:false` execution approval template. It fabricates no completed R1 reference. `review-request.json` records `retrospective_release={status:pending,path:null,sha256:null}` and all execution flags false.

The unchanged dynamic contract requires the eventual independent execution approval to bind actual `retrospective_release={path,sha256}`. `check_approval` rejects missing, malformed or placeholder references. Local stages rehash spec, runner, job, placement, approval and review before any remote call. The same binding persists across submission, ledger cache, placement, memory gate and check. A new approval cannot silently replace the approved binding mid-chain.

The remote job hashes the actual release as part of `frozen_inputs` before running the unchanged seal script. That frozen script verifies the complete release before writing development artifacts; the unchanged campaign and fit guard require the R1 release and exact development operation gates. Code-only approval cannot satisfy this execution contract. Actual final input/release/runtime/fresh-output/admission checks and a distinct final execution approval remain required.

`forecast_gpu_placement.py` retains the generic upstream CLI, including its historical `replace` route. This package authorizes no direct invocation or replacement: the reviewed chain calls only `place` and preserves its one-attempt receipt protocol. The generic evaluation branch would seek a sibling `forecast_campaign.py`, which is deliberately absent here; N fit placement does not take that branch. No new wrapper or scientific source outside this directory is needed.

## Review closure and requested verdict

Run `python -B make_package.py` only to regenerate local package metadata. `review-request.json` binds the runner, complete placement source, job, spec, false approval template, offline builder, tests and this packet; it also records original v2 and original placement hashes.

Review all those exact files, the retained seal/prepare interfaces and the original v2 evidence:

- `docs/paper/forecasting-improvement-20261017/REVIEW-PACKET-NEWPERIOD-CORE-CHAIN-V2.md`
- `docs/paper/forecasting-improvement-20261017/reviews/opus-h1-review-newperiod-core-chain-v2.txt`
- `docs/paper/forecasting-improvement-20261017/REVIEWER-AUTHORIZATION-20261020.md`
- `docs/paper/forecasting-improvement-20261017/REVIEW-PACKET-TEMPORAL-LAUNCH-CONTINUATION-V2.md` for the measured export failure and controls.

The new tests retain v2's binding/memory/receipt coverage and add reviewer-policy/author-refusal, unresolved-release refusal before network, exact original-to-v3 parameter parity, placement tamper refusal and both transport command forms with hostile inherited export metadata. All inputs are synthetic; tests never contact a cluster or open real payloads.

Author validation: **72 v3 tests plus all 45 original v1/v2 tests pass (117 total)** in `focused-tests.txt`. Ruff passes for the runner, builder and tests; `bash -n` passes for the job. The copied placement file preserves its original seven lint diagnostics exactly (including executable-bit/import/style warnings and loop-closure warnings in unchanged code), with zero new diagnostics; `placement-lint-baseline.json` records the comparison. No unrelated formatting/refactoring was introduced into the reviewed placement source.

Please write a code-only review and machine-readable verdict under this directory's `reviews/`, identifying actual reviewer model and distinct worker/session, exact review-request/spec/runner/job/placement hashes, findings and tests. Include `code_review_passed`, with `execution_authorized`, `fits_authorized`, `predictions_authorized`, `scoring_authorized`, `newperiod_unseal_authorized`, `protected2026_authorized`, `r1_open_authorized`, and `retry_authorized` all false. Do not complete the execution approval template or invent a release reference.
