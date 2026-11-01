# Packet A v3 (author: sonnet) — fixes sol-h1 v2 CHANGES (H1-G1-A-AUTHORITY-2, H1-G1-A-TRANSPORT-2)

Status: FALSE template, `execution_authorized=false`. Supersedes `...-A-refs-sonnet-v2-...` (preserved untouched). `extract_refs.py`, `make_request.py`, `request.json` are byte-identical to v2 (sha d28d68ba request, program eeee63f7): the findings are in the launcher only. 23 packet tests + 15 runner tests pass (tests.txt). Semantics/read scope/root sequence as in v2 REVIEW.md except steps 2-3 below.

## Finding -> fix (all in `run_once.py`; tests in `test_runner.py`)
| finding | fix | where |
|---|---|---|
| AUTHORITY-2: non-PASS review, unissued phase, zero space, bad timestamp, `attempt_limit=True` accepted | independent PASS review bound to exact program/runner/request sha + once kind (`REVIEW_FIELDS`, reviewer not root/not in `authors`) | run_once.py:73 `check_review`, :96 `verify` |
| | issued phase (passed, issued, no retry, kind `root_joint_storage_v*`, free >= its minimums) + typed fresh df (ints, floors > 0, free >= floor + WRITE_BYTES, custody log/all-writer stat-only true, `unaccounted_writers==0`, utc fresh) | run_once.py:81 `check_phase_and_df` |
| | `type(attempt_limit) is int and == 1`; utc/rescan parse, fresh (<=1800 s), rescan >= utc, not future | run_once.py:100, :103 |
| TRANSPORT-2: `capture_output` unbounded, rc0+stderr = success | `execute()`: Popen in its own session, both streams read with hard caps while running (<= cap + 64 KiB held), wall deadline, `killpg` of the owned group on overflow/timeout (grandchild killed), stdin fed non-blocking | run_once.py:126 |
| | success = rc 0 AND status `exited` AND empty stderr; every outcome recorded in `result.json`, no retry, `records` must not exist | run_once.py:182 `run` |
Tests reproducing each: `test_review_refusals`, `test_phase_and_df_refusals`, `test_attempt_time_and_template_refusals`, `test_stdout_overflow_killed_and_bounded`, `test_stderr_overflow`, `test_timeout_kills_owned_process_group_including_grandchild`, `test_run_rc0_with_stderr_is_refused`, `test_run_overflow_and_nonzero_recorded_not_retried`, `test_isolated_cli_template_refusal` (documented `-I -B` command).

## Authority record formats the reviewer/root must produce (new in v3)
- review (independent PASS post or file): `passed:true, verdict:"PASS...", scope:"ROOT_ONCE_H1_G1_PACKET_A_REFS_V1", program_sha256, runner_sha256, request_sha256, reviewer_worker, reviewer_session, reviewer_model`.
- phase: the issued joint phase doc (fields `passed, issued, automatic_retry_authorized=false, kind, fresh_*_free_bytes, *_minimum_bytes` as in root-joint-storage-phase-v42). If sol-h1 prefers an existing reviewed controller for phase/resource checks, swap `check_phase_and_df`; I could not find a reusable one.
- once `fresh_df`: `{utc, models_free_bytes, results_free_bytes, models_floor_bytes, results_floor_bytes, custody_log_stat_only:true, all_writer_accounting_stat_only:true, unaccounted_writers:0}`; once also carries `authors` (every author/session of this packet and upstream).
Assumption to confirm: the field names above for review/phase evidence; free-space and custody evidence are root-attested stat-only values, not measured by the launcher. Fresh root-only once and immediate post rescan remain necessary.

## Root sequence (changed steps)
2. Root fills the once (template now includes `authors`, typed `fresh_df`, `review`, `phase`), all timestamps within 30 min.
3. `cd /tmp && python3 -I -B run_once.py <filled once>`; exit 0 only if `result.json` has `success:true` (rc 0, `status:"exited"`, empty stderr). Other steps as v2.
