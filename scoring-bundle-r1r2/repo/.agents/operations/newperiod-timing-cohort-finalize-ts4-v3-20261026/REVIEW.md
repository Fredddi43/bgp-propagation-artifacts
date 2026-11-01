# T-S4 finalize v3 - mapping of v2 findings (sol-final CHANGES)

Copy of v2 plus two fixes; v1/v2 untouched. Cohort review f907a960... reused unchanged (pinned in `request.json`). Science call unchanged (`ts4_operator.py` finalize call in BOOTSTRAP). Tests: `test_ts4_v3.py`, 98 pass (`tests.txt`). Regressions reproduced against v2 first: `repro-v2-failures.txt` (7 fail on the v2 operator).

## TS4-V2-TERMINAL-1 (rc0 with no result.json)
- Fix: `ts4_operator.py:186-216`. result.json write failure sets status `TERMINAL_RECORD_FAILED` (208); STOPPED.json attempted, then finite fallback `STOPPED.min` (209-215); return is 0 only if COMPLETED and result recorded (216). Intent/stdout/stderr preserved; exactly one exchange, no retry.
- Tests: `test_v3_result_write_failure_after_completed_transport_is_nonzero_and_stopped`, `test_v3_stopped_persistence_failure_is_nonzero_with_finite_fallback`, `test_v3_all_record_writes_fail_still_nonzero_and_no_retry`, `test_v3_intent_write_failure_is_nonzero`, `test_v3_failed_transport_with_result_failure_nonzero`.

## TS4-ADMISSION-1-MEMORY (unsupported 62.6MB decoded figure)
- Basis: `request.json` `audit_admission` + `measure-ts4-audit-memory.txt`. Exact audit size 59760447 B; decoded worst-case measured over pessimal JSON shapes at that size: max 29.7x (one-key dicts, VmPeak 1775344 kB); real unchanged finalize over a 67 MB / 7.47M-id synthetic audit peaked 12.5x. Admitted factor 32 + 256MiB margin = 2180769760 B < 4GiB AS. The old 62610227 figure (encoded size) is gone.
- Remote enforcement before the audit is read: `ts4_operator.py:73-76` (stat-only exact size and cap `TS4_R_AUDIT_SIZE`; VmSize + factor*size + margin <= RLIMIT_AS else `TS4_R_AUDIT_MEMORY`); values passed from the request `spec_for` 177. Local: derivation recomputed and tied to adoption accounting at `admission` 133 (`TS4_AUDIT_ADMISSION`).
- Tests: `test_v3_audit_admission_derivation_consistent`, `..adoption_must_account_derived_decoded_memory`, `..derivation_tamper_refused`, `..spec_carries_audit_admission`, `..bootstrap_refuses_wrong_audit_size/_oversize_cap/_insufficient_as_headroom`, `..measured_worst_case_factor_below_admitted_factor`, `..real_finalize_audit_scale_within_as`.
- Limit stated: factor is a measured bound over the pessimal shapes tried on python 3.14 here, not a proof for all inputs; remote python's version differs, hence the 32x vs 29.7x margin and the live VmSize check. No audit body was read.
