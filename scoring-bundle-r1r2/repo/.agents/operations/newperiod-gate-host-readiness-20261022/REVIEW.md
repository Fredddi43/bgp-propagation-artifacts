# Review packet: execution-host readiness for the N input gate (<BATCH_HOST>), LOCAL candidate

- Author: claude-opus-5-5, session <SESSION_ID> (`/root/opus_implementation`).
- Status: plan and programs for independent review. Nothing was staged, installed, placed or run on the host.
- Gate: CODEPASS revision-v3. Pins fedf72b3; round-3 review 668b719e, verdict f1d86be2; commit 9207556.
- **The CODEPASS is code-only. It does not mean the host is ready.** This packet lists what is known and closes
  what can be closed locally. It also defines the one synthetic host run that would close the rest.

## 1. What was inspected on the host (read-only, bounded, once each)

Two probes, piped over `ssh -o BatchMode=yes <BATCH_HOST> 'bash -s'`. Each did stat, hash and version calls only.
No file payload, no directory walk, no write.

| Probe | sha256 as run | Output |
|---|---|---|
| `evidence/host_probe.sh` | 4bdde3b4 | `host-probe-output.tsv` |
| `evidence/placement_probe.sh` | e8a0ef30 | `placement-probe-output.tsv` |

| Fact | Value on <BATCH_HOST> | Consequence |
|---|---|---|
| host / user / Slurm | <BATCH_HOST>, <USER>, not in a job | the gate runs directly on the host, never under Slurm (a job's ptrace/seccomp policy is untested) |
| kernel | 6.6.144.1 | — |
| yama `ptrace_scope` | 0 | ptrace of a child is allowed (≤ 1 required) |
| `CONFIG_SECCOMP_FILTER` | y; this shell `Seccomp: 0`, `NoNewPrivs: 0` | `--seccomp-bpf` should work; only the synthetic run proves it |
| `/usr/bin/strace` | 6.1, sha256 `aebaf212ce84a12208c5fa25f08c892029e6f6949b778da55e071ac145404a1e` | differs from the dev host (6.19, f4734268). Plans and bindings on this host must name aebaf212. The output format of 6.1 is unproven until the synthetic run. |
| python | venv `<RESULTS_ROOT>/work/<PROJECT>/venv` → miniforge `python3.12` 3.12.8, sha 62f0c11a (= the R1 runtime); base prefix `<RESULTS_ROOT>/work/vllm/miniforge` | — |
| editable `bgbench` | `<RESULTS_ROOT>/work/<PROJECT>/repo/src` | see §2 |
| that checkout | branch `main` at 36ec73ac; it has none of the gate closure (`custodian_newperiod_inputs.py` etc. absent) and no `.agents` package | it cannot be the gate REPO as it is |
| N roots (models mount) | B, `data-custodian`, `newperiod-identification-v1` (access-log directory), `history-root-2026`, `development-data-newperiod-v1`: all `nfs4 nfs-inet-10:<CLUSTER_EXPORT>`, dev 80 (0:80), `f_fsid` 0 | G3 single-marker design: data and witness output must share dev 80, so the witness output goes under the models mount. `f_fsid` is 0 as predicted, so `st_dev` carries the proof. |
| results mount | repo/venv/miniforge on `nfs-inet-10:<CLUSTER_EXPORT>`, dev 81 | reference roots and data roots are on different devices and cannot overlap |
| system files | `/etc/ssl/openssl.cnf`, `/usr/lib/x86_64-linux-gnu`, `/usr/share/zoneinfo`, `/etc/localtime` (symlink) present | the measured allowlist classes exist; completeness is unproven (N5) |

The actual N gate inputs (custodian N master, exports, stage receipt) do not exist yet. Their exact roots must be
stat-probed again once they do.

## 2. Placement: why not the existing checkout, and what instead

**The problem.** The witness's trace reference roots are code-fixed: REPO/src, REPO/scripts, the package,
`sys.prefix` and `sys.base_prefix`.
- The shared venv's editable `.pth` puts the shared checkout's src on `sys.path`.
- Locally, a closure-only mirror run with `PYTHONPATH=<mirror>/src` failed every positive run. There was exactly
  one refused open: the editable src *directory*, listed by Python's path finder on an import miss.
- The round-3 reviewer saw the same thing with a mirror on the real venv.
- So the gate must run from a venv whose editable path is its own REPO/src.

**Rejected:**
- *Switching the shared checkout to the gate commit.* It changes the environment of every user of that venv,
  including the live R1 v7.
- *A fresh full venv.* An install, and not the reviewed package set.

**Chosen.** One self-contained placement on the results mount, for example
`<RESULTS_ROOT>/nobackup/<PROJECT>/newperiod-gate-host-v1/`:
- `repo/`: exactly the closure (`stage.py`), 105 files:
  - `src/bgbench/**`
  - the four audit scripts
  - revision-v3 with its pins
  - the reviewed boundary file its AST test compares against
  - `pyproject.toml`

  The closure refuses any data-like suffix. `stage-manifest.json` sits beside it.
- `venv/`: a hard-link copy (`place.py`, `cp -al` semantics) of the shared venv.
  - The only new file is `_editable_impl_bgbench.pth`, pointing at `repo/src`.
  - No existing file is written. The original `.pth` and every package are untouched (shared inodes).
  - `place.py` refuses unless the source venv has exactly the plain-path editable `.pth` to the expected checkout
    plus `distutils-precedence.pth`, and no other `.pth`.
  - This is unknown on the host until `place.py` runs. It fails closed.

**Local proof:**
- The placement passes 38/38 gate smoke tests and the full gate suite, 162 passed, with no `PYTHONPATH` and no
  change to the shared `.venv`.
- `sys.prefix` is the placement venv, and `bgbench` comes from the staged src.

## 3. Deployment findings that the code review did not cover

- **USER/LOGNAME must be set.** `custodian_access_log` records `getpass.getuser()`. In an empty environment
  that falls back to the passwd database (`/etc/nsswitch.conf`, `/etc/passwd`), and default deny refuses it.
  This was observed locally (14 refusals). `host_run.py` sets both. A real gate launcher must too.
- **Inherited descriptors (N1).** A descriptor passed in from the launching shell is invisible to the trace.
  `host_run.py` refuses if any fd beyond 0-2 is open at start. A real launcher should do the same: `-I -B`, a
  minimal environment, `close_fds`.
- **Data under reference roots (N2).** The base prefix is the shared `vllm` miniforge. `<USER>` can write to it,
  and the gate would admit data placed there. `host_run.py` records the names and sizes of data-like files under
  `sys.prefix` and `sys.base_prefix`, with no content read. The reviewer must judge that list before any real run.
  This walk is part of the reviewed host program, not of today's probe.
- **Tracer window (N4).** strace is hashed and then executed by path. This is unchanged and disclosed.
- **Witness output device.** The real witness output and the access log must be on dev 80 (the models mount)
  with the data. The placement itself is on dev 81, which is right: the references stay apart from the data.

## 4. The synthetic host run (proposed; needs its own exact approval)

**When:** only after the live R1 v7 preparation is terminal. Hard-linking increments link counts and ctimes on the
shared venv's files, so nothing is placed while it runs.

**Steps:**
1. **Local:** `python -B stage.py --dest <local>/newperiod-gate-host-v1/repo`. This writes `stage-manifest.json`;
   record its sha256.
2. **Transfer, as <USER>:** `rsync -rlt --chmod=Du=rwx,Dg=rwxs,Fu=rw,Fg=r` of `<local>/newperiod-gate-host-v1/`
   to `<BATCH_HOST>:<RESULTS_ROOT>/nobackup/<PROJECT>/newperiod-gate-host-v1/`. Never `-a`
   and never as root (slurm skill §0c).
   - The tools `stage.py`, `place.py` and `host_run.py` go to a sibling `newperiod-gate-host-tools-v1/`.
3. **Host:**
   `python3 -B tools/place.py --root <ROOT> --expected-stage-manifest-sha256 <M>`
   `--source-venv <RESULTS_ROOT>/work/<PROJECT>/venv`
   `--source-editable-target <RESULTS_ROOT>/work/<PROJECT>/repo/src`.
   Record the `placement.json` sha256.
4. **Host:**
   `<ROOT>/venv/bin/python -I -B tools/host_run.py --placement <ROOT>/placement.json`
   `--expected-placement-sha256 <P>`
   `--expected-strace-sha256 aebaf212ce84a12208c5fa25f08c892029e6f6949b778da55e071ac145404a1e --full`.
   - **Checks first:** host, user, no Slurm, ptrace, strace sha, no inherited fd, `-I -B`, the placement venv,
     the closure equal to the manifest, the editable `.pth` exact, a fresh `run/`.
   - **Then:** the CODEPASS gate suite (162 tests, synthetic worlds only, under `run/`), in about 4-6 min on CPU,
     run directly with low priority.
   - **Writes:** `run/pytest.log` and `run/result.json` (return code, summary, log sha, the data-like listing).
   - **Removes:** the synthetic worlds.
5. **Copy back, read-only:** `result.json` and the last 200 lines of `pytest.log`.

**Resources:** one process tree, CPU only, under 4 GB of memory. Disk: about 3 MB of closure plus hard-link
directory entries.

**Cleanup:**
- Keep the placement if the run passes; it becomes the gate placement.
- Otherwise `rm -rf <ROOT>`. Removing hard links never touches the originals.

**Not in this run:** any N data, custodian path, access-log write, gate issuance or protected read.

## 5. Still required before a real N gate on this host

1. The synthetic host run above passes. That proves strace 6.1 parsing, `--seccomp-bpf`, the system allowlist
   on this host, and the placement imports.
2. The reviewer has accepted the data-like listing (N2).
3. The real N inputs exist (custodian staging), and their exact roots are stat-probed. They must be on dev 80,
   with the witness output on the same device.
4. The real A plan and B binding name `tracer_sha256` aebaf212 and the `trace_reference_roots` that this
   placement's `reference_roots()` returns.
5. A launcher with USER/LOGNAME, a minimal environment, no inherited fd, and `-I -B`, plus exact execution approvals.

## Tests (local)

| Suite | Result |
|---|---|
| `test_host.py` | 24 passed |
| full gate suite from a local placement | 162 passed |
| gate smoke from a local placement | 38 passed |
| `ruff check` | pass |

`test_host.py` covers:
- **Closure:** equal to the CODEPASS pins, the four scripts, `src/bgbench` and the extras; no stray `.agents`
  files.
- **Refusals:** a data-like file in the closure (3 kinds, plus a control); a non-CODEPASS gate; any stage
  difference (an extra, a changed byte, a missing file, a symlink).
- **Unreviewed source venvs:** another target, a finder-style editable, an extra `.pth`, a setuptools finder.
- **Placement:** refuses a closure off its anchor or with extra content. The placement leaves the shared venv
  unchanged (same bytes, inode and link count of the original `.pth`; a package file shares its inode).
- **Host program, positive:** runs the smoke from the placement and keeps only `pytest.log` and `result.json`.
  A second attempt refuses.
- **Host program, refusals before writing anything:** wrong strace, Slurm, an inherited fd, no `-I`, a foreign
  python, staged bytes, the editable `.pth`, the placement anchor.

Mutation controls (`mutation_controls.py`):

| Mutation | Targeted tests |
|---|---|
| fd check removed | 1 failed |
| strace check removed | 1 failed |
| slurm check removed | 1 failed |
| staged tree not verified (host) | 1 failed |
| editable .pth not checked (host) | 1 failed |
| placement venv not required | 1 failed |
| unreviewed .pth allowed | 1 failed, 3 passed |
| editable shape unchecked (place) | 2 failed, 2 passed |
| stage verify ignores extras | 1 failed, 3 passed |
| data-like files allowed in closure | 3 failed |

All 10 guard removals make a targeted test fail.
