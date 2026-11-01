# Resource F1 correction, source v3, and unchanged calibration

Author `/root`; separate reviewer `/root/recovery_independent_review`.
Root pauses implementation during review. No delegation or actual-data work.
Preserve the failed resource-v1 verdict.

## Focused correction

`../r1-release-memory-20261020/v6/forecast_retrospective_release.py`
SHA `4573658eb2b360a8b63466e35165cae9cfffda854426142c5db12a2d2d34d519`
adds live Torch intra/inter-op checks requiring integer1, compares those values
with runtime admission at both existing gates, and bootstraps CLI evaluation
before dispatch. It does not reset drift at either admission check.
Direct Python callers must initialize threads first or are refused.
The future exact launcher must also initialize OMP/MKL/Polars to1.

All scientific formulas/query paths, helpers, cardinality handling, marker
semantics and budgets are unchanged. Inspect the v5→v6 diff.
New tests include wrong counts/types, environment insufficient for admission,
explicit bootstrap, both full evaluation gates refusing before labels/scores,
and a fresh real Torch process detecting drift. An extracted exact guard smoke
on the installed cluster runtime passed using no scientific files; script and
receipt are pinned. The verbatim AST smoke script is evidence, excluded from
Ruff's standalone module-layout checks.

## Prospective source-only overlay v3

`prepare_v3.py` derives `candidate-v3` from previously staged v2. Only the driver
file changes; five re-added preparation/helper files remain byte-identical.
All373 source files, plus source manifest and pending base draft,375 staged files.
New root: `<FORECAST_ROOT>/r1-release-assembly-v3-20261021`.
Candidate SHA `cdac5824dcce8758d1ec6df5c14bc26af6f1b2c0e3395b641ac65f331721f485`.

`stage_v3.py` is the reviewed v2 stager with literal root/kind/scope changed
to v3; same once-only intent, exclusive fresh root, bounded files/bytes,
hash-before/readback, ownership/disk/closed-registry checks and fsync behavior.
23 synthetic stager tests pass. No source has been staged for v3 yet.
Approval may permit only this exact source-copy attempt, never execution.

## Resource candidate v2

`build_resource_candidate_v2.py` preserves the v1 artifact and generates fresh
`resource-candidate-v2`. It binds captured live thread counts into admission.
The v3 source relocation changes the science/input identity through scorer
paths but preserves every scientific byte/decision and family.

- Input identity `46c1e96cde9ebf9d53775de504706c0220280c5c4907db409325ba3e17e88002`.
- Runtime `45e866868e18189778350f170240ba8db528c38461ae27af03a497936e0e75ba`.
- Label `97dddbd836a22eba76ea8d9ffbdaeaa77437a11bf86c4a3a7d16c54a50489c7c`.
- Contract `89c6e074995f78d91b2a18308ca76910e315131b1dc4cd383af85d63956a6c7d`.

Existing v3 synthetic capture is reused rather than hashing the same installed
libraries again. The builder checks every captured staged scientific source
against the new manifest; the only permitted changed byte identity is the
explicit old→new driver. That change imports no new third-party dependency:
Torch is already captured and exercised. Original v2 source paths stay pinned
alongside the new source root. Result:2134 implementation paths. Eleven tests
cover corrupt sources, captured thread counts and the certificate chain.
Label coefficients,256GiB analysis/64GiB allocator/1536GiB process ceilings and
128GiB output/64GiB reserve remain unchanged. Fresh runtime, whole-process,
count-derived and disk guards remain mandatory. No fit/success assumed.

## Requested independent outputs

If supported, write one review plus separate narrowly scoped approvals:

1. v6 code verdict and `r1-release-resources-v1` approval bound to the exact
   resource contract and driver; labels/scoring false.
2. `r1-source-only-staging-v3` approval matching every expected field in
   `stage_v3.py`, exact candidate/stager/review hash and root. Only source
   staging true; consumer/labels/scoring/freeze/seal/retry false.
3. `r1-probability-reliability-v1` updated implementation approval for v6.
   The prior v5 approval is `reviews/astra-v5-calibration-approval.json`;
   decision remains d359941fba53b7ab3531de4b5a6a7efe2996b98f6b496f41f06c435f7dc55ad6,
   scorer remains740bf610afc2d2cdaae40e8726ab6bd8ab9b38d5e6db262a4f0b7f7a14bc4c3d.
   No new calibration/test-outcome use or execution authorized.

Record actual model/worker and distinct <PROJECT_STORAGE>. If anything is unsupported,
return concrete blockers and withhold the relevant approval. Do not fix code.

Full opaque preflight remains in flight. Resource approval alone neither assumes
its success nor authorizes retention/preparation/evaluation. No target values,
forecast decoding, fits/prediction, new-period/protected2026 or retry is allowed.
