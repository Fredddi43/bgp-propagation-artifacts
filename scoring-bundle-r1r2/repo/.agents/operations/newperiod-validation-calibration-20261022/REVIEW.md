# Review packet: N-core validation decision-rule calibration producer (local candidate)

- Author: Opus 5.5 implementation session `065d2f16` (claude-opus-5-5), role label `/root/opus_implementation`.
- Status: synthetic-only candidate for independent code review, plus a policy addendum for independent policy
  review. Exact bytes: `pins.json`. No commit.
- Contract: N-validation contract review
  (`.agents/workers/opus-takeover-20261021/review/n-validation-contract-review/review.txt` 181b05d7, verdict
  e7385f1f), sections 1-8: G1-G6 and T1-T12.

**Not done and not authorized:**
- no real ledger, fit, label, tensor or remote read
- no calibration of real fits
- no execution approval exists, so the producer refuses every real run
- nothing touches the frozen-2025 publication 66c2ce8c or the live R1 v7 run

## Files

| File | Role |
|---|---|
| `calibrate.py` | the producer (`calibrate`, sanitized `run`, CLI `main`) |
| `POLICY-ADDENDUM.md` | proposed D1 (authority) and C1 (slice anchor) policy; unapproved |
| `test_calibrate.py` | synthetic world with 40 real CPU fits, 45 tests |
| `mutation_controls.py` | 12 guard removals, each must fail its targeted tests |

## What it reuses unchanged

| Step | Reused code |
|---|---|
| ledger, snapshot, marker, recipe, release, manifests, gates | `forecast_newperiod_campaign._checked_ledger` |
| all 40 completions rc 0, receipts, checkpoints, exact gated input IDs | `forecast_newperiod_campaign.check` |
| D1 data-class authority | `forecast_release.authorize(operation="core_fit")` |
| validation tensors only, hashed against the gate member | `forecast_campaign.split_tensor_fields` |
| stored predictions bound to the receipt | `forecast_campaign.validation_ranking` (H3) |
| global threshold reproduced; slice/remainder thresholds | `forecast_campaign.calibrate_decision_rules` (H2) |

`calibrate_ledger_decision_rules` (H5) is not reused, for the reviewer's reasons (a)-(c): there is no top-level
gate in an N ledger, the gate-equality check cannot hold for an N gate, and the gate-manifest shape is the 2025
one. Its order is followed: slice before fits, completed fit, H3, H2, then the `result.update` shape.

## Order of checks (`calibrate`)

1. **`inputs`.** The output is a fresh canonical directory, not overlapping the frozen-2025 publication directory.
   - The approval must be independent and exact: kind, scope, `passed`, reviewer model, and a reviewer session
     that is not an author session.
   - It must bind the producer sha, the source closure, the addendum sha, the ledger sha, the slice sha, the
     output path, `attempt_limit` 1 and `n_validation_label_read_authorized`, with the 8 forbidden flags false.
   - The slice rule must equal `forecast_recipes.SLICE_RULE_SHA256` and must not be the R1 publication hash. It
     must have `fit_outcomes_used` false and both horizons with a variable and an integer cut.
2. **`fits`.**
   - `_checked_ledger`.
   - The ledger is the N-core phase with `fit_count` = recipe `fit_count` = 40 runs, unique run IDs, and both
     horizons.
   - `check()` passes all 40 in ledger order. A failed or missing fit refuses; none is dropped (P9 pending).
   - Every completion names its run and ledger and completed after the slice rule's `created_utc`.
   - Each receipt is read once against its completion's `fit_receipt_sha256`.
3. **`authority`** (per horizon):
   - `authorize(core_fit)` runs on the ledger's own manifest, gate and release. Its result must equal the
     ledger's recorded authorization and every fit receipt's, field for field. The release guard must be the
     snapshot's copy.
   - The manifest is re-validated. It must have no `protected_test`/`locked_test` and only train/validation rows.
   - Exactly one gate member names the manifest. Each fit's `validation_inputs` must equal the member's hashes
     for the validation rows.
4. **`intent`.** The output directory is created, and `intent.json` is written with fsync and mode 0444. It
   names the approval, ledger, slice rule, producer, closure and the validation tensors per horizon. This happens
   before any tensor is opened.
5. **`labels`.** H4 on the validation split of each horizon.
6. **`rules`.** For all 40 fits, in ledger order, still in memory:
   - the predictions are read once
   - H3 runs, then the file is re-hashed (a change during the run refuses)
   - H2 runs with the frozen horizon rule and the receipt threshold
   - the result gets `run_id`, `validation_predictions_sha256`, `slice_rules_sha256` and `source_sha256`
7. **`write`.** Only now:
   - `rules/<run_id>.json` ×40, then `publication.json` (R1 shape plus provenance), then `completed.json`
   - every file exclusive, fsynced and 0444

`run()` turns any failure into `CalibrationFailure('Calibration refused at stage <stage>')`, with no cause or
context. A failure after `intent` leaves the directory with only `intent.json`, so its path cannot be reused.

**Deliberate deviation from contract G4:** rules go to the producer's own fresh output directory, not "beside the
fit". That way the fit directories, whose files are hash-bound by the completions, are never written. Nothing
partial is left among them, and one exclusive `mkdir` makes the whole output fresh. `predict.checked_rules`
reads rules only through the publication's `{path, sha256}`, so the location does not matter to it (T2 shows it
passes).

## Publication shape (consumed by the frozen-inference `checked_rules`)

`passed` true, `test_outcomes_opened` false, `new_threshold_search` false, `calibration_split` `validation`,
`slice_rule_sha256`, `driver_sha256` (= each rule's `source_sha256`), `fit_ledgers` `[{path, sha256}]` of the N
ledger only, and `decision_rules` `[{run_id, path, sha256, validation_predictions_sha256}]` ×40.

Provenance: `kind`, `arm` N-core, `training` updated, `source_closure`, `policy_addendum_sha256`,
`approval_sha256`, `release_authorizations` per horizon, `fits` 40, and
`frozen2025_publication_excluded_sha256`.

## Tests

`test_calibrate.py`: **45 passed**. `ruff check`: pass.

The world is the reviewed driver's own test world: snapshot, core ledger, recipe, marker, release, source and
boundary audits, gates. Its development documents have 1 train and 3 validation events. The issue-time signatures
put one validation event inside the frozen slice (early growth 4 ≥ cut 2) and two outside. `driver.prepare`
writes the 40-run ledger. `driver.run` runs all 40 real CPU fits through `python -m bgbench.forecast_development
fit` under the `core_fit` guard.

**Positive:**
- T1: every rule equals the unchanged H2 recomputed in the test. The global threshold equals the receipt's. Each
  fit has 1 slice and 2 remainder events. The publication binds all 40 in ledger order. Files are 0444.
- T2: each of the 40 rules passes the CODEPASS inference candidate's `checked_rules` (predict.py a2c0285b,
  unchanged) for an updated arm.
- T3: two runs give byte-identical rule files and publications equal up to the output path and approval sha.

**Refusals.** Each asserts the exact internal reason, the public stage on a fresh second attempt, and that no
rules or publication exist:

| Group | Cases |
|---|---|
| approval | 14 cases: author session (full or prefix), other reviewer, not passed, other scope, producer, addendum or closure differs, attempt limit 2, label-read flag false, a forbidden flag true, other output, other ledger |
| inputs | existing output path; output inside the frozen-2025 publication directory |
| T7 slice | another cut; the R1 publication hash as the slice anchor; `fit_outcomes_used`; a missing horizon; created after the fits |
| T9 | cut 0 empties the remainder, so the unchanged H2 refuses; only `intent.json` exists |
| T8/T12 ledger | 39 fits; a duplicated run; a non-N phase; a ledger sha mismatch; the 2025 core ledger |
| fits | a failed fit (rc 1); a rebound receipt; a missing completion |
| D1 | an authorization differing from the fits'; a changed gate (refused by the ledger binding) |
| T4 | protected flag or a test row, via the producer's own split check and via the real validator |
| T5 | a fit's validation inputs differ from the gate (plus its passing control); a validation tensor's bytes differ from the gate (refused at `labels`, after the intent) |
| T6 (H3) | row threshold changed; probabilities changed so the stored decision no longer follows (the run is chosen so it does change); a dropped event; a self-consistent rescoring with another Jaccard |
| T11 | the exact import set; no custodian, custody, freeze, export or access-log reference |

**Not covered by a producer test:** H2's own "recomputed global threshold differs" refusal. A synthetic input
where H3 passes but H2's argmax differs is not constructible without editing the receipt, which the completion
binds. H2 is reused unchanged.

**Mutation controls** (`mutation_controls.py`):

| Mutation | Targeted tests |
|---|---|
| approval binding removed | 9 failed, 5 passed |
| approval independence removed | 5 failed, 9 passed |
| frozen slice anchor removed | 1 failed |
| R1 publication as input allowed | 1 failed |
| R1 output overlap allowed | 1 failed |
| slice-before-fits removed | 1 failed, 2 passed |
| complete 40-fit ledger check removed | 2 failed, 1 passed |
| driver check() skipped | 2 failed |
| release authorization equality removed | 1 failed |
| split check removed | 2 failed, 1 passed |
| receipt validation identity removed | 1 failed |
| H3 binding of stored predictions removed | 3 failed, 1 passed |

Every guard removal makes at least one targeted test fail. The passing tests in a selection are its other cases.

## Limits and residuals

- **Stored predictions are not hash-bound by the fit.** The fit receipt does not hash
  `validation_predictions.json`. The only binding is H3: the stored rows must reproduce the receipt's validation
  Jaccard to 1e-12 and be self-consistent. A rewrite that keeps both would pass. This is the same binding R1
  used, and the producer loads no checkpoint by design. From the publication on, inference hashes the file.
- **One-way order is not re-proven here.** The slice-before-fits check compares the rule's `created_utc` with each
  completion's `completed_utc`, as H5 does. The timestamps are trusted metadata.
- **Imports come from the running checkout.** The approval pins the closure sha256s, and the release guard must
  equal the fits' snapshot copy.

## Remaining prerequisites before any real run

1. Independent policy review of `POLICY-ADDENDUM.md` (D1, C1); root/owner acceptance.
2. Independent CODEPASS of this producer (`pins.json`).
3. The 40 real N-core fits exist and `check()` passes. They need the N development gates and the complete R1
   release; R1 v7 is running and not finished. A decision on the P9 failure policy is needed if any fit fails.
4. A real execution approval binding:
   - the real ledger sha and the slice rule 0291d789
   - the output path
   - this producer and its closure, plus the addendum sha
5. Inference A1 (revision-next c0c17349) reviewed, so the updated publication has its frozen-2025 counterpart
   pinned.
