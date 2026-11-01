# d300 v2 diagnostic delta (v3)

Prepared for sol-storage2; no execution authority. Frozen v2 remains unchanged.

The same remote predicates now carry 22 distinct reason tokens. The batch wrapper retains the same gates and has separate exit codes: array 90, digest alphabet 91, restart 92, argc 93, plan digest 94, digest length 95, binding hash 96, cwd 97, digest read 98, limits 100–104. Transport retains only a bounded D300_REMOTE token; arbitrary stderr remains hidden. The operator records that token in STOPPED.json. No retries, submissions, production reads or adoption fills occurred.

20 local tests pass, including actual remote entrypoint → bounded transport → operator refusal, batch exit codes, unchanged assertion predicates, real frozen scientific plan/independence consumers and the existing binding-size check against v43. Both canonical FALSE authorities refuse the real CLI --check-only at the issued-root gate.

This changes operator/script pins: prior v2 reviews/concurrences/adoption-helper operator references cannot authorize v3. Root must rebind controls after independent delta review. Existing scientific plan and successor remain byte-identical. #3/#4 are outside this minimal #1/#2 delta: active SSH remains the pinned standard; system Python staging remains an external runtime-admission condition. Root fills live adoption only after the ris7-d60 audit jobs are terminal.
