# H1 transport extension

Narrow extension of independently reviewed H3/timing transport (commit fbb941a). Existing frozen version preserved. Adds only the fixed20-cell H1 K500 family, its reviewed source dependencies and exact own-calibration/primary-input/common-slice references. Original scheduler, held submission, resource admission, separate release and no-retry behavior are unchanged. H1 uses a dedicated immutable namespace and full retained grid; explicit upstream failures remain retained.

All36 tests pass29.82s, including allthree complete fake-cluster stage/held-submit/admit/release chains. H1 tests cover invalid roles, missing cells, retained failures, changed evidence, source mutation and exact actual frozen candidate reproduction. H3/timing candidate outputs remain byte-identical to v1. No actual protected data reads, staging or jobs occurred. Exact actual execution bindings and independent approvals remain separate.
