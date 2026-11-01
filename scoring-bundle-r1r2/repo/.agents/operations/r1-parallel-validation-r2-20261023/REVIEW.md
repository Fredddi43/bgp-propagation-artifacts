# Revision 2: close initial import bytecode gap

Independent reviewer found one blocker in frozen revision1: the child audit started after first imports. Revision2 changes only helper startup and regression tests. Driver remains SHA45b99a7165aedc4c7d2989271efe07addfa856be1d3132bcddcb9dbf514c01fa. See revision.diff and prior frozen REVIEW.md for full contract/limitations.

The child audit now starts before the first driver/bgbench import, so staged `.pyc` attempts always become cache misses and pinned source is executed. Spawn imports the helper itself before initializer: parent requires Python `-B`/sys.dont_write_bytecode and refuses any standard/optimized/legacy helper bytecode cache before creating workers. The operational launcher MUST enforce cache-free immutable source staging before its own first import of this helper; this is an explicit remaining integration precondition, not something this helper retroactively proves.

Full synthetic suite: 118 passed, 1 skipped (same inherited parent-list instrumentation exclusion). New regressions plant timestamp/size-valid stale driver and bgbench validator bytecode containing an execution trap, prove actual source executes, reject standard/optimized/legacy helper caches before spawning, and require `-B`. Existing stable actual-verifier, timeout/crash/private-memory/partial-submission/badbytes/closed-cache cleanup tests pass. Revision1 scientific-output comparison still applies because driver and scientific validator code are identical. No need to repeat the frozen baseline suite.

No host action, result read, scientific retry or execution approval. Independent review pending.
