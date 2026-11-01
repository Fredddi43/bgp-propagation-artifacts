# B-publish-sonnet-v4-20261026 (author: sonnet) — v4: fixes H1-G1-A-PHASE-FLOOR-3 (sol-h1 v3 CHANGES)

Status: FALSE template, execution_authorized=false. Supersedes v3 (preserved). Only `run_once.py` (+ `test_runner.py`) changed vs v3; extractor/publisher, request.json (A: d28d68ba) and everything else are byte-identical. Tests: see tests.txt (all pass).

## Finding -> fix
- PHASE-FLOOR-3: with real V44 minimums (models 847577881600, results 45231374336) and the exact A request, v3 accepted 1 B free with 1 B floors because floors were caller-supplied. v4 `check_phase_and_df` (run_once.py:92 ff.) refuses caller floors below the issued phase's `models_minimum_bytes`/`results_minimum_bytes` (`R_DF_FLOOR_BELOW_PHASE`) and requires fresh free >= max(caller floor, phase minimum) + WRITE_BYTES (`R_DF_BELOW_FLOOR`; WRITE_BYTES 0 for A, 64 MiB for B); the phase's own fresh free reading must still cover its minimums (`R_PHASE_SPACE`).
- Regression: `test_PHASE_FLOOR_3_floors_must_cover_full_phase_minimums_read_fresh` (test_runner.py) was written first and FAILED on the v3 code (1 B accepted), then passes. It also covers floor 1 B under the minimum, free 1 B under, and WRITE_BYTES margin (B).
- Residual assumption: the launcher reads minima from the phase file bytes (pinned, fresh_df utc <= 30 min); the df free values are root-attested stat-only readings.
