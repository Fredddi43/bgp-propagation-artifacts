# Exact independent recovery decision and execution review requested

Author `/root`; reviewer `/root/recovery_independent_review`.
Root pauses implementation. No delegation, remote execution or actual-data reads.

## Terminal evidence: old attempt failed to finish

The previously approved full opaque preflight PID4181630 is a zombie with
Linux wait status14, decoded by `os.WIFSIGNALED` and `os.WTERMSIG` as SIGALRM.
Its bound source scheduled a14400-second alarm. It started around16:13UTC and
the watcher observed termination20:13:26UTC. No complete/failed receipt and empty
stdout/stderr. This is an incomplete time-limited attempt, **not a passed
provenance verification**.

Exact captured metadata:
`../../r1-full-custody-preflight-20261020/observations/terminal-20261020T2013.json`
SHA27cb2d57334dbaca0ab19611c224bf06f4e8e8ae9fe7fb5d7fb7311a3f6fe554.
It contains the original started marker, empty logs and proc stat/status/cmdline
as base64. The adjacent watch JSONL records read-only observations. No scientific
values were captured. Original attempt and its source are unchanged.

## Proposed recovery; please decide it explicitly

Do not repeat the standalone opaque preflight. Authorize one fresh metadata
preparation operation that performs the **entire** original `verify_batch`
itself and only then publishes the specification, canonical seal and ledger.
It was already a required fresh full pass; this removes an extra standalone
successful-pass prerequisite, not any check inside the preparation or evaluation.
No reuse of partial results, skip, cached verdict, reduced families or
scientific-input change. Later evaluation still fully re-verifies all inputs.

The standalone preflight was intended to establish provenance/resource
evidence before release. Actual label/runtime bounds now have separate reviewed
header/producer/source evidence and resource approval; initial preflight success
was explicitly not assumed by that approval. A20:05UTC observation recorded
392057084KiB RSS under1536GiB AS; this is descriptive, not a complete memory
bound, final peak or proof of all inputs. Preparation retains the hard1536GiB limit,512GiB
raw-cache cap,2GiB file cap and fresh host/disk guards, and now has12h wall time.
A verification failure publishes no spec, seal or ledger. Later publication
failures preserve partial output; no automatic retry.

This is a new proposed independent recovery decision. No earlier approval is
being treated as permission to retry. If a separate successful opaque pass is
scientifically necessary beyond the complete preparation validation, explain
the remaining check; do not silently approve a weakened gate.

## Narrow changes from reviewed execution-v1

- `execute.py` requires explicit recovery flags in the execution approval.
- It checks the pinned terminal capture: matching actual original started
  marker/scope/spec, zombie/empty-cmdline/SIGALRM kernel witness, no successful
  receipt, no live old command and no changed old terminal state.
- The old incomplete attempt is never counted as passed. All new preparation
  semantics, source/runtime hashes, resource guards, exact seal write boundary,
  once-only markers and supervisor are unchanged.
- Transport includes the extra exact terminal evidence file.
- Existing retention/preparation approvals remain byte-identical because the
  final draft, preparation module, driver, custody, output and required full
  verification do not change. They alone still cannot authorize this launcher.
- 52 synthetic tests/Ruff/bash syntax pass, including rejecting wrong signals,
  live processes, changed/missing evidence, pass claims and absent recovery
  authority.

## Exact package

`package/execution-spec.json`
SHA3038a3560ae8a3f8cb2ee1bef6885c6a6da92e6cfefc956fa8047ac40bde8839.
All static hashes and resources are inside it; package has15 current files,
awaiting only execution approval and its review text. Prospective control root
is the same uncreated `.../r1-release-assembly-v3-20261021/control-v1`;
prepared output is `/prepared` below it. No staging or execution has occurred.
Current approved source v3 is unchanged.

Please verify all exact bindings and source deltas, the full-verification
invariant and recovery rationale. If supported, write independent review,
verdict and execution approval with:

- `scope:r1-single-pass-metadata-execution-v1`, `passed:true`;
  actual reviewer model and independent worker.
- Exact spec, launcher and review-text hashes.
- `retention_review_sha256:daadafb2d1e44aa85d8485f68e58b0f5aa3a4e2d241307a68068dd580ee65563`.
- `preparation_review_sha256:2bf9ac8d77e335b971efa837bfc8b9034b9ad941f75a684f5ec1c1c78e80838d`.
- `transport_authorized:true`, `metadata_execution_authorized:true`,
  `attempt_limit:1`, `preflight_timeout_recovery_authorized:true`,
  `fresh_full_metadata_verification_required:true`,
  `incomplete_preflight_accepted_as_pass:false`,
  `old_attempt_retry_authorized:false`.
- Every `execute.FORBIDDEN` field false (including labels, scoring, prediction
  decoding, fitting/prediction, R1, new-period/protected2026, automatic retries).

Only the owner may stage/launch after this exact review. No actual scientific
access by the reviewer, no fixes, no previous-attempt mutation, no new workers.
If unsupported, return concrete blockers and no execution approval.
