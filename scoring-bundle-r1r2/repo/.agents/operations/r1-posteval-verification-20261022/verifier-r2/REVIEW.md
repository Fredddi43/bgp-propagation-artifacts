# Review packet: independent R1 verifier, round 2 (V1-V6 + N2; the math core is unchanged)

- Author: claude-opus-5-5, session <SESSION_ID> (`/root/opus_implementation`).
- Base: `../verifier` (pins bac7f440) is preserved byte-unchanged. Round-1 verdict 735ad63f: CHANGES_REQUIRED
  V1-V6, with P-b decided as `numpy_pairwise`.
- Synthetic fixtures only. No report, per-event, label or prediction byte has been read. No run, no job.

## Deltas (each with tests and a mutation control)

| Item | Change |
|---|---|
| P-b | `run_verify.SAMPLE_SUM = 'numpy_pairwise'`. `--sample-sum` accepts only that value, and the CLI refuses any other. `verify_r1.bootstrap` keeps both modes for the tests. |
| V1 | `secondary_verify`. For each primary: the record set equals the seal's secondary groups; the subsets are {built, v6_other}; identity (cells in seal order, primary_reused, population `transfer_all_2025_secondary`, events 8399) is exact. Unavailable means `failed_cells` equals exactly the cells missing from `per_event_sha256`. Scored means: the union of rows is 8399 unique ids; its population_sha256 equals the subsets' `secondary_population_sha256`; the metric key set (jaccard/smape_2h only when every row defines them) matches; means pass under V1. Driver L403-428. |
| V2 | The `history_median` arm is present at R1 (arm spec 9a6d36e8), so `analysis_families` recomputes `history_median_vs_mean_jaccard` per horizon: mean/median extent Jaccard (fsum means), `median_minus_mean` (median vs online_history, all-row blocks, p), and `c2_c5_jaccard_against_median_history` with C2 only. `descriptive_only` is true. The median arms join the slice-agreement set, as in `_contrast_families(median=True)`. |
| V3 | `eligibility.abstentions` holds `abstention_counts` per arm and per training seed for every derived arm: the `no_input` / `technical_failure` counts plus `eligible_abstentions`. Compared exactly. |
| V4 | `extent_recompute(…, seal_cells)`: the key set equals every seal cell. Exact: per-metric denominators, `complete_input_available_events`, `complete_input_quantile_events`, `available_forecasts`, `quantile_calibration_events`, `status`, `calibration_status`. V1: means and `complete_input_curve_cover80`. Each reliability report: status, reference/available/probability events, zero-candidate, contributing, candidate_nonseeds, new_targets, outside_candidate_targets, and bin lower/upper/upper_inclusive/counts exact, float sums V1 (driver L357-401: `forecast_available` defaults true, `partial_panel_input` filtered). Cells already failed at B2 are skipped, not double-counted. |
| V5 | Unavailable retrospective-14 records carry and compare the evaluator's exact failure objects, `{arm, expected_seeds, retained_seeds}` or `{arm, unavailable_cells}`, plus `events`. |
| V6 | `run_verify`: `--complete-sha256` is mandatory and checked before parsing. The predicate: `passed`, spec 95ee898d, retry false, exact report path, 64-hex report sha. The per-event dir must be a real directory, and every entry is read through one `O_NOFOLLOW` descriptor and must be a regular file. |
| N2 | Every family's `family_wise_alpha` must equal the spec's alpha. |

## Tests

| Suite | Result |
|---|---|
| `test_verify.py` | 76 passed (53 + 23) |
| `ruff check` | pass |

**New tests:**
- **Oracle-backed** (the staged driver's own `extent_calibration_report` and `secondary_report`, test-only):
  - V4 agrees on every counter;
  - a scored and an unavailable secondary record agree.
- **V1, V4, V5 refusals:**
  - V4: 9 changed counters;
  - V1: 5 secondary disagreements (population, mean, metric key set, events, failed cells);
  - V5: exact failure records.
- **V2, V3, N2:** the families test's arms now include `history_median`, and it matches the oracle evaluator.
  Disagreement cases cover a median interval, a median mean, an abstention count and the family alpha.
- **V6:** the complete anchor and its 4 predicate refusals; a symlinked dir and a symlinked entry refuse.

**`mutation_controls.py`:** all 20 detected. The 12 round-1 controls are unchanged, re-run against r2.

| New mutation | Targeted tests |
|---|---|
| V1 union population unchecked | 1 failed |
| V2 median family not compared | 2 failed |
| V3 abstentions not recomputed | 1 failed |
| V4 complete-input filter dropped | 1 failed |
| V5 failures compared by arm only | 1 failed |
| V6 complete.json anchor dropped | 1 failed |
| V6 per-event `O_NOFOLLOW` dropped | 1 failed |
| N2 family alpha unchecked | 1 failed |

## Unchanged and still pending

- Unchanged: the math core accepted in round 1; independence (stdlib + numpy only); rule V1; numpy 2.5.2.
- **Adapter binding:** the class (d) adapter (`../adapter`, pins a42c8918, under review) loads `../verifier`
  (bac7f440). It uses only round-1-accepted functions (`rescore_event`, `compare_event`, `derive_arms`,
  `retro14_groups`, `Findings`), which r2 leaves byte-for-byte unchanged in behaviour. Rebinding it to `verifier-r2`
  is a one-constant change, made only after this round is reviewed.
- **P1:** the pre-planned claims beyond the 66 cells.
