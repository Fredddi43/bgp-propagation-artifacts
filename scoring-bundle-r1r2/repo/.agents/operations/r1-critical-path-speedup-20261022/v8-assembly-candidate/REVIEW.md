# Review packet: LOCAL v8 assembly candidate (planned root r1-release-assembly-v8-20261022)

- Author: claude-opus-5-5, session <SESSION_ID>.
- Built by `build_v8.py`, which mirrors the reviewed v6-to-v7 builder (`r1-release-v7-20261022/build_source_resource.py`).
- **Nothing staged, frozen as a scientific artifact, approved or run.** No remote path was checked or created.
- **No reviewer record is written here.**

## What it builds (`source-candidate/` candidate a272aab3, `resource-candidate/` candidate f32f7d19)

| Item | sha256 | Exact difference from v7 |
|---|---|---|
| Source tree (373 files) | — | Only `scripts/forecast_retrospective_release.py` changes: 4573658e to **bb7f7e00** (D-1 pins 0598f935, CODEPASS 3c4ed35c). Every other file is the v7 tree byte for byte (tested). `prepare_r1_metadata.py` c42e78ac and custody 409e1171 are unchanged. |
| `source-manifest.json` | b60c4f93 | Leaf diff vs 7f35bd22 = `/root` and `/files/<driver>`. **The root must change** because the tree is restaged under the v8 root. |
| `base-draft-pending-bindings.json` | 10665b66 | Leaf diff vs v7 draft 44acc870 = 11 leaves (next table). Every other key is identical. |
| `runtime.json` | c2663564 | v7 9fae8d2e plus the 373 v8 source paths appended (history kept); `input_identity_sha256`; `release_driver_sha256` |
| `label-bound.json` | d7b9dede | Only `input_identity_sha256` and `runtime_admission_sha256`. Every certified bound value is unchanged. |
| `resource-contract.json` | d7508847 | Only `input_identity_sha256`, `release_driver_sha256`, `output_filesystem_root`, and the `runtime_admission` / `label_bound` refs. **Every number is unchanged** (tested). |

Draft leaves that change, and why:

| Leaf | Value |
|---|---|
| `/release_driver_sha256` | bb7f7e00 |
| `/scorer/{adapter,numeric,scorer}/path` | relocated v7 to v8 root; their shas are unchanged and equal the staged v8 bytes (`scorer.scorer` is `forecast_score.py`, not the release driver) |
| `/release_resources/contract/{path,sha256}` | the v8 contract above |
| `/release_resources/review` (was `/path`, `/sha256`) | **null**: the resource review is reviewer-issued |
| `/probability_calibration/approval/{path,sha256}` | v8 control path; **sha null**: the calibration approval binds the driver sha and must be re-issued by the reviewer (the v7 one, 22381173, lives in the v3 control dir and binds 4573658e) |

## Two corrections to the reuse assumptions in assessment 4e8ca557

1. **U1.** The draft diff is not only `release_driver_sha256` plus the resource refs.
   - It also includes the three scorer paths, which point into the staged source tree.
   - It also includes `probability_calibration.approval`.
   - All are binding fields; no scientific leaf changes.
2. **U4.** label-bound 662066aa **cannot be reused byte-identically:**
   - (a) It binds `runtime_admission_sha256`, and the runtime record must change for the v8 driver path and sha.
   - (b) `resource_identity` hashes the `scorer` block including paths, so relocation changes it: d03ee0b2 becomes
     **397e6e28**.
   - A test proves the identity change is due solely to the path relocation: moving the paths back reproduces
     d03ee0b2.
   - The certified label/target values are unchanged. The v6-to-v7 builder handled it the same way.

## Records only the independent reviewer issues (all null or absent here)

| Record | Binds |
|---|---|
| Resource review | `resource-contract.json` sha |
| Calibration approval re-issue | driver bb7f7e00 and scoring source 740bf610; the decision bytes are unchanged |
| Retention review | the final draft sha after binding, custody 409e1171 |
| Preparation review | prepare c42e78ac, the new driver sha |

The bind step that writes the two reviewer shas into the draft is the v7 `bind_controls.py`, re-pinned constants-only
(it is in the inventory below). It is not run here.

## Single-pass preparation (no redundant verification)

- Preparation stays `prepare_r1_metadata.py` c42e78ac: **one** `verify_batch` writes spec, seal and ledger. About
  3.9 h was measured for v7.
- Then the evaluation does its one mandatory fresh re-verify.
- The separate freeze/seal/plan commands (3 passes) are not used.
- The preparation launcher (`r1-release-v7-20261022/execution/*`) changes only its root (inventory). Its 12 h
  limits cover the measured 3.9 h.

## U2 / U3 (after preparation; mechanical, refusal on any difference)

- `check_u2.py <new-seal> <sha> <new-spec-sha>` requires:
  - sealed_view (`cells`, `arms`, `r1_event_ids_sha256`, `prerequisites`, `resource_accounting`) equal field for field
    to v7 seal 6412d726 (held capture);
  - the fixed flags;
  - a new spec sha different from 17f81575;
  - 1066 committed / 90 failed.
- U3, re-binding of the B8 sources/fits assessments to the new spec/seal, is the reviewer's mechanical re-binding
  once U1 and U2 hold. No tool is proposed.

## Constants-only re-pin inventory (`repin_inventory.py` gives `repin-inventory.json`; edits nothing)

**Coverage:** 34 entries in 15 files.

| Group | Files |
|---|---|
| post-eval capture | requests, census, k2c |
| verifier-r2 | |
| adapter-r2 | |
| classd / vrun / d2-r2 | |
| pre-eval chain | stage, bind_controls, build_execution, the preparation launcher |

**Values:**
- **Known now:** the v8 root paths, the v8 driver, manifest b60c4f93, and the runtime, label and contract shas.
- **Explicit placeholders**, filled only by the step that creates them:
  - `__V8_SPEC_SHA256_AFTER_PREPARATION__`, `__V8_SEAL_…`, `__V8_LEDGER_…`;
  - `__V8_EXECUTION_SPEC_SHA256_AFTER_BUILD__`;
  - `__V8_R1_AUTHORIZATION_SHA256_AFTER_REVIEW__`;
  - `__V8_CALIBRATION_APPROVAL_SHA256_REVIEWER__`.
- 2 `text` entries are prose mentions (a verify_r1 docstring and an adapter-r2 error message) to update alongside.

**12 notes:**
- The v7 preparation/execution tools bind the **failed v6** evidence (`FAILED_V6`).
- Whether a v8 chain must also bind the v7 terminal record is a reviewer decision. No value is proposed.

## Tests (`test_v8.py`: 21 passed) and controls (`mutation_controls.py`: 7/7)

**Tests:**
- deterministic rebuild equals the written bytes;
- the source tree is v7 plus exactly the D-1 driver;
- the draft diff is exactly the 11 leaves, reviewer fields null, scorer shas unchanged;
- the identity change is due only to relocation;
- runtime, label and contract change only bindings, never values;
- builder refusals (5): D-1 pins, v7 draft, an extra draft change, wrong driver base, wrong prepare;
- U2 accepts an equal view and refuses 8 kinds of difference plus a wrong anchor or the old spec;
- the inventory regenerates identically and only reads.

**Controls**, all detected: bound digest, v7 base, draft leaf guard, U2 view, U2 new-spec, U2 flags, U2 anchor.

## Not here

- **No D-1 alias end-to-end fixture (F3).** The synthetic world cannot produce aliases without a custody fixture
  change; that stays an open item for the launch review.
- **O1** (decode-only post-label) remains a proposal.
- **No remote existence check.** A future stager must create the v8 root exclusively and refuse if it exists.
