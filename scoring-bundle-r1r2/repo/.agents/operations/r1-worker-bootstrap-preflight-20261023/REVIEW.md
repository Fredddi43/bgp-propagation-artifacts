# One-task worker initialization preflight

LOCAL code candidate, no runtime binding change and no execution. Root owns the separate CPU-node mismatch probe and any actual staging/submission. This packet never issues a scheduler command.

`build_preflight.py` accepts exact externally pinned production topology and already separately reviewed worker-runtime bytes. It creates a fresh preflight topology changing only transport root and worker runtime reference. All 64 original lane/cell definitions and scientific source bytes remain identical; only array task 0 is proposed. The metadata-only candidate suggests CPU partition, one CPU, one task, 640 GiB (same production allocation), 15 minutes, held, no requeue, no node pin. Runtime bytes are not rewritten/copied by this builder.

`preflight.py` launches the exact production `array_bootstrap.py` with isolated, unoptimized, no-bytecode Python and original thread environment. The unchanged bootstrap performs source checks, calls unchanged `distributed_scoring.worker`, and completes `parallel_scoring.initialize`, including the full runtime admission. The supervisor requires actual digest-committed ready identity plus subsequent heartbeat growth. It never creates activation or tasks, refuses their presence and any global label marker, and terminates/reaps only this disposable child process group. A successful record is written only after cleanup. Failures remain terminal; no automatic retry and no replacement allocation.

This proves the specific sampled node completes actual initialization under the pinned worker runtime. It does not establish compatibility of every heterogeneous CPU node; each eventual production worker still repeats exact runtime admission before readiness. It does not test or authorize label access, numerical scoring, old-worker supersession or any replacement array.

Tests: `.venv/bin/python -B -m pytest -q -p no:cacheprovider .agents/operations/r1-worker-bootstrap-preflight-20261023/test_preflight.py` — 8 passed in 1.72s. Actual disposable local subprocesses cover readiness/growth/cleanup and early exit, timeout, wrong identity and forbidden activation. Additional tests refuse preexisting global marker/wrong scheduler index before child creation, and compare the full generated topology against the production metadata preserving every cell/source field.

No actual preflight candidate was generated yet: new worker-runtime admission awaits the CPU-node probe and independent review.
