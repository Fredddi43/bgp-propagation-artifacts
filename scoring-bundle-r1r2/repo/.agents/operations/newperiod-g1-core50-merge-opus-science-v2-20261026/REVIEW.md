# G1 core50 merge v2 (opus-science, author) — ready before remote49 runs

Turns the accepted remote49 v3 actual into the last missing fields of the 50 primary
neural arms in complete400 (merge v1 e4f5770d): model_path, model_sha256, decision_rules,
and frozen10 provenance. Local metadata only; no checkpoint/rule/label/score opens.

Field shapes are exactly what the v3 predictor checks (`newperiod-core-remote-metadata-once-astra-v3-20261026/predict.py`):
updated provenance {kind newperiod_core_ledger_v1, ledger} must ALREADY equal the row's
fit_ledger (refuses otherwise, never rewritten); frozen provenance {kind frozen2025_plan_v1,
plan, calibration_membership} is built and cross-checked against the reviewed adapter
`bind_core_map.attach_frozen_provenance`; frozen rules via `bind_core_map.frozen_map`
(which re-validates the campaign certificate). Updated models come from remote49
children40 (cached rows must equal the accepted local identity); updated rules from
remote rules['updated'].

Uses merge v1's conflict-refusing `apply_fields`. Preserves arm IDs, outputs, statuses
(PENDING), manifests, gates, slice decisions, six primary baselines, all other 344
entries and the 54 failure rows (checked). Requires an independent remote49 actual
acceptance (`passed`, `accepted_output` == the result ref, reviewer != opus-science) and
the same certificate ref as the v3 request 94e53bce. Output goes to a fresh sibling.

Tests: `cd /tmp && python3 -B -s -E <dir>/test_prepare_v2.py`: 10/10 with a synthetic
remote result derived from the real v3 request (all 50 bound, predictor shapes, 160
field changes over 50 roles, no promotions, typed model path match, refusals for missing
rule / other certificate / self-acceptance / cached checkpoint drift). No files written.
