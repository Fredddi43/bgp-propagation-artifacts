# R1 v5: corrected full preparation, staging and execution candidate (review packet)

Author: claude-opus-5-5, session `<SESSION_ID>`, role label `/root/opus_implementation`.
Status: built and tested locally. Nothing has been staged or launched, nothing remote was touched, and no approval
exists. The author issues no approvals. Exact pins are in `pins.json` beside this file.

## 1. What this is

v4 failed at `verify_batch:1809` (custody 818497e4). It published nothing and exited with returncode 1, and no retry
was authorized. The diagnosis and fix are packet `r1-preparation-failure-v4-20261021`, pins `c620662f`. An
independent review gave the fix CODEPASS (`reviews/opus-horizon-round1-review.txt` 2fdc08e3, verdict 243637a2).

v5 runs one fresh, full preparation from a fresh root, `B/r1-release-assembly-v5-20261021`, where
`B=<FORECAST_ROOT>`. The source differs from the executed v4
source in exactly one file: the custody file, 818497e4 → fb9468b8. All other source bytes, the scientific draft
content, the scorer bytes and the physical limits are the v4 ones.

v5 reuses the reviewed v4 machinery: `stage.py`, `bind_controls.py`, and `execute.py`/`launch.py`/`run.sh`/`supervise.py`.
There is no new generic launcher. v5 supersedes the failed v4 attempt; it neither retries nor modifies it.

## 2. Reviewer identity convention (root decision on preliminary finding P2)

- `reviewer_worker` and `author_worker` are logical role labels owned by the coordinator. They are **not** native
  agents and **not** filesystem paths:
  - reviewer: `/root/opus_review`
  - author: `/root/opus_implementation`
- The real identities are the persistent Claude Code session UUIDs:
  - reviewer: `reviewer_session = <SESSION_ID>`
  - author: `<SESSION_ID>`
  - both on model `claude-opus-5-5`
- The checks accept either of two reviewers:
  - `reviewer = "gpt-6-astra"`
  - `reviewer = "claude-opus-5-5"` with a `reviewer_session` of at least 8 characters that does not contain the
    author session
- In both cases `reviewer_worker` must be a canonical `/root/...` label. These labels are refused:
  - `root`
  - `reference_reuse_recovery`
  - `opus_implementation` (the author label, new in v5)
  - `impact_consumer_review` (execute.py only)
  - any label containing the author session
- These checks are applied in four places:
  - `stage.independent_reviewer`
  - `bind_controls.assemble`
  - `execute.independent`, which covers the execution, retention and preparation approvals
- The resource candidate records `author_worker = /root/opus_implementation` and `author_session`.
- The staged `prepare_r1_metadata.py` (c42e78ac, unchanged) does not compare the session against the author.
  `execute.package()` does that before prepare runs.

## 3. Exact subjects

| Item | sha256 |
|---|---|
| source candidate `source-candidate-v1/candidate.json` (kind `r1_reviewed_source_overlay_v5`, 375 files, 373 source) | `f1b8a21eed7008ae6f9b6db45fabe52b83d14a72309d4562f79f7f899b1c4748` |
| source manifest (root `B/r1-release-assembly-v5-20261021/source`) | `e7263d38bd8b0c513ef6b3cf58cb1222edd94175bf55529c6ef31a2f3a7795ba` |
| base draft, pending bindings | `6fae9bf1e8d96d56df33b6a4e16ae517e269ecc8d7d37b3b4ac47cf8dbf9988c` |
| resource candidate `resource-candidate-v1/candidate.json` | `8605241a8ddbac3c0ca7e2490f3b9fb8369c5caf2518a34c0f6dc0aad61f13b9` |
| resource contract / runtime / label-bound | `8d3c4889…` / `28b1fe29…` / `20cd0fea…` |
| input identity | `1e8c21b3e892e239088dd0959d898ed5be04ff01b1707d3bc958c6ec163847b5` |
| custody, staged | `fb9468b81b194c8c6768d0f395f84caa725bebe83fe2cba1f835899caf2cd7bf` |
| release driver, staged (= the executed v4 driver, H2) | `4573658e…` |
| prepare_r1_metadata.py, staged (= executed v4) | `c42e78ac…` |
| review archive `archive/r1-v5-candidates.tar` (380 members: both candidates exactly as listed) | `56102cbffcb4b14d62398db0658a53d90d181752d5916dad655dc412d275aeab` |
| execution code pins `execution/code-pins.json` | `78da073978b01932598f7bde059178dac06ee66d0a15aa1055a83b4b623350a5` |

The preliminary review saw resource candidate 193d6e78. The only change since then is the `author_worker` label and
the added `author_session`; runtime, label-bound and contract are byte-identical. `pins.json` covers every other file.
The diffs against v4 are in `diffs/`, one file per source.

## 4. Changes from v4

- **Source**:
  - `build_source_resource.py` copies the v4 overlay (candidate 00d16f3d) verbatim.
  - It replaces only the custody file with the CODEPASS candidate, bound through fix pins c620662f.
  - It asserts that exactly one file changed and that the file set is identical.
  - The custody diff is `diffs/forecast_retrospective_custody.py.diff`: the `adapt_retro_finals` hunk only.
- **Draft**:
  - Only the three scorer paths (scorer, numeric, adapter) and `release_resources.contract` move from the v4 root to
    the v5 root. Their bytes are unchanged.
  - Every other key is asserted equal, including families, consumer_sources, analysis, arm_spec and
    probability_calibration.
  - The input identity is recomputed from the moved scorer paths.
- **Resources**:
  - The contract changes only identity/binding keys and `output_filesystem_root`. The limits are byte-equal to v4.
  - The runtime keeps every v4 entry and appends the 373 v5 source paths (2507 → 2880).
- **Stager** (`diffs/stage.py.diff`):
  - root v5 (in the constant and the remote literal)
  - kind `…_v5`
  - scope `r1-source-only-staging-v5`
  - the reviewer rule from §2
  - The remote still refuses an existing root and stages only the files the candidate lists, mode 0444 with fsync.
- **Binder** (`diffs/bind_controls.py.diff`):
  - the v5 control root
  - the new source and resource candidate SHAs
  - the reviewer rule from §2
  - The resource scope stays `r1-release-resources-v1`, because the staged driver 4573658e requires it.
  - The calibration approval is the same 22381173 bytes as in v4.
- **Execution wrapper** (`diffs/execute.py.diff`, `launch.py.diff`, `run.sh.diff`, `supervise.py.diff`):
  - root v5
  - scope `r1-horizon-fix-metadata-execution-v4`
  - the reviewer rule from §2
  - `prior_attempt`/`original_process_terminated` (v3 predecessor plus diagnostic stop) are replaced by
    `failed_v4()`, see §5
  - STATIC set: the two old evidence files are replaced by `failed-v4-evidence.json` (12 static files)
  - Everything else is v3 bytes: resource and memory guard, audit hook, bounded failure frames, exclusive
    markers, and no retry.
- **Package builder** `build_execution.py`:
  - It assembles the failed-v4 evidence from local SHA-bound bytes only: the 18 executed v4 package files (spec
    8d23df29, approval 49ce5afb), the startup observation 9babcc34 and the bounded terminal capture b0076762.
  - The spec carries `predecessor_spec_sha256 = 8d23df29…`.
  - Resources: 1536 GiB address space and physical budget, 64 GiB host reserve, 64 GiB disk reserve, 4 CPUs, 12 h.

## 5. Failed-v4 supersession semantics (no success claim, no retry)

`execute.failed_v4(spec)` runs inside `package()` before any preparation. It reads the v4 root read-only and requires
all of the following:

- The evidence has kind `r1_failed_preparation_v4_evidence_v1`, root = v4 `control-v1`, `success_claimed: false`,
  `metadata_published: false`, and `spec_sha256 == spec.predecessor_spec_sha256`.
- Each of the 18 staged v4 files still has its exact SHA.
- `stage-complete.json` equals `{"spec_sha256", "files": staged}`.
- The terminal set is exactly `execution-exit.json` + `launch.err`, and their bytes equal the captured bytes.
- `execution-exit.json` equals `{"automatic_retry_authorized": false, "returncode": 1}`.
- `execution-started.json` and `launched.json` equal the recorded start.
- `prepared/spec.json` and `prepared/complete.json` are both absent.

The v4 attempt therefore stays terminal and failed. It is superseded, never accepted as a pass, and never retried.
The execution approval must say `failed_v4_accepted_as_pass: false` and `old_attempt_retry_authorized: false`.

## 6. Read scope (physical)

- **Staging:** writes only the new v5 root. It refuses an existing root, symlinks, traversal, more than 400 files or
  more than 16 MiB, and the unblinding markers, which it checks before and after.
- **Launch:**
  - the v5 control root (STATIC + DYNAMIC files)
  - the read-only v4 terminal and package metadata listed in §5
  - the access registry check
- **Preparation:** the same reviewed verification reads as v4. Those are the draft's SHA-bound family ledgers,
  commitments and predictions under the unchanged label-bound and runtime admission, plus the audit hook that allows
  writes only to `control-v1/prepared` and the one derived seal. It does not decode labels, scores, tensors or
  checkpoints.
- **Local precheck (§8):** zero remote reads and zero protected reads.

## 7. Approvals the reviewer issues (root routes them; the order is strict)

1. **Staging**, scope `r1-source-only-staging-v5`:
   - `candidate_sha256 = f1b8a21e…`
   - `review_text_sha256`
   - `stager_sha256` = sha of `stage.py` (see pins)
   - `root = B/r1-release-assembly-v5-20261021`
   - `staging_authorized: true`
   - false: `consumer_execution_authorized`, `labels_authorized`, `scoring_authorized`, `freeze_authorized`,
     `seal_authorized`, `automatic_retry_authorized`
   - `passed: true`
   - reviewer fields per §2
2. **Resources**, scope `r1-release-resources-v1` (may be issued in parallel with 1):
   - `release_driver_sha256 = 4573658e…`
   - `input_identity_sha256 = 1e8c21b3…`
   - `resource_contract_sha256 = 8d3c4889…`
   - `runtime_admission_sha256 = 28b1fe29…`
   - `label_bound_sha256 = 20cd0fea…`
   - `review_text_sha256`
   - `resource_admission_authorized: true`
   - false: `labels_authorized`, `scoring_authorized`, `execution_authorized`
   - Then the coordinator runs `bind_controls.py` → `control-candidate-v1`, which fixes the `draft.json` SHA.
3. **Retention**, scope `r1-committed-retrospective-evaluation-v1`:
   - newly issued (H1)
   - `draft_sha256` = control `draft.json`
   - `release_driver_sha256 = 4573658e…`
   - `custody_source_sha256 = fb9468b8…`
   - `labels_authorized: false`, `scoring_authorized: false`
   - The old 818497e4 approvals cannot pass `execute.package()` or custody `:1876`.
4. **Preparation**, scope `r1-single-pass-metadata-preparation-v1`:
   - newly issued (H1)
   - draft SHA
   - `retention_review_sha256`
   - `preparation_source_sha256 = c42e78ac…`
   - driver
   - custody fb9468b8
   - `output_dir = B/r1-release-assembly-v5-20261021/control-v1/prepared`
   - `metadata_preparation_authorized: true`
   - false: `labels_authorized`, `scoring_authorized`, `automatic_retry_authorized`
   - `fresh_evaluation_reverification_required: true`
   - Then: `build_execution.py --control-candidate-sha256 … --code-pins-sha256 78da0739… --retention … --preparation …`
     writes `execution/package/` and the spec SHA.
5. **Execution**, scope `r1-horizon-fix-metadata-execution-v4`:
   - `spec_sha256`, `review_text_sha256`, `launcher_sha256`
   - `retention_review_sha256`, `preparation_review_sha256`
   - true: `transport_authorized`, `metadata_execution_authorized`, `horizon_fix_recovery_authorized`,
     `failed_v4_supersession_authorized`, `fresh_full_metadata_verification_required`
   - false: `failed_v4_accepted_as_pass`, `incomplete_preflight_accepted_as_pass`, `old_attempt_retry_authorized`
   - `attempt_limit: 1`
   - false, every one: `labels_authorized`, `scoring_authorized`, `prediction_decoding_authorized`,
     `fits_authorized`, `prediction_authorized`, `r1_authorized`, `newperiod_authorized`,
     `protected2026_authorized`, `automatic_retry_authorized`

Sequencing: step 3 needs the binder, step 4 needs step 3, and step 5 needs the package.
`test_build.py::test_full_synthetic_chain_reaches_the_exact_transport_check` runs this chain end to end with
synthetic approvals and finishes at `launch.check`. With `old_attempt_retry_authorized: true` the chain is refused.

## 8. Post-1809 local metadata precheck

`precheck_post1809.py` → `precheck-report.json`. The run is reproducible, makes no remote or protected reads, and
writes no bytecode. Result: **16 pass, 0 fail, 8 unchecked**.

- **Pass:**
  - consumer_sources equal the v5 overlay
  - the secondary authorization's review, scope, window, and union set equal the four family unions
  - secondary primary_cells are distinct transfer cells
  - the sensitivity integration gate is the core ledger's R-core gate
  - the probability-calibration approval (scope, reviewer, decision, driver 4573658e, scoring source)
  - the recipe receipt header (review, module source, kind, frozen_before_r1, the required set)
  - the scientific protocol is held
  - the H3 reference grid (20 = 30/60 × seeds 0–4 × sage/none, from the fit-ledger roles) with manifest, gate and
    model SHAs equal
  - decision-rule keys cover all 122 learned ledger cells exactly
  - the scorer numeric, adapter and coverage convention, and the scorer script, are in the overlay
  - the arm spec is held
  - the analysis constants are typed
  - the retention custody requirement (fb9468b8)
- **Unchecked:** these are left to the fresh full pass, and no capture is requested (independent review §5):
  - the delay cohort receipts
  - secondary primary reuse (union documents)
  - the history-sensitivity bundle and reporting guard
  - recipe files and `receipt_issues`
  - the exposure-ledger bytes
  - decision-rule contents, slice provenance and the calibration publication
  - the H1 calibration commitment chain
  - the slice-rule horizons
  - Population and event-ID agreement and cohort-row agreement need protected event IDs, so they are run-time only.
- The independent reviewer's bounded assessment found no contradictions in the checks that can be made locally.

## 9. Verification

```
.venv/bin/python -B -m pytest -q -p no:cacheprovider \
  .agents/operations/r1-release-v5-20261021/test_build.py .agents/operations/r1-release-v5-20261021/execution/test_execution.py
# 79 passed
.venv/bin/ruff check .agents/operations/r1-release-v5-20261021/*.py .agents/operations/r1-release-v5-20261021/execution/*.py
# All checks passed  (the verbatim v4 source copy under source-candidate-v1 is intentionally not linted or changed)
# test_candidates_are_byte_reproducible: build() reproduces both candidate trees byte-for-byte
```

`find .agents/operations/r1-release-v5-20261021 -name '*.pyc'` finds nothing. This fixes preliminary P1, a stray .pyc
left by an earlier precheck run.

## 10. Residuals and deliberate non-actions

- **Local `src/bgbench/forecast_retrospective_custody.py` is not patched, and stays 818497e4.** The frozen
  horizon packet's `test_regression.py:161` asserts that the imported `src` custody is 818497e4, and its pins bind
  it. Patching it now would invalidate CODEPASS evidence that is under use. The staged v5 source carries fb9468b8
  regardless. If root wants it, patch `src` after the v5 freeze, as a separate change that keeps 818497e4 in git.
- H3 (optional zero-shot bin 1/15 and failed-cell role tests) was not added: the horizon packet is frozen.
- H2: DIAGNOSIS's `scripts/forecast_retrospective_release.py:243` citation is the local driver 6aeab809. The
  same statement is line 281 of the executed driver 4573658e, which v5 stages unchanged.
- Line 1809 and the guards after it have never been exercised on real data. Only the one fresh full preparation
  proves them. If it fails, that attempt also ends terminally, with no automatic retry.
- No stage, launch, network mutation, commit, push or message. The author issues no approval.
