# G1 controls binding (Sonnet author; local reads + read-only lstat; nothing executed)

Produces `controls.json` (the owner fragment for `g1_draft_prep.assemble_plan`) and `controls-report.json` (evidence, acceptance, open items). `build_controls.py` recomputes every local sha and checks the pinned cluster lstat record (`controls-lstat.json`: size equal to the local copy, mode 0444, regular file).

| control | cluster path used by the Reader | sha256 |
|---|---|---|
| recipe | `.../newperiod-development-v1/all-recipes-astra-20261019/evidence/docs/paper/forecasting-improvement-20261017/ALL-RECIPES-DRAFT.json` (118761 B) | 6d851282... = kernel `RECIPE_SHA` |
| scientific_protocol | same dir, `NEW-PERIOD-PROTOCOL.md` (7468 B) | fd0a1a1c... |
| exposure_ledger | same dir, `EXPOSURE-LEDGER-DRAFT.json` (2534 B) | ba323f55... |
| retrospective_release (R1) | `.../r1-release-parallel-v11-20261024/control-v1/release-native-v2/r1-release.json` (6220 B) | ba2a1e2e... (flags passed, development_frozen, evaluation_release_complete all true; local copy `operations/r1-v11-posteval-20261024/release-actual-v1/r1-retrospective-release.json`) |

Acceptance evidence found: recipe freeze receipt `newperiod-gbdt-20261020/recipe-freeze-receipt.json` (passed, frozen_before_r1, retuning_reserve_closed; its draft/exposure refs equal the controls), its independent root review, and the remote `review.json` 7e354b7f (9705 B, 0444, reviewer openai/gpt-6-astra).

## Missing / flagged (also in `controls-report.json.open`)
1. **`protocol` (freeze name string): no accepted value exists** in the repo. `controls.json` carries `null` and `assemble_plan` refuses until ROOT decides. Proposal only: `newperiod-complete400-v1`.
2. **R1 release acceptance has no board verdict file**: only HANDOFF prose (2026-10-24, "remote publication/readback independently accepted by Opus 55ae40e5/e1440bee"). Ask ROOT for the verdict path or have sol-g1 accept the pin before the draft once.
3. **Scientific protocol** has no standalone acceptance verdict; it is pinned by the recipe-freeze evidence tree and by `REVIEWER-sol-final-T040-COMPLETE400-SOURCE-CONSISTENCY`, which names the same sha.
4. `publication_root` is not a control; the runner requires `<ROOT>/finalize/attempt/output`.
5. Remote bytes were not re-read (size + mode only); the draft Reader will hash them against these pins at run time.

Tests: `test_controls.py` (4). Runner recommendation r3-retained d6d13ca8: see the draft-prep REVIEW.md.
