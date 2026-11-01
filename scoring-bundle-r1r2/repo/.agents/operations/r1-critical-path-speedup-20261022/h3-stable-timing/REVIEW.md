# Local synthetic timings: H3 and stable paths (reviewer s0b-budget-assessment §4 (i)/(ii))

- Author: claude-opus-5-5, session <SESSION_ID>.
- LOCAL only, synthetic rows, no real payload, label or tensor.
- **The exact functions are called:**
  - pre-label: the CODEPASS O1 driver's `payload_checks` (33011eed), plain and under `tracemalloc.start(1)` as the
    validation loop runs it. For H3 that is `check_forecast_rows` + `aligned_rows`; for stable, `complete_rows` +
    `check_forecast_rows`.
  - post-label: `json.loads` + the staged `aligned_rows` / `score_panel` (H3) and `score_stable` (stable).
- **Shapes come from metadata only:**
  - 3543 events;
  - 900 / 1800 / 3600 candidates, reaching the real maxima (H3 ≤ 450.5 MB, stable ≤ 378.8 MB, from
    `prediction-sizes.json`);
  - H3 learned (probabilities + cummax curves) and history (integer counts + extent, typed history binding);
  - stable `sage_on` / `online_history` / `persistence` with 24 certified abstentions.
- **One test-only seam:** `custody.bound_verifier` returns the staged stable verifier module (the real loader reads
  it from the verified byte cache).
- Thread variables were set to 1.

## Results (MB/s locally; `timings.jsonl`, `timings-repeat-900.jsonl`)

| Path | Candidates | Pre-label plain | Pre-label traced | Post-label |
|---|---|---|---|---|
| H3 learned | 900 / 1800 / 3600 | 5.63 / 18.24 / 20.28 | **2.23** / 7.25 / 8.01 | 7.98 / 9.65 / 11.01 |
| H3 history | 900 / 1800 / 3600 | 14.19 / 13.44 / 15.11 | 4.62 / 4.72 / 4.97 | 15.69 / 16.88 / 17.96 |
| stable sage_on | 900 / 1800 / 3600 | 12.78 / 12.48 / 12.06 | 3.30 / 3.23 / 3.15 | 9.62 / 10.21 / 9.50 |
| stable online_history | 900 / 1800 / 3600 | 8.68 / 11.08 / 11.35 | **1.80** / 2.14 / 2.21 | 20.51 / 29.29 / 31.60 |
| stable persistence | 900 / 1800 / 3600 | 66.69 / 58.72 / 56.75 | 17.09 / 16.23 / 15.98 | 62.93 / 73.25 / 81.74 |

**Repeat of the 900 size:**
- H3 learned traced 7.56 MB/s: the first-call 2.23 was a warm-up and did not reproduce.
- Every other value repeats within about 10%; online_history traced was 1.94.
- Budget r4 nevertheless takes the SLOWEST per byte over both runs, and reports the warm-up as a sensitivity only.

**Comparison:**
- S0b's local plain-row traced rate was 8.2-10.7 MB/s.
- H3 learned at 1800-3600 candidates is about 0.8× of it (7.25-8.01 MB/s).
- H3 history is about 0.5× of it. `aligned_rows` and history-extent validation make it slower.
- Stable online_history is about 0.2×. `complete_rows` re-validates every row inside `payload_checks`.

These per-byte costs are what the reviewer asked to measure. They feed `budget-r4` through the 0.45 host floor.
