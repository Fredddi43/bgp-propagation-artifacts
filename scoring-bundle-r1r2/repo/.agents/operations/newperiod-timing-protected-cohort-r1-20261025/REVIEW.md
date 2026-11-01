# Protected timing cohort compute, runner r1 (P-T-1)

Author: h3_author (claude-opus-5-5). Local code + local assembly only. No host writes, no protected reads, no approvals.

Purpose: run the independently reviewed kernel `protected_cohort.compute` (timing protected inputs r2, 4c28e80b) once, through the independently reviewed metadata runner 449b2c08, to produce the input-only eligibility audit. The finalize op (`protected_cohort.finalize`) runs later, after an independent actual eligibility review.

Why a runner delta is needed: runner 449b2c08 sets `RLIMIT_FSIZE=output_file_bytes` (max 512 MiB) in the worker and then appends to the shared custody log. That log is 1,489,550,606 B (stat 2026-10-25 ~06:10Z), so the first append would fail with EFBIG. This is the H1r2 lesson; FileLimits (c0207e4e) is the reviewed fix.

`build_runner.py` derives `runner.py` (981a70ae) from 449b2c08 by closed edits that each match exactly once:
- E0 docstring.
- E1 fresh namespace `.../newperiod-inputs-v1/timing-protected-cohort-r1` (the old `timing-metadata-v1` does not exist on the host).
- E2 pins = the H1r2/timing-metadata-execution supervision set: job.py 576fc514, runtime_verifier b80e8fb7, common 265179ef, plus file_limits c0207e4e and reviewed_budget 2c98b74b.
- E3 only `cohort`/`finalize` remain in OPERATIONS.
- E4 worker: drop the FSIZE line. Order is now lazy imports → Budget → FileLimits hook → custody-log appends → kernel.
Everything else is byte-identical to 449b2c08. This includes shape/approval keys, the read_scope equality for cohort, the resource-admission binding, the single cpu allocation check, the supervisor, and failed.json.

`build.py` packages runner.py, reviewed_budget.py and file_limits.py, plus three kernel files (protected_cohort, reviewed_source_io, original_pack, all hash-checked against r2 review-ready), plus the primary construction closure verbatim. Slurm logs go to the namespace root, which exists after staging. The old `root/<op>/` log path would have collided with the runner's `mkdir(exist_ok=False)`, and Slurm cannot create that directory anyway.

`assemble_cohort.py` produces `actual-binding-v1/`:
- `control/` (99 files);
- `control/kernel-plan.json` 8e7fe2ae, whose staging is the primary's own stage receipt 751e (= kernel STAGE), development cohort 0deeb97d (= kernel COHORT; 66,000,120 B), and the primary's two development tables;
- `plan-without-resource.json` 1e7d7fe0;
- `job-cohort.sh` 36cff0ab;
- `resource-request.json`, binding e87603ac.

Limits are file 1 GiB, total read 256 GiB, metadata 128 MiB, max_events 100000. They are fail-closed caps: crossing one aborts before output, and nothing is chosen from data. Resources are cpu, 4 CPUs, 64 GiB, 4 h, output file 512 MiB / total 1 GiB, free floor 250 GiB.

Host facts checked, metadata only: the five bound paths are canonical regular files/dir (realpath == path), so there is no leaf-link exposure (the H3 F1 lesson). The custody log is below the 2 GiB FileLimits ceiling, with ~0.66 GB headroom. If it reaches the ceiling before launch, FileLimits refuses before any kernel read (tested).

Tests: `.venv/bin/python -B -m pytest -q -p no:cacheprovider test_runner_r1.py` gives 25 passed. The suite carries over the reviewed authority/reviewer/resource/timeout/job tests. It packages the real primary closure. It runs a genuine isolated cohort worker: the real Rule-A and six-horizon split on the r2 synthetic fixture, with a 4 MiB custody log above the 1 MiB output cap, the appends checked, and statuses/source failures retained. It checks that a log at the ceiling is refused before any read, and that the runner equals the closed-edit derivation. Mutation: restoring the FSIZE line fails 3 targeted tests (derivation, log-above-cap worker, order).

Still required, none of it fabricated here:
1. Independent code review of this delta.
2. An independent exact resource admission whose ref completes the plan.
3. An independent exact cohort-operation approval.
4. A root joint storage row (1 GiB output plus log growth on the models fs) and a once-authority for stage, sbatch and capture.
5. After the run, an independent actual eligibility review, then the finalize op under its own approval.
