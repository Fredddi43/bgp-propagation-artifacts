# One diagnostic operation after opaque metadata verification failure

Root author; separate reviewer required. User explicitly directed diagnosis.
Only the reviewer is active during this review; no remote execution by reviewer.

Observed: approved metadata preparation control-v1 exited1 at23:14UTC after
~2h51. Only attempt.json, no specification/ledger/complete or unblinding marker.
Its stderr records ValueError only. Exact terminal capture is included; no
claim about which check failed. This is not a timeout and not a passed attempt.

Request one new diagnostic-only stage/launch, never reopen or mutate the old
attempt. `probe.py` verifies the unchanged old package with its exact historical
anchors, source manifest and terminal bytes. Those old approvals establish
source identity only; the new operation needs your exact independent approval.

It checks inexpensive probability-calibration and frozen-recipe prerequisites
first, using the original helpers and read bounds. On success, it runs the
unchanged complete custody.verify_batch with the same26 families, same draft,
retention review, source and512GiB/2GiB byte limits. Each existing format adapter
is wrapped solely to emit a fixed phase, bound family ID and retained byte count;
arguments and returned objects remain unchanged, and dispatch is restored.
It records bounded exception type and20 code-location frames, never messages,
source lines or locals. No forecast or label decode, model action, scoring,
publication, R1 opening, N access or retry. A successful diagnostic does NOT
substitute for later metadata preparation or evaluation re-verification.

The bound original read-only audit boundary permits writes only inside the new
attempt directory and prohibits spawning/network/other mutation after installed
Torch/bootstrap imports. It is an operation boundary, not a semantic proof that
arbitrary code cannot decode data; the unchanged reviewed custody path supplies
that separation. No preparation/evaluation function is called. The old package's
resource checks provide fresh1536GiB+64GiB reserve; processAS1536GiB,48hCPU,
4CPUaffinity/native threads1,12hwall. Supervisor retains terminal return code,
including alarm, with no retry. Existing sources and failed artifacts unchanged.

Local `launch.py` has one durable intent, one bounded exact package transfer and
one exclusive remote root. No automatic retry after any uncertain result. Remote
bootstrap checks host/user/isolated context, stages exact bytes read-only,
readbacks, checks failed predecessor/resources/source, then starts a detached
supervisor with clean environment. Outputs confined to
B/r1-failure-diagnostic-v1-20261021 (B is unchanged forecasting-20261017 root).
No staging or launch has happened. 26 synthetic tests/Ruff PASS.

Please independently verify code and exact spec; if supported, write review.txt
and approval.json here, plus reviews/verdict.json. Approval schema:
- scope r1-failure-diagnostic-v1; passed true; actual reviewer gpt-6-astra,
  distinct reviewer_worker; exact spec_sha256 and review_text_sha256;
- diagnostic_execution_authorized true, transport_authorized true, attempt_limit1;
- every probe.DENY field explicitly false (including publication and old retry).
No source changes, no remote operations, no extra agents, no outside messages.
If unsupported, preserve findings and withhold execution approval.
