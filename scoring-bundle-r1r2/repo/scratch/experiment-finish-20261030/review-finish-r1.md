# Independent finish-patch review, round 1

Verdict: changes required in the finish patch. Full label-opening approval is withheld separately pending checkpoint integration and combined review.

Reviewed copied driver SHA-256: `dab98fa60b8137fc3d9d9bac3949c6fd490e7773d35b864d96abda3758d64113`.
Reviewed copied tests SHA-256: `9a8ce4307381e399a2ee74f80638a53f3209798b1c4294ea6c821ddb730aa52e`.
Paths: `scratch/experiment-finish-20261030/author/chain/{r2_rescore_secondary.py,test_r2_rescore_secondary.py}`.

1. **Persisted family bytes are not verified (`r2_rescore_secondary.py:647-655`).** The new gate checks manifest equality and the number of glob matches, but never their ordered expected names, regular-file status, byte count or digest. Independent reproduction: truncate `families/stable.pkl.part0000` to zero bytes after fixture creation; `finish` still returns `passed: true`. Require the expected ordered regular part files, total length equal to the persisted byte count, and concatenated SHA-256 equal to the persisted digest. Add truncation, same-size mutation and wrong-name-with-same-count cases. This is required to support the patch's claimed on-disk integrity gate.

2. **Durable and returned completion gates differ (`r2_rescore_secondary.py:710-757`).** `secondary-result.json` is encoded and written before `blocking` and final errors are added to the gate. The on-disk header therefore omits `completion_gate.blocking`, including on a scientific-gate refusal; the returned/logged gate contains it. Build the scientific blocking verdict before encoding. Preserve any final write failure in a separate durable completion record if the result document cannot describe its own write failure. Tests should compare durable and returned scientific gate fields on success and inspect the durable blocking fields on a failed family/primary comparison.

3. **Pinned-source drift test silently skips (`test_r2_rescore_secondary.py:279-282`).** `parents[3]` resolves to the repository's `scratch/`, so the test searches `scratch/.agents/...` and returns successfully without testing the sources that are present. Locate the actual repository root, require these sources to exist in this workflow, and rerun the test without a skip.

The substantive primary equality, expected-family multiplicity, composition-key and family-failure gates are otherwise correct for the pinned call graph. Retained unavailable/no-input/censored cells are not reclassified as failed scoring calls. Failure now raises after preserving results, preventing a false successful job exit. Label, marker, primary and checkpoint code paths are unchanged by this patch.

Independent validation: the supplied test command completed `12/12 passed`; the pinned-source test was one of those passes but actually skipped. Additional isolated tmp-directory probes reproduced the zero-byte family-part false success and the missing durable `blocking` field. No experiment artifacts or source originals were changed.
