# Independent review request: release resource integration v3

Author /root. Reviewer /root/recovery_independent_review, separate session; same model permitted. Root pauses implementation while review runs. Code/synthetic scope only; no actual scientific reads, staging, execution, freeze, seal or scoring.

Preserves v2, extends its driver with three exact previously reviewed helper copies. New code derives metric+analysis/report requirements from the already verified result, checks contract minimums plus explicit positive filesystem reserve and16MiB auxiliary evidence reserve BEFORE process memory snapshot and the one-time label marker. Runtime admission must list/hash all three helpers, actual runtime and executable. Contract requires exact diagnostic caps. Diagnostics now persist at most16 code frames,512 filename chars,128 function/type chars,signed64bit lines, without formatting messages or reading source lines/locals. CLI suppresses value-bearing tracebacks; argparse SystemExit behavior remains. Existing scorer/model/scientific rules unchanged. Old error_type in outer failure is normalized to exception_type.

Actual resource certificate and execution authority remain absent. Header audit output will not by itself prove a target resident bound: trusted producer/layout, clone/cast/scorer/native allocations must still be admitted. R1closed/Nunsealed/protected2026 untouched.

Review exact source-pins.json and diff v2/forecast_retrospective_release.py against v3. Validate helpers exactly match r1-metric-bounds-20261020/{bounds.py,aggregate.py,analysis_overhead.py}. Prior reviews are there; do not self-approve source inherited from the author.

Root tests:40 component/resource tests PASS;81 inherited synthetic release tests PASS; Ruff all edited/new implementation/helper/test harness files PASS. Commands:
`.venv/bin/python -m pytest -q .agents/operations/r1-release-memory-20261020/v3/test_resources.py .agents/operations/r1-release-memory-20261020/v3/test_components.py`
`.venv/bin/python .agents/operations/r1-release-memory-20261020/v3/run_inherited_tests.py`

Harness copies canonical source/tests to a temporary tree, installs exact candidate/helper copies, adds only synthetic contracts/limits. One previous assertion intentionally changed: expect bounded type/frames instead of persisting scorer exception message. New tests include pre-marker underbudget refusals with no scorer calls, component-before-memory-snapshot order, preserved single-open behavior, outer failure no private value, missing/helper-drift rejection and hostile-message/long-Unicode/deep-stack diagnostic bounds. Process hard limits are simulated in synthetic tests only.

Please write reviews/astra-release-memory-v3-review.txt and a hash-bound code-only verdict JSON, naming actual model/session and explicitly denying execution/label/scoring authority. Do not author fixes, do not launch, and do not delegate.
