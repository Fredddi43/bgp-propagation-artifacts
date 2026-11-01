# Review: substitute E5 checker vs pinned check_e5.py

Verdict: CHANGES (substitute is not a superset; several pinned assertions dropped or weakened; false-pass paths exist).

Basis note: ALERT-G2-E5.md lines "What the pinned checker actually asserts" do not describe check_e5.py. The pinned file
(newperiod-core-e5-freeze-check-astra-v1-20261025/check_e5.py) has no freeze-dir hash, no arm-sha/shard-sha, no extra-file
or closure assertion, no field whitelist. It is a metadata check on a published freeze plus the G1 completion chain. The
table below uses the real pinned assertions. No tests exist for check_e5_g2.py or fill_e5_admission.py (only test_e5.py for the pinned one).

P = check_e5.py, S = g2r2/g2/check_e5_g2.py, F = g2r2/g2/fill_e5_admission.py

| # | Pinned assertion (P line) | Substitute | Status |
|---|---|---|---|
| 1 | Pinned source/control files re-hash (sources.json) (P:24-25) | none; S reads E1-E4 time from an unpinned file (S:100-102) | DROPPED. F re-verifies the draft's required_byte_pins (F:67-72) but that is a different set; it omits check_e5.py/prepare.py/sources.json |
| 2 | Prior review contract_evidence == E1-E4 passed, E5 pending (P:27-28) | F checks E1-E4 "passed" only (F:64-66); extra keys/E5 value unchecked | WEAKER |
| 3 | Exact binding set; references canonical (abs path, normpath, 64-hex) (P:17-20,38-39) | none | DROPPED |
| 4 | Freeze bytes sha == binding (P:32,41) | S hashes what it reads (S:110) but compares to nothing; F takes global_freeze_sha256 from the receipt (F:100) | DROPPED (self-referential) |
| 5 | Independent accepted G1 finalization review (passed, scope, independent worker/session, model, terminal COMPLETED, full_roles 400, bindings equal) (P:45-50) | none | DROPPED |
| 6 | done.json: passed, op finalize, plan/approval bound, no retry, gate_issued False, predictions_computed False (P:51-53) | none | DROPPED |
| 7 | result.complete_freeze==freeze, ten family files exactly, namespace (P:54-58) | S loads 8 group docs, no name-set or ref check (S:33,70) | DROPPED |
| 8 | freeze.complete_retention_review == binding (P:59) | none | DROPPED |
| 9 | m.complete400(f, review): 400 roles complete (P:60) | S only reports len(f["arms"]) (S:112), never asserts 400 | DROPPED |
| 10 | Disposition review has reviewer_model (P:61) | none | DROPPED |
| 11 | frozen_at tz-aware and >= prior E1-E4 utc (P:62-63) | S:99-103: same ordering, naive/aware mismatch raises and is caught -> fail; reference file is not hash-pinned and differs from P's pinned review | EQUAL on logic, WEAKER on source pin |
| 12 | All56 primary executable: no retained_failures role in primary keys (P:64-65) | none | DROPPED |
| 13 | Learned selection via client.retained_learned(f) (P:66-67) | S:72-74 uses status==committed && family==neural && not in group docs; different selector, can disagree | DIFFERENT / unproven equivalent |
| 14 | exactly 50 learned, 40 updated (P:68) | S:75-78 50 and 40 updated plus 10 frozen_2025 | EQUAL or stronger |
| 15 | every learned arm status committed_for_prediction (P:71) | S filters on committed (S:72) so a non-committed learned arm is silently excluded and only the count of 50 catches it | WEAKER |
| 16 | each learned arm slice_decisions == expected_slice from m.build()[3] (full object) (P:67,71) | S compares only slice_decisions.publications, identical across arms and == draft (S:80-87) | WEAKER (other slice_decisions fields unchecked; expected_slice not derived from pinned code) |
| 17 | decision_rules is canonical reference (P:72, via 17-20) | S:88-90 only keys and len 64; no hex, absolute, normpath check | WEAKER; S adds existence+sha on cluster (S:92-97), which P does not do |
| 18 | learned_bindings_sha256 over rows (P:73,79) | S:107,114 same encoding | EQUAL |
| 19 | Output passed False, independent verdict required (P:76-77) | S emits checks_passed only, F sets passed True | DIFFERENT by design (see below) |

BLOCKERS: rows 1,3,4,5,6,7,8,9,10,12 dropped; 2,13,15,16,17 weakened. Substitute is not a superset.

## False-pass paths (substitute true, pinned would reject)
1. Freeze with fewer/more than 400 arms, or with incomplete retention/disposition (rows 8-10), passes as long as 50 neural committed arms with matching publications exist.
2. Freeze whose G1 finalization was never accepted/finalized (rows 5-7) passes. This is the main risk: the receipt asserts nothing about publication provenance.
3. Primary-role retained_failures (row 12) not checked.
4. Arms with a wrong slice_decisions field other than publications (e.g. other slice keys) pass (row 16).
5. If one of the eight group docs is absent, S aborts (good), but F silently skips it (F:55-58), so `others` shrinks, and F's learned count could differ from S's; F then may use a different learned set than the receipt covered.
6. Receipt is never bound to the freeze: F never compares receipt.actual_global_freeze.sha256 with the sha of the freeze it read (F:50,62,100), never checks receipt kind, learned_bindings_sha256, or admission_draft_sha256. A stale or hand-made receipt with checks_passed true yields passed=true. F re-derives the publications check itself (F:83-94), which limits this to rows 1-4 above, but the receipt gate is nominal.
7. If the draft has no contract_evidence key, ce is a detached dict (F:64,112): E5 is not written, yet passed=True is still set. If it has extra keys, they are not rejected, so exact E1..E5 is not enforced by F (F:65 only inspects E1-E4; E5 prior state unchecked).

## fill_e5_admission.py questions
- Can passed be set without a passing receipt? Only checks_passed truthiness of an unauthenticated file (F:62). Not bound to the freeze (point 6). Partially no.
- contract_evidence stays exactly E1..E5 passed? On the normal draft (all five keys present) yes: only E5 is flipped (F:112) and the receipt is outside (F:107). Not enforced if keys differ (point 7).

## Required changes before ratification
1. Either port rows 1-12 (as a new byte-pinned file with a delta table, ALERT option B) or have root explicitly accept each dropped assertion in the ratification text with the compensating control named. The ALERT's audit list must be corrected; it misstates the pinned checker.
2. S: hash-pin and assert the E1-E4 review source; assert len(arms)==400, tz-aware frozen_at, canonical reference form, status committed on every learned arm, full slice_decisions equality against an expected object built from the pinned prepare code, and no retained_failures role in primary.
3. F: require receipt.actual_global_freeze.sha256 == sha(freeze read), receipt kind, and recomputed learned_bindings_sha256 equal; require full E1..E4=passed and E5 == pending before the flip, contract_evidence present, and a set-equality assertion on its keys afterwards; fail if any group doc is missing.
4. Add tests (positive plus one negative per assertion) for both scripts.
