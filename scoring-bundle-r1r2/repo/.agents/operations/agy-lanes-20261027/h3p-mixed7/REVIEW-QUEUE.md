# Review Queue: h3p-mixed7 lane

## h3-captured (4 scopes) -- queued 2026-10-27T05:50Z by claude-sonnet-5-5 subagent (PENDING until audits finish + capture)
- Packets (created by watch_capture.sh): .../newperiod-inputs-v1/h3-captured-sonnet-20261027/<scope>/panel-review.PENDING_ROOT.json (4 files: ris7-d30, ris7-d60, mixed7-d30, mixed7-d60) + input-gate.json, scope-record.json, event-ids.json.
- Summary: protected H3 chain ran via direct driver run_step2.py (same kernel.run_phase args as runner.py; plan.json hash-pinned 129 files verified; ONE deviation: bgbench.__path__ extended with plan-pinned construction/source for forecast_input_panel, which the builder snapshot lacks; method unchanged). Review file asserts mechanical checks only (done.json chain under one plan sha, full-input-proof rows == manifest rows, population/protocol/inventory/availability/audit hashes agree, gate inputs == manifest rows).
- Flip: `signoff.sh <review>` for each of the 4; then `ssh <BATCH_HOST> 'python3 -B -' < .agents/operations/agy-lanes-20261027/h3p-ris7/bind_h3.py`.
- Risk: input_gate is derived (passed=true, manifests[].inputs) by this author, not by an independently issued gate op; panel_review reviewer_worker/session strings are claude-sonnet-5-5 labels (not in predict.py AUTHORS). Root must confirm that is acceptable for G1/predict.

## UPDATE 06:40Z: h3-captured READY (4 scopes). Supersedes the 05:50Z entry (review files are now panel-review.json, final bytes).
- Dir: <FORECAST_ROOT>/data-custodian/newperiod-inputs-v1/h3-captured-sonnet-20261027/ ; signoff record to flip: ROOT-SIGNOFF-h3-panel-reviews.PENDING_ROOT.json (signoff.sh flips verdict). G1 inputs: scopes.json (manifest,input_gate,availability,panel_audit,panel_review,custody_inputs per scope) + event-ids-by-manifest.json for h3_fragment.promote().
