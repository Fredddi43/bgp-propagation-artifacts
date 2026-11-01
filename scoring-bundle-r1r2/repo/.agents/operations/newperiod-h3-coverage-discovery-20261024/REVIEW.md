# One finite metadata capture: reuse existing H3 coverage evidence

The approved R1 resource preflight already bound `h3-frozen-v1/metadata/metadata-ledger.json` to a84a9037. This probe reads that exact file and exactly its four unique ris7/mixed7×30/60 coverage-extract refs. It returns only panel/horizon, extract identity and the full coverage receipt's path/SHA. The full receipt is not opened; no event rows, scores, labels, tensors or predictions are returned. This identifies any later receipt before proposing redundant source recomputation.

Execution request binds capture.py and sole exclusive host access-log path. Runtime python3 -I -S -B;4GiB address space,120CPU seconds, external180s wall,64KiB stdout/stderr. Ledger≤16MiB, each extract≤128MiB, total≤528MiB; stable nofollow descriptor and SHA verified. Durable access logging precedes each open; no path discovery/listing, no other follow, no scientific execution/retry/overwrite. Local intent/results must be exclusive. Original known R1 ledger remains untouched. A separately reviewed exact request is required before execution.

Tests5PASS0.08s: fixed four scopes, absence of source payload in projection/no full-receipt follow, duplicate/extra build refusal before nested read, wrong panel and noncanonical path refusal. Actual capture has not run.
