# Budget r4: the reviewer's limit structure, every term evidence-labelled (O1 driver; no limit approved)

- Author: claude-opus-5-5, session <SESSION_ID>.
- Implements `s0b-budget-assessment.txt` §5 exactly: `wall = ceil(1.25 × Σ high-side terms)`, CPU = 4 × wall,
  supervisor = wall + 300 s, render cap 168 h.
- Inputs are pinned by sha:
  - S0b host result 9bfd31cc;
  - prediction sizes c6ab8325;
  - diagnosis sample-2 bc23b852 (read_bytes);
  - live observations fb9eaab2;
  - budget-r3.json 1c6c04e8;
  - `h3-stable-timing` timings 6d32236e and its repeat e9a0766c.

| Term | High (h) | Kind | Basis |
|---|---|---|---|
| membership scoring | 25.77 | measured_local × floor | r2 local 0.0951 s/payload MB over ALL bytes / 0.45 (also covers H3/stable bytes: deliberate double count) |
| pre-label H3 | 25.36 | measured_local × floor | 91.63 GB × slowest local traced `payload_checks` (first-call 2.23 MB/s) / 0.45 |
| pre-label generic | 16.18 | measured_host | 339.16 GB at the slowest S0b host traced rate 5.82 MB/s |
| post-label H3 | 7.08 | measured_local × floor | `json.loads` + `aligned_rows` + `score_panel` |
| re-verify | 4.13 | measured_host | v7 eval verify + 10% |
| cold I/O | 3.32 | metadata_bound | 328.7 GB on disk × 44/42 at the v7 read_bytes rate 28.78 MB/s (389.08 GB / 3.755 h); every read uncached |
| pre-label stable | 2.78 | measured_local × floor | 8.10 GB, slowest `complete_rows` path (online_history 1.80 MB/s) |
| object build | 2.40 | reviewer_bound | ASSUMPTION per the reviewer (json.loads × 3.7 alloc/byte) |
| post-label decode generic | 2.00 | measured_host | O1 `json.loads` at 47.1 MB/s |
| post-label stable | 0.54 | measured_local × floor | `json.loads` + `score_stable` |
| materialization | 0.30 | reviewer_bound | `torch.load` of ~3.29 TB at ≥ 3 GB/s |
| analysis | 0.21 | measured_host | 10000 repetitions |
| **Σ high** | **90.08** | | |

**Derived for review (not approved):**
- **wall 113 h** (406,800 s), **CPU 452 h** (1,627,200 s), supervisor 407,100 s;
- inside the 168 h cap.

**Sensitivity:** without the primary run's first-call warm-up (the repeat measured 7.56 MB/s), pre-label H3 is 13.19 h,
Σ high 77.90 h and wall 98 h. The derived limit above deliberately keeps the slower figure.

**Not guaranteed:**
- `object_build` is an assumption;
- cold I/O uses the observed v7 storage rate;
- local timings use synthetic rows at metadata shapes.

**Unchanged:** the resource contract values and the pre-label memory gate; one attempt; 1066/90; tolerances; analysis
constants.

**Tests:** `test_budget_r4.py`, 2 passed (exact regeneration; formula, cap and CPU = 4 × wall; labels; the byte split
sums to the total). ruff clean.
