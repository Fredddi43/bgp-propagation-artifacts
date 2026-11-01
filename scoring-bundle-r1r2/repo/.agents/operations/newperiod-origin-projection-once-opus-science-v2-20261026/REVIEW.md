# Origin projection once v2 (opus-science)

Successor of v1 (newperiod-origin-projection-once-opus-science-v1-20261026, consumed). v1 ran once at 04:55:12Z: rc 250,
stdout 0 B. stderr: a polars-async panic `Os code 11 WouldBlock`, then `memory allocation of 1024 bytes failed`. The
remote custody output dir `data-custodian/newperiod-origin-projection-v1` is ABSENT (stat-only check 2026-10-26), so
nothing was written.

Cause: v1's worker set `os.environ['POLARS_MAX_THREADS']='1'` AFTER `import polars`. polars sizes its pool at import,
so the pool was nproc = 128 on <BATCH_HOST>. Spawning 128 threads under the supervisor's RLIMIT_AS 8 GiB exhausted
the address space. Shown locally with polars 1.44.1, the remote version:
- `POLARS_MAX_THREADS=128` under RLIMIT_AS 8 GiB: `memory allocation of 1520 bytes failed` (same failure).
- `POLARS_MAX_THREADS=4`: 2,000,000-row parquet read + to_dicts OK, maxrss ~1.0-1.2 GB.
- Setting the env after import leaves `thread_pool_size()` at nproc (16 locally), confirming the v1 bug.

Changes (diffs: prepare.v1-v2.diff, once_operator.v1-v2.diff). projection.py and test_projection.py are byte-identical
to v1 (v1C source PASS).
- prepare.py SUPERVISOR: the worker child is started with `env=dict(os.environ, POLARS_MAX_THREADS='4')`, so polars sees
  it before it loads. RLIMIT_AS (8 GiB) and FSIZE (512 MiB) are unchanged.
- prepare.py WORKER_MAIN: refuses unless `POLARS_MAX_THREADS == request.runtime.polars_threads (4)` before import and
  `polars.thread_pool_size() == 4` after it. The ineffective late assignment is removed. The request carries
  `runtime.polars_threads: 4`.
- proof/proof_supervisor_threads.py runs a synthetic 2M-row probe through the EXACT v2 SUPERVISOR string with polars
  1.44.1, with an inherited `POLARS_MAX_THREADS=128`: pool 4, RLIMIT_AS 8 GiB, rows 2,000,000, rc 0 (proof/proof.out).
- once_operator.py: authority kind `ROOT_ONCE_ORIGIN_PROJECTION_V2` (a v1 authority is refused). The phase goes through the
  reviewed phase_compat v2 (b84be518) with own lane `origin_projection`: a newer issued phase may add or change other
  lanes' rows but never this row. After the consumption mkdir and before the transport, a stat-only remote statvfs check
  requires models free >= NEWEST models floor + 512 MiB and results free >= NEWEST results floor, recorded in
  df-preflight.json. `root_current_phase_acknowledged` is dropped.
- Request regenerated on v42 (a8fb3c53; origin_projection earmark 512 MiB unchanged). Custody output dir unchanged
  (`newperiod-origin-projection-v1`, absent), matching the earmark scope text.

Tests: test_projection 12 PASS (unchanged); test_operator 9 PASS (adds: newer phase adding another row accepted with
the newest floor, newer phase changing the origin row refused, v1 kind refused). Consumer dry run
(newperiod-origin-projection-exec-request-opus-science-v2-20261026): the real once_operator.check() passes against the
real ops dir. Newest phase = v42, models floor 735423241216.
