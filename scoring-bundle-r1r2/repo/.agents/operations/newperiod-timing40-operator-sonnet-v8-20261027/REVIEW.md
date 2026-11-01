# Timing40 operator v4 (Sonnet author, 2026-10-27): release-only recovery for held job 52575987

Prepare only. Not executed; local tests only (`cd /tmp && python3 -I -B <dir>/test_packet.py`, 31 tests). Release is far downstream (after d300/d900/T-N4, all 18 bindings, four accepted horizons, GPU NIL canary acceptance, current phase/adoption/custody/storage). Nothing here authorizes release, fit or capture.

## Situation (facts, from the accepted record)
v3 `replace_held` ended STOPPED at `cancel_confirm` (consumed, no retry, no `result.json`), but its effects are sound and independently accepted: old 52555460 all 40 CANCELLED, new `52575987` held NIL with full 0..39/throttle 1 (typed acceptance `REVIEWER-sol-final-TIMING40-REPLACE-HELD-EFFECTS-ACTUAL-ACCEPTED.json` sha 3760c19c, held record 6546da77). The v3 release gate needs `actual-replace_held/result.json`, which must never be fabricated.

## Cause of the v3 refusal (my own bug) and fix
The real post-run row is `52555460_[0-39%1]|CANCELLED by 23847|0:0` (one compressed row; `sacct -P` prints no trailing delimiter). `cancel_coverage` required a trailing empty field, so any real `-P` row raised. `cancel_coverage` now accepts exactly: `JobID|State`, `JobID|State|` (`-p`), `JobID|State|<N:N>` (ExitCode column); anything else (extra/junk columns, foreign job id, foreign/duplicate/overlapping index, partial range) still refuses or reports incomplete. The compressed single row `_[0-39%1]` counts as exactly the disjoint set 0..39. The same latent defect existed in `terminal()` (capture): it demanded a trailing field; it now accepts `JobID|State|ExitCode` (and the `-p` trailing form) only. Regression tests use the real row from `ROOT-ADOPTION-TIMING40-003/post-run-scheduler-evidence.txt`. Also: `operate.run` now retains the raw stdout of every ssh exchange as `raw-NNN.json` (before the result is parsed), so a parser refusal is diagnosable.

## What v4 is
Copy of v3 without any replacement code: no `replace_remote.py`, no `replace_held` action, no `scancel`/`sbatch` anywhere in `operate.py` (tested). Actions `release` and `capture`; all earlier actions refuse with `Exact action`. `entry/writer/transport/remote/ssh_contract` are byte-identical to v3 (tested), manifest sha a5053dff unchanged, staged `job.sh` is the NIL script (`94ed9662`, tested against the v3 swap record).
`prepare.recovered_predecessor()` is the release predecessor. It reads only pinned bytes: the typed acceptance (sha pinned, kind/passed/independently_accepted/control_and_consumption_accepted/replacement_effects_accepted, `producer_result_present` false, `producer_terminal_status` STOPPED/cancel_confirm, retry/downstream/execution false, job_id 52575987, replaced 52555460, replacement facts identical), the seven consumed v3 records by sha (exactly those seven files, no `result.json`), STOPPED/submitted identity, the held record (sha 6546da77) which must satisfy `check_held(..., NIL)` for 52575987 (not for 52555460, not for NONE), and independence of the acceptance reviewer. `release` gate: root once `previous_actual` = the STOPPED.json ref, `previous_acceptance` = the acceptance ref, review also carries `held_record`; the release bundle is rebuilt by the unchanged `release_bundle(..., job_id='52575987', ...)`, so `release.json` carries the new id (entry.py checks `SLURM_ARRAY_JOB_ID == release.job_id`). `capture` requires a v4 accepted `actual-release/result.json` and job 52575987, all as before.

## Release procedure in v4 (unchanged chain, one root once each)
held readback of 52575987 (exact NIL SubmitLine, PENDING/JobHeldUser, 40 tasks) -> install exclusive bundle -> held readback again + remote preflight (floors/custody/stage tree/job.sh) -> `scontrol release 52575987` -> `result.json`. Raw stdout of each exchange retained.

## Re-review / needs before use
1. Independent source review of v4 (this packet; new pins).
2. At release time (not now): fresh adoption bound to the then-newest phase, control snapshot, release inputs (all 18 bindings, resource_readiness, approvals), release review (`bundle_sha256`, `held_record`, `previous_*`), root once. Accept the GPU-array NIL canary evidence independently first.
3. v3's acceptance/records and v3 pins stay as history; v4 never edits them.

## Residual risks
- `cancel_coverage` and `terminal` now accept the documented `sacct -P` shape; I have the real cancelled-array row but no real completed-array raw output, so capture's accounting parser is untested against live completed rows (the retained raw files will show it).
- The held record is a point-in-time record; the gate re-reads the live job (`held()`) before install, before release, and requires the exact NIL SubmitLine.
