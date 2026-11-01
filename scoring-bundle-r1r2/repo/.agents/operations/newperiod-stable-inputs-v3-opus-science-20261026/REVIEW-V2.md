# Stable inputs v2 (opus-science): one-pin successor of newperiod-stable-inputs-20261023

Defect in v1 (never run): `source_runner.py` PINS `construction/job.py` = dd8ff4b1 (the original
construction package-v3). The ACTUAL primary construction, used by the accepted T040 cohort run
(`newperiod-timing-cohort-t040-final-transport-v31-20261025/final/plan.json` primary_construction),
ships job.py 576fc514 + runtime_verifier.py, and `build.package` itself requires
`construction/runtime_verifier.py`. So v1 cannot bind the real primary construction: package-v3
lacks the verifier, and the T040 closure fails the job.py pin.

576fc514 = dd8ff4b1 + `runtime_check` (private-venv placement/verifier check, strictly stronger);
all functions the stable runner calls (c.validate, source_checks, input_checks, bounded_run) are
otherwise identical (diff checked).

Change: source_runner.py PINS['construction/job.py'] -> 576fc514. Nothing else (diff -r shows one
line). Tests: `PYTHONPATH=src .venv/bin/python -B -m pytest -q -p no:cacheprovider <dir>` 36/36.
Real package: `build.package('source', T040 control/construction, T040 primary_construction,
package-source-v1)` -> 98 files; all three runner PINS satisfied; runner.py == source_runner.py v2.
The original `common.validate` (265179ef) accepts the T040 primary_construction.
Plan output_root must be the runner's fixed ROOT .../newperiod-inputs-v1/stable-source-v1.

## Second defect: custody-log volume (fixed in the same successor)

v1 logs every admitted read-scope path individually, twice per process (checks() preflight and
worker()). The real N-stable plan (plan-v39, 18,132 events) has a 57,154-path scope. One log line
is ~520 B (`scripts/custodian_access_log.py` record incl. host/pid/user/script). Per stage task:
2 x 57,154 scope lines + ~1.9k durable source reads = ~60 MB; x 32 tasks + assembly (~55k shard
output reads) = ~2.0 GB appended to the shared access log, which is 1,499,205,784 B now (stat
~01:25Z) with a 2 GiB ceiling that must never be rotated. The stage could not run.

Fix: `scope_purpose()` + one aggregate entry per phase:
`log_read(kernel_plan_path, '<label>: N paths sha256=<sha of sorted scope list>', files=N)`.
Every actual open is still logged per file, durably (fsync log + dir), before it happens
(`operation.durable`, unchanged). Expected appends: ~32 x 1.9k + ~55.5k = ~117k lines = ~61 MB.
The scope list itself is pinned in the plan (read_scope) and its sha is in the log line.
