# R1 v11 bounded-resource recovery candidate

Local only; no staging, submission, release or scientific execution is authorized by this readiness. Independent actual records remain required.

The exact v10 source closure is retained except `src/bgbench/forecast_metric_bounds.py`, whose independently approved mapping-key JSON serialization bound uses the actual known key. Scientific driver, numerical kernels, unknown string value bounds, resident-memory bounds, all 1156 retained cells (1066 committed and 90 failures), calibration choices, 64 scoring lanes and full fresh verification remain unchanged. The previous 64 v10 workers are terminal with independently reviewed prelabel cleanup evidence.

New namespace is r1-release-parallel-v11-20261024/control-v1. Parent remains 33 CPUs/1536 GiB/24h; 32 validation workers retain 24 GiB each, and 64 scoring workers retain 1 CPU/640 GiB/24h on partition cpu. No node pin, requeue, stop operation or automatic retry is added.

The exact reviewed metadata preflight (actual capture 5d50d883) bounds corrected combined output at 369034448816 bytes (343.690 GiB), including component output plus the 64 GiB floor, task envelopes, result transport and controls. The original unchanged distributed_scoring.py computes required from the component minimum plus these transport terms, then compares that sum against output_required_bytes. It does not add transport to the configured allowance. Thus output_required_bytes=384 GiB covers the whole R1 write envelope and its floor once. Maximum reply 135879236 bytes fits the unchanged 256 MiB transport cap; maximum task IPC 670071601 fits 2 GiB; analysis upper 27.303 GiB fits 256 GiB.

Before expensive verification, the operational memory_guard now requires fresh free storage of 384 GiB R1 +128 GiB future replay +1 GiB history =513 GiB. No second 64 GiB floor is added. The former archive and source acquisition future-write reservations are retired only because actual independently reviewed jobs are terminal; their retained bytes remain included in fresh df. Future Aug31 acquisition is not launched or authorized here.

Derivation reuses the exact original reviewed metadata derivation. Calibration/resource/retention/recovery/R1 execution records must be supplied by separate reviewers; the author does not mint them. Actual final spec/ledger and launch approval are acyclic later bindings. No metadata preflight is represented as payload validation; fresh full verification remains mandatory.

Local verification: 45 tests pass (1.28s), including exact source/runtime/cell retention and the fresh 513 GiB admission boundary. No host calls in these tests.
