# Packet C (author: sonnet; reviewer separate) — complete20 H1 bind + fixed audit_gate

Status: FALSE template, `execution_authorized=false`, local only (no remote, no payload). 23 synthetic tests pass (tests.txt). Replaces v1 `audit_gate.py` (refused: H1-G1-ROLE-1, H1-G1-CLOSURE-1, H1-G1-GATE-TYPE-1; collector finding is closed in Packet A).

## The five v1 false-PASS mutations: each now FAILS (tests)
| v1 mutation | v2 test | caught by |
|---|---|---|
| arm-role swap | `test_M1_arm_role_swap`, `_M1b` | exact arm_id -> full role dict vs pinned g1-slots h1 |
| full-role change (family/variant/panel/history/training/K) | `test_M2_*` | same + outer horizon == role horizon == horizon key/group |
| output path substituted in binding AND collection | `test_M3_*` | exact14 rows vs `expected_outputs(handoff)`; builder refuses the mutated refs |
| construction SHA replaced in both | `test_M4_*` | equality with handoff construction pin (not the `matches_handoff_pin` flag) |
| phase-chain acceptance SHA modified | `test_M5_*` | `complete_accepted_history` and capture review vs pinned handoff/review sha b5196ff1 |
Also tested: receipt rows, slot_manifest path AND sha vs export ref, source pins (slots a5ef7d37, refs, report, reviews) bound in the pure gate, finalizer audit cannot be the input gate (four distinct files; gate/audit must equal Packet B actuals), gate from wrong horizon, descriptor swaps (model/decision rules), fabricated disposition/promotion, event-id count/digest, malformed documents (any exception is a failure), all20 unique roles, bindings == deterministic rebuild.

## What it binds (`build_bind.py`, status stays PENDING)
Per role: model/calibration/decision-rule/commitment/prediction/slice descriptors from the reviewed projection (5b4f09ba), manifest = Packet A export manifest, input gate + finalized audit + review copy + evidence from Packet B, primary_manifest/issue-time tables/slice rule/custody inputs from Packet A projection, phase-chain acceptance. Literal event-id lists are NOT copied (`event_ids=null` + count/digest + ref to the finalized audit that holds them). `independently_accepted_final_disposition` stays null: the exact H1 family/arms/disposition review (which may precede the complete400 freeze, no cycle) and the G1 owner merge are separate gates. The ROOT-only G1 draft/finalize once is the G1 owner's separately reviewed packet, not this one.

## Exact root sequence
1. Packet A and B actuals independently accepted (their acceptance posts exist).
2. Independent reviewer PASSes this packet (source, `run_bind.py`, FALSE once, tests).
3. Root: rescan posts; fill `root-bind.FALSE-TEMPLATE.json` (all pins incl. A/B acceptance, both reviews, `authors`, fresh `records`); `cd /tmp && python3 -I -B run_bind.py <filled once>`; PASS 0 writes `records/h1-slot-bindings-v2.json` (exclusive) + `result.json`; any audit_gate failure writes nothing but the result.
4. Independent review of that actual; then the exact H1 family/disposition review; then the G1 owner merges and the separately reviewed complete400 G1 freeze.

## Reviewer must check
(a) the G1 slot field names against `g1-inventory`/`g1-freeze` (fields here are a superset of the PENDING slot schema plus explicit group/horizon); (b) `audit_gate._check` invariants are written independently of `build_bind`, and rebuild-equality is only the last check; (c) the v1 gate itself was not re-run on the mutations; the five tests are the v2 evidence.
