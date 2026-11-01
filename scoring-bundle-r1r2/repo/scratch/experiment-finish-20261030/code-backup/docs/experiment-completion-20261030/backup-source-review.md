# Independent backup-source verification

Verified at 2026-10-30 14:03:09 UTC (clock tool). Verdict: PASS for the current clean-backup bytes at `scratch/experiment-finish-20261030/code-backup/`. This is source-preservation proof, not an experiment-outcome claim.

- Frozen `docs/experiment-completion-20261030/scientific-closure.json` has the expected SHA-256 `a72c35de1f716921a5092d3f096ea4d2491161d17e4ab00f0998eee9b7aecccd` and is byte-identical to the independently retained original closure.
- Derived the relative paths independently from that closure's bound `source_root`. All **90 unique scientific files** exist in the backup and match their original closure SHA-256 values; **zero mismatches**. The relative `scientific-source-sha256.json` is exactly that independently derived 90-file map, SHA-256 `e2cbe1cb148f3c932b450f49b9160a111395d97fed67ba148ceed4a88278b5a0`.
- The **14-file v2 runtime map** exactly equals the independently approved map in `review-combined-final.md`. All 14 backup files and the current operational source copies match it. Map SHA-256: `ccbf5229d8590c6da4a289a1d0688c37776f93b9c63127813ca6f924bc72f345`.
- The original persistence-runner folder's **19 non-test Python modules plus three JSON controls** (`pins.json`, `review-ready.json`, `root-independent-review.json`) are byte-identical between the backup and the operational checkout.

The two restored backup files match both the frozen scientific closure and operational source bytes:

| File | SHA-256 |
| --- | --- |
| `src/bgbench/forecast_recipes.py` | `04691c483a64c0e6c93fd058da8d41347eabdc0c31ba881f165746074ab50d6e` |
| `src/bgbench/forecast_retrospective_custody.py` | `818497e430b9871cdb3761e44b554a8c84e87ccbc66fd44647d28fd2cf9ccbc7` |

No source fixes, git operations, cluster changes, label reads or job operations were performed. The reviewed backup bytes are ready for the owner's planned commit; commit/push state is outside this proof.
