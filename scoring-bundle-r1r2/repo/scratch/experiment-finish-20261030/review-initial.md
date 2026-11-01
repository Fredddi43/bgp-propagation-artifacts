# Initial independent experiment completion review

Verdict: changes required before the D-A39 label-opening run. This review covers experiment completion only; it does not review the paper. The reviewer changed no experiment artifacts or source code.

Reviewed source bindings, relative to `.agents/operations/agy-lanes-20261027/g2r2/chain/`:

| File | SHA-256 |
| --- | --- |
| `r2_rescore_secondary.py` | `dee6d9a2aba9c312e00a69eb2f4bd38d0b6c0304789cbbfcd40bdadb09f5d0bb` |
| `r2_float32_scoring.py` | `4896b740bfec1b647d9db5d9bfa343f40a68f986ba9fa26c94a232bccf84edf8` |
| `r2_rescore_secondary.sbatch` | `505484f43dc1ac73acc4f1aecb05124850e97ac1f8d971b01c6bd5a0d0ac1a0a` |
| `r2_float32_offline.sbatch` | `8af59167e34f7e3f8b80f8befcc09d02226bbb7bbc985740f61def868c63a0d7` |

## Required changes

1. **Completion can falsely pass.** `r2_rescore_secondary.py:640-646` ignores both primary comparison booleans and expected secondary callback coverage. A direct in-memory probe of `finish`, with all output I/O mocked, returned `passed: true` for `families=[]` and both primary comparison booleans false. Require both comparison booleans to be exactly true and exactly nine callbacks once each: `counts`, `membership-h1`, `membership-h3`, `membership-timing`, `membership-history`, `membership-ordinary`, `stable`, `origin`, `additional_baselines`. Require successful durable results or explicitly declare unresolved persistence failures/incomplete output. A failed family remains an explicit failure, never a successful numeric result.

2. **Approved dry-run preparations are not bound to the open run.** `verify_approval` verifies code hashes, but the open run never compares its loaded checkpoint digests with the approved ready record. Legacy loading verifies size and fingerprint header, then computes a fresh content digest without comparing it with the dry run. Rolling loading verifies a fingerprint but has no content digest. Bind all preparation inputs to the approved ready record before creating the second-read marker.

3. **Correct the attempt-12 failure account.** The ledger at `qwen/q11-deviations/DEVIATIONS-LEDGER.md:431` and the driver's introduction say no secondary outcome was computed. The pinned count consumer's `evaluate_with_counts` runs primary evaluation, then `score_counts`, before composition starts membership evaluation. The recorded membership crash therefore occurred after counts were computed. Appropriate wording: no complete secondary report was persisted/released; count scoring ran before the membership failure. Do not claim that the entire secondary computation was untouched.

## Exact checkpoint receipt contract

Use an order-independent map keyed by `(stage, full fingerprint)`, with exactly the expected nine preparation calls (one origin, one baseline, one counts, five members, one stable). Reject duplicate keys, missing keys and extra keys. Keep elapsed time and other runtime-only fields outside the comparison.

- **Legacy receipt:** exact source format, canonical path, full fingerprint, file byte length, and SHA-256 of the bytes actually consumed by `load_legacy`. Retain its expected stage/header/size checks. Open mode must match every field to the approved ready receipt.
- **Rolling receipt:** canonical manifest path, exact manifest byte length and SHA-256; validated manifest stage, full fingerprint and positive integer part count; ordered part receipts containing index, canonical expected path, byte length and SHA-256. Hash the actual bytes loaded, or verify identity before/after hashing and loading, so receipts cannot describe different bytes from the unpickled preparation. Require a complete single pickle with no trailing bytes. Open mode must match the whole receipt to the approved ready receipt before the label marker.
- **Origin computed during a dry run:** the dry run may compute and save origin once. It must record the successfully saved rolling artifact with the same manifest/parts receipt that the open run will load. Open mode must refuse recomputation or a failed/missing rolling save. If that artifact is already present during the replacement dry run, use its full rolling receipt without recomputing origin.
- **Approval:** retain the ready record path/hash and current code hash checks, and carry the approved checkpoint receipt map into pre-label validation. A replacement cached label-free dry run supersedes the old ready record after any driver fix.

The current fixed legacy assumption is acceptable: counts, baseline, all five membership preparations, and stable must still load the named attempt-12 `.pkl` files. Current preference for a rolling file would shadow a legacy file, but the pre-label legacy-source check rejects it. Prefer an early explicit refusal on shadowing. Do not silently relax the requirement. The existing dictionary keyed only by stage collapses the five members entries, so exact checks should examine every preparation receipt rather than only the final source for a stage.

## Required focused validation

1. Unchanged legacy and rolling receipts pass; elapsed times may differ.
2. Same-size legacy mutation with unchanged fingerprint/header fails before marker creation.
3. Same-size rolling part mutation, manifest byte mutation, changed part order/count, missing part, trailing pickle bytes, and changed stage/fingerprint each fail before marker creation.
4. Missing, extra or duplicate preparation receipt fails; all five membership fingerprints must be checked.
5. Open-mode origin recomputation and failed save fail before marker creation; a cached label-free replacement dry run succeeds without recomputing origin.
6. Either primary comparison false/missing prevents completion; a missing, duplicate, unknown or failed scoring callback prevents completion. Retained scientific not-estimable cells inside a successfully scored family remain valid dispositions.
7. Output persistence failure produces an explicit incomplete state. The complete positive case has all nine scored callbacks, both primary comparisons true, exactly one label read, and durable result receipts.
8. Dry run never reads labels or writes a second-read marker; repeated open mode refuses an existing target/marker.

## Checks already completed

- Original primary artifacts are read through pinned hashes; recomputation writes separate paths.
- Original one-opening marker remains intact; the new second-read marker is exclusively created in a separate target directory.
- Dry-run label guard and Reader's once-per-run label restriction remain in place.
- The float32 patch changes only the private membership consumer's committed global comparison. Primary, origin, stable and additional-baseline modules remain unchanged, as do ranking metrics, cohorts and retained failures.
- A synthetic float32(0.94) boundary row reproduced the original refusal and the patched committed selection. The original shared scoring module remained unchanged.
- Driver and patch Python syntax parse; both sbatch scripts pass `bash -n`.

These checks do not approve opening labels with the initial driver. A successor needs independent review and a fresh, code-bound label-free ready record.
