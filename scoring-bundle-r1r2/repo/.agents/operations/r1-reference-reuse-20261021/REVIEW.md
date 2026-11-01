# H3 reference-baseline reuse: narrow batch-custody correction

Author: /root. Request independent code review only. The ongoing diagnostic is
unchanged and uses staged source2180791d8f23d41ee4e70e06de242e4a52161b2c5ebe9106b9494ea81d20826b.
No new production staging, preparation, R1 opening or scoring is authorized here.

Existing exact metadata captures demonstrate eight H3 reference baseline entries
sharing prediction paths with their retained R-base originals (two estimators,
two candidate policies, two horizons). Evidence is in
../r1-failure-diagnostic-20261021/shared-path-evidence.json, SHA256
d30fc61078ba23336fcafe9015cfb25598b9a76efb69152c30e575fc61f0ca01.
The unchanged batch condition rejects these with ValueError after the per-family
passes. This is a proven deterministic blocker in the actual frozen draft, not yet
a claim that the previous opaque terminal failure reached precisely this line.
The live diagnostic will resolve whether an earlier blocker also exists.

Changes:
- H3 history adapter retains its already verified original baseline commitment ref.
- Before stripping large side metadata, a batch helper binds each reference H3
  baseline to exactly one committed R-base original by canonical commitment path
  and hash, and checks estimator/policy/horizon, forecast path+hash, manifest/gate
  paths+hashes, source/input/population/cohort, and complete event IDs.
- Only those verified forecast-path reuses are exempt from uniqueness. Commitment
  paths stay unique; a parent cannot have multiple H3 references; unverified
  prediction_reuse_of declarations refuse. All other duplicate paths refuse.
- prediction_reuse_of is an audit field, NOT alias_of. Both cells, H3 contexts,
  distinct scorers, and metric computation remain. Existing panelfix aliases stay
  unchanged. No retraining, regenerated predictions, calibration or outcome reads.

Validation: 163 tests pass across reference-reuse, retrospective-release and
history-adapter suites. Ruff passes. Synthetic regression reproduces the former
shared-path condition for both policies and checks byte/provenance/role/cohort
mutation, missing/failed/duplicate original, double reuse, unreviewed reuse field,
shared envelope path, accidental duplicates and existing panelfix behavior.

Please review scientific semantics as well as fail-closed behavior, inspect the
actual metadata evidence, run the focused tests, and return concrete findings or
CODE PASS. Write review and verdict under this directory. Record actual model and
separate reviewer session and exact hashes. Do not author fixes, spawn workers,
read remote payloads, launch jobs or contact anyone. Owner pauses while you review.
A code pass still requires refreshed source/runtime/resource/draft and independent
execution bindings before any future actual recovery; old attempts stay preserved.
