# d300 chain packet: Audit (32 shards, 2 GiB graph cap)

Pins (sha256 prefixes): successor.py ddaa490f538d, plan.json d7c98ff66173, prepare.py c0a559add388, operate.py 23b6ec55eaad, remote.py bcd51b76db88.

No execution authority; nothing here was staged, submitted, cancelled or released. Local tests only: `cd /tmp && python3 -I -B <packet>/test_chain.py` (22 tests; 4 replace_old flow tests run only in wave 1).
Shared sources and regeneration: `newperiod-timing-d300-chain-sonnet-v1-20261027/` (build_packets.py regenerates the four packets; operator files are byte-identical across packets, tested).

## Design decisions fixed by root (and what they mean in code)
- Every new job: `--export=NIL`, absolute-path `job.sh` (only builtins plus /usr/bin/env, grep, sha256sum, cut), `env -i` exec of the pinned python; no dependencies between stages (release order and acceptance are root's, so no job can start by itself).
- Workers reuse the original frozen kernel/runtime/budget/audit modules by sha (taken from the original plan's `files`), the original Budget and output_budget factories, original bounded_run and original `derived_audit_plan`. They add: a staged plan + one-shot release binding (independent concurrences, V48 phase, adoption), exact scheduler identity, per-slot intent files (a slot is never reused), RLIMIT_AS/FSIZE from the plan, and a stat-only terminal record. No scientific code is changed.
- The original Budget has no mkdir/rename gate, so the CAIDA-cache mkdir that stopped successor v6 is not an issue here (the 32 original 2025 tasks ran under the same Budget).

## Read-only evidence used (2026-10-27)
- Old array 52515293: tasks 32-63 PENDING JobHeldUser (`ArrayTaskId=32-63%16`, SubmitLine `--array=0-63%16 --export=ALL --mem=131072M --hold`); tasks 0-31 COMPLETED except 27 FAILED. Real `sacct -P` shape is the compressed row `52515293_[32-63%16]|PENDING|0:0` (fixture `real-scontrol-52515293.txt`). 52515294/5/6 each carry `--dependency=afterok:<previous> --kill-on-invalid-dep=yes`.
- Accepted 2025 shards (stat only): allocated 333.7-367.7 MB each (max 367,669,248; sum of 31 = 10,577,758,208; sixteen largest = 5,530,590,208), logical 2.5-3.2 GB, largest graph file 524,105,539 B (shard 17), shard 27 corrective 807,007,655 B. The original FSIZE 536,870,912 killed the first shard 27.

## Packet: audit (32 shards, 2 GiB graph cap)
`successor.py`: array worker `--array=0-31%8` running the original `audits/timing/audit.py` `audit_shard` with `limits = original audit_limits + graph_file_bytes 2 GiB` (original 512 MiB; shard 27 has a 770 MiB graph) against `recovery/timing-d300-assemble-sonnet-v1/assembly/audit-plan.json` (sha bound in the release binding), outputs `recovery/timing-d300-audit-sonnet-v1/audit-00NN`, original per-shard 1 GiB total / 512 MiB per file, memory 131072 MiB, AS memory-256 MiB.
Decoded-memory admission (analytic, not measured): audit.py:148 reads the graph file into bytes (<= 2 GiB), copies it into `io.BytesIO`, and `torch.load` decodes tensors of at most the file size: bound 3 x 2 GiB = 6 GiB per graph, below AS (127.75 GiB) and the cgroup (128 GiB); binding must carry `decoded_memory_acknowledged: true`. Whether other audit allocations (history/signature libraries up to 1e6 events) scale with the larger graph is not established and needs the reviewer's read of audit.py/source_io.py.
Funding: same `timing_audit_chain` allowance and adequacy-review requirement as assemble (shared row; one chain at a time). Finalizer 52515296 is cancelled by the scheduler cascade of wave 1; a replacement finalizer is NOT built here and d900 stays held.
Review set: source + allocation concurrences; decoded-memory admission review; adequacy review; operation reviews (stage_hold, install_release); adoption refill (8 x 131,072 = 1,048,576 MiB); held acceptance; acceptance of the assembly (terminal + `audit-plan.json` sha).
