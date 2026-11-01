# Independent finish-patch review, round 2

Reviewed at 2026-10-30 13:07:19 UTC (clock tool). Verdict: APPROVED for the finish-patch scope. This does not approve label opening; checkpoint bindings and the combined driver remain subject to independent review and a fresh bound dry run.

Exact reviewed files:

- `author/chain/r2_rescore_secondary.py`: SHA-256 `495b6db74cc65046e9159b6bbd8970bed7ca8572cec3da30d596832cbd5d8292`.
- `author/chain/test_r2_rescore_secondary.py`: SHA-256 `2012be0aca4ef2f709f8d030db6cfee90a9c3983182a2242b5c65685b2586d48`.

All three round-1 findings are resolved. The family gate now streams the expected regular part files in order, checks total byte length and verifies the concatenated digest. The scientific blocking verdict is encoded in the result document before writing; a separate exclusive, fsynced `completion.json` records the final verdict, including write failures. The pinned-source drift test finds the actual repository sources and fails if they are missing instead of silently skipping.

The completion gate requires both primary comparisons to be exactly true, one primary-score receipt, exactly the nine expected scored callbacks without persistence errors, and the expected composition keys/families/coverage list. Retained scientific no-input, unavailable and censored dispositions remain valid inside a successfully scored family. Failed scoring remains explicit; completion refusal prevents a successful process return. The patch preserves the existing label guards and primary output bindings.

Independent validation completed: supplied suite `13/13 passed`, with the pinned-source test actually executed and no skip. Additional fresh tmp-directory probes verified (a) a valid result succeeds with equal durable and returned scientific gates; (b) the previously reproduced zero-byte stable part is refused and both durable records identify `families_not_persisted: [stable]`; (c) primary numeric mutation is refused and both durable records identify the failed primary equality. No source originals, labels or experiment artifacts were changed.
