# Sequential independent review: count-only forecast resource measurements

Author /root; reviewer /root/recovery_independent_review, distinct agent/session.
Root pauses implementation during review. Review only local code and synthetic tests;
no delegation, actual scientific reads, cluster changes, staging or execution.

This isolated candidate extends independently reviewed v3 with count-only measurements
needed for finding B4 in r1-target-resource-proof-20261020. It does not yet derive or
approve a scorer allocation budget. R1 remains closed, N unsealed, protected2026 untouched.

Diff v3/forecast_retrospective_release.py against v4. During the existing mandatory
pre-marker payload validation, count lengths of candidates, ranking scores, probabilities,
seeds, input seeds, predicted sets, and curve axes. For H3, observe the already required
aligned_rows result before it is discarded. No second decode or input-file scan is added.
Keep per-format maxima across cells and a deterministic chain bound to each cell ID,
prediction SHA, payload kind and exact counts in validation order. These observations
contain no event IDs, ASN values, predictions or labels. Existing memory measurements
now include the counting/chain temporaries. Post-marker calls keep the observer disabled.
The outer verified result/resource identity supplies the input context; the chain alone
is not a stand-alone input admission.

All three resource helper copies are unchanged from v3. Canonical production code is
unchanged. Actual resource certificates, runtime admission, deployment and label/scoring
authority remain absent. The independent target-resource review remains INCOMPLETE.

Validation commands:

- `.venv/bin/python -m pytest -q .agents/operations/r1-release-memory-20261020/v4/test_resources.py .agents/operations/r1-release-memory-20261020/v4/test_components.py .agents/operations/r1-release-memory-20261020/v4/test_cardinalities.py`
- `.venv/bin/python .agents/operations/r1-release-memory-20261020/v4/run_inherited_tests.py`
- `.venv/bin/ruff check .agents/operations/r1-release-memory-20261020/v4`

First run: 54 focused tests and 81 inherited tests passed. Added inherited integration
assertions check all 19 synthetic committed cells contribute counts/chains before scoring.
An initial assertion incorrectly assumed this fixture included H3 and failed with a
KeyError; removed that assumption. H3's actual observer path is covered separately with
synthetic aligned rows, including enlarged input_seed_asns and exactly one alignment.
Final rerun is recorded in inherited-tests.txt.

Please independently check correctness, maxima/lifetimes, no scientific behavior change,
no omitted count fields used by scorers, and tests. Write reviews/astra-release-memory-v4-review.txt
and a source-pin-bound code-only verdict JSON identifying actual model/session. Do not
author fixes or grant resource/execution/label/scoring admission.
