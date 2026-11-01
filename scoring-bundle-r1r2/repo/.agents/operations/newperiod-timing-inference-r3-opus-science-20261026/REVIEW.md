# N-timing inference r3: F2 one-pin successor (opus-science)

Successor of newperiod-timing-inference-r2-20261023 (unchanged; PASS_CODE_ONLY in
codex-takeover-20261023/timing-inference-r2-independent-review.json). Assigned by ROOT-DECISIONS-TIMING-ORIGIN-0225 (F2).

Problem: r2 `checked_fit` requires `FIT_RUNNER_SHA == 6379ba41…` (runner.py:101,237), the v1 timing fit run_package
(newperiod-timing-client-20261023). Every staged timing development package ships fit run_package r2 `bded5e0e…`
(newperiod-timing-client-r2-20261024/policy-candidate, development-launch actual-candidate-v1/v2, development-budget-r2).
r2 inference would refuse every fit produced by those packages.

v1 -> r2 fit run_package diff is one line (run_package.py:185): the embedded guard-closure sha c254ecd2… -> 94f2e755…
(the reviewed horizon-tuple change to forecast_manifest._base, see newperiod-timing-client-r2-20261024/REVIEW.md).
The scientific source closure digest that checked_fit also requires (3e853133…) is the same in all three staged
package.json files.

Change:
- runner.py:237 `FIT_RUNNER_SHA` -> `bded5e0e5f2cd84eedcab46079d3bfad5a95f1f606c3f807edab36d5facbdcaa`. Nothing else.
- test_runner.py: the two fit fixtures (`fit_world`, `test_actual_timing_namespace_is_fixed`) load
  newperiod-timing-client-r2-20261024/policy-candidate instead of the v1 client. 45 passed (tests.txt).
- pins.json, reviewed_helpers.py, reviewed_runner.py byte-identical to r2. review-ready.json has the same schema as r2,
  with author opus-science.

Transport cascade: the learned transport generator (newperiod-sensitivity-transport-r2-20261023/build.py, unchanged)
takes the producer dir + review-ready ref as arguments. transport-timing-candidate/ is its `generate('timing', r3, ready)`
output. Against transport-r2/timing-candidate the only differences are RUNNER_SHA in bootstrap.py and client.py
(31dd8011 -> df758f8c = sha of the r3 runner.py) and the runner.py line above. transport-check/ runs the transport's
own test_build.py with the timing producer pointed at r3 (only HERE and the producer path change): 36 passed.

Retention: newperiod-complete-retention-20261024 pins the r2 runner.py file, and only exec's its role_key/timing_arms
functions. Those are identical in r3, and the r2 file stays unchanged, so retention is unaffected.

Not covered here: the 40 fits themselves, the protected timing cohort review (T040 eligibility semantics), resources and
release. This is code only.
