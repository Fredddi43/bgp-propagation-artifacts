# H1 adapter source loading correction

This separate local revision preserves the committed v1 snapshot. It changes only `run_package.load_adapter` and its two callers to verify the package-bound adapter SHA and compile those exact source bytes in a private module. A timestamp-valid package-root bytecode cache can no longer override verified source.

The scientific source closure, guard snapshot, H1 adapter, graph builder, twenty frozen cells, recipes, resource assumptions, planned production namespaces, no-retry behavior and every actual-input/execution gate remain byte-identical. Package and client hashes are regenerated for the changed runner. This revision creates no new scientific attempt namespace and authorizes no execution. Existing H1 audit source/runtime bindings may continue to name the preserved v1 guard closure because those guard bytes are unchanged.

A regression builds timestamp-valid stale bytecode and proves the previous import mechanism executes the stale value, while the corrected loader executes the exact bound source. A changed source fails before execution. An additional equality check verifies all unchanged frozen files and all package fields except the changed runner hash. The original adapter/transport synthetic suites are retained.

Actual staging, execution bindings, resource sufficiency and independent operation review remain pending. This is a source-loading correction only; H1 validation slice calibration is separately owned by the parent agent.
