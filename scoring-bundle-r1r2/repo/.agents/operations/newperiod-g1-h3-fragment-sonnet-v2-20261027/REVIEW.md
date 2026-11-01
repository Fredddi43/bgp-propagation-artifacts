# G1 H3 fragment v2 (Sonnet author; sibling of v1, v1 untouched)

Fixes astra-final findings H3G1-1/H3G1-2 (v1 pending artifact PASS stays valid; promote() was not approved). `h3-arms.PENDING.json` (sha f18687dd) = v1 content + `package_confirmation` (stage acceptance 32a0f9a6 + stage receipt 4b2923a9, astra-final's confirmation) + corrected schedule wording: protected H3 chain is 36 waves in total (4 groups x manifest + 4 build waves + assemble/master/export/audit), not 36 per group (sol-h3t2). The wording lives in each arm's `pending_owner`.

## promote() v2 (h3_fragment_v2.py)
- `fill()` fills slots only; `promote()` = `fill()` + exactly five typed approvals (chain, ids, frozen, destinations, disposition), each a file loaded by exact path+sha, `kind` matching, `passed is True`, scope `newperiod-h3-retention-v1`.
- Each approval binds `fragment_sha256` = digest of this exact fragment and `evidence_sha256` of the evidence it approves (scopes / ids / accepted frozen primary arms / sorted 160 destinations); disposition binds the exact filled candidate hash and exactly the 80 arm_ids (no unknown, duplicate, partial).
- Reviewer worker/session/model must be non-empty; worker/session may not equal or prefix-match any author/alias id given (case-insensitive).
- A fragment differing from a fresh `build()` (tampered checkpoint hash, destinations, flags) is refused; any missing/malformed scope, ID, frozen source or unconsumed pending flag refuses the WHOLE call (no partial promotion). Output status `FINAL_APPROVED`, `executable:false`.
- Limits: approval documents are produced by reviewers (templates not provided here); promote cannot check that the reviewer actually examined the evidence, and the authors set is whatever root passes.

## Review ask / root sequence
1. A fresh independent reviewer (not Sonnet; astra-final may review a successor) reviews `h3_fragment_v2.py` and the 21 tests (`tests.txt`), incl. the v1-bypass regressions: missing model, zero/None fragment hash, author reviewer, tampered checkpoint hash, missing scope/ids/frozen, unknown/duplicate arms, unconsumed flags.
2. Then the steps 2-6 of v1 REVIEW.md (sol-h3t2 chain acceptance -> extra ID request/extraction -> M1/M3/M4 -> destination admission -> approvals -> promote -> family review `newperiod-h3-retention-v1` -> sol-g1). `make_h3_request.py` is unchanged from v1.
