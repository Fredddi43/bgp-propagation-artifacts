# Review packet: N input-gate package, revision-v3 (round-2 G1, partial-assessment C1/C2/C3)

- Author: Opus 5.5 implementation session `065d2f16` (claude-opus-5-5), role label `/root/opus_implementation`.
- Status: synthetic-only candidate, ready for independent code review. Exact bytes: `pins.json` here.
- Answers the round-2 review `reviews/opus-gate-round2-review.txt` (9c1d5cc6) and its verdict (9d8b4455): G1 open,
  G2-G5 accepted. It also answers the reviewer's read-only partial assessment of this revision
  (`.agents/workers/opus-takeover-20261021/review/gate-v3-partial-assessment/assessment.txt`, c503e905):
  C1 blocking, C2, C3.
- revision-v2 (pins 80ef042b) and revision-v1 (`../pins.json` d9497c05) are unchanged.

**Not done and not authorized:**
- no run of A or B on real data, and no protected or remote read
- no execution-host preflight (see Limits)
- no authority, gate issuance, freeze, prediction or scoring
- no commit, stage or push

## Files and changes from revision-v2

| File | Change |
|---|---|
| `boundary.py`, `label_handoff.py` | byte-identical to v2 |
| `syscall_trace.py` | new. Pure parse and default-deny verify of an strace open-family trace |
| `audit_witness.py` | parent/child re-exec under strace; untraced witness, then the v3 witness with `syscall_trace`; plan fields `tracer_sha256` and `trace_reference_roots`; denylist backstop extended |
| `input_gate.py` | requires witness kind v3; re-verifies the trace; binding fields `tracer_sha256` and `trace_reference_roots`; recomputes the trace scope |
| `synthetic_world.py` | v3 code pins; the two new plan fields |
| `test_gate.py` | v2 tests adapted to v3, plus the round-2 and C1/C2/C3 tests |
| `mutation_controls.py` | v2 cases, 6 round-2 cases, 7 C1/C2/C3 cases |

## Round-2 G1: the observed set is closed at the syscall level

- `audit_witness.main()` (parent) runs the same entry point again as a child:
  `/usr/bin/strace -f -qq -y --seccomp-bpf -e signal=none -e trace=open,openat,openat2,creat,open_by_handle_at,io_uring_setup`.
  `-f` follows every thread and child process. `-y` prints the kernel's resolved path of each opened fd.
- The child refuses to run unless its TracerPid is that strace binary (`under_tracer`). It runs the v2 witnessed
  audit unchanged and writes `witness-untraced.json`.
- The parent parses the trace and applies `syscall_trace.verify`. Only then does it write `witness.json`, which
  carries the trace's path, sha256 and size, the tracer identity and the open counts.
- The trace stays beside the witness as `<out>.syscall-trace`. A failed attempt leaves it in place, so its output
  path cannot be reused (stage `tracer`).
- `parse` fails closed on:
  - an unparsable or truncated line
  - an unknown syscall
  - an unfinished syscall that never resumed, or a resumed one without its start
  - a successful open without a decoded absolute path
  - a non-octal escape
  - any successful `io_uring_setup` or `open_by_handle_at`
- The denylist of native readers stays as a backstop. It gained the reviewer's 9 round-2 names and 5 more.

## C1 (blocking): default deny

Every successfully opened path must fall in one named class, or the trace is refused:

| Class | Rule |
|---|---|
| data | under a data root, and a declared/observed path or a recorded listing directory |
| reference | under a plan-bound reference root: repo `src`, repo `scripts`, this package, `sys.prefix`, `sys.base_prefix` |
| system | a fixed file (`/etc/ld.so.cache`, `/etc/ssl/openssl.cnf`, `/etc/localtime`, `/dev/null`, `/dev/urandom`, 4 `/proc` and 5 `/sys` files) or a fixed prefix (`/usr/lib/x86_64-linux-gnu/`, `/lib/x86_64-linux-gnu/`, `/lib64/`, `/usr/lib/locale/`, `/usr/share/zoneinfo/`), or `/sys/fs/cgroup/.../cpu.max` |
| proc | `/proc/<pid>/...` of a pid that appears in the trace |
| input | the A plan and authority files, the child's entry script, and that script's directory itself (Python lists `sys.path[0]`) |
| output | under the witness output directory, the access log, the log directory itself |

- Prefix matching is by path component: `/data` does not admit `/database`.
- Data roots must not overlap the reference roots, the witness output directory, the inputs or the entry script.
- `reference_roots()` in `audit_witness.py` fixes the reference roots in code. The plan must name exactly that list,
  or the witness refuses at stage `plan`. So the list cannot be widened to a home directory, `/tmp` or a parent of
  a data root.
- The system list was measured from real synthetic audit runs on the development host. Testing found three gaps
  in the first list, now fixed: `/sys/devices/system/cpu/{present,kernel_max}`, the entry script and its directory
  (test drivers live outside the package), and the pid column. strace pads pids to five columns, so a pid below
  10000 is followed by two spaces. The first parser refused such lines.

## C2: the tracer binary is pinned

- The A plan carries `tracer_sha256`. The parent refuses at stage `tracer`, before creating the trace file or
  starting any child, when `/usr/bin/strace` hashes differently.
- B's external witness binding carries `tracer_sha256`. B refuses a witness whose recorded tracer sha256 differs.

## C3: B derives the trace scope from its own inputs

B requires the witness's `trace_scope` to equal values it derives itself:
- `roots` = the data roots recomputed from the documents B reads (stage receipt `data_root`, master
  `history_root`, export dir, the parents of master, construction and stage receipt, the master's graph parents)
- `reference_roots` = the binding's `trace_reference_roots`
- `skip_file` = the configured access log
- `entry` = this package's `audit_witness.py`
- `dirs` = the witness's own resolved listings, each an existing directory (lstat only)

B does not read the A plan and authority files. It only requires that they lie outside the data roots.

## Tests

Run with the repo `.venv`.

| Suite | Result |
|---|---|
| `revision-v3/test_gate.py` | 162 passed |
| original `../test_gate.py` (v1) | 43 passed |
| related suites (273) | 273 passed, 1 warning |
| `ruff check` on the package | All checks passed |

New for C1/C2/C3:
- An outside **copy** and an outside **hard link** of a data parquet, read through `pyarrow.memory_map` with the
  denylist emptied: refused at `trace` and no witness is written.
- `sole_offender`: each such negative also proves that renaming the offending path's opens makes the same trace
  verify. So the refusal comes from that path and nothing else in the run. The 9 round-2 no-denylist probes use it
  too, with reason `Unrecorded data open`.
- Positive control: every open of the real audit runs (d30, d60) falls in a named class.
- `verify` unit cases: each allowed class; 15 outside paths, including a prefix-sharing `/database`, an unlisted
  `/proc/<pid>`, `/proc/self`, another cgroup file and another file in the entry's directory; 12 malformed or
  overlapping scopes; 4 scopes where a reference root, the output directory, an input or the entry overlaps a data
  root, each otherwise consistent with its trace so that only the overlap check refuses (reason `overlap`).
- A: wrong planned strace sha refused at `tracer` with no sidecar, output or log; 4 plan-binding variants refused at
  `plan`.
- B: 9 forged-witness cases and 2 changed-binding cases, each refused at `evidence-d30` for its exact internal reason
  (`refused_because`).
- Parse: the padded pid column.

Mutation controls (`mutation_controls.py`, a throwaway copy per case):

| Mutation | Targeted tests |
|---|---|
| G1 no refusal at all | 13 failed, 149 deselected in 56.17s |
| G1 only package attribute patched | 4 failed, 9 passed, 149 deselected in 50.89s |
| G1 prebound check removed | 4 failed, 158 deselected in 19.71s |
| G2 binding check removed | 10 failed, 152 deselected in 22.24s |
| G3 A st_dev check removed | 1 failed, 161 deselected in 5.86s |
| G3 B mount check removed | 1 failed, 161 deselected in 11.39s |
| G4 explicit loads dropped | 1 failed, 161 deselected in 10.79s |
| G5a post-hoc records removed | 1 failed, 161 deselected in 10.47s |
| G5b shard records removed | 1 failed, 161 deselected in 10.99s |
| G1r2 A trace verification skipped | 9 failed, 153 deselected in 33.45s |
| G1r2 unrecorded data open accepted | 9 failed, 153 deselected in 36.05s |
| G1r2 bypass syscalls accepted | 1 failed, 10 passed, 151 deselected in 1.12s |
| G1r2 B re-verification removed | 8 failed, 154 deselected in 9.25s |
| G1r2 child tracer check removed | 1 failed, 161 deselected in 3.19s |
| G1r2 denylist additions removed | 2 failed, 7 passed, 153 deselected in 31.74s |
| C1 default deny removed | 17 failed, 145 deselected in 9.05s |
| C1 output/input overlap check removed | 3 failed, 1 passed, 158 deselected in 1.19s |
| C1 data/reference overlap check removed | 1 failed, 3 passed, 158 deselected in 1.11s |
| C1 A reference roots unbound | 3 failed, 1 passed, 158 deselected in 13.56s |
| C2 A tracer pin check removed | 1 failed, 161 deselected in 5.19s |
| C2 B tracer pin check removed | 1 failed, 1 passed, 160 deselected in 10.05s |
| C3 B scope taken from the witness | 7 failed, 2 passed, 153 deselected in 12.89s |

Every mutation makes at least one targeted test fail. The passing tests in a selection are its other cases
(for example the outside-open case of the B scope test, which the trace re-verification still refuses).

## Limits

- **Not an OS sandbox and not a universal host proof.** The trace shows which paths the traced tree opened, not
  what it did with them.
- Data placed under an allowed reference or system path is admitted. G4 hashes the loaded repo modules, but not
  other files under `src`, `scripts` or the venv.
- A descriptor received from another process is not an open in this trace.
- The tracer binary is hashed and then executed by path, so there is a short window between the two.
- The trace does not tell read opens from write opens (assessment N1). D4 stays covered by the stat-equality tests.
- The system list is measured on this host. Another host may open other system files; the witness then refuses,
  which fails closed.
- Execution-host preconditions, to check before any real witnessed audit (not done here):
  - `/usr/bin/strace` present with the pinned sha
  - ptrace of a child allowed (yama `ptrace_scope` <= 1, no Slurm or container policy blocking it)
  - `--seccomp-bpf` supported by that kernel and strace
  - a synthetic run on that host with no unlisted system path
