# Packet B v3 (author: sonnet) — fixes H1-G1-B-BUDGET-2 and the inherited A transport/authority findings

Status: FALSE template, `execution_authorized=false`, preliminary until A is accepted. Supersedes v2 (preserved). 19 packet tests + 15 runner tests pass (tests.txt). `run_once.py` = A's v3 launcher with `ONCE_KIND=..._PACKET_B_PUBLISH_V1`, `PROGRAM_NAME=publish.py`, `TIMEOUT_S=900`, `WRITE_BYTES=64 MiB` (df must cover floor + 64 MiB); `test_runner.py` is byte-identical to A's (see A REVIEW.md for AUTHORITY-2/TRANSPORT-2 mapping).

## H1-G1-B-BUDGET-2 (finalizer bytes entered the cap after being written; FSIZE is per-file)
- Cumulative budget is charged BEFORE any file exists: `charge()` (publish.py:165) checks final-file count, apparent bytes and 4 KiB-rounded allocated bytes against `BUDGET`, used by both our writes (`write_new`) and the finalizer.
- The pinned kernel bytes are untouched. `budgeted_kernel_write` (:172) replaces only the module-level `write` of the exec-ed kernel (`k.write = ...`, :224): identical serialisation (`json.dumps(sort_keys, allow_nan=False)+"\n"`, exclusive create) but it charges first and never creates directories. `test_budgeted_kernel_write_is_byte_identical_to_pinned_kernel` compares bytes with the unpatched kernel.
- Reviewer's scaled counterexample reproduced as `test_B_BUDGET_2_cumulative_cap_enforced_before_finalizer_write` (cap 5000 B): refusal `E_BYTES_BUDGET`, finalized audit does NOT exist, only the review copy remains. `test_allocated_rounding_and_file_cap` covers the allocated and file-count caps.
- Partial attempts: any failure after the first write raises `PublishRefused` (:186) carrying `partial_report()` (:191: every retained file with size and allocated bytes, `deleted:0`, `retry_authorized:false`); `__main__` prints it on stderr (which the v3 launcher records and treats as a failed run). Nothing is deleted or retried.
- Doc correction: `RLIMIT_FSIZE` (64 MiB) is only a per-file backstop; the cumulative limit is `charge()`. Allocated-byte/temporary-file bounds still need re-checking in the actual-bound physical packet (as the reviewer asked).

Everything else (gate/audit typing, consumer adapter, review copy, root sequence) is as v2 REVIEW.md, with the v3 launcher authority record formats from A's REVIEW.md (review `scope` = `ROOT_ONCE_H1_G1_PACKET_B_PUBLISH_V1`).
