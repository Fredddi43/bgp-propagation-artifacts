# Adoption evidence collector (d300 v3 and h3refit40), V44

Author: sonnet worker (not a reviewer). Scripts only: no launch, issue, board post, git or remote write.
`collect.py` is read-only against <BATCH_HOST> (stdlib probes; one FSIZE-0 import trace) and <SUBMIT_HOST>
(squeue/scontrol/sacct only). It never opens a scientific payload, label, score, prediction, parquet or tensor.

## Root commands (from /tmp)

    H=<REPO>/.agents/operations/newperiod-timing-adoption-evidence-sonnet-v10-20261026
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

## v6 (root ruling: second exclusion rule class for jobs whose WorkDir is $HOME)

Ruling (coordinator, from root): a static text hit in the home WorkDir (shell history, caches, docs) is not evidence of a writer. Implemented as rule
class `home_workdir_live_scan`; the v5 class `tree_and_fd_scan` is unchanged. A group whose WorkDir is `<HOME>` is excluded iff
(a) its batch script has zero hits; (b) the srun --overlap scan of every process of each running job of the group (processes picked by the job's own
cgroup hash learned from a step inside that job) has zero open fds, cwd, exe or mmaps (`/proc/PID/maps`) under the protected <PROJECT> paths or the custody log;
(c) every such process's /proc cmdline and environ have zero pattern hits (counts only; unreadable environ is recorded as `na`, not as a failure; the probe's own shell is
skipped by a marker); (d) the scripts/configs the batch script names lie in a tree other than the <PROJECT> markers and not in system dirs, and the trees are recorded
(`command_trees`). Any hit, an unattributed running job (no step into it succeeded), a missing script, or hits in the referenced scripts keeps the group unresolved.
Pending jobs have no processes; `pending_jobs_without_processes` records how many. The home-tree text hits are kept as path + count (`non_dispositive_home_tree_text_hits`,
with the rationale), never contents. Same 24 h expiry and script-sha binding as v5.
Collection-time enforcement added: any <USER> process whose cmdline/environ hits the patterns must belong to a probed running n-* job's cgroup, else
`NON_LANE_PROCESS_TEXT_HIT` refuses; maps hits are attributed by cgroup exactly like fd hits. Tests: 66 (v6 cases: static hits non-dispositive, each live check blocks,
referenced-script hits block, non-home hits still block, text-hit refusal at collection, TXT wire format).

### v6 live results (2026-10-27, read-only; no job was touched or signalled)
- Exclusion evidence rebuilt live: all 13 other-project groups `excluded` (xen-gfe-w2/w3/w4 by class tree_and_fd_scan; whitd-comfy-serve, whitd-ct3-clean and
  xeno369-L-b3/b4/b5, S-b1..b5 by class home_workdir_live_scan: zero script hits, zero fd/cwd/exe/mmap and cmdline/environ hits for the jobs' processes, command trees recorded;
  the home-tree text hits are recorded as path + count, non-dispositive). 13 rules written to `bounds.json`, evidence in `exclusion-evidence-live/`.
- Live d300 collection: `passed:false`, refused with `UNCLASSIFIED_BGBENCH_JOB`: two root-side srun jobs named `oc-locale-probe` (<COMPUTE_NODE>, <COMPUTE_NODE>; Command `env`, WorkDir <HOME>,
  fields mention the pinned <PROJECT> venv path) have sat in CONFIGURING for more than 5 minutes. They are neither n-* lane jobs nor other-project jobs and have no bound
  rule, so the collector fails closed. They need a cited bound/exclusion rule (or to leave the queue) before a collection can pass; I did not invent one.
- Rule `oc_locale_probe` (growth 0) cites probe_nodes.py by sha256; marker-referencing non-n-* jobs now need a rule like lane jobs (WRITER_BOUND_REQUIRED).
- 2026-10-27 live d300 recollection (65 writers, no oc-probe, H3 array terminal): passed:true and the real fill.py accepted the evidence (collect then fill_wrapper back to back). Probe-time owners: hits owned by a job that finished before the final snapshot are attributed via the probe-time snapshot (owner_in_final_snapshot:false); unbounded ones still refuse. 71 tests.

## v7 (sol-storage2 ADOPTION-006 R1: evidence/adoption bound V44 but the real latest-phase gate returns V48)

v6 is untouched. v7 derives the phase and never hardcodes a version: `latest_phase()` (in `collect.py` and in v7's own copy of the filler `fill.py`) loads the pinned
`phase_compat.py` (sha256 b84be518...), scans `<ops>/*/root-joint-storage-phase*.json` for the single highest passed phase and runs the same `accept(...)` call
operate.py makes (`own_keys = timing*`), refusing if the result is not that phase. Every record of the evidence graph (root evidence, inventories, process facts,
admissions, runtime evidence and facts) carries `PHASE`; the filler's `packet()` takes the adoption's phase from the same function and checks it against the evidence phase, so V44
evidence cannot fill under V48 (test). `fill_wrapper.py` runs v7's `fill.py` (sha256-pinned) instead of the root v2 one; `collect()` refuses if the newest phase advanced since import.
Concurrences, operation review and root authority are not produced by this tooling and must be re-issued against the exact phase in `d300-root-evidence.json` (`phase`).
Regression test: v6's `PHASE` is V44 (e5fab44a), v7's equals the real gate's newest (V48, 913754c6 today, version >= 48), and the source files contain no phase literal.

V48 models margin and d300 stage_hold: V48 `models_minimum_bytes` 867383093888, live avail 868274405376 -> margin 891311488 B. stage_hold writes only the frozen source set
(plan.json + successor.py + job.sh = 30631 B, hard cap < 1 MiB in remote.py) with preflight `free >= floor` before the write; the later install_release adds a binding <= 256 KiB.
The 1 GiB `allocated_bytes` and 64 MiB logical figures are ceilings, not write sizes. So it fits with ~890 MB to spare, but only as long as no other writer eats the margin before the once.
Live run (V48): collect passed:true, real fill accepted it (adoption phase 913754c6). 75 tests.

## v8 (d300 moved to the v6 operator/successor namespace; adoption-007 pinned the v5 plan)

v7 untouched. v8 binds the v6 operator (`newperiod-timing-d300-operator-astra-v28-v6-20261027`): `collect.py` OPERATOR and `fill.py` PACKETS point there; `pins.json` d300 pins and template pins
are regenerated from that operator's own `templates/operation-review-stage_hold.FALSE.json` and operating-adoption template (all hash-checked). `operator_facts()` takes the plan from the v6 operator's
`source()` (successor v6 `plan.json`, sha 857c8b77..., root `.../timing-d300-shard0027-astra-v6/controls`) and refuses unless it equals the operator template's `plan` ref. The evidence records
`operating_plan` (path + sha256) and `fill.py` refuses evidence whose `operating_plan` differs from the adoption's plan (`EVIDENCE_PLAN_BINDING`; tests with a v5-plan and a missing field).
The phase is still derived (currently V48, 913754c6). `bounds.json`: the d300 non-job actor is now `d300_v6_stage_hold_and_singleton_worker`, citing v6 `prepare.py` (custody_appends 0).
Scheduler-external-writes fact: the v6 held submit no longer has `--export=NONE`; the fact now passes when the job script execs the worker under `env -i` (parsed from the operator's own job.sh,
recorded as `job_script_execs_under_env_minus_i`) and still records `sbatch_export_none:false`; stdout/stderr /dev/null and no mail are unchanged. A non-issued dry run on the live cluster passed
(plan 857c8b77, phase 913754c6, closure 3114 files). 77 tests.

### v8 amended in place for operator v7 (UNREVIEWED edit after the v6-operator version)
Operator is now `newperiod-timing-d300-operator-astra-v28-v7-20261027` (only prepare.py changed: held_argv `--export=NIL`, absolute paths in job.sh). `pins.json`, `fill.py` PACKETS, `collect.py` OPERATOR, the bounds actor
(`d300_v7_stage_hold_and_singleton_worker`, cites v7 prepare.py) are rebound; the job.sh parser accepts `/usr/bin/env -i`; the scheduler-external-writes fact records `sbatch_export: NIL`
(plan/successor unchanged, sha 857c8b77). `fill.py` changed, so `fill_wrapper.py` FILL_SHA256 was re-pinned. 78 tests; non-issued live dry run passed.

## v9 (d300 operator v8 + successor v7 namespace; v8 untouched)
Operator is `newperiod-timing-d300-operator-astra-v28-v8-20261027`, plan = successor v7 `.../timing-d300-shard0027-astra-v7/controls/plan.json` (sha 2541d4e0..., taken from the operator's
`source()` and required equal to its template `plan`); `pins.json` regenerated from the v8 templates; `fill.py` re-pinned in `fill_wrapper.py`; bounds actor `d300_v8_stage_hold_and_singleton_worker`
cites v8 prepare.py. `--export=NIL` fact unchanged. Phase still derived. 78 tests; non-issued live dry run: see result in the report. Unreviewed.

## v10 (sol-storage2 D300-V8 RETAINED-ALLOCATION-RECONCILIATION CHANGES; v9 untouched, unreviewed)
Evidence and adoption now bind `retained_allocation` (file `retained/retained-allocation.json`, a root record; `fill.py` copies the ref into the adoption and refuses unless the record is clean):
(a) census: `--retained-census` (default ROOT-D300-RETAINED-ALLOCATION-CENSUS-V1/census.json) is hash-bound; per-namespace and total arithmetic re-verified (v5 110080 + v6 1684480 + parent 512 +
    other entries = 1795072); its root must equal the plan's recovery root. A live stat-only recensus (`remote_census.py`, lstat only) must match it entry for entry; drift or a missing entry gives
    `retained_census_drift`, a new namespace `unmapped_retained_namespace:*`, and residue in the next attempt's own namespace `next_attempt_namespace_exists:*` (stage would refuse it: D300_REMOTE_NAMESPACE_EXISTS).
(b) terminal dispositions: `sacct -n -P -j 52573670,52574966` inside the collector, parsed and required to be CANCELLED by 0 (0:0) and FAILED (1:0) with an End time, not in squeue, and equal to root's `terminal-sacct.txt`
    (`--terminal-sacct`); raw output is stored hash-bound in `retained/sacct-terminal.json`. Other jobs via repeated `--terminal-job JOB:STATE:EXIT`.
(c) `--allocation-acceptance` is a REQUIRED input (d300): the file is hash-bound and must be a PASS (`passed:true` or verdict starting PASS), carry a reviewer_session and contain the census sha256.
(d) mapping (`charge_mapping`, needs root `--ack-charge-mapping`): V48 row `timing_d300_singleton_path_b` (read from the phase, 16106127360) vs next-attempt model = plan allocated ceiling (15032385536) + controls allocation (1073741824) = 16106127360,
    i.e. exactly the row, zero slack. The phase grants this row no consumption credit (so no credit/reset here) and the retained 1795072 B are physical allocations already inside current free space, hence inside
    the live free >= floor test; they are neither deducted from the row nor added to the model (no double count). The collector flags `next_attempt_model_exceeds_phase_row` if the model ever exceeds the row.
    Please review this reading: it is my interpretation of the phase accounting, not a phase statement.
Tests: 86 (each finding, incl. drift/new/own namespace, terminal mismatches, acceptance missing census sha / not PASS, ack flag, row overflow, stat-only remote script). Non-issued live dry run (with a SYNTHETIC acceptance file, since the real one does not exist yet):
passed, live recensus equals the census (1795072 B, no new namespaces), both terminal jobs confirmed, model == row.

### v10 amended in place (unreviewed): real sol-storage2 acceptance shape
Root's issuing run failed with `allocation_acceptance_has_no_reviewer_session`: the real acceptance (REVIEWER-sol-storage2-D300-RETAINED-ALLOCATION-ACCEPTANCE-PASS.json) has `verdict: PASS`, `accepted: true`
and a nested `reviewer: {model, session, role}`. `check_acceptance()` now reads reviewer session/model from the top level or from `reviewer`, treats every present signal (`passed`, `accepted`, `verdict`) as required to be
positive (at least one must exist), and also requires the terminal-sacct sha256 to appear in the acceptance when root's terminal file is supplied. Tested against the real file (and negative variants); non-issued live dry run with it passes.
