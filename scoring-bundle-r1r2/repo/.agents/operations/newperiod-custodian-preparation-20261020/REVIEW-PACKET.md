# N custodian preparation — code-only synthetic review

This is a small library of pure preparation functions plus an exclusive JSON writer. It is not an operational custody runner. No actual N inputs, membership, targets, predictions, tensors, or outcomes were opened. No cluster access, staging, jobs, seal, release, or scientific execution took place. Author approval is false.

## Existing primitives reused

- `forecast_custodian_eval.role_arm`, `derive_new_period_arms`, `check_arm_spec`, and `evaluation_window`: unchanged arm identities, seed pairing, both horizons, twelve primary contrasts, and binding extension window.
- `forecast_manifest.validate_custodian_manifest`, `validate_prediction_manifest`, and `utc`: complete declared populations, input purpose, clocks and status contracts.
- `custodian_multipart_acceptance_2026.sets_from_membership`: unchanged canonical membership-to-target sets. The 7200-second target is inclusive and uses raw `first_seen`. Filtering to the fixed reference collectors precedes set formation. This matches `tgn_data.observed_membership` / `build_event`; duplicate members collapse naturally, and no new lower-bound rule is added.
- `replay_multipart.event_coverage`: existing `target_window_complete`, `boundary_censored`, and gap semantics. Those coverage fields are consumed, not reconstructed from prediction success, graph availability, or target values.
- `forecast_history.issue_time_slice_variables` and `in_issue_time_slice`: unchanged input-only slice variables and frozen cut application.
- `forecast_custody.write_once`: exclusive output; partial or existing files cannot be overwritten.

The exact imported source and semantic reference hashes are in `source-bindings.json`. This code-only package uses local repository imports; a future execution package must freeze those dependencies and supply a separately reviewed runtime closure. It does not self-approve that future closure.

## Implemented functions

`checked_bytes` / `document` accept already-read bytes and an externally retained `{path, sha256}` binding. They verify bytes in memory and never open the provenance path. No input reader or production CLI exists.

`target_status` produces a write-ready source-status record from explicit onset, fixed reference panel, and bound source summary/coverage. Complete sources require canonical membership bytes. Coverage gaps or a censored boundary remain censored. Missing source evidence without a bound existing censor declaration refuses; a declared missing/censored status is preserved verbatim. Input availability and technical failures do not determine target censoring.

`label_table` consumes both complete master manifests, the binding extension decision and exact per-event source/status bindings. It verifies shared horizon populations, incidents, onsets, explicit panel, master-bound membership/summary, complete coverage for every reference collector, valid timezone-aware membership, and inclusive onset+7200-second target. It emits exactly the existing `custodian_label_table` schema with provenance. Censored rows have a status/reason and **no target array**; missing evidence is never converted to an observed empty footprint. A genuinely empty membership with complete declared source coverage remains a scorable empty target.

`attach_roles` attaches a separately reviewed, hash-bound explicit role plan to the exact complete retained arm set. It preserves every existing arm field and all non-primary families; existing roles cannot be changed. Roles never come from filename heuristics. The real existing derivation validates required primary/secondary arms, deterministic uniqueness and paired learned seeds. This function does not establish that a declared role matches an actual checkpoint: the future reviewed role plan and existing custodian checkpoint checks retain that responsibility.

`issue_time_table` consumes every reference event's explicit input-only projection, bound to its exported input hash. Only event identity, input-only flag, input hash, history signature and seed ASNs are allowed. It calls the existing variable/cut helpers and rejects labels, nonfinite/nonmonotone signatures, wrong inputs, absent events, and imputation. It does not deserialize production input tensors or claim that a supplied projection was independently checked against a tensor; that projection must be produced inside the future authorized custodian read layer.

`arm_spec` derives all arms mechanically from the supplied final retention document, binds that exact document, both optional issue-time tables, frozen slice rules and the extension decision, and retains the existing evaluator defaults of 10000 repetitions, alpha 0.05 and bootstrap seed 1701. Slice rules/tables are supplied together or omitted together. Bound table horizon, source rule and every derived arm's population must agree. Omission leaves slice analysis unavailable through the existing evaluator contract; no replacement slice is selected. The artifact is not a custody freeze or seal.

`write_candidate` serializes a caller-provided document exclusively after checking JSON finiteness. It grants no approval. Tests write only synthetic temporary files.

## Exact remaining production prerequisites

1. A complete reviewed N retained-arm inventory, explicit role plan and actual immutable models/configurations, manifests, gates, predictions, commitments and failure/abstention accounting. The role builder never prunes retained families. Actual freeze/seal remains the unchanged custodian route.
2. A separately authorized custodian read layer owning hash-bound protected reads and access logging before passing bytes to these functions. This package deliberately implements no production access path. An R1 release cannot substitute for protected custody authority.
3. Separate exact coverage/status bindings. Current `custodian_newperiod_inputs.master` binds membership, summary and anomalous files but **does not bind coverage.json**. Coverage cannot be inferred from the input-status field. Any missing source needs an explicit retained source/censor receipt.
4. The actual binding five-seed extension decision and complete 30/60-second reference populations. Neither draft dates nor the current R1 release supply these.
5. Input-only projections for **every** retained reference row, including abstentions, if slice tables are desired. No missing variables are synthesized. A future custodian exporter must produce and verify the projections from actual exported input bytes.
6. `slice_predicted_asns` production remains missing: current repository search finds only the custodian schema and consumer checks, no prediction producer. This package does not modify predictors or invent slice decisions. The optional slice-Jaccard family remains unavailable until a separately reviewed producer supplies commitments.
7. Final exact operational/source/runtime/resource review, actual custody authorization, and owner-controlled once-only execution. No such authority is contained here. Report-to-manuscript numerical integration also remains separate; these functions produce prerequisites, not released results.

## Synthetic evidence and requested verdict

Forty focused tests pass, with Ruff clean. They exercise real existing validators and target/arm/slice helpers without mocked scientific validation. Fixtures cover both horizons, reference-panel exclusion, duplicate ASNs, inclusive +7200 seconds, later microseconds, timezone-equivalent timestamps, naïve/invalid/null clocks, protocol start/end and extended end boundaries, pre-onset canonical membership behavior, declared missing/censored states, coverage contradictions, source hash changes, retained technical failures, no zero-fill, exact role populations, seed conflicts, immutable existing roles, input-only slice projections, wrong table horizons, R1 authority substitution, and exclusive output. A dedicated test forbids filesystem provenance reads while running the pure builders.

Independent review is requested **code only**. All protected-read, label-generation execution, prediction, fitting, scoring, custody freeze/seal, N unseal, R1 release, staging, submission and retry authorities must remain false. Actual review should record source bindings, package pins and the exact remaining blockers above.
