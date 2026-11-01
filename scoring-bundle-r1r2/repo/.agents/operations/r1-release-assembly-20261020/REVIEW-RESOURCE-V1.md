# Combined resource candidate — independent review requested

Author: `/root`. Separate reviewer: `/root/recovery_independent_review`.
Root pauses implementation while this review runs. No delegation.

Review the local `resource-candidate-v1` and `build_resource_candidate.py`.
These are proposed certificate payloads, not author-issued approvals. The
wrapper explicitly records resource admission and execution as false.
No control files have been staged. No final retention draft exists.

## Exact chain

- Staged source v2: candidate `6634eee62cdf356a24bac51644f85b32e4673161de483069ed41940cfba46d90`.
- Driver v5: `3f4eaed2f5f7d46a26d9bd9492aab0afdc4181d1cb0226399b1cc57aa16ed16a`.
- Input identity: `56101e75c7acd3cc67acd8f9df8ef72aa93e65d0d24f9cf3b3059eb9e2acbdcb`.
- Runtime candidate: `d1da542a089cf49ae86cd7637b8e97266a4e86d0c1d2198eee7db626ff2d0373`.
- Label candidate: `b401d77e177790645c53f985d7db5c17f0e5d33d1c061156e2eb0a7cbdeafd18`.
- Resource contract: `3dde01ff7b057cbe56eb1292618b78592ea66c4729ca148d71eb7e8967d1b9fb`.

The identity uses the driver's exact canonical science/input keys. It preserves
families, scientific consumer hashes, analysis and arms; scorer paths point to
the staged v2 source. The final retention draft must preserve this identity.

## Existing independent evidence

Under `../r1-target-resource-proof-20261020`, use the prior producer/schema,
allocation and Parquet closure reviews, their pins and exact source evidence.
The allocation's old pending list is immutable historical evidence, not a claim
that the later reviews did not occur.

Conditional label charges are copied without changes: target409505709654,
retained raw labels5627902, scorer transient148905586688, maximum label5429410
bytes. The previous reviews support these coefficients under their explicit
conditions. The v5 implementation review and its 155 passing tests cover
forecast counters, workspace integration, pre-label checks and Polars controls.

Native source correspondence uses the trusted installed release/package
assumption admitted by the allocation/Parquet reviewers, not a reproducible
binary-build attestation. This assumption remains necessary.

## Runtime inventory: inspect sufficiency, do not infer it from size

Synthetic capture v3 imports all18 scientific consumers, the staged driver and
four helpers; it exercises invented Torch/NumPy/ZIP/Arrow/Polars operations and
records exact installed versions, loaded module files and mapped native files.
Its audit hook prohibits scientific-root reads outside the staged source.
Capture source and result are preserved unchanged; no actual values were read.
The capture itself explicitly says it does not prove complete closure.

The proposed inventory unions1738 captured runtime files, all373 staged source
files and25 exact verifier source references recursively present in the draft:
2104 distinct paths. Verifier sources were captured as bounded source bytes
only, with their original external hashes verified. Their archive is
`../r1-target-resource-proof-20261020/verifier-source-capture.json.gz`.

Please specifically assess whether the scoring allocation paths are closed.
The verifier source union is not claimed to enumerate every metadata-only lazy
import. Those paths run during mandatory full validation before the measured
process baseline; they do not deserialize target tensors or score. For example,
the count producer's sklearn imports are inside producer execution functions,
not its commitment verification. The actual full opaque run's observed source
paths are not yet available. If additional runtime paths are required, identify
the relevant reachable function/library and the narrow missing evidence.

## Budget composition and fail-closed behavior

Proposed process AS and physical budget:1536GiB. Host reserve:64GiB.
Analysis budget:256GiB. Allocator/fragmentation reserve:64GiB.
Required output free space:128GiB, including64GiB filesystem reserve.
These are explicit ceilings/allocations, not a claim that the job fits yet.

The driver derives metric/analysis/output lower limits from verified metadata
and rejects insufficient fixed budgets. It measures whole-process RSS and
virtual peaks after forecast validation, adds the certified label allocation,
actual-count-derived forecast workspace, analysis and allocator terms, then
checks finite AS, physical allocation, fresh host memory and disk before labels.
It rechecks exact runtime files/settings before targets.

The opaque custody preflight is still running; no completion assumed. Successful
resource review does not supersede it or the fresh checks. Runtime/label/contract
files refer to prospective `.../r1-release-assembly-v2-20261021/control-v1`;
this directory has not been created.

## Validation and requested verdict

Nine local corruption/hash-chain tests and Ruff pass. Independently reproduce
the candidate from pinned local inputs without overwriting its directory.
Inspect the current v5 guard and evidence before accepting the combined claims.

If supported, write a distinct review and `r1-release-resources-v1` approval
binding the exact contract and driver, actual model/worker, `passed:true`,
`labels_authorized:false`, `scoring_authorized:false`. Otherwise return concrete
blocking findings and no approval. Do not author fixes.

No remote changes, actual forecast/label access, scoring, fitting, prediction,
freeze, seal, ledger preparation, R1 release, new-period/protected2026 access,
or retry is authorized by this review.
