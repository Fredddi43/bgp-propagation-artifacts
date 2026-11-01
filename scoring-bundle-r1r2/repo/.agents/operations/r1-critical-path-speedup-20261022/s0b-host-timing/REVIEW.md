# S0b: torch-free synthetic host timing on <BATCH_HOST> (LOCAL packet; nothing run on the host)

- Author: claude-opus-5-5, session <SESSION_ID>.
- Root authorizes LOCAL implementation only. **Host execution needs a fresh independent review and an exact approval**
  (new scope `r1-s0b-host-timing-v1`).
- Built from the reviewer's S0 terminal assessment
  (`workers/opus-takeover-20261021/review/s0-terminal-failure-assessment/s0-terminal-assessment.txt`), section 5
  fallback. Root chose it over the import-ordering variant (R1).
- **S0 is not retried.**
  - Approval cbecfab2 is consumed.
  - The S0 records `s0-host-timing/run-records/` (intent d7bc2ea4, result aa657886) stay untouched; a test pins them.
  - S0b has its own `run-records/` in this directory.
- S0 outcome, recorded separately: `s0-host-timing/coordination/run-outcome.json` (a6a539de).

## Diff from S0 (small, no framework)

| | S0 (a923415e / 2227fb6a) | S0b |
|---|---|---|
| torch | `import torch` after the hook: failed on the host's CUDA build (ldconfig spawn) | **never imported**. The hook refuses any `torch`/`cuda`/`triton` import, and the end line reports `torch_imported` |
| Hook position | before every third-party import | **unchanged**: before every third-party import. No spawn or `/dev/null`-write exception, no monkeypatching |
| scale (`check_forecast_rows` plain / traced / `json.loads`) | 300, 900, 1800 candidates | same, plus **3600 (~116 KB rows, B5)** and **900 with `curve_log_quantiles`** (`check_curve`, cummax) |
| bootstrap | `evaluate_retrospective` + `retrospective_14`, 200 / 1000 reps | `evaluate_retrospective` only (the driver's analysis). `retrospective_14` needs torch: **unmeasured** |
| score (`score_membership`) | 300 / 1200 | **unmeasured** (needs torch) |
| decode | sha256 + `torch.load` | sha256 only; `torch.load` **unmeasured** |
| Output | one JSON document at the end | **one flushed JSON line per completed part**: `meta` first (before the staged imports), `end` last |
| Tool | parses the last line | parses **every complete line**. `result.json` keeps rc, stdout and stderr verbatim plus `parts` and `complete`. Success needs rc 0, meta first, end last, and `torch_imported` false |
| Approval | scope, shas, command, one attempt, all false flags | same, with scope `r1-s0b-host-timing-v1`, **plus R4**: `host_venv_facts` naming the CUDA torch, and `local_run_host_import_equivalent: false` |

Unchanged:
- the exact remote command and the caps (wall 1800 s + 30 s kill, CPU 1800 s, AS 24 GiB, nice 10, single-threaded
  libraries);
- the read whitelist and the write/side-effect refusals;
- the identity guard (<USER>, <BATCH_HOST>, outside Slurm, `-I`);
- one attempt, never retried.

The program still opens nothing outside the staged v7 source, the interpreter prefixes, and `/proc`, `/sys` and the
other listed system paths.

## Host-import parity: what is and is not known

- The S0 traceback shows numpy imported fine under the hook on the host (program line 61); only torch failed.
- S0b imports, under the hook:
  - numpy;
  - the staged driver;
  - `forecast_custodian_eval` and what they import.
- Locally none of these imports torch: checked with `sys.modules` after the imports, and enforced in the program.
- **The local run is NOT host-import-equivalent** (local torch 2.14.0+cpu; host CUDA venv). If a host-only import path
  spawns or writes, the hook refuses it and the run fails closed. `meta` is already on stdout by then and is recorded.

## Measurements and what they feed

Ordered by budget value:

| Part | Feeds |
|---|---|
| scale | host factor for pre-label validation (13.4-37.1 h) and the post-label re-parse (4.8-12.7 h; O1 would replace this with `json.loads`, which is also measured) |
| bootstrap | the driver analysis (B4 half) |
| sha256 | CPU part of decode |

Still open:
- B1 (storage), B2 (object building), H3/stable payload kinds, membership scoring, `retrospective_14` and
  `torch.load`;
- each still needs the torch-ordering variant (reviewer R1) in a separately reviewed candidate.

S0b measures a host factor. It does not prove a runtime.

## Local evidence (same program, host/user/source substituted)

- `evidence/local-run.jsonl` (the stdout lines) and `evidence/local-run-binding.json` (program sha, substitutions,
  rc).
- rc 0, 10 lines, 147 s, max RSS 4.9 GiB, torch_imported false. scale plain 25.2-30.1 MB/s, traced 8.2-10.7 MB/s, json.loads 94.1-98.9 MB/s; 116 KB rows: 29.2 / 10.7 / 95.6 MB/s. Caps leave large margins; expected host time a few minutes.

## Tests (`test_s0b.py`: 59 passed; ruff clean)

**Inherited from S0:**
- audit read whitelist and refusals (now including `/dev/null` O_RDWR);
- side-effect events;
- wrong host / multithreaded libraries refused (real subprocess);
- exact remote command;
- approval refusals;
- one attempt with records;
- failure recorded and never retried;
- no ssh without an exact approval.

**New:**
- the hook refuses `torch`, `torch.cuda`, `cuda.bindings.runtime`, `cuda.pathfinder` and `triton` imports, and allows
  numpy, json and bgbench;
- **after the hook, in the real program** (subprocess, local host substituted):
  - a spawn is refused (`subprocess.Popen`, and `/dev/null` O_RDWR when DEVNULL is requested);
  - `import torch` is refused, even though local torch exists;
  - a file write is refused;
  - stdout stays empty in each case;
- the hook precedes `import numpy`, which precedes the staged driver import; the program text has no `import torch` and
  no `forecast_retrospective_scoring`;
- partial lines: meta + scale + a torn line with rc 1 records exactly 2 parts, `complete` false, stdout verbatim;
- incomplete outcomes refused: no end line, rc 1 after end, `torch_imported` true;
- approval refusals added: old S0 scope, missing venv facts, a claim of local equivalence;
- the S0 records keep their shas, and S0b's records directory is separate.

## Exact command (after an exact approval only; root routes it)

```
cd .agents/operations/r1-critical-path-speedup-20261022/s0b-host-timing
../../../../.venv/bin/python -B s0b.py run --approval <A> --approval-sha256 <sha>     # once; never retried
```
