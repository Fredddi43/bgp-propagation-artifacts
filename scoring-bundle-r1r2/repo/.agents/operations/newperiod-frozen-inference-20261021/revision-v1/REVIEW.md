# N frozen-inference commitment adapter (N-core updated + N-frozen2025): code-only review

**Author:** Opus 5.5 implementation session `f1d352ff`.
**Design:** `.agents/workers/opus-takeover-20261021/implementation/DESIGN-v2.md`. It applies the conditional design
verdict `review/proposal-review/verdict.json` (P1-P9) and the root scope decisions of 2026-10-21. The initial
`PROPOSAL.md` is preserved.

**This is a synthetic candidate.** No real data, remote action, GPU, fit, calibration, freeze, seal, label read or
scoring was involved. Code review grants no protected read, prediction, calibration, freeze or execution authority.

**No existing reviewed source was edited.** That includes `forecast_train`, `forecast_inputs`, `forecast_custody`,
`forecast_custodian_eval`, `custodian_newperiod_inputs`, `custodian_access_log` and the preparation `prepare.py`.

## What it does

`predict.run(freeze_path, expected_freeze_sha256, arm_id, *, access_log, device='cpu')` commits ONE learned arm of an
externally anchored complete retention freeze. The freeze is written by the unchanged `forecast_custody.freeze`. The
internal steps are in `_run`. `run` is the sanitized boundary: any failure becomes
`FrozenInferenceFailure('Frozen inference refused at stage <stage>')`, where the stage is a code constant. The
exception carries no context, cause or protected value, as in the reader candidate.

### P3: complete batch (`checked_batch`)

- The freeze receipt is read once and must match the external anchor.
- It must have the freeze shape with `all_retained_outputs_absent_at_freeze`.
- Every arm needs a role, and `derive_new_period_arms(receipt)` must succeed. So every evaluator arm must exist at
  both horizons, with at least two paired seeds. A partial or one-arm freeze is refused.
- The protocol and exposure-ledger SHAs are rechecked.
- The arm must be a learned N-core/frozen2025 arm (`role_arm` ∈ `LEARNED_ARMS`).
- Its frozen output files must be absent, and their parent directories must already exist.
- The custody anchors (`custody_inputs`) come only from the freeze-bound arm.
- Only the arm's own `input_gate_path`/`sha256` is used.

### P1: batch-level slice mode (`checked_slice_batch`)

- Every learned arm must carry the identical `slice_decisions`:
  `{mode: two_threshold_v1, slice_rules, issue_time_tables{30,60}, publications{updated, frozen_2025}}`.
- Every learned arm must also carry its own `decision_rules` ref.
- The slice rules SHA must equal `forecast_recipes.SLICE_RULE_SHA256`.
- There is no unavailable/omitted mode.

### P6: provenance (`provenance_updated`, `provenance_frozen`)

**updated:**
- The N-core ledger is SHA-bound and in phase `newperiod-core-development`.
- Exactly one entry matches the typed message_passing/history/seed/horizon.
- Completion record: rc 0, its run_id, its ledger SHA and the model SHA all match.
- `fit_receipt.json` is bound by the completion's SHA. It must be validation-only with `test_inputs_opened` false and
  the typed identity. Its manifest, `core_fit` gate and release must equal the ledger's.
- It must equal the checkpoint's embedded receipt plus `checkpoint_sha256`.

**frozen2025:**
- The plan SHA must be `FROZEN2025_PLAN_SHA256`, with sage/on/configuration 3.
- Exactly one (seed, horizon) entry with this checkpoint.
- Its completion and fit_receipt are each bound by the plan's SHA.
- The same receipt identity and equality checks apply. The fit ledger is the plan's `ledgers[entry.ledger]`.

### P2: decision rules (`checked_rules`)

The R1 `checked_decision_rules` rules are applied to both periods.

**Publication** (by `role.training`):
- `passed`, with no test outcomes and no new threshold search.
- Same slice SHA, unique run_ids, and it lists this fit ledger.
- Exactly one entry for this run_id, whose path and SHA equal the arm's `decision_rules` ref.

**Rules file:**
- Validation-only, with finite thresholds in [0, 1.01].
- `run_id` equals the fit's.
- `validation_predictions_sha256` equals the published value, and also the SHA of `<fit dir>/validation_predictions.json`.
  Those bytes are hashed, never decoded.
- `source_sha256` equals the publication's `driver_sha256`.

**Slice file:**
- The frozen slice `{variable, cut}` at this horizon.
- `fit_outcomes_used` false.
- `created_utc` earlier than the completion's `completed_utc`.

**Threshold:** `checkpoint.threshold == receipt.threshold == global_threshold`.

**Decision:** `slice_decision` is `forecast_retrospective_scoring.py:106-112` unchanged, applied to the bound table's
variables. Available rows only. The table's `seeds_at_issue` must equal the input seed count.

### P7: contract (`checked_contract`)

Each of these must hold:
- equal history indices
- equal feature contract
- equal library protocol
- `in_dim == width == len(mu) == len(sd)`
- `n_edge_types <= n_types`
- `delta_s` equals the role horizon

The training identity is already checked in `checked_checkpoint`. There is no mapping and no fallback.

### P5: durable log (`configured_log`, `durable_log`)

**Before the first log record**, every check that opens no custody export runs: freeze, slice, checkpoint, provenance
and rules. The manifest and gate hashes are deliberately NOT read in `checked_batch`.

**Log setup:** `custodian_access_log.LOG` must equal the canonical `access_log` argument. This is the logger
`custody_load` uses. An existing log must be a regular file with nlink 1.

**First durable record:** one `log_read` record each for:
- the manifest (files = events + 1)
- the source inventory
- the issue-time table

Then fsync the log and its directory.

**After that record:**
- the bound manifest read
- the P7 checks
- the unchanged `custody_load`, which logs again, then calls `load_inputs`
- the table checks

**Second durable record:** written before `verify_arm` re-reads.

### P8: normalisation (`normalized`, `infer`)

This follows `load_partition`'s prediction path:
1. project to `INPUT_KEYS`
2. clone the six tensors
3. `edge_index`/`edge_type` `.long()`, `x` `.float()`
4. checkpoint `transform_events`
5. `MatchedSAGE(**settings)` with `prediction_rows(..., checkpoint threshold)`

Abstention rows from `load_inputs` are appended unchanged.

### P4: exact paths, validation before output (`validated_rows`, `write_exclusive`)

1. All `verify_arm` row checks run in memory: the schema, which the `ALLOWED_ROW_KEYS` literal pins to `verify_arm`'s set
   via an AST test; finite numerics; and the exact frozen population with no duplicates.
2. Predictions and commitment are serialized with `allow_nan=False`.
3. Exclusive `xb` writes go to exactly `arm.predictions_path`, then `arm.commitment_path`.
4. Then `verify_arm`.

## P9: inference failure is terminal, and the documents disagree

**What the code does:**
- A failure before the writes leaves no output.
- A failure between the writes leaves predictions with no commitment.
- In either case the arm cannot be sealed. Once any frozen output exists, any rerun is refused at `freeze`. There is no
  retry and no cleanup.
- The adapter never converts a failure into an abstention row.

**Attempt accounting.** Started/completion markers and a one-attempt rule, as in the existing drivers, belong to the
not-yet-built execution package. A failure before any write leaves the paths absent. In this library only the package
prevents an unreviewed rerun.

**Tension for the coordinator:**
- `EVALUATION-PATH.md:95` says inference failures score as `technical_failure`.
- NEW-PERIOD-PROTOCOL says to resolve them or record them under a predeclared rule.
- But the evaluator takes abstention status only from the manifest's `input_status`, and `seal` needs every retained arm.
- So an actual inference failure currently blocks the whole batch. A predeclared rule needs its own reviewed decision.
  This code does not choose one.

## Tests

`test_predict.py` has 22 test functions, giving 45 test cases. Everything is built synthetically in temporary
directories. Real tiny `forecast_train.fit` CPU fits produce the checkpoint and receipt formats: 2 seeds × 4 controls ×
2 horizons updated, and 2 × 2 frozen per library variant. The custody export goes through the unchanged
`forecast_inputs.export_inputs`. The issue-time tables come from the unchanged `prepare.issue_time_table`. The freeze
comes from the unchanged `forecast_custody.freeze`, and covers 20 learned arms and 6 stand-in baseline arms.

What they cover:
- **End to end:** all 20 learned arms committed, then `seal`, then `authorize_outcome_join`, then
  `prepare.arm_spec`, then the unchanged `evaluate_new_period` with a synthetic label table and the slice family
  available. Committed slice decisions are checked against the scorer formula.
- **P3:** partial and one-arm freezes refused, plus anchor, protocol, baseline arm, existing output and missing
  output-directory refusals.
- **P1:** unavailable mode, one differing arm and missing rules.
- **P6:** checkpoint identity; updated rc, completion checkpoint, fit receipt and release; frozen plan anchor,
  completion and receipt bytes; embedded receipt equality.
- **P2:** another seed's rules, global threshold, source, slice rule, test outcomes, validation-predictions hash, and a
  slice rule frozen after the fit. Every pre-freeze edit is republished consistently, so only the targeted check can
  refuse.
- **P7:** a frozen2025 library-protocol mismatch refuses while updated arms still commit; plus unit checks for
  feature, index, edge-type and horizon mismatches.
- **P5:** instrumented `read_bytes`/`read_text`/`open`/`fsync`/`log_read` show durable records precede the first
  custody-export read and the `verify_arm` re-read. Also covered: an unconfigured log, a changed gate (refused after
  the log), and a table bound to another manifest.
- **P8:** per-event equality with `load_partition` + `prediction_rows`, for sage/none × history on/off, with int32
  edges and a float persistence mask.
- **P4/P9:** a NaN refuses before any output; an inference exception is sanitized and leaves no output; a partial write
  is terminal and the rerun is refused.

Every refusal test first asserts the unsanitized internal reason, then the public stage. The two exceptions are the rerun checks, which assert only stage `freeze`.

Commands:
```
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider \
  .agents/operations/newperiod-frozen-inference-20261021/test_predict.py -W ignore::FutureWarning   # 45 passed
.venv/bin/ruff check .agents/operations/newperiod-frozen-inference-20261021/                        # All checks passed
```

Unchanged related suites also pass (260 tests): `test_forecast_custody`, `test_forecast_custodian_eval`,
`test_forecast_manifest_contract`, `test_forecast_train`, `test_custodian_newperiod_inputs`, and the preparation
`test_prepare`.

## Synthetic-only substitutions in the tests

`SLICE_RULE_SHA256` and `FROZEN2025_PLAN_SHA256` are monkeypatched to the synthetic files' hashes. The
deterministic baseline commitments, the decision-rule publications, the issue-time projections (including the
abstention variables) and the prediction-input gate are test fixtures. They are not producers.

## Remaining actual dependencies (absent here)

1. Prediction-input gate producer.
2. Issue-time projection producer. It must cover every row, abstentions included, with no imputation.
3. N-core N-validation decision-rule calibration and its publication.
4. The real R1 calibration publication for the frozen2025 rules, and its external anchoring.
5. The retention/freeze plan. It must carry the `slice_decisions`, `custody_inputs`, `provenance` and `decision_rules`
   fields and create the output directories. It must also decide on N-core numerical-failure cells.
6. Real frozen2025 contract equality with the N export.
7. An execution package with attempt accounting, runtime/resource binding and independent authorization.
8. The reviewed P9 failure-rule decision.
9. The deterministic N-base driver, plus prediction adapters for GBDT, temporal and counts.

Completion records for updated fits have no external hash, the same as `forecast_newperiod_campaign.check()`. They
are bound only by their content to the ledger SHA, the model SHA and the fit-receipt SHA.
