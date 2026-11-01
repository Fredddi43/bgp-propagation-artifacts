# d300 chain packet: Wave 1 (tasks 32-47)

Pins (sha256 prefixes): successor.py b3aef1248e32, plan.json be9965f10df5, prepare.py c0a559add388, operate.py 23b6ec55eaad, remote.py cf81817a39a7.

No execution authority; nothing here was staged, submitted, cancelled or released. Local tests only: `cd /tmp && python3 -I -B <packet>/test_chain.py` (22 tests; 4 replace_old flow tests run only in wave 1).
Shared sources and regeneration: `newperiod-timing-d300-chain-sonnet-v1-20261027/` (build_packets.py regenerates the four packets; operator files are byte-identical across packets, tested).

## Design decisions fixed by root (and what they mean in code)
- Every new job: `--export=NIL`, absolute-path `job.sh` (only builtins plus /usr/bin/env, grep, sha256sum, cut), `env -i` exec of the pinned python; no dependencies between stages (release order and acceptance are root's, so no job can start by itself).
- Workers reuse the original frozen kernel/runtime/budget/audit modules by sha (taken from the original plan's `files`), the original Budget and output_budget factories, original bounded_run and original `derived_audit_plan`. They add: a staged plan + one-shot release binding (independent concurrences, V48 phase, adoption), exact scheduler identity, per-slot intent files (a slot is never reused), RLIMIT_AS/FSIZE from the plan, and a stat-only terminal record. No scientific code is changed.
- The original Budget has no mkdir/rename gate, so the CAIDA-cache mkdir that stopped successor v6 is not an issue here (the 32 original 2025 tasks ran under the same Budget).

## Read-only evidence used (2026-10-27)
- Old array 52515293: tasks 32-63 PENDING JobHeldUser (`ArrayTaskId=32-63%16`, SubmitLine `--array=0-63%16 --export=ALL --mem=131072M --hold`); tasks 0-31 COMPLETED except 27 FAILED. Real `sacct -P` shape is the compressed row `52515293_[32-63%16]|PENDING|0:0` (fixture `real-scontrol-52515293.txt`). 52515294/5/6 each carry `--dependency=afterok:<previous> --kill-on-invalid-dep=yes`.
- Accepted 2025 shards (stat only): allocated 333.7-367.7 MB each (max 367,669,248; sum of 31 = 10,577,758,208; sixteen largest = 5,530,590,208), logical 2.5-3.2 GB, largest graph file 524,105,539 B (shard 17), shard 27 corrective 807,007,655 B. The original FSIZE 536,870,912 killed the first shard 27.

## Packet: continuation wave 1 (tasks 32-47) and replacement of the held old array
`successor.py`: array worker for tasks 32..47 only (year 2026 slots 0-15, count 32 per year as in the original array), outputs in `.../recovery/timing-d300-tasks32to47-sonnet-v1/build-00NN`, 2 GiB per-file exception (writer total 8 GiB unchanged), RLIMIT_AS 48 GiB (job.sh `ulimit -v` identical), `--mem=24576M` cgroup (2025 RSS 7.3-11.9 GiB, VM 16-26 GiB incl. the heavy shard 27), `--array=32-47%16`, scheduler identity (array job id, task count 16, task 32..47, cpu, 2 cpus, 24576, restart 0).
Terminal accounting per task: passed only if allocated <= 493,228,800 (= row/24), logical <= 8 GiB, max file <= 2 GiB, files <= 4096, dirs <= 64. A task over the ceiling fails its terminal record and root must not release the next wave.
`operate.py` actions: `stage_hold` (stage fresh namespace, submit the held NIL array once, readback), `replace_old` (see below), `install_release` (needs the accepted replace_old result; installs binding; release once).
`replace_old` (one root once, after the new held array is accepted): re-reads new held array; verifies old 52515293 is exactly PENDING/JobHeldUser, `ArrayTaskId=32-63%16`, SubmitLine `--array=0-63%16 --export=ALL --hold`, sacct shows tasks 0-31 terminal and 32-63 pending; runs exactly one `scancel 52515293_[32-63]`; polls sacct until the cancel is confirmed (strict `cancel_coverage`: every task 32..63 CANCELLED exactly once, compressed row `_[32-63%16]` accepted, `-p` trailing delimiter and ExitCode column accepted, foreign id/overlap/duplicate/started task/retained task changed all raise); re-reads the new held array; retains the raw stdout of every ssh exchange (`raw-NNN.json`) before parsing. It never sbatches or releases.
Scheduler cascade (not issued by the operator): 52515294, 52515295, 52515296 each have `--kill-on-invalid-dep=yes`, so Slurm will kill the old assemble/audit/finalizer when the old array tasks are cancelled; the operator records their sacct state (`cascade-record.json`, not asserted). Old set 52480023-26 is untouched; cancelling it is a separate decision.

### Funding and admission against V48 (statement requested by root)
- Row: `timing_live_build_wave` = 11,837,491,200 B (11.0245 GiB), issued in V48. Mechanical stop contract: required row = max(24 x max shard allocated, ceil(1.5 x wave)) = max(8,824,061,952; 8,295,885,312) = 8,824,061,952 -> headroom 3,013,429,248 B. `binding.issued_phase` row must be >= that or the worker refuses.
- Why two waves: two uncredited waves would be ~10.9 GB (92% of the row) if 2026 resembles 2025; the row is credited only by accepted consumption in a later phase, and the stop contract says to stop before any next release on excess. Wave 2 therefore needs `previous_wave_accepted` + acceptance ref and a phase that credits wave 1.
- Margin: live df at authoring: models free 867,673,571,328 - floor 867,383,093,888 = 290,477,440 B (0.27 GiB) unreserved slack. It suffices only because every byte of the stage lies inside the existing row; it cannot absorb a row overrun (a wave 8% over its estimate would). `shutil.disk_usage` >= phase floor is re-checked by the worker before every task.
- Controls per packet <= 1 GiB nominal (measured ~124 KB for the shard-27 controls) are funded by `timing_stage_controls` (4 GiB; four packets = exactly 4 GiB nominal): reviewer to confirm.

### Review set (continuation wave 1)
1. Source review: `successor.py` vs original `job.py` build path (limits and admission only), `plan.json`, shared operator files (`prepare.py`, `operate.py`, `remote.py`, `transport.py`, `ssh_contract.py`, `pins.json`) -> `stage_science` concurrence bound to `prepare.py` (re-issue if operator changes).
2. Allocation review -> `allocation_premise` concurrence: row, ceiling, tail16 rule, 2 GiB file cap, AS 48 GiB, 24 GiB RAM, 0.27 GiB margin, wave split.
3. Operation reviews: stage_hold, replace_old (incl. cascade), install_release; adoption refill (memory 393,216 MiB = 16 x 24,576; plan = wave 1 plan); held acceptance of the new array (exact scontrol record) and of `result.json` of replace_old.
4. Root: V48 or newer phase, control snapshots, authorities (3 onces), fresh df/floors before each once.
Order: concurrences -> stage_hold -> held acceptance -> replace_old -> acceptance -> install_release (binding + release) -> tasks run -> capture/acceptance -> phase credit.
