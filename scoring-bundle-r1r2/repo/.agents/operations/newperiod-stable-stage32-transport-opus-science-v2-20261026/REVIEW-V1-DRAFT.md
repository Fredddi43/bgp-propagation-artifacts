# N-stable stage32 transport (opus-science, DRAFT, never executed)

Status: **prepared, not executable**. Blocker B1 below makes the accepted runner v2 refuse its own approval.
Nothing here was run remotely; no authority issued; all docs in `draft-v39/` are FALSE/UNSIGNED.

## Inputs bound (sha256)
- runner = package-source-v2/runner.py = source_runner.py `082b2ae5436d…52ac`; receipt `bc50c346…e2aa` (98 files); build.py `d25e9737…0156`
- kernel plan plan-v39 `517ad503…e943` (57,154-path scope); T040 final plan `b498e57c…5b82` (primary_construction + runtime copied verbatim)
- phase v39 `fea2ecd6…70d5` (models min 608168057856, no stable row); v40 `d01e51d3…7f37` (min 640380312576, `stable_source_stage` 20 GiB)
- PASS: board/REVIEWER-opus-review-STABLE-INPUTS-V2B-AND-PLAN-V39-PASS.json (`edc3e779…`)

## Files
- `build_transport.py` (`3c33261e…9d92`): `build(out, kernel_plan, phase[, admission, review, approval])`, assembly builders.
- `test_transport.py` (`5dfc4d1d…a83a`): 10 tests against the real runner/build/kernel code. Result: `10 passed`.
  `cd <repo> && PYTHONPATH=src .venv/bin/python -B -m pytest -q -p no:cacheprovider <dir>/test_transport.py`
- `draft-v39/` = `build(draft-v39, plan-v39, phase-v39)`, rebuilt byte-identical (test 1):
  - `control/` = exact ROOT/control tree: 98 package files + `kernel-plan.json` + `plan.json` (`a1e39e4c…bca7`)
    + `resource-admission.json` + `review.json` + `approval.json` (`95c8b2b8…d6fb`) + `stage.sh` (the Slurm job script)
  - `templates/`: FALSE templates of admission/review/approval + `root-once-authority.FALSE-TEMPLATE.json`
  - `transport/`: `payload.tar` `f97bc326…988c` (104 members, 32,787,718 B), `stage.sh` `f85855f6…2d6e`,
    `submit-held.sh` `6318dfab…a655`, `request.json` `e2b561c7…8848` (`signed:false`)

Remote layout after staging: `ROOT=<CLUSTER_STORAGE>/…/newperiod-inputs-v1/stable-source-v1`, `ROOT/control/{runner.py,…,stage.sh}`;
runner records `ROOT/shards/NNN/attempt/{intent,disk-admission,worker-intent,done|failed}.json`, kernel output
`ROOT/shards/NNN/attempt/output/<eid>/…` + `output/done.json` (shard receipt); Slurm logs `ROOT/slurm-stage-%A_%a.{out,err}`.

## Blockers
- **B1 (runner v2 defect).** `source_runner.py:65` `read(aref, 2<<20)`: approval limit 2 MiB. `shape()` (:55) requires
  `approval.read_scope == plan.read_scope` = 57,154 paths; the approval is 7,624,285 B. `checks()` refuses with
  "Canonical bounded metadata required" before `shape()`. Proven by `test_BLOCKER_runner_v2_refuses_full_scope_approval`
  (real `read()`; a 32<<20 bound admits it). T040's approval was 14,360 B (5-path scope), so the pattern never hit it.
  Fix = runner v3, one constant (`2<<20` -> `32<<20`), new package receipt + review. Builder takes the package by path.
- **B2.** v40 kernel plan not built yet (only `free_floor_bytes` changes). Builder takes it as a parameter; test 9 shows
  a v40-floor plan differs from v39 only in `resources.free_floor_bytes`, `kernel_plan`, `storage_phase`, `resource_admission`.
- **B3.** No 32-array once-operator exists. T040 `operate_cohort.py` (`5e54e572…`) is singleton/cohort-specific
  (readback of one held job, capture of `cohort/attempt`). Root template leaves `operator_sha256`, `records` null.
- **B4.** v40 issue condition 11: stable stage custody appends vs the H3 64 MiB campaign gate (see custody section).

## Diffs vs the T040 pattern (make_transport in operate_cohort.py v2, prepare.py)
1. Submit argv comes from `build.source_submit_argv` (required by the runner package), not T040's inline argv:
   `--array=0-31%32`, `--time=120` (minutes, not HH:MM:SS), `PATH=/usr/local/bin:/usr/bin:/bin`,
   `--output/--error` into ROOT, job name `n-stable-source-stage`. Everything else (`--hold`, `--no-requeue`, `cpu`,
   `--export=ALL`, `--chdir=ROOT/control`, 4 positional plan/approval refs) as T040.
2. Job script = `build.source_job_script` (plain `runner.py -I -B` under `env -i`), staged as `control/stage.sh`
   because the argv names `<stage>/<op>.sh`. Name clash only with `transport/stage.sh` (the staging script).
   T040 `job.sh` embedded the allocated launcher `f7b6445f` (census before/after); **no allocation envelope here**.
   Storage limits rest on runner Budget/RLIMIT_FSIZE, kernel `Writes` (per-file, per-task, statvfs floor), disk
   admission. Root decides whether an allocated launcher is required.
3. `stage.sh` minimum = `free_floor + 32 x output_total_bytes` = the runner's own disk admission (`source_runner.py:166`),
   not just the phase minimum (with floor == phase min that is phase min + 20 GiB: v39 629642894336, v40 661855149056).
   Otherwise identical: user check, parent readlink, `test ! -e/-L ROOT`, `mkdir ROOT`, `mkdir ROOT/control`,
   `tar --keep-old-files`, `sha256sum --strict --check` of all 104 staged files, `chmod 400`. Heredoc `EXACT_STABLE_FILES`.
4. Payload: 98 bound files + 6 control files; `source-receipt.json` not shipped (T040 shipped none). 64 MiB guard kept.
5. Plan carries `storage_phase` (phase ref) instead of `allocation_envelope`; it is inside `resource_binding`.
6. Approval fields = exactly what `shape()` reads (`stable_source_reconstruction_authorized`, 8 false flags); no T040
   `input_projection_*` flags. Admission adds `maximum_concurrent_tasks 32`, `aggregate_write_bytes 21474836480`.
7. Signed docs are checked like T040 prepare.py: equal to template except flips + reviewer fields (+ review
   `checks`/`conditions`), then real `runner.shape()` with only the review read substituted.
8. Root template kind `newperiod_stable_source_stage_once_authority_v1`, adds `array_tasks 32` and a custody preflight
   note; `maximum_wait_seconds` null (32 x 2 h may not co-schedule; root sets it).

## Resources (proposal)
- `cpus 2`: derivation is per-event polars on one thread pool (`POLARS_MAX_THREADS=cpus`); I/O-bound fsync per open.
- `memory_mib 16384` (RLIMIT_AS = 15,872 MiB, virtual). Per task: context = primary receipt 11.6 MB JSON + 2 query
  manifests + 5 tables (26.8 MB on disk) + 18,132-entry event map, a few hundred MB as Python objects; then one event
  at a time. Max shard source 538,936,001 B (min 66.8 MB). Largest single event 336,709,512 B (anomalous parquet
  336,699,661 B, `20230901T000000_leak_1031`), next 199 MB. Event holds raw bytes + decoded frame + filtered copy +
  membership; at 5-10x zstd ratio that is ~2-4 GB decoded, ~6-10 GB peak with copies, plus torch/polars import.
  **Risk:** decoded size is unmeasured (payload not read) and there is no retry. If the reviewer wants margin: 24576.
  32 x 16 GiB = 512 GiB cluster memory.
- `wall_seconds 7200` (whole minutes; = runner alarm = `--time=120`): ~567 events, <=539 MB read, ~1.8k durable opens
  (log + dir fsync each) per task.
- `output_file_bytes 536870912`, `output_total_bytes 671088640`, `free_floor_bytes` = plan limits (runner :93).

## What reviewer/root fill (dependency order; rerun `build` after each)
1. Reviewer: `resource-admission` -> `passed`, `input_memory_admitted` true + `reviewer_model/worker/session`.
   Rows auto-filled from the phase (v40: `stable_source_stage` 21474836480; v39: null). `build --admission`.
2. Reviewer: `review` -> `passed` + `checks`/`conditions` + reviewer fields (binds the plan sha). `build --admission --review`.
3. Reviewer: `approval` -> `passed`, `execution_authorized`, `stable_source_reconstruction_authorized` + reviewer fields.
   Final `build` with all three -> `request.signed/real_runner_shape_passed = true`.
4. Root: once authority -> `request`, `independent_review`, `control_post_snapshot`, `operator_sha256` (B3),
   `records`, `scan_dirs`, `maximum_wait_seconds`, `passed`.

## Assembly (prepared only)
`assembly_kernel_plan(stage_kernel_ref, 32 sized shard receipt refs)` and `assembly_plan(stage_plan, source_plan, raw)`:
scope = stage scope + source plan + 32 receipts (57,187); singleton, `--dependency=afterok:<array id>`, `assemble.sh`.
Files go beside the stage control as `*-assemble.json`; the stage `stage.sh` (ROOT must not exist) can't be reused:
the assembly staging script must require `ROOT/control` to exist and add files with `--keep-old-files`. Not written.
Same B1 applies (approval with 57,187 paths).

## Custody-log volume (v2b aggregate scope logging)
Counted from runner/kernel `log_read` call sites only, ~520 B/line (REVIEW-V2 estimate):
- per stage task: 2 (checks: kernel plan + aggregate scope) + 11 primary preflight (receipt, release, 2 sealed,
  2 dev tables, 5 release evidence) + 2 (worker) + 9 context (receipt, 2 queries, 5 tables, selection)
  + 3-4 per event + 1 per query coverage = 1,794-1,815 lines; **32 tasks = 57,736 lines ~ 30.0 MB**.
- assembly: ~55,939 lines ~ 29.1 MB (32 receipts + 55,707 shard files + 177 feature files + preflight).
- total ~113.7k lines ~ 59 MB, matches v2b's ~61 MB. Stage alone is under 64 MiB, but it is a separate writer:
  the PASS condition still applies (stat-only: refuse if size + 64 MiB + 128 MiB > 2 GiB).

## remote_metadata_needed (not run)
- `stat -c '%s %i' <CLUSTER_STORAGE>/…/newperiod-identification-v1/access-log.jsonl` right before submit.
- `df -B1 --output=avail <CLUSTER_STORAGE>/…/newperiod-inputs-v1` (stage.sh gate).
- `sinfo -p cpu -o '%n %c %m %t'`: can 32 x (2 CPU, 16 GiB) co-schedule.
- Optional, root decision (parquet footer only): uncompressed row-group bytes of the largest event's anomalous.parquet.
