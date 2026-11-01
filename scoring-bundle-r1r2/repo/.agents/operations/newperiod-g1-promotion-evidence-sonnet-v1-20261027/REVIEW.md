# G1 promotion evidence for the 122 slot-complete arms (Sonnet author; local reads only; nothing promoted)

Answers sol-g1 `promotion-evidence-review.json`. `build_evidence.py` re-derives `promotion-evidence.json` from the pinned fragment be7c140c and 21 pinned records (path + sha256 each, `refs`); every one of the 122 arms is bound to an accepted actual output by exact value containment (not by name), 5 tests.

## What exists (per group)
- **primary56:** 40 updated checkpoints + their rules + ledgers = accepted `core-remote-metadata-actual v3` stdout 8b831f4d (REMOTE49-V3-ACTUAL-ACCEPTED c28a5113) with ROOT all-40 completion assessment cf79a052 and membership certificate c12e40e2 (accepted by CORE-CAMPAIGN-LOCAL-WITNESS); 10 frozen_2025 checkpoints/rules = accepted `core-local-metadata` (REVIEWER-sol-final-CORE-LOCAL-METADATA-ONCE-V1-ACTUAL-ACCEPTED) and the frozen plan d0b727fb; 6 history-kNN configs = configs24 actual 5a774b35 (accepted, opus ACTUALS...CONFIGS24-GRU10); corrected primary export manifests (PRIMARY-EXPORT-KEY-CORRECTION accepted).
- **history48:** 40 neural arms reuse shared core checkpoints (remote49), each carries the core ledger provenance (history40 review); **the 8 arms "without provenance" are history-kNN config arms (delay900/delay1800/withhold x matched/native)**: bound by the accepted configs24 rows (path+sha equal). Provenance is required only on the 40 neural arms, so these 8 are not a missing ref (sol-g1 to confirm).
- **ordinary12:** 10 GRU checkpoints = accepted gru10 actual c6d8461e (each `original_embedded_authorization_equal`); 2 GBDT checkpoints = the astra completion assessment of the two fits.
- **baseline6:** configs24 actual rows (path+sha equal) + opus BASELINE24/BASELINE6 PASS.

## What truly does not exist (readable in `truly_missing`)
- **M1** identity attestation: nothing states the plan-supplied primary/baseline arm_id strings equal accepted actual identities.
- **M2** per-arm completed-fit role-bound acceptance for the 12 ordinary arms (gru10 actual says `completed_fit_review=false`; GBDT assessment is author-side, payload not rehashed).
- **M3** per-arm exact custody binding acceptance for any of the 122 (baseline descriptors say false).
- **M4** actual G1 acceptance of the core calibration consumer / history lineage (both PASS_PREPARATION, `actual_g1_accepted=false`; remote49 is metadata-only, scientific_ready false).
Minimal closure: sol-g1 (or another distinct reviewer) either accepts these bindings as sufficient for M3/M4 or issues one typed acceptance per missing item (M1 attestation of the id rule, M2 over the 12 listed fits); only then sign `G1_DISPOSITION_PROMOTION_V1`. Until then all 122 stay PENDING.

## Runner
Per ROOT decision: stay on reviewed r2 `runner.py` 180bdcab; no r3-retained activation now (the r3 recommendation in earlier REVIEW.md files is withdrawn). Plans use namespace `complete-retention-v2`, no `retained_admission`/`retained_guard.py`; `g1_draft_prep.runner_module('runner_r2')`.
