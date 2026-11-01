# Final data validator review — 2026-10-30

Verdict: **CHANGES REQUIRED — two remaining scientific consistency gaps.** This reviews the validator implementation; the actual experiment remains incomplete while its dry run prepares origin and has no ready record.

Exact bindings:

- `audit/validate_final_data.py`: SHA-256 `0ded649343e2bcec69baca886835524fe09927b5b8740204c939a07856532c8a` (preserved as `review-validator-snapshot-rev4.py`).
- `audit/test_validate_final_data.py`: SHA-256 `d1703de5b9d63641597521851420ec394cb4e9de2a2d04d2104e81a53ed72387`.
- Approved producer `g2r2/chain-d39-v2/r2_rescore_secondary.py`: SHA-256 `bce67ffcbcb10d1a246a74da4951a7ffffcad61af3f93ea55075958182d4c8d8`.
- Approved parallel adapter `g2r2/chain-d39-v2/r2_parallel_scoring.py`: SHA-256 `97c1f295565ef469e0ae486e3c630cdb70e1ca8500a316a5c88314065df0e422`.

## Remaining blockers

1. **P1 — Raw aggregate primary is not compared with the verified primary.** Validator lines823-828 requires only `"primary" in agg`; lines835-838 compare the nine secondary sidecars and leave the aggregate primary unexamined. A legal complete fixture whose raw aggregate `primary` is replaced with `{}`, with its persistence receipt updated, still returns `--require-complete` PASS/exit0. The immutable original and the independently checked recomputed JSON remain valid, so this specifically proves the aggregate report can silently omit its primary data. The producer's `components/composition/compose.py:79-88` puts the actual primary report in `result['primary']`; producer `finish` persists that same result as raw output. Require that raw primary canonically matches the verified recomputed primary (and therefore the original with the one allowed marker exclusion). This is a comparison of existing values, not statistical recomputation.

2. **P1 — JSON scientific values may disagree with the validated raw result.** Validator lines841-854 compares JSON top-level key sets, membership/origin families, coverage names and cell identity sets, then reports `"JSON secondary parsed and composed identically"`. It never compares the cell statuses, roles, scientific values or even `secondary.kind` with the raw aggregate. Changing one JSON counts-cell status and changing JSON `secondary.kind` to an invalid kind, updating only the JSON persistence receipt, still returns final PASS while the raw aggregate and all nine sidecars stay unchanged. For decoded documents within the existing bound, compare normalized scientific JSON values against the producer's JSON projection of the raw secondary (including kind, flags, statuses, roles and values), or reject mismatches with equivalent checks. The producer's `finish:1001-1019` constructs JSON secondary directly from `result` minus primary, so these views must agree. For documents above the existing cap, raw result plus recorded output bytes can remain the explicit authoritative proof; do not claim an independent JSON-value equality check that was not performed. This small-document counterexample requires no new multi-GiB parser, label read or scoring run.

## Verification completed

- Ran the supplied suite: **28/28 mock probes passed**.
- Verified current fixtures use nested artifact receipts,64digit fingerprints and production `binding_of`, complete actual approval fields, the exact eleven-file code map and parallel options/cap.
- Independently compared validator and approved production `binding_of` on a legal nine-stage fixture: identical canonical items and digest.
- Independent small-fixture probes reproduced both remaining false PASS cases. Script: `review-validator-probes-rev4.py`; output: `review-validator-probe-results-rev4.jsonl`.
- Confirmed the previous completion nesting, raw-bytes split handling, full approval/ready/checkpoint binding chain, D-A39 marker reference graph, direct canonical primary comparisons, and final-mode inventory requirement are now implemented against the actual producer schema. The395 evaluated +5 retained/excluded identity accounting remains correct.

No requested implementation changes were authored by the reviewer. No label contents or real scientific artifacts were read or changed; no cluster mutations, job actions, giant inventory scan, external messages, signals or git writes were performed.
