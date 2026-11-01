# configs24 + gru10 staging successor (opus-science, author)

Successor of `newperiod-g1b-next-steps-v1-20261026` (configs14 + gru10, preparation PASSed by
sol-g1, never run). Reasons: (1) that operator hard-codes `reviewer_worker == 'sol-g1'` (Codex
reviewers out of credits); (2) 10 baseline configs had no staging packet at all: the 6 primary
baselines and the 4 stable baselines (complete400 model_path null). One staging once instead of three.

Exact diff vs predecessor:
- operate.py: TASKS {'configs24','gru10'}; reviewer_worker 'opus-review'; reviewer_session also
  excludes 'opus-science'; self-announcement `to` 'opus-science'. Nothing else.
- worker.py: task in ('configs24','gru10'); row count 24 for configs24. Nothing else.
- gru10.plan.json: byte-identical copy.
- configs24.plan.json (from make_plan.py): the 14 reviewed rows unchanged, plus
  * 6 primary rows: same schema/encoder and original `baseline.checked_config` validator as the
    secondary 6 (baseline, candidates, k=20, frozen_at None (online), horizon_seconds);
  * 4 stable rows: exactly what the stable transport checks
    (`newperiod-stable-transport-20261023/candidate-v1/runner.py:129-130`): {role, k: 20,
    stable_peer: forecast_stable_peer.sensitivity() (reviewed module a8209bc0), frozen_at: None}.
  Local copies in configs/. Destination unchanged (g1b-configs-v1, never created).
- Templates rebound to this directory, configs14->configs24, reviewer opus-review.
- test_next.py: predecessor tests with the same renames; 24 rows, size total 4660+728+1802. 6/6 OK.

Still needs: capacity rows in the issued phase (configs24 1 MiB, gru10 1 MiB), filled requests,
opus-review execution review, root once each. Remote writes: 24 + 10 small files.
