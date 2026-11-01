# Prospective source-only staging + calibration binding refresh

Root is sole implementer and pauses during independent review. Review local
metadata/source only; no cluster calls, scientific reads, other agents or CLI.

Source-only candidate candidate-v2/candidate.json
SHA6634eee62cdf356a24bac51644f85b32e4673161de483069ed41940cfba46d90.
373 source files,375 staged files,5058831 total bytes, under fresh literal root:
<FORECAST_ROOT>/r1-release-assembly-v2-20261021

prepare_v2.py reproduces the old368-file exact source manifest48620b8e,
replacing only scripts/forecast_retrospective_release.py with v5 CODEPASS3f4eaed2,
and adding the four exact reviewed metric/analysis/forecast helpers plus the
reviewed single-pass prepare_metadata module(c42e78ac) under scripts/prepare_r1_metadata.py.
All other source hashes, consumer hashes, scientific families and input bindings
are unchanged. base-draft-pending-bindings.json remaps the three scorer source
paths and release driver hash only. Its old probability approval and absent
resource contract make it deliberately NOT a final executable retention draft.
No freeze/seal/plan/evaluate invocation is part of this request.

stage_v2.py is the previous source-only stager adapted to this exact root/package,
with mandatory exact independent approval/review hashes and stager selfhash,
source-only authority booleans, finite file/byte/disk bounds, write-once local
intent and fresh remote root, literal-path/no-symlink/path-escape checks, <USER>
ownership, closed R1 registry checks, immutable source files and hash readback,
fsync of files and directories. It never imports or executes staged code. A failed
or uncertain attempt is preserved and cannot automatically retry. Eight local
synthetic subprocess tests pass; Ruff passes. Host/root/account substitutions
are explicit in those tests; actual byte, manifest, closure and once-only guards
run unchanged. Runtime capture/imports will be a later separate action; this
approval grants no consumer execution or actual scientific-data access.

At19:27UTC root was absent; the destination filesystem had517216403456 free bytes.
The existing full opaque pass remains running, unrelated to source-only staging;
its result is NOT required to copy reviewed code, but is required for final release.

Please write reviews/astra-source-v2-review.txt and reviews/astra-source-v2-approval.json
with exact scope r1-source-only-staging-v2 and the required expected fields in
stage_v2.py. A favorable review may authorize ONLY this one staging attempt;
all consumer execution, labels, scoring, freeze, seal and retries remain false.

Also separately refresh the probability reliability implementation approval to
v5 driver3f4eaed2 if its scientific implementation remains unchanged. The prior
independent approval is candidate-v1/calibration-approval.json, scope
r1-probability-reliability-v1, prior decisiond359941f and scorer740bf610.
Write reviews/astra-v5-calibration-approval.json with exact same decision/scorer,
newdriver, revieweridentity, priorapprovalsha, newreviewtextsha, passedtrue only
if verified; test_outcomes_usedfalse and all execution/fit/calibration/label/
scoring/freeze/seal/N/protected/retry authority false. This is source-binding
refresh, not approval of actual calibration or results. Root will use the exact
receipt later when constructing the final draft.
