# Independent combined D-A39 successor review

Review clock: 2026-10-30 13:35:35 UTC. Verdict: APPROVED for the exact source set below, including its replacement label-free dry run. No code blocker remains. The one authorized second label read still requires a fresh v2 ready record, its exact approval binding, and unchanged source/artifact digests. This is a code review, not certification of an execution outcome or release authorization.

Reviewed directory: `.agents/operations/agy-lanes-20261027/g2r2/chain-d39-v2/`.

| Runtime file | SHA-256 |
| --- | --- |
| `r2_rescore_secondary.py` | `bce67ffcbcb10d1a246a74da4951a7ffffcad61af3f93ea55075958182d4c8d8` |
| `r2_parallel_scoring.py` | `97c1f295565ef469e0ae486e3c630cdb70e1ca8500a316a5c88314065df0e422` |
| `r2_rescore_secondary.sbatch` | `b1e850c6dfda4c536cd03c8a8acd581612f9151e88a4a44324028f7521e3e49e` |
| `r2_float32_scoring.py` | `4896b740bfec1b647d9db5d9bfa343f40a68f986ba9fa26c94a232bccf84edf8` |
| `r2_checkpoint.py` | `97382e4abe67240152e5c01763eb970b0fc5c32eedfb77f0e7453d3dcb580be4` |
| `r2_exec.py` | `3cee152145559f52141ce49b987dbb4b8672ce89432ac4e78863fd815d0162a3` |
| `r2_parallel_origin.py` | `db1b4b403bdebc44c635aa012bdd18a17cc8c2849d285aca9ab049866139d174` |
| `r2_float32_decision.py` | `c26a6d35996c733044ffe246966ab671160106e3e447fe051571143ba8f42c8e` |
| `r2_stable_persistence.py` | `e4cc468f1b52fdf95d75caee78194f13d1ccbd690718476c4e7e7b5f90fb98a4` |
| `r2_input_cache.py` | `b18b9b8ab5b358f6b6964c574884b77e06f45a10febb3075cfa0fa91127d60b2` |
| `r2_fast_authorize.py` | `4aa818d68d4446a5ec521827cdfcc6b2160700979806dab3d359d7e49e545855` |
| `r2_fast_json.py` | `f30a855b5ad5ea56d50f8c6ca50f15a3cdbbb8b7ec208d074b01678da31acd59` |
| `amend_wiring.py` | `a08c073e98112ff501d5f3c52e9de87a865dde6915afd301653ad51ed86169b2` |
| `d60_only.py` | `3c84b0f138004cb59b036a06cf3faf6e00fcc5fd2b27e9f70f0cbf7e4fbde0c3` |

## Review findings resolved

- The approved completion helpers and `finish` are AST-identical to the independently approved finish patch. Primary and primary-score equality are mandatory; exactly nine expected families must be scored once and persisted with verified lengths/digests; composition coverage is checked; failed families remain explicit; a separate exclusive completion record is durable before return/refusal.
- The approved checkpoint functions are AST-identical to the independently approved checkpoint patch. All nine full stage/fingerprint/artifact bindings are compared against the approved ready record before the marker; every legacy source is checked; open mode cannot recompute a missing preparation; old rolling origin checkpoints are hash-derived during loading and remain compatible.
- Eleven unchanged runtime modules, including the checkpoint module and float32 scorer, are byte-identical to the original chain. The stage-key source lists do not include the new post-preparation adapter, so installing it does not invalidate the existing preparation fingerprints.
- Parallel adapters attach only by rebinding each secondary consumer's own `scoring` and `original` references to private module copies. Membership's float32 scoring is selected first; stable/origin/additional-baseline scoring remains float64. Shared scorer/evaluator attributes and the primary evaluator retain their exact function identities. Every successful family still executes all original per-row validation and arithmetic.
- The hard cap of eight now applies even when both configurable worker counts are oversized, with smaller affinity and row counts lowering it. Automatic cyclic GC is disabled before fork, remains disabled in children and the parent's prior state is restored after worker drain, including exceptions.
- Valid admitted outputs are exactly equivalent and ordered. The accepted limitation for several independent invalid `per_event_rows` inputs is documented and tested: both paths refuse the entire family, while the particular original validation/scoring error surfaced may differ. No admission was weakened.
- Ready/open checks bind the adapter's SHA-256, fixed options (`max_workers=8`, `min_parallel_rows=8192`, `chunks_per_worker=4`) and hard cap. The sbatch entry points at the separate v2 directory, retains a fresh isolated environment and no-requeue policy, and preserves the original live chain.

## Independent verification

Executed the five focused suites together on the combined bytes with repository Python 3.12, bytecode writing disabled and pytest cache disabled: **62 passed in 14.84 seconds**. The suite includes real pinned component loading, private/shared function identity checks, checkpoint-key stability, adapter/options drift refusal, byte-corruption refusals, completion refusals, real scorer output equality, mixed invalid-input fail-closed behavior, worker limits and GC-state restoration. Driver/helper AST parsing and sbatch `bash -n` also pass. The final synthetic per-event benchmark records exact equality at 2/4/8 workers; it is supporting local evidence, not a full-scale memory guarantee.

No labels, experiment artifacts, source originals, live jobs or cluster state were changed by this review.

## Concrete next action

After the owner deploys and verifies this exact runtime hash set on the cluster, and after the original dry run has finished writing its origin rolling manifest and every named part, submit the new label-free job through the dispatch host:

```bash
ssh -o BatchMode=yes <SUBMIT_HOST> 'sbatch --export=NIL <RESULTS_ROOT>/nobackup/g2-chain-20261029T001120Z/repo/.agents/operations/agy-lanes-20261027/g2r2/chain-d39-v2/r2_rescore_secondary.sbatch dry-run'
```

Waiting for the origin manifest is material: starting a replacement dry run while the original is still writing parts but has not published its manifest could enter the dry-run recomputation path and collide with those partial checkpoint filenames. Once the original has published the complete rolling checkpoint, the replacement may load it while the original continues its read-only decision check. Verify replacement stage receipts show `origin` loaded from the rolling checkpoint and all eight other preparation calls loaded from their fixed attempt-12 legacy files. Its ready record must show zero label reads and no second-read marker. The old ready record cannot authorize the changed driver.

The open job may proceed only with the new ready record's exact digest bound by the existing D-A39 authorization and unchanged sources/checkpoints. Its final audit must verify one label read in that run, both primary comparisons true, all nine scored family callbacks, intact output receipts and a successful completion record. The cumulative history remains one original opening plus the one disclosed second opening; no further opening or automatic retry is approved here.
