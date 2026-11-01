# Timing40 operator successor v2 (Sonnet author, 2026-10-27): `--export=NIL` and replacement of held job 52555460

Not executed: no scheduler, cluster or network call was made; local tests only (`cd /tmp && python3 -I -B <dir>/test_packet.py`, 25 tests). Authors: this Sonnet worker. Execution requires an independent review and an issued root once; nothing here is authority.

## Why
Held job `52555460` (`n-timing40-v1`) has `--export=NONE` in its SubmitLine (verified read-only with `scontrol show job -o`: PENDING, JobHeldUser, SubmitTime 2026-10-26T12:50:20). Root canaries show `--export=NONE` batch jobs are cancelled by uid 0 at start; `--export=NIL` works with an empty environment (no PATH). A release of 52555460 would die. Slurm cannot change the export mode of an existing job, so the job must be cancelled and resubmitted.

## What changed vs `newperiod-timing40-operator-astra-v28-v1-20261026`
- `prepare.py`: `held_argv()` now uses `--export=NIL` (the only argv difference; `export='NONE'` reproduces the v28 line for reading the old job). `script()` is the NIL-clean job.sh: `exec /usr/bin/env -i ...` instead of bare `env` (everything else was already absolute: `/usr/bin/sha256sum`, `/usr/bin/cut`, the venv python; `umask ulimit test cd exec` are builtins). `script(legacy=True)` is the exact staged v28 bytes. `replacement_facts()`, `old_chain()` bind the replacement and the pinned v28 stage/submit_held actuals and acceptances (by sha of the files, not by this packet's pins). `FILES` gains `replace_remote.py`.
- `replace_remote.py` (new, pinned): the only remote write. Replaces `ROOT/job.sh` iff it equals the legacy bytes, `manifest.json` has the accepted sha, no `release.json`, no stale tmp; exclusive temp + chmod same mode + atomic rename; touches nothing else (not manifest, workers, stage source, output, custody log).
- `operate.py`: actions `replace_held`, `release`, `capture`. `stage` and `submit_held` are refused (done in v28). Release's predecessor is `actual-replace_held/result.json`. The release/capture/transport/remote.py logic is unchanged apart from that.
- `entry.py writer.py transport.py remote.py ssh_contract.py` are byte-identical to v28 (tested), so `manifest.json` (operator_files hashes) is byte-identical, its sha stays `a5053dff...`, and the job.sh argument stays the same. **No restaging is needed or performed.**

## Exact replacement procedure (`replace_held`, one root once, fixed `actual-replace_held`, no retry)
Gate (all of v28's, plus): root once binds `replacement` = `replacement_facts()` (cancel argv exactly `['scancel','52555460']`, old/new export, old/new job.sh sha, old/new held argv); review binds the same; `previous_actual`/`previous_acceptance` are the pinned accepted v28 submit_held actual/acceptance, whose chain to the accepted stage is verified, and whose recorded held rows must satisfy `check_held(..., 'NONE')`.
Steps (each recorded in `actual-replace_held/`; any failure writes `STOPPED.json` and stops, consumed):
1. `old_readback`: `scontrol show job -o 52555460` must be PENDING, JobHeldUser, exact v28 SubmitLine (`--export=NONE`), all 40 tasks.
2. `remote_check` (`preflight.json`): read-only; job.sh == legacy bytes, manifest sha, no release.json.
3. `replace_job_script` (`job_script_swap.json`): swap job.sh to the NIL bytes. Held 52555460 is unaffected (sbatch spools the script at submit).
4. `remote_consistency` (`consistency.json`): remote.py `preflight` (stage tree, workers, job.sh == `prepare.script()`, custody, floors).
5. `submit_new` (`submitted.json`): the one `sbatch` with `held_argv(manifest_sha)`; new id must differ from 52555460; `new_readback` exact (`--export=NIL`, held, 40 tasks, throttle 1).
6. `old_still_held`: re-read 52555460, still exact v28 held.
7. `cancel_old`: the one `scancel 52555460` (never twice, no wildcard/user/name selectors); `cancel_confirm` polls sacct up to 8x5 s until all rows of exactly that job are CANCELLED (`cancel.json`); unconfirmed = STOPPED, not passed.
8. `new_final_readback`, then `result.json` (`action: replace_held`, `job_id` = NEW id, `replaced_job_id`, `old_held`, `job_script_swap`, `replacement`).
Submit-before-cancel order is deliberate: a failure never leaves us without a held job; worst cases are both held (step 7 fails: root cancels 52555460 by hand, still a held job that can never start without a release) or a swapped job.sh with only the old job (steps 3-5 fail; the old job is still held; a new once is needed). Never any other job: both scheduler mutations are the two fixed argvs, asserted by test.

## Downstream effect (what the replacement invalidates)
Still valid (unchanged bytes/identity): manifest and all worker files, v28 `actual-stage` + `accept-stage` (job.sh bytes are not part of the stage record or manifest), phase-independent scientific package, d300/d900 chain, release inputs that do not name the job id (bindings, resource_readiness, approvals).
Invalid or unusable:
1. v28 `actual-submit_held`, `accept-submit_held` and `review-submit_held` name job 52555460 (cancelled afterwards) and v28 pins: kept as history only, never a release predecessor. Any v28 root/review for `release` or `capture` and the v28 `operate.py` must never be used (it would release the cancelled job).
2. `ROOT-ADOPTION-TIMING40-002/adoption.json` is bound to phase v43 and a 11:28Z custody observation. The gate demands the newest issued compatible phase and v43 no longer chains to the newest (`phase_compat.accept` refuses: own-lane `timing_*` rows changed at v44, v48 is now newest). A fresh root adoption bound to the current newest phase (v48, `timing_forty_fits` unchanged at 42949672960) and a fresh custody observation, plus a fresh control snapshot, are required. It must be re-issued again if another phase is issued before the once.
3. Every pin changes (new directory, `prepare.py`, `operate.py`, new `replace_remote.py`), so all action reviews and root onces bind to the new pins.
4. `release.json` carries `job_id` and `entry.py` checks `SLURM_ARRAY_JOB_ID == release.job_id`: the release bundle and its review `bundle_sha256` must be built from the new id (the replace actual). Nothing was built yet with 52555460 if no release review exists; any that does is void.
5. Notes, ledgers or HANDOFF entries naming 52555460 as the held job are stale after the once.

## Re-review set (independent reviewers, not this author)
1. Source review of this packet (`replace_held` flow, `replace_remote.py`, NIL script, byte-identical workers, test coverage).
2. Root: new operating adoption (current phase) + control snapshot; root once for `replace_held`; review-`replace_held` (bound to new pins/phase/adoption/replacement facts/pinned v28 chain).
3. Acceptance of the `replace_held` actual (new job id, held readback, cancel record, job.sh swap record).
4. Release action review + release inputs/bundle for the new job id and pins; capture review, as before but on the successor pins.
No re-review of manifest, stage actual/acceptance, workers or scientific inputs is needed beyond confirming they are byte-identical.

## Residual risks, stated plainly
- Not proven: `CUDA_VISIBLE_DEVICES` and the gres environment under `--export=NIL` on `gpu-rtx8000` (canaries were cpu). job.sh passes it through as `${CUDA_VISIBLE_DEVICES:-}`; slurmd normally sets it for the task regardless of export. A GPU-partition NIL canary would settle it; the author did not run one.
- A job released while a different uid-0 behaviour applies to arrays is likewise untested: canaries were not arrays.
- Between `old_still_held` and `scancel` there is a millisecond window in which someone else could release 52555460; only root can, and nothing else releases.
- The phase gate is as strict as v28's; the adoption/phase pair is the fragile part.
