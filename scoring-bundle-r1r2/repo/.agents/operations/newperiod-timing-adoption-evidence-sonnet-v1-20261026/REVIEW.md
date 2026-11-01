# Adoption evidence collector (d300 v3 and h3refit40), V44

Author: sonnet worker (not a reviewer). Scripts only: no launch, issue, board post, git or remote write.
`collect.py` is read-only against <BATCH_HOST> (stdlib probes; one FSIZE-0 import trace) and <SUBMIT_HOST>
(squeue/scontrol/sacct only). It never opens a scientific payload, label, score, prediction, parquet or tensor.

## Root commands (from /tmp)

    H=<REPO>/.agents/operations/newperiod-timing-adoption-evidence-sonnet-v1-20261026
    O=<fresh absolute dir, must not exist>
    /usr/bin/python3 -I -B $H/collect.py --lane d300 --out $O --root-session <id> --issue --ack-risks \
        --ack-future-once-writers --ack-no-release
    /usr/bin/python3 -I -B $H/fill_wrapper.py --evidence $O/d300-root-evidence.json --adoption $O/adoption.json

    # h3refit40: driver.py adopt ... --bounds $O/h3-bounds.json --zero-writers-evidence $O/zero-writers-evidence.json
    /usr/bin/python3 -I -B $H/collect.py --lane h3refit40 --out $O --root-session <id> --issue \
        --ack-future-once-writers --ack-no-release

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
