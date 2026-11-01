# G1 promotion item M4: core50 consumer + history lineage inputs (author: Sonnet; unsigned, authorizes nothing)

Source: sol-g1 `REVIEWER-sol-g1-G1-PROMOTION-EVIDENCE-M1-M4-V1.json` required_next_records.M4. All inputs are local, hash-pinned metadata (build.py verifies each pin). No cluster access, no protected payload, no threshold/label/score content, no authority consumed. `execution_authorized=false` in every document; no promotion record is issued.

## Files
- `e1-e4-admission-request.json`: exactly what designated sol-h3t2 must admit (E1-E4 typed, byte-pinned; E5 stays `pending_actual_freeze_binding`). 15 required byte pins (prior h3t2 status, accepted capture 14907dea, template 755dde9a, matrix, learned50 packet, producer b8265789, producer approval, plan be07e211, completion assessment cf79a052, predictor 5e36a2f6, evidence template, contract, h3t2 proof/verify, sol-final prep review).
- `core50-consumer-binding.json`: 50 rows (40 updated, 10 frozen_2025): checkpoint, decision-rules ref, fit receipt, completion, fit ledger, publication (e665c593 updated; 66c2ce8c frozen), issue-time table/evidence per horizon, frozen provenance (plan d0b727fb + membership c12e40e2). Locally cross-checked: updated checkpoint/rule equal remote49 actual; frozen equal local metadata + remote49; 50 distinct checkpoints and rules.
- `history-check-inputs.json`: check A (feature contract / global threshold) and check B (intervention/query/library audit) inputs. 40 neural history arms each joined to their core role: checkpoint equals core checkpoint, provenance ledger 9b4388e5 identical, 20 reuse keys (10 keys used 3x, 10 used 1x); 8 history-kNN configs listed separately (no checkpoint/threshold, bound by accepted configs24). Same-horizon descriptor check: exactly 1 distinct manifest/master/source_inventory/input_gate set at d30 and at d60.
- `build.py`, `test_build.py` (7 tests), `tests.txt`, `SHA256SUMS`.

## Finding the reviewer must know
`history-inference/runner.py:169` writes `normalization_and_global_validation_threshold_unchanged=True` as a literal, not a computed equality. It is not evidence. The evidence for "threshold unchanged" is: history arm rule/checkpoint/provenance refs equal the core role refs (this packet), plus the runtime guards at runner.py:86-87 (reuse-key equality of model_path/sha/provenance) and :127 (`checked_contract`). Actual rule contents are not read here; equality is on accepted path+sha refs only.

## Not established (still missing, stated so nothing is read as accepted)
- Rule index membership in publication e665c593 `verify_output` rests on the accepted E3 attestation; the 40 refs here are the enumeration to confirm against it.
- 20 of 40 updated completion JSONs were hash-only in remote49 (`completion_mode=hash_only_no_JSON_parse`).
- History custody_inputs, event_ids, source_declarations, four-library memory/runtime inventory: absent. Any capture needs a finite source-grounded read-only design, scope/resource review and a fresh ROOT once.

## Root sequence and reviewers
1. sol-h3t2 (core calibration consumer reviewer): admit E1-E4 per `e1-e4-admission-request.json` in a fresh reviewer directory, exact bytes. Reviews: calibration admission only. Not all-five.
2. sol-final: review `core50-consumer-binding.json` against the accepted core50 merge (2026-10-26) and remote49/local metadata (checkpoint/rule/receipt/ledger/publication/issue-time per row). Reviews: core50 consumer binding and learned50 preparation.
3. sol-g1: check A and B from `history-check-inputs.json`: feature contract / rule+checkpoint+provenance equality for 40 arms, intervention/query/library audit with identical same-horizon bindings; supplies or specifies the finite read-only projection for custody/event/source bindings (needs separate review plus ROOT once). Reviews: history lineage and family disposition.
4. After 1-3: actual exact-arm core/family disposition reviews (core50 arms by sol-final, history48 by sol-g1), then sol-g1 may sign `G1_DISPOSITION_PROMOTION_V1` only when M2 and M3 also hold.
5. Actual G1 freeze, then sol-h3t2 E5 freeze-binding check (`check_e5.py`) and the all-five admission, then learned50 assembly. E5 is not a pre-G1 gate.

Reviewer independence: every review above must be a session distinct from the Sonnet author and from the authors of the packets being reviewed.
