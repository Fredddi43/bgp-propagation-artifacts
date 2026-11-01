# Independent checkpoint-binding review, round 2

Review clock: 2026-10-30 13:17:28 UTC. Verdict: APPROVED for the checkpoint-binding scope. This does not approve opening labels; the combined driver, scoring adapter and fresh bound dry run remain separate gates.

Exact reviewed copies:

- `checkpoint-author/chain/r2_rescore_secondary.py`: SHA-256 `7a1fa44d453dbaec38a8a4536a28537eee6ad534b2a9c750395ffe40ba8da633`.
- `checkpoint-author/chain/test_r2_rescore_binding.py`: SHA-256 `9116d60ab33a17cccf1f200ce82a55c372b26cd482eac9112e2a420da7ca1cf2`.
- Unchanged `r2_checkpoint.py`: SHA-256 `97382e4abe67240152e5c01763eb970b0fc5c32eedfb77f0e7453d3dcb580be4`.

The round-1 findings are resolved for the fixed production paths and pinned checkpoint contract. Open mode refuses a missing origin checkpoint before invoking preparation or saving anything. Every legacy-stage receipt is checked individually, including all five membership fingerprints, and rolling shadow manifests are refused before loading. Rolling manifests validate stage, fingerprint, bounded metadata length and a finite part count before constructing the reader; parts have regular-file and per-part size checks. Binding records now include full absolute artifact paths, reject duplicate paths and require one manifest plus contiguous expected part names.

Legacy hashes cover the bytes actually consumed by unpickling. Rolling reader hashes every consumed part, verifies trailing-byte absence and checks optional manifest part attestations. The writer captures part hashes while saving and records the manifest's hash. Origin's computed-and-saved dry-run receipt and subsequent rolling-load receipt normalize to the same artifact binding. Open mode compares all nine stage/fingerprint/artifact bindings against the SHA-bound approved ready record before creating the label marker. Old-format rolling checkpoints remain loadable and receive derived byte receipts without recomputation. Failure accounting correctly records that attempt-12 count scoring ran before its membership failure.

Independent validation: `12/12 tests passed`, including same-size legacy mutation, rolling part/manifest changes, old-format rolling loading, multi-part reader compatibility, missing/duplicate stages, immediate no-recompute refusal, non-final membership source checks, rolling-shadow refusal, stage/count/manifest-size/part-size bounds and full-path/structure binding. No source originals, labels, cluster state or experiment artifacts were changed.

Scope note: path validation is lexical and the production checkpoint directory is fixed by the hash-bound base specification. This approval does not authorize relocating checkpoint artifacts or substituting symlink-based paths. The integration must preserve the current checkpoint module bytes and stage-key inputs.
