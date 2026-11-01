# Experiment completion runner

This snapshot preserves the independently reviewed D-A39 secondary-scoring runner. The existing experiment is still running; this commit does not declare its data complete. Paper work is deferred.

The primary of record remains the original attempt/primary.json (849e064518d1aa7e0b1c61c4c5836acd75864de12dce0278dab75918493e9ac1). D-A39 permits the previously approved single second label read for secondary scoring, through a separate exclusive records directory. The runner requires a fresh label-free dry run whose ready record binds all preparation bytes, code and fixed options before that opening.

Code lives in .agents/operations/agy-lanes-20261027/g2r2/chain-d39-v2/. Its sibling g2/g2_exec.py provides existing runtime/metadata helpers. Runtime digests and independent review are retained here. The five focused suites passed 62 tests on the reviewed source. Actual inputs and protected artifacts remain in the existing cluster experiment; no outcome artifact is added by this snapshot.

The original live preparation uses the older chain directory. Wait until its complete rolling origin checkpoint is published before starting the successor dry run, so it loads that preparation rather than recomputing it. The two pure scoring adapters operate on private secondary modules, preserve admitted outputs, and use at most eight workers. The checkpoint source and keys are unchanged.

The standalone final-data validator and synthetic regression suite are retained under `validation/`, with their exact independent review in `validator-review.md`. The test fixtures import the approved producer from the author checkout path recorded in the test; the validator itself accepts an explicit JSON layout override. This is implementation validation; no production completion or final-data PASS has occurred yet. The default JSON allocation cap must be raised explicitly if the completed report exceeds256MiB.

The original scientific source-closure document (SHA-256 `a72c35de1f716921a5092d3f096ea4d2491161d17e4ab00f0998eee9b7aecccd`) and90 relative source digests are retained here. Two existing source files were restored to their frozen pinned bytes in this backup branch; all90 now match. This does not change the deployed experiment.
