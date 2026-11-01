# REVIEW-VERDICT: q34-origin-par-infer (independent review, 2026-10-28)

Verdict: CHANGES (2 BLOCKER, 3 RISK, 2 NIT). The science argument is sound; the failure handling and the
"env unset = pinned serial" claim are not. Reviewer edited nothing except this file.

## BLOCKER
B1 Dead worker hangs the arm. reviewed_parallel.py:82-83 (`mp.get_context('fork').Pool(...).map`) and :200-201 (fused,
  same). A SIGKILLed/OOM-killed pool worker makes `Pool.map` wait forever (Pool respawns the process, the task is lost).
  Reproduced here: 3-worker fork Pool, one worker os.kill(SIGKILL), `timeout 20` -> exit 124 (hang). With a 1-day wall
  and 32 workers x ~0.5 GiB this is a realistic OOM mode, and it burns the arm's wall instead of failing promptly.
  No test kills a worker (grep of test_parallel_equivalence.py: no kill/timeout on the pool). The other candidate uses
  fork-context ProcessPoolExecutor -> BrokenProcessPool, and test_guards.py:213-228 SIGKILLs a real worker (REVIEW-VERDICT-2).
  Fix: switch both pools to ProcessPoolExecutor(mp_context=fork) + ordered `ex.map`, add a SIGKILL test; this changes
  reviewed_parallel.py so its sha (pinned in runner.py:12 diff hunk, ROOT-APPROVAL, g2templates, ORIGIN-CROSSCHECK) all move
  and the approval must be re-issued.
B2 The "env unset -> pinned serial path unchanged" claim (REPORT.md, ROOT-APPROVAL basis) is false under Slurm.
  Non-fused branch is always `par.infer` (runner diff, else-branch), not `p.infer`; `infer` defaults workers to
  `$SLURM_CPUS_PER_TASK` (reviewed_parallel.py:68-70, :160-161) and threads to 1. So with all BGBENCH_* unset inside any
  Slurm job the successor silently forks a pool. Science is still exact if determinism holds, but the approval rests on
  a false premise, and the crosscheck's "original" run only proves the pinned af8c03eb runner, never the successor's
  unset-env path. Fix: default workers to 1 unless BGBENCH_PARALLEL_WORKERS is set (drop the SLURM fallback), or make the
  successor call `p.infer` verbatim when no knob is set; and have the crosscheck run the successor unset too.

## RISK
R1 Thread determinism on real weights is not proven. bench_determinism.py:42,75 uses `torch.manual_seed(0)` random-init
  MatchedSAGE weights + synthetic graphs (1/2/4/8/16 threads, bitwise). test_parallel_equivalence.py uses a real fit but
  only synthetic graphs, and its original-vs-successor reference runs at whatever thread count the test env gives (not 8/16
  vs 1 pinned explicitly; I saw no thread assertion). Real-weights evidence therefore exists only at the ORIGIN-CROSSCHECK
  (original at plan cpus=16 vs workers threads=1, real invalid arm). Valid arms run plan cpus=32 (OMP=32 in the parent
  per reviewed_runner.py:68-69) and larger graphs; 32-vs-1 is outside the synthetic 1..16 range. index_add/scatter order
  is the only plausible source of non-bitwise difference; the crosscheck is the real gate, and it covers 16 vs 1 only.
R2 Fork-after-torch / OpenMP. Parent has run torch (checkpoint load, contract checks) before fork. Workers call
  `torch.set_num_threads(threads)` in the Pool initializer (:98-101); default 1 avoids an OpenMP parallel region, so the
  deadlock the other candidate saw at threads>1 is not hit by default. But `BGBENCH_PARALLEL_THREADS=inherit` or >1 is
  accepted without any guard (:162-163, :228-235) and would re-open that deadlock (combined with B1 = silent hang).
  Fix: reject threads != 1 when workers > 1, or fail loudly.
R3 Env mis-set cannot change science but can fail oddly or degrade silently: CUSTODY_LOAD must be exactly '1' (:105),
  any other value ('true', ' 1') silently selects the unfused path; WORKERS non-integer raises ValueError at call time
  (loud, fine); WORKERS=0 or > events is clamped (:67-71, :234). Output bytes are unaffected in all of these cases
  (rows sorted by event_id in assemble_rows, reviewed_baseline.py:229). Fix: strict parse, fail on unknown values.

## NIT
N1 ORIGIN-CROSSCHECK.md gate compares only the invalid arm at 16 cpus/16 workers; add a bounded valid-arm slice (or a
  32-vs-1 spot check) if the valid arms will run at 32 cpus.
N2 `runner.py` import change `import ast,sys,...` and exec of `reviewed_parallel.py` are fine, but the PINS/sha chain
  must be re-stamped after B1/B2 (runner cc63a91c, reviewed_parallel 1222d49e, ROOT-APPROVAL, g2templates.py:79,
  origin.json:64-65, ORIGIN-CROSSCHECK.md header).

## Verified clean (file:line)
(1) Diff vs pinned (runner-vs-pinned.diff, 5557 B): exactly 2 hunks: import line + a 4th PINS entry + exec of
  reviewed_parallel.py (hunk 1); replacement of the single `custody_load`+`infer` call site by a three-way dispatch,
  `encoded=p.validated_rows(...)` retained (hunk 2). Everything after (commitment, writes) is untouched.
(2) Purity/order/merge: `prediction_rows` (forecast_train.py:279-296) is per-event, eval + no_grad; `transform_events`
  with checkpoint mu/sd is per-event (forecast_train.py:243-260; fused refuses mu/sd None, reviewed_parallel.py:190-191).
  `_ranges` (:36-45) gives contiguous disjoint ranges in order; chunks concatenated in order; assemble_rows sorts by
  event_id and checks the available/abstention partition (reviewed_baseline.py:217-229). Fused worker (:106-135) is a
  line-for-line twin of forecast_inputs.load_inputs loop (forecast_inputs.py:285-301). Custody log: pinned
  custodian custody_load logs once (`frozen inference load: <purpose>`, actor automated-frozen-inference,
  scripts/custodian_newperiod_inputs.py:608-613); the fused parent does the same call (:176) after the same budget
  checks (runner diff, mirrors reviewed_runner.py:145-154), and the per-input read log still comes from the unchanged
  `durable_log(custody_read_paths)`. Workers write nothing. The preamble checks (:179-205) match load_inputs :256-276.
  Any worker exception propagates through pool.map to the pinned failure handler (not dropped); only death is mishandled (B1).
(5) With the three knobs set explicitly there is no way to change row bytes; see B2 for the unset case.
(6) ORIGIN-CROSSCHECK.md is a good real-data gate: real g2_exec chain, one real invalid arm, scratch freeze/specs, original
  without BGBENCH_*, row equality modulo forward_seconds, commitment equality modulo predictions_sha256, self-verify
  (origin_crosscheck.py:234-278), and an automated fallback. Gaps: B2 (unset successor), dead-worker, N1.

## (7) Which candidate
Use q34 fused only after B1/B2 are fixed and the invalid-arm crosscheck passes, because only the fused custody-load
(~90 ms/event vs ~45 ms forward) reaches the ~1 h valid-arm target; q35-origin-g2-parallel (forward-only, PASS with
BrokenProcessPool handling and kill test) is the safe fallback if that fix/re-approval cannot land in time.

Must still run before trusting it: (a) SIGKILL-a-worker test failing the arm in under a minute; (b) the real-invalid-arm
crosscheck (original vs successor, plus successor with env unset); (c) one 32-worker/32-thread-plan run on a real valid
arm slice compared to serial; (d) re-stamp all shas and the root approval after any source change.

## Not checked
Real checkpoint/export (cluster not touched), actual Slurm/NFS behaviour, the 20-passed pinned suite and 500-event gate
were not re-run (read only); thread behaviour of the real libgomp build.
