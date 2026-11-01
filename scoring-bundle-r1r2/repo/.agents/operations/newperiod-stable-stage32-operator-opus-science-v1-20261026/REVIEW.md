# N-stable stage32 once-operator (opus-science, B3), prepared, never executed

Status: **source only**. No remote action, no authority, no board post. Needs a separate review (not opus-science), then a root
authority filled from the transport FALSE template (with the changes below). Prepared, not accepted.

## Files (sha256)
- `operate_stage32.py` `56f6d9a34792b09ddfbc087ab850c40a4e4a0cca62ec78470bcdd0f3a462a4e6`
- `test_operate_stage32.py` `0ed5b7be38aaa5a532507e0bd05edd357d860eb211816fd16ed6ba4c687a753e`
- Run: `cd /tmp && python3 -I -B <dir>/test_operate_stage32.py` gives `Ran 17 tests ... OK` (unittest, no pytest cache, no __pycache__).

## Bases read (sha256)
- cohort r3 `operate_cohort.py` bee8e357… (REVIEWER-sol-h3t-cohort-operator-r3-PASS), r4 6438fbda… (REVIEWER-sol-h3t2-cohort-operator-r4-PASS:
  scan only `*.json`), T040 v2 5e54e572… (REVIEWER-sol-h1-T040-OPERATOR-V2-SOURCE-PASS: control snapshot, operator self-hash, fixed records,
  separate review binding operator+request, check-only mode, custody +64 MiB). The guards come from T040 v2, the newest accepted version.
- transport v2 `build_transport.py` 7a6b5f8f…; draft-v40 `request.json` 119b699c…, `submit-held.sh` 5efa1aa6…, `stage.sh` 37b35d31…,
  `root-once-authority.FALSE-TEMPLATE.json` 27629297…; runner `source_runner.py` cc71f46e… (= package-source-v3/runner.py);
  kernel `stage.py` 5c58c1a4… (`derive_shard` :98-117); `phase_compat.py` 3dd49cb0… (ROOT-DECISION-PHASE-FORWARD-COMPAT-0219).

## Chain (one invocation, exit 0 = all 32 passed, 4 = terminal but not all passed, 3 = STOPPED)
constructor checks then `RECORDS/authority-consumed.json` → G stage → stage.sh<payload.tar (<BATCH_HOST>) → G submit → submit-held.sh
(<SUBMIT_HOST>) → one ArrayJobId → `scontrol show job -o ID` readback → G release → `scontrol release ID` once → sacct wait → per-task capture.
Any exception, including KeyboardInterrupt, writes STOPPED.json {reason, exception_type, step}. Jobs are left as they are; nothing is cancelled or retried.

## Guards kept (from T040 v2 / r3)
- Exact authority: kind, passed, `/root`, max 1 invocation, retry false, op list, `operator_sha256` == own bytes, `records` == fixed unused
  sibling `newperiod-stable-stage32-actual-v1-20261026` (exclusive `mkdir`, so a second run is refused), separate review pinned and binding
  operator sha + request ref (reviewer worker/session not empty, `/root` or `opus-science`).
- Control snapshot: exact path→sha of every ROOT-/REVIEWER-/OWNER-/OPUS-REVIEWER-`*.json` in scan_dirs. Checked in the constructor and before and
  after every fresh stat. The only exception is the exact 4-field GO announcement `{utc,kind:ROOT_GO_STABLE_STAGE32_ONCE,to,authority:<this ref>}`.
- Gates before stage, submit and release: STOP file, phase, controls, fresh models/results df, canonical <USER>-owned custody log lstat
  with stable dev/inode. Injected run/sleep/now. Every record is written with `open('xb')`. Each remote call gets intent, stdout, stderr and result records.
- Request: signed, real_runner_shape_passed, both scripts and the tar pinned. Every tar member is a regular file and the member set equals `request.files` by sha.
  The submit argv is rebuilt independently (`expected_argv`) and must match exactly, and `submit-held.sh` must equal `set -eu` + that argv.
  stage.sh must contain `test ! -e ROOT`, the minimum and all 104 sha lines. Plan, approval and admission are parsed from the tar
  (approval passed/execution/stable_source true, 8 false flags; admission 32 tasks, 32×write). The kernel plan has 32 shards and the exact output_root.
- Probe (local): the real draft-v40 request passes every check up to "Signed exact stage approval required" (FALSE template). Its argv
  matches the rebuild. The unsigned draft is refused at the `signed` check (test).

## Array-specific
- Readback accepts any mix of range records (`ArrayTaskId=0-31%32`, comma lists; throttle must be 32) and per-task records. Every
  line: ArrayJobId=ID, PENDING/JobHeldUser (JobHeldAdmin refused), cpu, ReqNodeList/ExcNodeList/Dependency `(null)`, NumCPUs 2, MinMemoryNode
  16384 MiB, TimeLimit 02:00:00, NumTasks 1, NumNodes 1, UserId <USER>(, Requeue/Restarts 0, WorkDir STAGE, StdOut/StdErr in ROOT
  named `slurm-stage-*`, and `Command=STAGE/stage.sh` followed by exactly the 4 plan/approval args, then a `k=v` token or end of line. JobIds are unique.
  The union of task ids must be exactly 0..31, each once.
- Wait: `sacct -n -P -X -j ID -o JobID,JobIDRaw,State,ExitCode,Elapsed,MaxRSS`. Rows must be `ID_N` (distinct N<32) or `ID_[range]`.
  A foreign row stops the run. Terminal means 32 task rows, no range row, all in the TERMINAL set. Up to 60 rc≠0/empty/exception polls are tolerated.
  A timeout writes `wait-timeout.json` (counts only, cancelled:false) and stops.
- Capture (<BATCH_HOST>, read-only): per task, one `python3 -I -S -B` reads `ROOT/shards/NNN/attempt`. It lists the top-level entries and,
  for intent, disk-admission, worker-intent, done, failed and `output/done.json`, refuses symlinks (realpath, O_NOFOLLOW) and anything that is not a regular
  file ≤16 MiB. It sends a JSON header (name, size, sha) followed by the bytes. It also stats the sizes of `slurm-stage-ID_N.{out,err}` (sizes only, no
  content). Locally the frame length and every sha are checked. Bytes go only to `RECORDS/tasks/NNN/` and are never printed.
  `capture.json` holds per-task state, rc, elapsed, MaxRSS, record shas/sizes, absent records, errors and the event count. It holds **no event ids**.
- Validation is exact against runner v3: intent {plan, approval, op, job_id == JobIDRaw, retry false}; disk-admission (3 keys, free ≥
  32×write+floor); worker-intent; failed (3 keys); done (9 keys, flags false, `result` == {path, sha, size} of the captured receipt);
  receipt kind, passed, index == N, count 32, `plan_sha256` == sha(encoded(kernel plan)), retry false. Byte check:
  done.output_bytes == receipt.output_bytes_before_receipt + receipt size. A task passes only with COMPLETED 0:0, all records present and no errors.
  One bad task fails only that task. Exit 4 means everything was captured and nothing is retried.

## Deviations from the brief (each a decision for root and the reviewer)
1. sacct adds `JobIDRaw`. Without it the per-task `intent.job_id` (= task SLURM_JOB_ID) cannot be bound. Held pending records do not carry task ids.
2. Capture uses bounded `python3 -I -S -B` (lstat/O_NOFOLLOW/sha256) instead of `cat`/`sha256sum`, the same as the accepted cohort capture. This
   avoids following links and makes 32 ssh calls instead of 192.
3. Phase: `phase_compat.accept(bound, OPS, k.startswith('stable_source'))` instead of T040's hard "newer phase refuses". The effective models
   minimum = authority minimum + (newest − bound models floor). The results floor comes from the newest phase.
4. scan_dirs are chosen by root (≥2, canonical, under the worker tree, board required) instead of T040's fixed six. The snapshot is confined to them.
5. Custody headroom is 64+128 MiB (template note), stricter than T040's 64 MiB.

## Root template changes needed (transport draft `root-once-authority.FALSE-TEMPLATE.json`)
- Remove `template_only`. **Add `root_issued_utc`** (string). The exact key set is enforced (`AUTH_KEYS`).
- Fill: `passed` true, `maximum_wait_seconds` (int, 7200..604800; suggested ≥ 21600 because 32×(2 CPU, 16 GiB) may not co-schedule),
  `request`, `independent_review`, `control_post_snapshot` ({posts:[{path,sha256}], root_acknowledges_all_controls:true}),
  `operator_sha256` 56f6d9a3…, `records` = the absolute path of `newperiod-stable-stage32-actual-v1-20261026`, and `scan_dirs`.
- `minimum_free_bytes` must equal request.minimum_free_bytes = plan floor + 32×write (v40: 661855149056).
- The independent review JSON must carry `passed`, `operator_sha256`, `request` (exact ref), `reviewer_worker` and `reviewer_session`.
- Check without consuming: `python3 -I -B operate_stage32.py check --authority A` (cd /tmp). Run: `... operate --authority A`.

## Risks / open
- RECORDS sits under `.agents/operations` (git-tracked tree). `tasks/NNN/output-done.json` holds shard receipts with event ids
  (metadata, allowed locally). Root should decide whether they get committed or ignored.
- A Stop between submit and release leaves the array held. Root disposes of it separately (as in T040).
- Up to 32×6×16 MiB could be captured in the worst case. Expected is ~a few MB per receipt.
- The real scheduler text format has not been observed for a held throttled array, so the parsing is defensive. If the format differs, the run fails at
  readback, before release.

## remote_metadata_needed (not run)
- On a throwaway held array (root decision): `sbatch --hold --array=0-1%2 --wrap true`, then `scontrol show job -o <id>`. Confirm the
  range record shows `ArrayTaskId=0-1%2` vs `ArrayTaskThrottle`, the StdOut rendering for an unsplit record, and that `Command=` lists the args.
- `sacct -n -P -X -j <id> -o JobID,JobIDRaw,State` on that array (pending range rendering `<id>_[0-1%2]`), then `scancel <id>`.
