# G1 complete-400 draft prep v2 (Sonnet author; source and metadata only; nothing executed)

Supersedes v1 (unchanged on disk). `g1_draft_prep.py` is byte-identical to v1 (kernel 20e885b3 and runner pins unchanged); the new piece is `consume_accepted.py`.

## What v2 consumes (all pins verified before use; `test_accepted_pins_and_real_ids`)
- merged fragment be7c140c; event-ID actual `stdout.json` f13a5f25 re-validated by the pinned checker b941b69b against request 20f4d0b1; sol-g1 acceptances 45661db3 (event IDs), 8de69af1 (controls v2), e66d7391 (typed R1 release acceptance), board verdict e9f8b14a; controls.json 446ed6ef (`protocol=newperiod-complete400-v1`, release binding equals the R1 acceptance release).
- `fill_available`: exact manifest path+sha mapping (all four manifests share the same 1289-ID digest 6c1cf870, so digest coincidence is never used). Result: event_ids filled for primary 56, history 48, ordinary 12, baseline 6 = 122 arms; no status is promoted.
- `promote` (record shape `G1_DISPOSITION_PROMOTION_V1`, not yet existing): the only way PENDING becomes committed_for_prediction; refuses unbound slots/IDs, unknown or other-group arms, wrong fragment, execution_authorized true, excluded reviewers. These 122 arms need only that independent record.
- `gaps`, `assemble_when_ready` (refuses until all ten groups are final).

## Refreshed readiness
`READINESS.md` / `readiness.json` (built by `build_readiness_v2.py`): per group exact null counts and, for each not-ready group, the exact accepted artifact the draft will consume when it lands (H1 `h1-arms.PROPOSED.json` from the final20 build once; H3 owner fragment from refit job 52558223 capture acceptance + protected H3 chain + destinations; timing, stable, origin owner fragments; count staged receipt + family review). Each non-primary group later needs one scoped extraction via `newperiod-g1-event-ids-extraction-sonnet-v1-20261027/make_request.py --extra`.

## Root sequence unchanged from v1 (extraction -> promotion -> assemble -> inventory -> reviewed package -> one draft once), with: controls and R1 now done; recommended runner r3-retained d6d13ca8 (diff vs r2 in v1 REVIEW.md; sol-g1 conditional PASS pending ROOT adopting the parsed G1 route).

Tests: `test_g1_draft_prep.py` (v1, readiness shape updated) + `test_consume.py` (5).
