# REVIEW-VERDICT: q35-origin-g2-parallel (independent final review, 2026-10-28)

Verdict: CHANGES (documentation/gate-spec only; no code defect found, no edit to any deliverable file by the reviewer)

## Verified with evidence
1. Re-diff of pinned runner (newperiod-origin-inference-r2-retain-20261027/runner.py, sha af8c03eb979851a7...8bbd88, confirmed by sha256sum)
   against successor/runner.py: `diff` shows exactly two hunks: line 6 (edit A, HERE) and +7 lines after 112 (insert B). Nothing else.
2. REPORT section 2 shas match sha256sum: runner.py 5219c868..., parallel_infer.py e900b077..., equiv_run.py 7c8223b8... (all equal). Insert B pins e900b077 (runner.py:116).
3. Tests re-run from /tmp with repo .venv, PYTHONPATH=src, -B: test_guards.py = 11 passed (4.15 s); e1_threads.py (threads 1,2,4, 8 events) = E1_PASS_threads_1_ok.
4. Equivalence argument holds in code: p.access is the same bound log module whose log_read the extracted pinned custody_load uses
   (reviewed_runner.py:87-91), so the single manifest log line is identical; _loader repeats forecast_inputs.py:260-301 checks and
   messages statement for statement (parallel_infer.py:_loader); per-event chain = normalized -> transform_events(mu/sd from checkpoint,
   no cohort statistics, forecast_train.py:243-260) -> prediction_rows, a pure function of (event, checkpoint); pool.map is ordered and
   assemble_rows sorts by event_id (reviewed_baseline.py:229), so merge order cannot change bytes; rows/abstentions pickle exactly
   (floats, lists). Status rows and tensor rows are routed to the same lists as the reference. No RNG, no shared mutable state
   (model built per worker, _STATE read-only after fork). Any worker exception re-raises in the parent -> pinned generic handler -> arm
   fails (runner.py run(): FamilyFailure), nothing is dropped.

## Findings
RISK-1 (E3 gate mis-specified for threads): the pinned reference runs with OMP/MKL/OPENBLAS/POLARS threads == plan cpus (enforced
reviewed_runner.py:67-69; valid arms 8 cpus). REPORT section 5 runs E3 on a 16cpu task and does not set those env vars, so the E3
reference side runs at an unspecified thread count (torch default, likely 16), not the production 8. "passed" would then prove
threads=1 == default-threads, not threads=1 == production. Fix: export OMP_NUM_THREADS=MKL_NUM_THREADS=OPENBLAS_NUM_THREADS=POLARS_MAX_THREADS=8
(valid arm cpus) in the E3 command (ideally also run once at the invalid arm's own cpus) and have equiv_run print torch.get_num_threads()
and refuse if it differs from a required --reference-threads. Also the claim "E3 re-runs E1-real implicitly ... reference at env threads"
(REPORT section 5 end) is only true after this fix.
RISK-2 (hung pool on worker death): multiprocessing.Pool.map hangs if a worker is SIGKILLed (OOM, node kill); the pool respawns the process
but the task is lost. Not silent: the parent's SIGALRM wall bound (runner.py run()) ends it as a stage failure, but only after the full wall.
Fix: use imap with a watchdog on worker pids, or concurrent.futures.ProcessPoolExecutor (BrokenProcessPool); at minimum document it.
RISK-3 (fork-after-torch): parent has run torch (checkpoint load, contract checks) before fork; pytest itself emits the
"multi-threaded, fork may deadlock" warning. threads=1 children never open an OpenMP region, so this is consistent with tests, but only E3 on the
real arm venv proves it; keep E3 gate mandatory (already F1).
RISK-4 (E3 coverage): equiv_run production mode calls m.original_loader directly with the predictor-module p (not the runner's bound
modules/wrapper), so the pinned byte-budget wrapper and bound access module are exercised only by the guard tests, not E3. Acceptable, but
the first valid arm should be checked against a pinned-runner arm of the same horizon if any exists, or at least the access log line set.
RISK-5 (F3 label): forward-side errors report stage 'inputs' instead of 'inference' (accepted, documented; operational text only).
NIT-1: REPORT section 6 queue text says "guards 10/10"; sections 1/3 say 11/11 (stale).
NIT-2: E3 reference run holds ~2x export; REPORT says a 16c/250G node suffices; successor fork after ~21 GB parent residency is COW-safe but the
`del payloads, rows` freed memory may not return to the OS, so the 250G figure should carry slack (policy says over-reserve).

## Docs vs code
No false behavioural claim found beyond NIT-1 and the E3 "implicit E1-real" statement (RISK-1). README claim "workers never touch the access log"
holds (no log_read in _event); "install refuses workers>16 / threads>1 with workers>1" holds (install()). Insert-B/edit-A claim holds (diff).

## Could not verify
Real checkpoint numerics at production thread counts (E3), arm-venv torch equality, real NFS behaviour with 16 readers x 16 arms,
end-to-end through g2_exec/Slurm, that pins.json custodian source equals current scripts/custodian_newperiod_inputs.py (pins.json
schema was not parsed; _loader was compared against the current repo file, not the pinned sha).
