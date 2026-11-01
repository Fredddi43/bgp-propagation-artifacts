# T-S4 finalize v2 - mapping of reviewer findings (sol-final CHANGES on v1)

Operator: `ts4_operator.py` (v1 was `operator.py`, shadows stdlib `operator` when cwd is the packet; v2 renamed). Tests: `test_ts4_v2.py`, 84 pass (`tests.txt`).
Cohort review (PASS, reused unchanged by hash f907a960...): pinned in `request.json` `cohort_review`; `ts4_operator.py:146-148`.
Science call unchanged: `ts4_operator.py:83` (same `pc.finalize(audit, review_ref, receipt)`), request fields equal v1 (`test_science_call_identical_to_v1`).

## TS4-ADMISSION-1
| Requirement | Code | Test |
|---|---|---|
| bind newest issued phase + full floors | `validate` 148-149 (phase_compat accept, bound V44, own row `timing_protected_cohort`); floors passed `spec_for` 167-176; remote check `BOOTSTRAP` 57-60 | `test_full_check_positive...`, `test_floors_and_phase_pins_passed_to_remote`, `test_bootstrap_admission_refusals[floor]` |
| root all-host/runtime/writer/resource adoption | `admission` 120-140 (runtime reuse/immutable, imports, local+remote memory incl. decoded 59.7MiB audit and 3 local processes, output funding, no allocation credit, all writers growth) | `test_admission_each_missing_field_refused` (19 fields), `test_admission_value_failures`, `test_native_check_refuses_authority_with_admission_fields_absent` (reviewer repro) |
| stat-only shared custody identity + EOF/growth ceiling | `BOOTSTRAP` 61-65 (`lstat`, never opened), devices 66-67, MemAvailable 68-70 | `test_bootstrap_admission_refusals`, `test_bootstrap_never_opens_custody_log`, zero-append byte check in `test_bootstrap_mints_receipt...` |
| immediate board + 4 old-dir acknowledgments, unused authority | `controls` 111-118, `validate` 161-164, re-validated right before consume `run` 215 | `test_full_check_positive_and_stale_controls_refused`, `test_consumed_authority_refused` |
| fund/limit 2 remote files + local records, keep T040 reservations | request `resource` (remote_output_max 128MiB, local records 4MiB); `admission` funding checks; own row must equal request own_rows | `test_admission_value_failures` |
| runtime/imports | adoption declares imports; bootstrap compares stat identity of every loaded module before/after finalize (`BOOTSTRAP` 80-86) | `test_bootstrap_mints_receipt...` |

## TS4-TRANSPORT-1
| Requirement | Code | Test |
|---|---|---|
| live stdout/stderr caps, process-group kill/reap, one exchange | reviewed `transport.py` (byte-identical to S2 v4), used in `consume` 180-203 | `test_transport_stdout_bound_live`, `..stderr_bound_live`, `..timeout_kills_process_group_descendants`, `test_only_one_exchange_no_retry`, `..byte_identical_to_s2_v4` |
| remote self-timeout, finite CPU+AS+wall | `BOOTSTRAP` 54-57 (SIGALRM 540s, RLIMIT_CPU 540s, AS 4GiB) below local wall 600s; local rlimits `run` 210-213 | `test_bootstrap_remote_self_timeout...`, `test_bootstrap_alarm_actually_terminates` |
| fixed sanitized outputs, 0 custody appends, nonzero own FSIZE (64MiB) | remote errors map to `TS4_R_*` codes only (`BOOTSTRAP` 92-94) | `test_bootstrap_refuses_wrong_review_sanitized`, `test_nonzero_own_file_fsize` |
| terminal records every path, STOPPED, no retry | `consume` 180-203 (result.json always attempted, STOPPED.json when not COMPLETED, write failure is never success) | `test_terminal_records_all_paths`, `..exception..`, `..write_failure_after_completed..`, `test_completed_path_no_stopped` |

Residual (stated, not hidden): the remote bootstrap spawns no child itself and the kernel finalize path imports no subprocess/multiprocessing at module level; there is no remote process-group reaper beyond SIGALRM and sshd HUP on channel close. Module identity is stat-based (size/mtime/inode), not content hash.

## TS4-INDEPENDENCE-1
| Requirement | Code | Test |
|---|---|---|
| nonempty distinct worker/session/model; exclude root aliases and actual author session | `independent` 102-109, `identity` 97-100, used for both cohort and execution review (`validate` 150-154) | `test_independent_negatives` (26 cases: `/root`, `ROOT`, `//root//`, author session in any case/slash form, empty/None/bool, passed/authorized non-True), `test_cohort_review_independence_gate...`, `test_full_check_refuses_root_execution_review_and_author_session` |
| `attempt_limit` type int ==1 | `validate` 144 | `test_attempt_limit_true_refused_and_int_one_required` |
| exact request/operator/cohort-review pins | `validate` 143-146,153-155 | `test_exec_review_pins_bound` |
