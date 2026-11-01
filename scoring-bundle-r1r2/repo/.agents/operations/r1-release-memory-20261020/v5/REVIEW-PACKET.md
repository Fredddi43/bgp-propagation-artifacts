# Release resource v5: forecast workspace and Polars branch guards

Author /root; independent sequential review requested. Root pauses implementation
while reviewer works. Synthetic/local source only; no actual targets or forecasts,
cluster calls, staging, freeze/seal, scoring, N/protected2026 or delegation.

Parent v4 driver651a3795cca41fb75f0eb63bada05897075bcb88d244bfbf6e2418e19b0a8390
has separate CODEPASS. This candidate preserves its query, scientific calculations,
cardinality observation paths, resource admission and one-time label barrier.
The reviewed metric/analysis helpers are byte-identical. Fourth helper
forecast_workspace_resources.py is an exact copy of reviewed forecast_workspace.py,
SHA df3663d125bf5a4591302b9eb514ec1ac40d01f4437eb06dbe52e74cc4a411fc.

Changes:
* Runtime admission now requires the Polars settings snapshot to equal the live
  `polars_resource_settings()` result both before mandatory forecast validation
  and again before labels. Enforces version1.44.1, actualthreads1 and
  POLARS_MAX_THREADS="1"; excludes all engine-affinity/force-streaming/auto-streaming/
  decode-target env overrides and engine-object overrides; resolvedauto/in-memory;
  inspects the actual collect default's projection/predicate flags. Flags are not
  overwritten or repaired. Exact runtime file checks remain mandatory.
* Fourth helper must be in runtime implementation closure. After all mandatory
  validation, observation formats/counts must cover every committed cell; H3
  alignment observations must cover exactly every H3-payload cell. No new decode.
* `check_release_resources` derives forecast workspace from those observations
  before the process snapshot, adds it once to both virtual and RSS prospective
  bounds, and records the component and original observation chains. Graph/label,
  metric/analysis, allocator, host and disk terms remain independent.

Review the diff against v4 and tests. Focused suite74PASS and inherited81PASS,
Ruff PASS. Existing synthetic fixtures mock only the new installed-runtime check
because the local test environment differs from the cluster; dedicated injected
module tests exercise every guard branch. The real cluster settings smoke executes
only the exact extracted guard function against installed libraries, with an
8GiB/120CPU bound and scientific-data-root audit denial. It runs no query and
provides no resource/execution admission. Its source/result are pinned here.

Independent source coefficient evidence resides in target-resource-proof:
allocation firstreviewf279011b + closure773d190c. Actual target/NPZ/Parquet terms
are supported conditionally; final exact input-bound label certificate/runtime
manifest/contract are not authored or admitted by this v5 code review. Source
closure will need the final staged helper paths and exact runtime hashes. No
production files are replaced, and the actual release remains closed.

Please save reviews/astra-release-memory-v5-review.txt and a hash-bound verdict.
Do not infer resource admission or execution authority from CODEPASS.
