# R1 v6: order-fix recovery, staging and execution candidate (review packet)

- Author: claude-opus-5-5, session `<SESSION_ID>`, role label `/root/opus_implementation`.
- Status: built and tested locally. Nothing staged or launched, nothing remote touched, no approval exists, and the
  author issues none.
- Exact pins: `pins.json`.
- Planned remote root (not created): `B/r1-release-assembly-v6-20261021`, where
  `B=<FORECAST_ROOT>`.

## 1. What this is

- **The failure.** v5 failed at `verify_batch:1817`.
  - The cause is an order-only disagreement between cells that carry the identical R1 event-ID set: sorted lists
    against H3 reference lists in manifest row order.
  - The author's diagnosis is the packet `r1-preparation-failure-v5-20261021`, pins `72349710`.
  - It agrees with the reviewer's assessment `review/r1-v5-failure-assessment` (verdict
    `DIAGNOSED_ORDER_ONLY_MISMATCH_NO_APPROVAL`).
- **The source.** v6 is the staged v5 overlay (candidate f1b8a21e) with exactly one file replaced: the custody file,
  fb9468b8 → a0dba7aa, the order-fix candidate.
- **Prerequisite still PENDING: an independent code review of a0dba7aa.** It is under separate review. The builder
  binds its pins and records `order_fix_code_review: "pending"` in the source candidate. Nothing here claims a
  code pass.
- **Machinery.** v6 reuses the reviewed v5 machinery unchanged, except for the root, kind and scope names and the
  predecessor (§4). The diffs against v5 are in `diffs/`.

## 2. Reviewer identity convention (unchanged from v5)

- `reviewer_worker` and `author_worker` are coordinator-owned logical role labels, `/root/opus_review` and
  `/root/opus_implementation`. They are not native agents or paths.
- The real identities are the distinct session UUIDs: reviewer `4ba6111c-…`, author `f1d352ff-…`.
- Every independence check rejects the author label and the author session. The checks are unchanged from v5.

## 3. Exact subjects

| Item | sha256 |
|---|---|
| source candidate `source-candidate-v1/candidate.json` (kind `r1_reviewed_source_overlay_v6`, 375 files, 373 source) | `dc17cbddaa207341adc211adb7973206ea950276dbe010a323d9e5d6a4d855e1` |
| source manifest (root `B/r1-release-assembly-v6-20261021/source`) | `97f7af7c116c7e19e8a347751d2fe933fa236c6f47eb47383d085f062a00c11e` |
| base draft, pending bindings | `549d1448025c1b2b2538cd8be6d3781802977c3cd244eb2d4ef5539169daf614` |
| resource candidate | `44fef98f8c80d01518948442ce969ecef70bd04f7394134345f4f3526bf65ed2` |
| resource contract / runtime / label-bound | `f77a24c3…` / `57ead7c5…` / `59d54832…` |
| input identity | `6a0f62d2731fc98ef3b6012479514dc9db4d524f7196cb17fcc561e1c529ba83` |
| custody (candidate; code review pending) | `a0dba7aa087804a0a03f443284f4b06ddfa69312de665e25543bd5f9bd932785` |
| release driver (executed in v4 and v5, unchanged) | `4573658e…` |
| prepare_r1_metadata (unchanged) | `c42e78ac…` |
| review archive `archive/r1-v6-candidates.tar` (380 members) | `3a4cf2aa2e97978bde3ed8ce7f596f8ce27f6e39e2d0bfd96a00dd434820da1b` |
| execution code pins `execution/code-pins.json` | `09bfd8f15e2b072bf81c8520d7e9984ca52e22d69e87dddf3e0d3b820e966056` |
| v5 start records `evidence/v5-start-records.json` | `d41ecf8e1e3481b4461f9358983e1bc430203f213d0af83fead3b78f47ca43b6` |

## 4. Changes from v5

- **Source** (`build_source_resource.py`):
  - The base is the v5 source candidate f1b8a21e, bound by hash. Its manifest must name custody fb9468b8, driver
    4573658e and prepare c42e78ac.
  - The custody file is replaced with a0dba7aa, bound through the order-fix pins 72349710.
  - The builder asserts that exactly one file changed and that the file set is unchanged.
- **Draft.**
  - Only the three scorer paths and `release_resources.contract` move from the v5 root to the v6 root. Their bytes
    are unchanged.
  - Every other key is asserted equal, including families, consumer_sources, analysis, arm_spec, probability
    calibration and decision rules.
  - consumer_sources is unaffected: custody is not one of the consumer modules.
- **Resources.**
  - The contract changes only `input_identity_sha256`, `runtime_admission`, `label_bound` and
    `output_filesystem_root`, and a test asserts exactly this set. Every `*_bytes` limit and the diagnostic caps
    equal v5.
  - The runtime keeps every v5 entry and appends the 373 v6 source paths (2880 → 3253).
  - **No resource limit changes.** The v5 run completed all 26 adapters within the unchanged limits before failing
    on logic, not on resources.
- **Stager and binder:**
  - root v6, kind `…_v6`, staging scope `r1-source-only-staging-v6`
  - the binder names the new source and resource candidates
  - resource scope `r1-release-resources-v1`, which the staged driver requires
  - calibration approval 22381173, unchanged
- **Execution wrapper:**
  - root v6, and scope `r1-order-fix-metadata-execution-v5`
  - the approval flag `horizon_fix_recovery_authorized` becomes `order_fix_recovery_authorized`
  - `failed_v4*` becomes `failed_v5*`, and `failed-v4-evidence.json` becomes `failed-v5-evidence.json` in STATIC
  - everything else is v5 bytes
- **Package builder** (`build_execution.py`): the v5 predecessor evidence (§5), and
  `predecessor_spec_sha256 = f1c3dcff` (the v5 spec).
- **Expected v6 spec differences from v5** (this corrects the v5 package-pins prose, which said only the predecessor
  differs):
  - These keys change: `root`, `output`, `scope`, `files`, `launcher_sha256` (launch.py changed),
    `source_manifest_sha256` and `predecessor_spec_sha256`.
  - These keys do not: `python_executable`, `python_sha256`, `resources` and `pending`.

## 5. Failed-v5 supersession (no success claim, no retry, no reuse as proof)

`execute.failed_v5(spec)` runs inside `package()` before any preparation. It reads the v5 `control-v1` read-only
and requires all of the following:

- **The evidence record:** `failed-v5-evidence.json` has kind `r1_failed_preparation_v5_evidence_v1`, root = the v5
  `control-v1`, `success_claimed: false`, `metadata_published: false`, and
  `spec_sha256 == spec.predecessor_spec_sha256`.
- **The package:** every one of the 17 staged v5 package files still has its exact SHA. They are 15 bound by v5
  `package-pins.json` 07b466b3, plus execution-approval 82c44d28 and execution-review 8e385d2c.
- **The stage record:** `stage-complete.json` equals `{spec_sha256 f1c3dcff, files: those 17}`.
- **The terminal files:** `execution-exit.json` and `launch.err` equal the pinned capture bytes (aa202f17,
  a21e9daf) from the v5 failure packet. `execution-exit.json` must equal
  `{"automatic_retry_authorized": false, "returncode": 1}`.
- **The start records:** `execution-started.json` and `launched.json` equal the parsed documents in
  `evidence/v5-start-records.json`.
  - These two documents were read once, read-only, at 06:31:30Z after the approved v5 launch.
  - Serialised with the writers' exact formats, they reproduce the observed sizes, 307 and 105 bytes.
  - They agree with the v5 startup observation 45b5c199: spec, approval, memory_before and supervisor pid 143098.
  - The original bytes were never hashed. A mismatch makes the v6 launch refuse (fail closed); it never makes the
    launch accept.
- **Nothing published:** `prepared/spec.json` and `prepared/complete.json` are absent. v5 failed at prepare:116,
  before `spec.json` is written (around prepare:149).

Nothing from the failed run is used as proof that any check passed: the v6 run repeats the whole verification.

## 6. Approvals the reviewer must issue later (all new; none of the v5 approvals is reused)

1. **The order-fix code review** of a0dba7aa (pins 72349710). This is a prerequisite and is pending.
2. **Staging**, scope `r1-source-only-staging-v6`:
   - candidate `dc17cbdd…`
   - stager `stage.py` (SHA in the pins)
   - root `B/r1-release-assembly-v6-20261021`
   - the same flags as v5
3. **Resources**, scope `r1-release-resources-v1`:
   - driver `4573658e…`
   - identity `6a0f62d2…`
   - contract `f77a24c3…`, runtime `57ead7c5…`, label `59d54832…`
   - Then the coordinator runs `bind_controls.py`, which fixes the control draft SHA.
4. **Retention**, scope `r1-committed-retrospective-evaluation-v1`. It must be new and bind:
   - the new control draft
   - driver `4573658e…`
   - custody `a0dba7aa…`
5. **Preparation**, scope `r1-single-pass-metadata-preparation-v1`. It must be new and bind:
   - the draft and the retention approval
   - prepare `c42e78ac…`
   - custody `a0dba7aa…`
   - `output_dir = B/r1-release-assembly-v6-20261021/control-v1/prepared`
6. **Execution**, scope `r1-order-fix-metadata-execution-v5`:
   - spec, review text, launcher, and the retention and preparation hashes
   - true: `order_fix_recovery_authorized`, `failed_v5_supersession_authorized`,
     `fresh_full_metadata_verification_required`
   - false: `failed_v5_accepted_as_pass`, `incomplete_preflight_accepted_as_pass`, `old_attempt_retry_authorized`,
     and every forbidden flag
   - `attempt_limit: 1`

The tier-1 seven-file metadata capture proposal (`r1-preparation-failure-v5-20261021/evidence/capture-proposal.json`)
is under separate review and **not executed**. Including the v5 `execution-started.json`, `launched.json` and
`stage-complete.json` in a reviewed capture would turn the §5 reconstruction into hashed evidence. That is optional,
and not planned here.

## 7. Verification

```
.venv/bin/python -B -m pytest -q -p no:cacheprovider \
  .agents/operations/r1-release-v6-20261021/test_build.py .agents/operations/r1-release-v6-20261021/execution/test_execution.py
# 82 passed
.venv/bin/ruff check .agents/operations/r1-release-v6-20261021/*.py .agents/operations/r1-release-v6-20261021/execution/*.py
# All checks passed
```

The tests cover:

- **Byte reproducibility:** both candidate trees, and the archive.
- **The single source change against v5:** driver and prepare are unchanged.
- **The draft:** it changes only v5-root paths plus the resource binding.
- **The resource contract:** exactly 4 keys change, and every limit equals v5.
- **The full synthetic chain:** builder → binder → package builder → `launch.check`, including:
  - evidence with 17 staged files
  - v5 terminal SHAs
  - launched pid 143098
  - retry refused
- **The start records:** they reproduce the observed sizes, and they cross-check against the startup observation.
- **The pending order-fix review:** it is recorded as pending, not claimed.
- **v5 artifacts untouched:** pins 4131ecad and package-pins 07b466b3.
- **`failed_v5` itself:** the wrapper's pass case, plus 14 relabelling and drift mutations.

## 8. Residuals

- Line 1817 with the candidate, and every later `verify_batch` guard, have not run on real data. Only the one fresh
  full v6 preparation proves them.
- Local metadata predicts that line 1846 (cohort rows) passes and that the sensitivity cohort hash is consistent.
  The delay receipts (1824) and the secondary union bindings (1834–1840) are not held locally.
- The downstream evaluation package must be re-targeted to the v6 root once v6 succeeds. That is not done here.
- No source or control stage, no launch, no remote read, commit, push or message.
