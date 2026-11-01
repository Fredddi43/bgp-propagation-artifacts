# Origin S3 boundary source v2 (author: Sonnet; local only, not authority)

Copy of `newperiod-origin-s3-boundary-source-astra-v1-20261026` (untouched). Reason: W21 refusal; dry run on <BATCH_HOST> showed the valid family has 136,833 rows per horizon
(events 136,832 + excluded 1 + source_failures 0) while `boundaries.py:28` (`sum(...)<=MAX_ROWS`) allowed 100,000, so W22 would follow the screen's W21.

## Delta (only thing to re-check)
- `boundaries.py:11` `MAX_ROWS=100000` -> `MAX_ROWS=262144`. It is used at line 23 (unknown-id count) and line 28 (rows per family, horizon-30 reference manifest). No other line changed (`diff` vs v1).
- Justification: 262144 = 2^18; 1.92x the measured max (136,833; margin 125,311), 2.72x the measured unknown-id count (96,399; margin 165,745). The bound is only a fail-closed shape limit; rows are never dropped.
- Output caps are NOT changed and stay independently enforced (`FILE_BYTES` 128MiB line 12, `TOTAL_BYTES` 256MiB line 13). Measured real outputs 7,923,294 B total (invalid 3,623,278 x2, valid 338,369 x2).
- `test_boundaries.py`: appended `test_max_rows_value_and_exact_boundary` (value is 262144; bound == max rows passes, bound-1 refuses; unknown ids one over refuses). Other tests byte-identical to v1.
- Tests: `PYTHONPATH=src .venv/bin/python -B -m pytest -q -p no:cacheprovider <dir>/test_boundaries.py` -> 13 passed (12 old + 1).

## Codex sol-g1 must check
`diff` v1 vs v2 of boundaries.py is exactly one line; the new test's boundary logic; that the old accepted boundary review (v1 hash) does not transfer and a fresh acceptance bound to the v2 sha is needed. Remaining worst case: at 262144 rows per family the 128MiB file cap would refuse before any bound is exceeded (see workspace v2 REVIEW), fail-closed.
