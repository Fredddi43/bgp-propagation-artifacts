# Metadata preparation execution candidate

Author `/root`; separate reviewer `/root/recovery_independent_review`.
Root pauses implementation during this review. No delegation.

Review `execute.py`, `launch.py`, `supervise.py`, `run.sh` and tests.
39 synthetic tests/Ruff/bash syntax pass. This is a code review; the final
execution spec is not built because the opaque preflight has not finished.
No transport or execution approval requested yet.

## Intended one-shot operation

Root is
`<FORECAST_ROOT>/r1-release-assembly-v3-20261021/control-v1`;
output is that root's `prepared`.
The source sibling `source` has already been independently approved/staged;
manifest SHA4363f0ea7d308adee95a46eb4797f67b1548780b37a3f08fc50250fbd4acbec5.
Control directory does not exist.

The existing exact reviewed preparation module
c42e78ac8b607ca3f896305b409ce23a1fb122d0e2aa28b145e32d74abb013ec
is unchanged. It executes the full validator once, then publishes spec, its
canonical seal, and evaluation ledger from that result. Its independent
46-test review is in the parent directory. Evaluation still requires its own
fresh full re-verification and R1 authorization later.

The new transport permits a bounded exact static file set plus separately
anchored retention/preparation/execution approvals. It validates in-memory
prospective control bytes and actual external source/preflight before staging.
Fresh root, exclusive local intents, remote stage/launch markers, source
readback and fsync; one detached supervisor and no retry. Supervisor preserves
exit status, including alarms, without exception values.

The runner requires <BATCH_HOST>/<USER>/isolated interpreter/exact runtime executable,
full static source manifest, successful hash-bound opaque preflight, independent
retention and preparation bindings. It initializes one native thread, sets
1536GiB AS, four-CPU affinity,12h wall and48h CPU limits, requires64GiB host/disk
reserves with fresh checks, and validates the resource contract/runtime before
the full metadata pass.

The audit boundary allows prepared output writes and only one exclusive seal
whose exact name is derived from the already written spec bytes. It rejects
other external mutations, spawning and network effects. The original reviewed
validator's opaque metadata-only access proof remains unchanged; neither the
audit hook nor file extensions alone are claimed to prove semantic label
isolation. No target load/scoring API is invoked by this launcher.

## Final retention draft

`../../r1-release-assembly-20261020/control-candidate-v1/draft.json`
SHA2bd4d3cf2328f9f249b50651debe3e29e08a87ad05f91159c5ab30497a092c06.
It changes the v3 pending base only by binding the approved resource contract/
resource review and approved v6 probability implementation. No families,
forecasts, labels, decisions, scientific consumers, analysis constants, or
arms change. Resource review2b752dd5 and calibration22381173 are exact prior
independent approvals. Input identity remains46c1e96cde9ebf9d53775de504706c0220280c5c4907db409325ba3e17e88002.

Driver4573658eb2b360a8b63466e35165cae9cfffda854426142c5db12a2d2d34d519;
custody2180791d8f23d41ee4e70e06de242e4a52161b2c5ebe9106b9494ea81d20826b.
All previous scientific gates remain.

## Requested outputs

Return independent code verdict and concrete findings. Do not fix files.
If supported, also issue:

- Retention review scope `r1-committed-retrospective-evaluation-v1`, passed,
  exact draft/driver/custody hashes, actual model/worker, labels/scoring false.
- Preparation review scope `r1-single-pass-metadata-preparation-v1` using the
  exact expected fields in the unchanged module (including the just-created
  retention-review hash, output literal above, preparation/driver/custody hashes,
  metadata_preparation_authorized true, labels/scoring/retry false,
  fresh_evaluation_reverification_required true).

These metadata-scope approvals do not authorize this new launch package.
Final independently bound execution spec/transport review remains required,
including successful actual preflight receipt. If that dependency prevents an
approval now, give the precise remaining condition; do not invent success.
No remote reads/writes, actual predictions/targets/labels/scoring, fits,
new-period/protected2026 or retries permitted in this review.
