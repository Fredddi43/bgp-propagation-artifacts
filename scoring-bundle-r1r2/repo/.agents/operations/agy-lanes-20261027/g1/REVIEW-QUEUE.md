# Review Queue: g1 lane

## 1. G1 Disposition Promotion 122 Roles
- **Packet path**: `<REPO>/.agents/operations/agy-lanes-20261027/g1/g1-disposition-promotion-122.json`
- **Summary**:
  - Covers 122 slot-complete roles across primary (56), history (48), ordinary executable (12), baseline (6).
  - Binds M1 identity attestations for primary56 and baseline6 arm_id strings against accepted remote49 and configs24 actuals.
  - Attests M2 ordinary12 completed-fit acceptance per M2 v4 actuals acceptance (74660dd4 in newperiod-g1-m2-v4-history-v2-actual-review-sol-g1-20261027).
  - Attests M3 custody bindings per M3 v3 acceptance (f13dbd41 in newperiod-g1-m3-v3-actual-acceptance-sol-g1-20261027).
  - Attests M4 history lineage & core50 consumer bindings (declaration 5571dcd6, core50 5613da61, E1-E4 4252c10d) + failure accounting for count34 (0e537a99) and ordinary20.
- **What changed vs predecessor**: Initial promotion packet completing M1-M4 requirements for all 122 slot-complete roles.
- **Tests**: `pytest -q <REPO>/.agents/operations/agy-lanes-20261027/g1/test_g1_merge.py` (1 passed).
- **Exact risks**: Promotes 122 roles to committed_for_prediction; all 122 have verified slots and event IDs.
- **Command to flip**: `<REPO>/.agents/operations/agy-lanes-20261027/signoff.sh <REPO>/.agents/operations/agy-lanes-20261027/g1/g1-disposition-promotion-122.json`

## 2. freeze_run.py + frozen-arm field merge (2026-10-27 sonnet subagent)
- Paths: g1/freeze_run.py, g1/incremental_draft.py (merge_custody_bindings, merge_runner_fields, required_fields), g1/OWNER-REQUIREMENTS.md. Tests: g1/test_g1_merge.py, g1/test_freeze_run.py (2 passed).
- Why: the 122 promoted arms lacked `custody_inputs`/`sources`/`baseline_sources`/ordinary `provenance`, all read from the FROZEN arm by the inference runners; a freeze without them would have made G2 impossible. Now merged from accepted artifacts (M3 c9d18709, 12 sol-g1 completed-fit reviews, history declaration 5571dcd6 / signature 469216cd).
- Risk: history/baseline `sources` = {master, history, signature} is inferred from runner usage; confirm at the first G2 canary.
- Root actions: run signoff.sh on g1/g1-disposition-promotion-122.json (still PENDING_ROOT) when satisfied; relay OWNER-REQUIREMENTS.md to h3/stable/timing/origin lanes.
- 2026-10-27 SIGN REQUEST (g1): promotions/g1-stable-fragment-promotion-24.json (sha e37ff048105d2f49...) — flips the 24 PENDING stable fragments (g1/fragments/stable, index 8b810690, combined cdd2518a) to committed_for_prediction at merge time. Evidence: input reviews 1a0d3ded/0575ccaf root-signed PASS 09:46:47Z (ROOT-SIGNOFF sha f593bfad, verified on cluster); every arm already passes required_fields()+slot checks (merge-report invalid=0). Nothing changes until you sign; merge re-validates at apply.

## 3. SIGN LIST (2026-10-27 11:58Z, g2r2 subagent): see FREEZE-RUNBOOK.md FAST PATH
Now signable: promotions/h3/approval-{chain,ids,frozen,destinations,disposition}.json (5) + promotions/g1-stable-fragment-promotion-24.json (rewritten, new sha). Later: timing/origin promotion packets (family_expectations.py draft) and the 8 freeze review packets. Then `promote_all.py`.
