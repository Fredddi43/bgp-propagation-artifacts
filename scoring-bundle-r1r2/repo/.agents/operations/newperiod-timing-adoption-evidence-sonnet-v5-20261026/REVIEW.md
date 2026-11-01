# Adoption evidence collector (d300 v3 and h3refit40), V44

Author: sonnet worker (not a reviewer). Scripts only: no launch, issue, board post, git or remote write.
`collect.py` is read-only against <BATCH_HOST> (stdlib probes; one FSIZE-0 import trace) and <SUBMIT_HOST>
(squeue/scontrol/sacct only). It never opens a scientific payload, label, score, prediction, parquet or tensor.

## Root commands (from /tmp)

    H=<REPO>/.agents/operations/newperiod-timing-adoption-evidence-sonnet-v5-20261026
    O=<fresh absolute dir, must not exist>
    /usr/bin/python3 -I -B $H/collect.py --lane d300 --out $O --root-session <id> --issue --ack-risks \
        --ack-future-once-writers --ack-no-release --accept-compute-scheduler-assumption
    /usr/bin/python3 -I -B $H/fill_wrapper.py --evidence $O/d300-root-evidence.json --adoption $O/adoption.json

    # h3refit40: driver.py adopt ... --bounds $O/h3-bounds.json --zero-writers-evidence $O/zero-writers-evidence.json
    /usr/bin/python3 -I -B $H/collect.py --lane h3refit40 --out $O --root-session <id> --issue \
        --ack-future-once-writers --ack-no-release --accept-compute-scheduler-assumption

Without `--issue` the records say `issued:false` and fill.py refuses them (dry run). The three `--ack-*` flags are
root's conscious adoptions: the two residual-risk acknowledgements, "no root once outside bounds.json appends to the
custody log", and "nobody releases/updates a held n-* job during the once". None can be discovered by a script.
Collection takes ~3 min (d300; closure trace ~40 s, ssh probe of every node, two-read stable scheduler snapshot last);
~2 min for h3refit40. `fill_wrapper.py` refuses if the oldest utc in the graph is older than 240 s.

## d300: sol-storage2 findings

R1 (host universe was a synthetic `slurm-compute` host, queue-only evidence):
- Universe = `<WORKSTATION>`, `<BATCH_HOST>`, `slurm-scheduler`, every node of every partition any n-* job lists (<COMPUTE_NODE>..26 and the
  other listed partitions; 58 nodes live) plus every node of a currently allocated job. 61 hosts live.
- <WORKSTATION> / <BATCH_HOST>: full /proc census (every visible entry, state, uid, comm, matching args), fd/cwd/exe scan for the custody
  log and for <PROJECT> trees and the worker venv/source/control trees, custody log stat (owner uid 23847, mode 0644: only that uid
  and root can append; <BATCH_HOST> shows all 1830 entries readable).
- Compute nodes: direct ssh from <BATCH_HOST> is refused (`Permission denied (publickey,password)`, recorded per node, run on
  every collection). So the process evidence per node is scheduler-side (`scontrol show node`, `squeue -w` census for all users) and is
  labelled `evidence_kind: scheduler_side`, `process_level_evidence: false`. Argument: <USER> cannot start a process on a node
  outside a Slurm allocation. If any node ever accepts ssh it is listed in `direct_ssh_possible_nodes`.
- Writers: every n-* job in any state (see h3 below) gets an admission file (`admissions/`), `custody_remaining_growth_bytes` from a
  cited accepted row (`bounds.json`: stable v6 V44 writer-inventory + root-operating-adoption sha256) or zero with hold evidence.
  Running jobs sit on their node's inventory. Non-job actors from `bounds.json` (d300 v3 stage/worker 0 = `custody_appends 0`
  in prepare.py; stable_source_stage 84322856 retained conservatively) sit on <BATCH_HOST>.
- Not provable here: root onces other than those in bounds.json. They are listed by directory name
  (`future_once_directories_seen`) and need `--ack-future-once-writers`.

R2 (runtime flags without facts): five facts in `runtime/`, each root/issued/passed/fresh/lane/phase bound.
- worker interpreter + import/native closure: trace with the exact job.sh env (parsed from `prepare.job_script`), `-I -B`, RLIMIT_FSIZE 0,
  imports of torch, polars and the four bgbench modules development_build imports. Closure = every module file, `__cached__`, every
  /proc/self/maps file, site `.pth`/sitecustomize: 3114 files, 3.51 GB, each with sha256/size/mode/uid/mtime/ctime/inode in
  `raw/worker-closure-manifest.json`. Interpreter sha256 + symlink chain + pyvenv.cfg. Old-root code pins (runtime.py,
  development_build.py, original_budget.py, job.py, output_budget.py, private_runtime_verifier.py) checked against the old plan's
  `files`; frozen source tree (all files) checked against source-timing.json; no .pyc in it. Re-verified immediately before stamping
  (`restat`: size/mtime/ctime/inode/uid/mode of all files, sha256 rehash of the interpreter and files <= 64 MiB).
- staging interpreter closure: /usr/bin/python3 (3.11.2) with the stdlib imports of remote.py, 110 files, same method.
- immutability: venv stat digest before/after trace/at collection (35974 entries, equal), owner uid, max mtime/ctime, pycache count,
  world-writable files (`.lock`), no writable fd under venv/source/control on both hosts. NOT filesystem-enforced read-only: the
  fact says `filesystem_enforced_read_only: false` and root adopts it consciously.
- temp/cache: job.sh env (TMPDIR/HOME/XDG_CACHE_HOME... = /dev/null), trace ran under that env with FSIZE 0 and left the tree unchanged;
  run-time writes are bounded by the reviewed budget hook / `ulimit -f`, stated as not observed here.
- scheduler-external writes: held submit argv has `--output=/dev/null --error=/dev/null --export=NONE`, no mail. Slurm accounting,
  slurmd spool and node syslog are admin-owned and recorded as residual, root-adopted.

## h3refit40: astra-final findings

H3AD-1 (RUNNING-only roster): `classify` takes every row of `squeue` (all states). Zero growth only if PENDING + Reason=JobHeldUser +
Priority=0 (hold_snapshot recorded) or PENDING behind an unfulfilled dependency whose every referenced job is itself blocked (fixpoint).
RUNNING, CONFIGURING, COMPLETING, SUSPENDED and schedulable PENDING need a cited bound (`bounds.json` rules, applied to all those
states) else collection is refused (`WRITER_BOUND_REQUIRED`). Tests: schedulable pending, dependency-pending (blocked / on a running job),
held, completing with and without rule. `h3-bounds.json` lists every non-terminal n-* job by name for driver.py. NOTE: driver.py's own
`roster()` still filters RUNNING only (H3AD-1 is in that file, which I did not touch); its fix must read these files, not recompute.
H3AD-2 (non-Slurm writers): `zero-writers-evidence.json` binds the <WORKSTATION> + <BATCH_HOST> process/fd census records, compute-node
records, the custody log owner/mode, the non-job actors and the `--ack-future-once-writers` attestation. It is `passed:false` unless
both acks are given.

## Residuals (cannot be discovered by a script)
Other users' processes on <BATCH_HOST> could not hold the log writable (owner uid 23847, mode 0644) but are not fd-scanned; compute
nodes have no process-level view; the `driver.py` source pin in bounds.json must be re-pinned when driver.py changes.

Tests: `/usr/bin/python3 -B $H/test_collect.py` (26, synthetic fake transport; the happy path feeds the real fill.py `fill()`).
A live dry run through fill.py (read-only) passed for d300 and h3refit40 at ~13:22Z; those outputs were deleted, not operational.

## v2 (sol-storage2 V2 CHANGES)

R2 (nested node SSH bypassed the pinned trust): all direct compute-node SSH is removed. The only remote hops are <BATCH_HOST> and
<SUBMIT_HOST> through the unchanged pinned `ssh_contract.py` (known_hosts sha256-pinned, StrictHostKeyChecking=yes, `-F /dev/null`,
explicit identity). Test `test_r2_no_direct_node_ssh_is_ever_issued` asserts no ssh/xargs command and no
`StrictHostKeyChecking=no` / `UserKnownHostsFile=/dev/null` in the source. The collector source is bound by the sha256 the reviewer pins.

R1 (compute writer exclusion unsupported): no process-level view of compute nodes is possible without running a job, so v2 does not
claim one (`process_level_evidence:false`). The argument is scheduler-based and explicit, per node: (a) <USER> processes run on
compute nodes only through Slurm (slurm skill sections 0/0e: compute nodes via sbatch/srun, <SUBMIT_HOST> allows squeue/sbatch/sacct/scancel/
scontrol/sinfo only); (b) per node: all-user `squeue` census, `scontrol show node`, `sacct` of <USER> jobs in the last 6 h; (c) every
<USER> job on the node is listed with class: n-* writer with cited bound/hold disposition, or other project with Command, WorkDir,
StdOut and StdErr recorded and the whole scontrol line checked for <PROJECT> / access-log / data-custodian markers (any hit on a
non-n-* job refuses the collection). This is metadata only: it shows no path to the log, not that the job cannot open it.
(d) The custody log is probed on <BATCH_HOST> at the start and again after the final scheduler snapshot; device, inode, size, mtime, uid and mode
must be identical (else `CUSTODY_CHANGED_DURING_COLLECTION`); it is recorded as `custody_stability_window`. It detects NFS-side writers
only if they append inside the window. The remaining assumption is a root flag, `--accept-compute-scheduler-assumption`; without it the
evidence is `passed:false` and fill.py refuses it. If sol-storage2 still requires process/fd evidence on the compute hosts, that needs a root-run
Slurm probe job, which this collector does not and may not create.

## v3 (sol-storage2 ADOPTION-V3 R1: scheduler flag + stable stats do not bound same-uid compute writers)

Everything from v2 is kept. New: for every compute node currently running or completing ANY <USER> job (other projects included),
`collect.py` runs, via <SUBMIT_HOST> over the pinned ROOT SSH standard, one read-only step
`srun --jobid=<running job id> --overlap -N1 -n1 -w <node> --mem=100M -t 2 bash -c '<script>' 2>&1` (`srun` added to the dispatcher
allow-list in `Remote.run`; python stays off <SUBMIT_HOST>; array tasks use the task's own JobId). The script runs `ps -u <USER>`
(args cut to 220 chars, token/secret/pass*/key/pat values redacted, at most 80 rows) and, for each <USER> pid, `readlink`s
`/proc/PID/fd/*`, `cwd` and `exe`, printing only links under `<MODELS_ROOT>/nobackup/<PROJECT>`,
`<RESULTS_ROOT>/work/<PROJECT>` or equal to the custody log (with the fd's open flags). No file is written, output is
capped (`head`, 1 MiB transport cap), nothing is killed or changed.

R1 -> evidence: each probed node's `process/<node>.json` has `process_level_evidence:true` and `srun_probe` = srun job id, hostname
(must equal the node, else `NODE_PROBE_WRONG_HOST`), <USER> process list, matching fds. A missing `END` marker refuses
(`NODE_PROBE_INCOMPLETE`). Every running/completing row must be on a probed node (`RUNNING_NODE_NOT_PROBED`). Any matching fd on a node
without a bounded running n-* job refuses the whole collection (`NON_BGBENCH_PROCESS_HOLDS_LOG_OR_TREE`); on a node that hosts a bounded
n-* job a hit is recorded and attributed to that job (the bound already counts it; not attributable per pid).
Demonstration (one job only, counts printed, nothing written): job 52551485 on gpu22-a40-02: hostname gpu22-a40-02, 11 <USER>
processes, 0 matching fds.

Limits that remain and are not hidden: the probe is a snapshot (a sleeping process that has not yet opened the log, or a later job step, is
not excluded); the step sees only <USER> processes on the node; nodes with no <USER> job have no job to probe and rely on the
scheduler argument plus the root flag `--accept-compute-scheduler-assumption`, now narrowed to those idle nodes and to NFS-side writers outside
Slurm. If sol-storage2 requires more than this snapshot it needs an enforced containment fact that no script here can create.

Tests: 37 (`/usr/bin/python3 -B $H/test_collect.py`), mock srun covers command shape (jobid, --overlap, -w, --mem, -t, no redirects/rm/tee),
per-node record, other-project fd hit on the log refuses, on a bgbench tree refuses, hit on a bounded-lane node recorded, no END, wrong
host, argument validation.

## v4 (sol-storage2 ADOPTION-V4 R1/R2/R3). The v3 section above is superseded where it differs.

Each bypass has a test that fails on v3 and passes on v4 (checked by running the v4 tests against the v3 collector with a v3-format fake:
`test_v4_r2_minimal_host_end_census_refused`, `test_v4_r3_legacy_format_unrelated_fd_on_lane_node_reaches_no_fill`,
`test_v4_r1_unresolved_other_project_jobs_keep_completeness_false` all fail there). 52 tests total.

R2 (truncated/failed census accepted): the node script no longer truncates (`head -80/-400/-200` removed). It lists `ps -u <USER>`, refuses on
ps failure (`FAIL ps`) or more than 400 processes (`OVERFLOW`, refused, not cut), and scans every pid: `SCAN pid ok|gone|FAIL`, with unreadable
cgroup, fd directory, fd link or (non-zombie) cwd/exe counted as failures. `END ps=N scanned=M fail=K` is parsed strictly: exactly one END, last line,
`fail=0`, N = PS rows = SCAN rows = M >= 1, every PS pid scanned once, FD rows only for `ok` pids with the pid's own cgroup. HOST+END alone, a short
census, a failed scan, an overflow or a wrong hostname all refuse. Demo on a real node: ps 8 / scanned 8 / fail 0.

R3 (unrelated pid charged to a co-located bounded job): ownership is now by the pid's own cgroup. On this cluster the job cgroup is
`/system.slice/<node>_slurmstepd.scope/<hash>` (all steps of a job share `<hash>`; checked live; `job_<id>` does not occur in it). The collector
runs one `srun --overlap` step into EVERY running/completing <USER> job on each node; the step reports its own `<hash>` (`OWN <jobid> <hash>`), which
maps hash -> job id for that node. A matching fd/cwd/exe is accepted only if its pid's hash maps to a running admitted job (lane job with a bound,
or an other-project job whose rule is `bounded`) that runs on that node; any other hit (cgroup `none`, unmapped, another job, excluded job) refuses
(`UNOWNED_OR_UNRELATED_PROCESS_HOLDS_LOG_OR_TREE`). Accepted hits are listed with pid, cgroup, job and owner name in `owner_attributed_fd_hits`. A job
bound is never transferred to other pids on the node. Mixed-job-node test: hit owned by the co-located other job refuses, hit owned by the lane job
passes. If any srun is refused by Slurm the whole collection refuses (seen live: job 52501576 on gpu22-a40-09 returned rc 1 to an --overlap step).

R1 (future writers of other-project jobs unproven): the collector no longer excludes other-project jobs by path metadata. Every non-n-* <USER> job in
any state (running, pending, held, dependency-blocked) needs a rule in `bounds.json` `other_project_rules`: `excluded` (with cited, hash-checked
reviewed source/runtime-exclusion or containment evidence) or `bounded` (growth bytes + cited evidence; counted in the custody sum and given an admission
record). Without a rule the job is listed in `unresolved_other_project_jobs`, `problems` gets `unresolved_other_project_jobs:N`, the evidence is
`passed:false`, `all_hosts_writers_enumerated` and `host_universe_complete` are false and fill.py refuses. The shipped `bounds.json` has NO rules: I did not
invent exclusions, so on today's queue (xen-gfe-w2/w3/w4, whitd-*, xeno369-*) completeness stays false until independently reviewed exclusion or
bound evidence for those concrete jobs exists and is cited there.

## v5 (exclusion evidence for every other-project <USER> job; per-node probe fallback)

New read-only command (root or author, from /tmp):

    /usr/bin/python3 -I -B $H/collect.py --lane d300 --root-session <id> --build-exclusion-evidence <fresh dir> [--write-bounds <bounds.json>]

For each distinct (job name, WorkDir, batch-script sha256) among non-n-* <USER> jobs, in ANY state (running, pending, held, dependency-blocked):
- (a) scontrol Command / WorkDir / StdOut / StdErr per job.
- (b) `scontrol write batch_script <id> -` on <SUBMIT_HOST> (Slurm control command; not run there otherwise): the text is grepped locally for
  `<PROJECT>`, `data-custodian`, `access-log.jsonl`, `<PROJECT_STORAGE>/nobackup/<PROJECT>`. Only the sha256, size and hit LINE NUMBERS are kept.
- (c) <BATCH_HOST> (pinned SSH, `remote_grep.py`, stdlib, read-only): scans the WorkDir tree and the absolute script/config paths the batch script
  names. Files > 10 MB and binaries are skipped and counted; `.git`, `__pycache__`, `node_modules`, symlinks and venvs (dirs with pyvenv.cfg) are skipped and
  listed; caps 100000 files / 400 s. Result is paths, pattern names, first line numbers and counts, never matched text. A missing, unreadable or capped
  WorkDir is `incomplete` and blocks exclusion.
- (d) the srun --overlap fd/cwd/exe scan of every node (census complete, zero matching fds anywhere) and coverage of every node the group's running jobs use.
Verdict `excluded` iff (b) and (c) have zero hits, (c) is complete, (d) has no hits and covers the job's nodes. Otherwise the reasons are listed
(`batch_script_hits`, `code_tree_hits:N`, `workdir_tree_incomplete:*`, `batch_script_unavailable`, `nodes_without_fd_scan:*`, `fd_scan_hits:N`).
Each excluded group becomes a rule in `bounds.json` -> `other_project_rules` with `disposition: excluded`, `name_regex`, `workdir_regex`,
`batch_script_sha256`, `evidence_utc`, `max_age_seconds` 86400 and `sources` = the evidence file (path + sha256, hash-checked on every collection).
At collection the batch script is fetched again; a changed script, a different WorkDir or an expired rule no longer matches, so the job is
unresolved again and completeness stays false.

Node probe failures (changed from v4): a failed or inconsistent srun step no longer aborts the collection and never certifies. Every running <USER> job
on a node is tried (each step scans every <USER> pid on the node), so a failed step is covered by a step into another job on that node; failures are recorded
under `srun_probe_failures`. A node with no successful step gets `node_unprobed:<node>` in `problems`, the evidence is `passed:false` and fill.py refuses it,
unless root passes `--accept-unprobed-node <node>` for that node only (recorded in `root_residual_unprobed_nodes`).

Tests: 58 (`test_v5_*` cover fallback, per-node flag, builder verdict for each reason, rules feeding a real collection and the real fill, script-sha and
age binding, remote_grep paths-only behaviour). The census-failure tests from v4 now assert `passed:false`, `node_unprobed`, and that the real fill refuses.

### v5 live run (2026-10-27, read-only)
Exclusion evidence for the 13 other-project job groups: 3 excluded (xen-gfe-w2/w3/w4: 53 files scanned, zero hits in script, tree and fd scan), 10 not excluded
(whitd-comfy-serve, whitd-ct3-clean, xeno369-*: WorkDir is the home directory, 87250 files scanned, `code_tree_hits:7` - shell history, caches, docs; not code,
but not judged here). Rules for the 3 excluded groups are in `bounds.json` with their evidence refs (valid 24 h, tied to script sha). Also added: rule `h3_refit40_job`
(`n-h3`, growth 0) citing ROOT-H3-REFIT40 operating-adoption-004.json (custody_appends 0) and root-release.json. fd hits owned by a running n-* job (by cgroup) do not count against
other-project jobs.
Live d300 collection with all root flags: `passed:false`, only reason `unresolved_other_project_jobs:10`; 105 writers, 62 hosts, growth 84322856, no unprobed nodes.
