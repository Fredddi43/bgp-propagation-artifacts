# d300 chain packet: Wave 2 (tasks 48-63)

Pins (sha256 prefixes): successor.py 1c74f201bd7a, plan.json 245fa7fca5ed, prepare.py c0a559add388, operate.py 23b6ec55eaad, remote.py 4f693dc63c88.

No execution authority; nothing here was staged, submitted, cancelled or released. Local tests only: `cd /tmp && python3 -I -B <packet>/test_chain.py` (22 tests; 4 replace_old flow tests run only in wave 1).
Shared sources and regeneration: `newperiod-timing-d300-chain-sonnet-v1-20261027/` (build_packets.py regenerates the four packets; operator files are byte-identical across packets, tested).

## Design decisions fixed by root (and what they mean in code)
- Every new job: `--export=NIL`, absolute-path `job.sh` (only builtins plus /usr/bin/env, grep, sha256sum, cut), `env -i` exec of the pinned python; no dependencies between stages (release order and acceptance are root's, so no job can start by itself).
- Workers reuse the original frozen kernel/runtime/budget/audit modules by sha (taken from the original plan's `files`), the original Budget and output_budget factories, original bounded_run and original `derived_audit_plan`. They add: a staged plan + one-shot release binding (independent concurrences, V48 phase, adoption), exact scheduler identity, per-slot intent files (a slot is never reused), RLIMIT_AS/FSIZE from the plan, and a stat-only terminal record. No scientific code is changed.
- The original Budget has no mkdir/rename gate, so the CAIDA-cache mkdir that stopped successor v6 is not an issue here (the 32 original 2025 tasks ran under the same Budget).

## Read-only evidence used (2026-10-27)
- Old array 52515293: tasks 32-63 PENDING JobHeldUser (`ArrayTaskId=32-63%16`, SubmitLine `--array=0-63%16 --export=ALL --mem=131072M --hold`); tasks 0-31 COMPLETED except 27 FAILED. Real `sacct -P` shape is the compressed row `52515293_[32-63%16]|PENDING|0:0` (fixture `real-scontrol-52515293.txt`). 52515294/5/6 each carry `--dependency=afterok:<previous> --kill-on-invalid-dep=yes`.
- Accepted 2025 shards (stat only): allocated 333.7-367.7 MB each (max 367,669,248; sum of 31 = 10,577,758,208; sixteen largest = 5,530,590,208), logical 2.5-3.2 GB, largest graph file 524,105,539 B (shard 17), shard 27 corrective 807,007,655 B. The original FSIZE 536,870,912 killed the first shard 27.

## Packet: continuation wave 2 (tasks 48-63)
Same worker and operator as wave 1 for tasks 48..63 (`--array=48-63%16`, namespace `timing-d300-tasks48to63-sonnet-v1`); no `replace_old` (wave 1 already cancelled the whole old array 32-63). The worker additionally requires binding extras `previous_wave_accepted: true` and `previous_wave_acceptance_ref` (accepted wave-1 capture), enforced in `run` and in the release binding.
Funding: same row/stop rule as wave 1, evaluated on wave 2's own tail16 after wave 1 is accepted and credited in a newer phase. If wave 1 exceeds its estimate (task ceiling 493,228,800 B) wave 2 is not released.
Review set: source + allocation concurrences (re-issued for this plan), stage_hold and install_release operation reviews, adoption refill (plan = wave 2 plan), held acceptance, plus acceptance of wave 1 (terminal records for tasks 32-47 and allocation census) and the phase that credits it.
