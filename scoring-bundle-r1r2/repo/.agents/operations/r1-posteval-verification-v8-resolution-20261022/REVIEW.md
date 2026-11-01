# v8 post-evaluation RESOLVED packet (LOCAL; nothing captured, staged or run)

Author: claude-opus-5-5, session <SESSION_ID>. Built 2026-10-22T17:59Z, after the actual R1 v8 evaluation launch
(launch receipt 0249ab6b, commit 5c30787).

## Resolution (`resolution.json`). Each value comes from an actual, bound record; none is chosen.

| Marker | Value | Source |
|---|---|---|
| SPEC / SEAL / LEDGER | 605a67ca / 8ff41179 / f0658364 | the reviewer's postprep resolution 3de7a2e7, equal to the final spec's `spec`/`seal`/`ledger` |
| EXECUTION_SPEC | 8293ee21 | `package-v1/execution-spec.json` (the launched spec; `launched.json` binds it) |
| R1_AUTHORIZATION | c175aafa | `package-v1/r1-authorization.json`; equal to the spec's `r1_authorization_sha256` |
| EVALUATION_SUPERVISOR_PID | 531850 | `launched.json` pid, from the first metadata-only status (status-1.txt, eval_status.sh af76655b) |

## Build (once)

    cd r1-posteval-verification-v8-20261022 && .venv/bin/python -I -B build_posteval.py --resolve \
        ../r1-posteval-verification-v8-resolution-20261022/resolution.json ../r1-posteval-verification-v8-resolved-20261022

- The candidate is pins 843d54e9 (CODEPASS 69f7b2ab).
- The build gave rc 0, with empty stdout and stderr. It wrote 21 files and no `__V8_` text remains; census
  `SUPERVISOR_PID = 531850` is an int.
- The output sits beside the v7/v8 packets under `operations/`, so every `HERE.parent` relation is unchanged.

## Local checks (read-only; no suite was run)

- `verifier-r2/pins.json` and `adapter-r2/pins.json` verify against their re-pinned files.
- `adapter.VERIFIER_PINS_SHA256` equals the resolved verifier pins, and `stage_code.PINS` holds both resolved pins.
- The `CODE_SHAS` of `vrun.py` (verify_r1 5ed5229f, run_verify 32c062e3, pins af9fbefd) and of `d2.py` (adapter
  6bb3cd38, run_adapter 45851f0b, verify_r1, pins) equal the resolved files' hashes.
- Against the candidate: 14 files differ (markers plus the cascade), and 7 are byte-identical: verify_r1,
  test_verify, extract_k2c, request-k2c, test_capture, test_vrun, test_d2.

## Not authorized

Any post-evaluation real-data capture, census, K1/K2 or numerical verification, transport (T1/T2), vrun or d2
submission, labels or scoring. Each needs its own exact approval after the evaluation is terminal. The evaluation is
running, and no outcome is claimed.
