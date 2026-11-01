# Final data validator review, rev5 — 2026-10-30

Verdict: **APPROVE the validator implementation at the exact hashes below.** No blocking findings remain from the reviewed changes. This does not certify finished experiment data: the actual run is still label-free origin preparation, with no ready/final outputs available for validation.

Artifact bindings:

- `audit/validate_final_data.py`: SHA-256 `e1302c03c56fdab57092851cfbafeb007def814ff5be4560263395f5a214fad2`.
- `audit/test_validate_final_data.py`: SHA-256 `4bd958949b0bc32fdd38975025001c0bd70202a1e5bdea997efe0e539831794d`.
- Approved producer `g2r2/chain-d39-v2/r2_rescore_secondary.py`: SHA-256 `bce67ffcbcb10d1a246a74da4951a7ffffcad61af3f93ea55075958182d4c8d8`.
- Approved parallel adapter `g2r2/chain-d39-v2/r2_parallel_scoring.py`: SHA-256 `97c1f295565ef469e0ae486e3c630cdb70e1ca8500a316a5c88314065df0e422`.
- Reviewed validator snapshot: `review-validator-snapshot-rev5.py`.

## Resolution of the final two findings

The raw aggregate's actual primary now canonically matches the independently verified recomputed primary. Replacing the aggregate primary with an empty dictionary fails final validation even when its persistence receipts are updated and every primary file/secondary sidecar remains intact.

The JSON secondary now undergoes full scientific-value equality against the raw aggregate through the producer's `_default`/`_stringify_keys` projection rules. Changing only JSON cell status and result kind fails final validation even with a matching updated JSON receipt. The projection preserves legal tuples, sets, non-finite values and mixed dictionary keys under the producer's existing encoding rules.

Final/deep mode refuses PASS when document size exceeds `--json-deep-cap`. The conservative default256MiB cap is acceptable: the operator can explicitly raise it to the actual document byte count on the batch host with adequate resources. This is an allocation/read bound, not a bypass of scientific-value verification. Independent boundary tests confirm a cap equal to the actual document bytes passes, while one byte lower fails.

## Evidence

- Supplied suite: **33/33 probes passed**, run locally with `PYTHONDONTWRITEBYTECODE=1`.
- Independent regression/boundary suite: **8/8 checks passed** in `review-validator-probes-rev5.py`; output retained in `review-validator-probe-results-rev5.jsonl`.
- Independent checks covered the legal production-shaped baseline, equality of validator/production preparation binding outputs, exact/undersized JSON caps, both previous false-PASS cases, missing final outputs, and a valid tuple/set/NaN/mixed-key JSON projection.
- Reviewed the rev4→rev5 source changes and compared encoding helpers with the approved producer. The previously reviewed completion/marker/approval/code/checkpoint graph, all-nine-family persistence, original primary preservation,395 evaluated plus5 retained exclusions, and mandatory final inventory proof remain intact.

The eventual scientific completion claim requires an actual `--require-complete` PASS over the finished production artifacts, using an explicit sufficient `--json-deep-cap` if needed. No claim of such a production PASS is made here.

Only review notes, snapshots and synthetic probe artifacts were written. No implementation fixes, label reads, real scientific artifact changes, cluster writes, job actions, giant inventory scan, signals, external sends or git writes were performed.
