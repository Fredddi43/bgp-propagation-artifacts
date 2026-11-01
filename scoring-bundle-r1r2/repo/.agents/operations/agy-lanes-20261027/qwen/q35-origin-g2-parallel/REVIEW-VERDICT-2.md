# REVIEW-VERDICT-2: q35-origin-g2-parallel (independent re-review of the fix round, 2026-10-28)

Verdict: PASS (one NIT, no blocking finding; reviewer edited nothing except this file)

## Checked against code
- Pinned runner af8c03eb... (sha256sum confirmed) vs successor/runner.py: diff shows exactly two regions, edit A (runner.py:6-8) and
  insert B (+7 lines after 112, runner.py:115-121). Insert B pins parallel_infer sha 47d1596c..., which equals sha256sum of the file.
- REPORT.md section 2 shas all equal sha256sum: runner 4804fe26..., parallel_infer 47d1596c..., equiv_run 38033a11..., test_guards b749e307..., e1_threads 3fb935ac....
- Tests re-run from /tmp, repo .venv, PYTHONPATH=src, -B -I: test_guards.py = 13 passed (4.43 s).
- RISK-1 fixed: REPORT.md:221 exports OMP/MKL/OPENBLAS/POLARS threads = 8; equiv_run.py:230-237 makes --reference-threads required in production mode;
  equiv_run.py:289-296 prints torch.get_num_threads() and SystemExit on mismatch; workers self-report threads and equiv_run.py:337 gates
  `passed` on worker_threads == [installed threads]. Mismatch refusal is real code, not just docs.
- RISK-2 fixed: parallel_infer.py:94-99 uses fork-context ProcessPoolExecutor + ordered ex.map; a dead child raises BrokenProcessPool in the parent;
  the list is only returned if every result exists, so no partial output; the exception goes to the pinned generic handler in run() (stage failure).
  test_guards.py:213-228 SIGKILLs a real fork worker and asserts BrokenProcessPool in <60 s under a 90 s SIGALRM anti-hang; it passes.
- RISK-4 fixed: production mode requires --plan and goes through the pinned reviewed_runner.bounded_calls wrapper (equiv_run.py, via_wrapper recorded);
  test_pinned_wrapper_drives_successor_byte_equal exists and passes.
- NIT-1 (13/13 counts) and NIT-2 (--mem 500G, REPORT.md:209) fixed; no stale "10/10" or "11/11" remains as a current claim.

## Findings
NIT-A equiv_run.py:230-237,309: --reference-threads is an operator-supplied number, not cross-checked against plan['resources']['cpus'] of the
  --plan file (installed cpus are derived from workers//2). The gate therefore proves "reference == the number typed", so a wrong typed value (not 8)
  would pass. Fix (optional): SystemExit if a.reference_threads != plan['resources']['cpus'].

## Not verified
E3 on real checkpoint/export, arm-venv torch equality, real NFS/Slurm behaviour (unchanged from the first review; E3 remains the mandatory gate).
