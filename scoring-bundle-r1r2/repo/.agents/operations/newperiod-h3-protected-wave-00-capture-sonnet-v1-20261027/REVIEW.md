# Wave-0 finite capture packet (chain step 2): job 52555157, mixed7-d30 manifest

Author: Sonnet worker (not a reviewer). No launch, signature, ROOT authority, cluster write, board post or git. `--prepare` and 8 local tests pass against the real consumed wave-0 records (`newperiod-h3-protected-wave-00-actual-storage2-v4-20261027`: CONSUMED, released.json, no STOPPED). Request sha256 `24b9d06d5eb72b2102ac4782870e7e9bcdcd1148fd7a293741ee9e69b27c0f3e`.
Observed (read-only, 2026-10-26 ~23:40Z, not part of the packet evidence): `sacct` says 52555157 COMPLETED 0:0, 0 restarts, <COMPUTE_NODE>, 00:19:15, End 00:24:48 (cluster local time, about UTC+1, i.e. ~23:25Z); models free 868273356800 B (v48 floor 867383093888, margin 890262912 B).

## Existing tooling reused
`newperiod-h3-protected-stage-storage2-v6-20261026/finite_capture.py` (candidate, pinned by sha in the request) does the exact-task capture: requires all tasks terminal COMPLETED 0:0 restart 0, reads only the small own `done.json`/`intent.json` per task (plan, group, phase, index, approval, job id, `gate_issued false`, no `failed.json`), and stat-censuses output and records dirs (owner, single link, no specials). `wave_contract.census` (pinned by the plan's file hash) gives the whole-namespace allocated census that `admit()` later compares as `predecessor.after_census`.

## What the one-shot does (operate.py, ROOT standard SSH, three exchanges, no retry, records dir `newperiod-h3-protected-wave-00-capture-actual-v1-20261027`)
1. <SUBMIT_HOST> `sacct` for 52555157 (exactly one row; id, state, exit code, restarts) -> `terminal.json`.
2. <SUBMIT_HOST>: `scontrol show job -o` for the other 23 jobs (each must be PENDING / JobHeldUser / exact name / exact id) and one `squeue -r` over all 24 ids (target absent, all others PENDING).
3. <BATCH_HOST>, one stdin script (`capture_remote.py`): exact mount, df, custody-log stat vs the stage baseline, census A, `finite_capture.capture`, stat of the Slurm out/err streams, sleep 310 s, census B, custody and df again. Stdlib only, no protected payload, label, score, prediction, parquet or tensor opened, no write.
`checks.reconcile` requires: capture all-zero and payload_files_opened 0, every task has both receipts, census A == B (allocation stable after >= 310 s), growth vs the release-time census (pinned `snapshot.stdout`) within wave-0 required_new (22 GiB), custody identity/growth within 64 MiB, both floors met after, Slurm streams plain single-link files.
Outputs: `actual.json` (independent acceptance still required, next release false) and `wave-history-acceptance.CANDIDATE.json`: the exact history document shape `wave_once.check` and `admit()` read (`all_completed_zero`, `before_census`, `after_census` = census B), with `passed`, `all_receipts_passed`, `delayed_allocation_stability_accepted` and reviewer fields false/null for sol-h3t2 to fill, so the later ordinal-1 predecessor needs no re-capture.
Genuine-once gate (`--check`): canonical ROOT bytes, kind `h3_wave00_capture_once_v1`, `maximum_invocations 1`, fresh records path, pinned request/operator, independent operator review (scope `h3-wave00-capture-v1`), independent release-actual acceptance (scope `h3-wave00-release-actual`), root barriers (other 23 stay held, no other H3 namespace writes), and the all-controls snapshot (re-checked before every exchange). FALSE templates: `root-once`, `independent-review`, `release-actual-acceptance`.

## Limits
Receipt metadata read = two control JSON files for the one task (small, own, canonical); their `result` (manifest refs) is not re-validated here. Output content is not hashed (stat only). Cooperative namespace only; Slurm accounting rows are scheduler facts. The 310 s pair is the delayed >= 300 s stability evidence; the reviewer still has to accept it explicitly.

## Ordinal 1 (mixed7-d30 build, indices 0-7): skeleton and storage need (`ordinal1/`)
`request.SKELETON.json` (targets 52555163_0..7, nulls for joint, predecessor, history, profile, reviews) and `needs.json`, both derived from the real contract and pinned by a test.
- Wave bytes (build, 8 tasks): retained max 16 GiB, temporary 4 GiB, padding 44 GiB, physical reserved **64 GiB**, required_new **62 GiB**.
- `admit()` needs the dedicated row `protected_h3_current_wave` >= required_new + 2 GiB = **68719476736 B**; V48 has 25769803776 B (24 GiB): **+42949672960 B (40 GiB)** short. If only that row grows, the models minimum becomes 910332766848 B; free is 868273356800 B, so about **42.06 GB** more free space (or an equal reservation reduction elsewhere with review) is needed. No row borrowing is allowed.
- `phase_scope` also refuses ordinal 1 under V48: `stage_held_allowed true` permits only [0]; the new phase must list 1 in `allowed_wave_ordinals` with `stage_held_allowed false` (test).
- Also needed: independently accepted wave-0 history document (above), new build-phase retained-input/read-scope reviews and physical profile (reserved 64 GiB), fresh adoption/evidence per `gate.py`, and `wave_once_v2.py` (records_path(1) = `newperiod-h3-protected-wave-01-actual-storage2-v4-20261027`).

## Root sequence
1. sol-h3t2 reviews this operator and signs `independent-review`; accepts the wave-0 release actual (`release-actual-acceptance`).
2. Root writes the control snapshot (7 dirs, exclude the GO post `ROOT_GO_H3_WAVE00_CAPTURE_ONCE` to `sonnet-h3-capture`), fills the once, runs `operate.py --authority <once> --check` then the single run.
3. sol-h3t2 accepts `actual.json` and fills the history document (delayed stability accepted).
4. Separately: successor phase with the ordinal-1 row and scope; then the build-wave packet.
