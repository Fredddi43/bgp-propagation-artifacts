# Paper methods/status cleanup r2 (docs only, LOCAL, uncommitted)

Author: claude-opus-5-5, session <SESSION_ID>. This applies review a2c90aa2 (`paper-status-review.txt`, CHANGES_REQUIRED)
to the two files that `../paper-status-cleanup-20261022/` (pins d04ef95f) changed. That packet and its diff are
preserved unchanged; it records the r1 state (methods a21978c0, outline 683d9933). Nothing else in `docs/` or `paper/`
changes.

## The four edits (`delta-r1-to-r2.diff`)

- **C1, methods §3.8 "Failed and unavailable cells":** the reviewer's replacement text, verbatim.
  - If any cell of the matched-seed analysis (R-core, R-gbdt, R-base) is not scored, the whole analysis is reported
    unavailable. Each of the original fourteen Jaccard contrasts is unavailable on its own.
  - The src comment adds `forecast_retrospective_release.py:54` (ANALYSED_ARMS) and
    `forecast_retrospective_scoring.py:225-233`. I re-read both lines in the v8 source tree (custody 409e1171,
    driver 33011eed).
  - The two existing sentences after it ("We never drop a failed cell ...", "The same rule applies to the secondary
    transfer union.") still hold and stay.
  - Note: the verbatim text has one semicolon, which the draft's own style rule (no semicolons) would split. It is
    kept as given. Splitting it is a delta-review call.
- **C2, methods §3.8 "One attempt per launch":** "Each R1 preparation or evaluation attempt ...". The src is scoped to
  every R1 preparation/evaluation execution approval (r1-release-v5..v7 execution/package, final-staging v7, v8
  approval 207caa00).
- **C3, outline §4 row F3, 22 October column:** the reviewer's first sentence, verbatim (GO under two stated
  conditions; the sub-second criterion failed, 3 of 10 collectors).
- **W1, methods §3.9 item 15:** "built on measured timings and conservative bounds".

No other line changed. There is no new result, number, protocol, analysis or literature claim.

## Files

| File | sha256 |
|---|---|
| `docs/paper/forecasting-improvement-20261017/MANUSCRIPT-DRAFT-METHODS.md` (r2) | 0914e57c540247060009c17d872d293534a6d41398420b4100675fc24ba404c2 |
| `docs/paper/forecasting-improvement-20261017/MANUSCRIPT-OUTLINE.md` (r2) | c98e7524c95a6be87a9cee8d1b9adbb3eeda14068a039e29761b32b70755a1ac |
| `delta-r1-to-r2.diff` (only the four edits) | see `pins.json` |
| `paper-status-r2.diff` (full diff against HEAD, i.e. bases 181e0f8f / 3694e7c7) | see `pins.json` |

The r1 files were reconstructed as HEAD plus `../paper-status-cleanup-20261022/paper-status.diff`. They re-hash to
a21978c0 / 683d9933, which equal the r1 pins.
