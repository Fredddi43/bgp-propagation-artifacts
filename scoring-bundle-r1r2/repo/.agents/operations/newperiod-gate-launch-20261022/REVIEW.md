# Review packet: N input gate execution launcher (LOCAL candidate; nothing authorized)

- Author: claude-opus-5-5, session <SESSION_ID> (`/root/opus_implementation`).
- Purpose: close the "real N gate launcher" prerequisite that the host reviews left open. Once the placement and
  the real N inputs exist, the gate can be run exactly once per phase with no further design work.
- It invokes the **unchanged CODEPASS gate v3** (pins fedf72b3: `audit_witness.py`, `input_gate.py`) from the
  host placement (base packet adbf072b design; revision-v2 7cbdf2ff under review, untouched).
- It **reuses the CODEPASS evaluation v7 execution contract** (`launch.py` stage/launch → detached `supervise.py`
  → `run.sh` → worker → `execution-exit.json`), retargeted:
  - `supervise.py` is byte-identical below its root check; a test enforces this.
  - `launch.py` and `run.sh` differ only in the roots, the file set and the interpreter.
  - The independence rule and the bounded failure record are the same as the evaluation's.
- **No new scientific gate or rule.** No frozen-2025 or P9 change. Nothing is written or chmodded inside the
  hard-linked venv.

## Design point surfaced: two separately approved phases

The B gate plan must bind each witness's `witness.json` and audit-report sha256, and its `witness_binding.modules`
must equal the witness's recorded module map. Those bytes exist only after A has run. B's authority is an
externally approved anchor over that exact plan (G2). So the launcher has two exact-once phases:

| Phase | Control root (models mount, the data's device) | Runs | Approval must say |
|---|---|---|---|
| `witness` | `B/newperiod-input-gate-v1/witness-control-v1` | A d30, then A d60 | `n_input_read_authorized: true`, `gate_issuance_authorized: false` |
| `gate` | `B/newperiod-input-gate-v1/gate-control-v1` | B, once | `n_input_read_authorized: false`, `gate_issuance_authorized: true` |

The B plan for phase 2 is built from phase 1's outputs and reviewed like any plan. The worker then refuses unless
B's bindings name the witness phase that actually ran: its `execution-exit` is 0, plus its plan and authority
shas, the tracer, this placement's reference roots, the placement python, and the witness paths under phase 1's
outputs.

**Rejected alternative:** a single launch whose worker fills in B's witness references itself. That would remove
the external anchor of B's plan (G2). Choosing it would be a design change to the reviewed gate, not a launcher
detail.

## What `gate_execute.py` checks, before any stage

1. **Host:** `<BATCH_HOST>`, `<USER>`, not in a Slurm job, no inherited descriptor beyond 0-2.
2. **Spec:**
   - the phase, scope and root match, with exactly the 4 static files, the launcher sha and gate pins fedf72b3;
   - `pending == []`;
   - finite limits: `nice ≥ 10`, `threads ≤ 4`, `wall_seconds ≤ 4 h` per stage, plus RLIMIT_AS/FSIZE/CPU values;
   - every reference is `{absolute path, 64-hex sha256}`.

   A null, partial or missing identity refuses; nothing defaults to a broad root.
3. **Approval:** an independent reviewer (not 065d2f16 or f1d352ff, not `opus_implementation`), the phase's scope,
   `attempt_limit` 1, `execution_authorized`, the phase-specific flags above, and every forbidden flag false
   (labels, prediction, scoring, fits, freeze, calibration, R1, automatic retry).
4. **Placement:**
   - `placement.json` and `stage-manifest.json` match the spec;
   - the staged closure matches its manifest byte for byte with no extra file;
   - the gate package's `pins.json` is fedf72b3;
   - this process runs from the placement venv with `-I -B`.
5. **Stages:** each plan and authority is the staged copy, at its exact sha, and each plan names the approved
   access log with its output under `<root>/outputs`. A plans name the approved tracer and this placement's
   reference roots. The witness output root, the access-log directory, `data_root` and `history_root` share one
   device (G3).
6. **Gate phase only:** the witness-phase bindings above.

**Then:**
- The spec's limits are applied to the worker itself (inherited by every stage and strace) and read back into
  `execution-started.json`.
- Each stage runs as `<placement>/venv/bin/python -I -B <gate>/<entry> --plan ... --expected-plan-sha256 ...` in
  a minimal environment: `PATH`, `LANG`, `USER`/`LOGNAME`, `HOME`/`TMPDIR` under the root, `CUSTODIAN_ACCESS_LOG`,
  and the thread caps.
- Each stage gets a durable intent record before it starts and a result record after it ends.
- The first non-zero stage ends the phase. `execution-result.json` and the supervisor's `execution-exit.json` are
  terminal. A repeat refuses (`execution-started.json` and `outputs/` exist). No retry.

## Tests

| Suite | Result |
|---|---|
| `test_launch.py` | 36 passed |
| `ruff check` | pass |

All tests use a local placement built with the base packet's stage/place tools, synthetic worlds from the gate's own
`synthetic_world.py`, and copies of the static files whose only change is the fixed host constants.

- **End to end:** supervise → `run.sh` → worker → the unchanged A twice, then the unchanged B, gives a passed
  gate. Limits are observed: AS 8 GiB, FSIZE 256 MiB, CPU 3600 s, nice ≥ 10. A second run of a phase refuses.
- **Failure path:** a d60 plan with a wrong export-input hash makes A refuse (`WitnessFailure: preimage`). The
  phase ends with rc 1, d30 keeps its result, and nothing retries.
- **Spec refusals (10):** a null plan path, an authority sha mismatch, pending items, nice 0, wall time over 4 h,
  no limits, another access log, another placement, another tracer, other gate pins.
- **Approval refusals (9):** an author session, the author label, a label containing an author session, no N-read
  authority in the witness phase, gate
  authority in the witness phase, retry, labels, attempt limit 2, the wrong scope.
- **Plan refusals (3):** other reference roots, another tracer, an output outside the phase root.
- **Process refusals (4):** an inherited descriptor, a foreign python, no `-I`, a Slurm environment.
- **Closure:** a changed staged closure file refuses.
- **Gate phase (5):** B bindings naming another plan, tracer, python or reference roots refuse, and so does a
  witness phase whose exit was not 0.
- **`launch.check`:** binds the exact package (static, reviewed and stage documents). A changed stage document or a
  different launcher refuses.
- **Contract:** `supervise.py` equals the evaluation v7 body below the root check.

Every refusal also asserts that no `outputs/`, no `execution-started.json` and no stage record exist.

## Unresolved until the real artifacts exist (each refuses today; nothing is defaulted)

1. **R1 release complete.** N admission depends on it; v7 is running.
2. **Placement:**
   - the host revision-v2 review, then the synthetic host run;
   - the reviewer's judgement of `reference-data-like.json`;
   - its real `placement.json` and `stage-manifest.json` shas.
3. **Real N inputs** from custodian staging: the A plans' `data_root`, `history_root`, stage receipt,
   construction, master, export manifest and inputs, graphs and history years.
4. **Resource values for real data.** The synthetic suite is measured at 4 GiB AS. A real audit's needs are
   unknown; the reviewer sets them in the spec, within the coded caps.
5. **Phase-1 spec, A plans and authorities, and approval.** After phase 1, the B plan (bindings from the
   witnesses), its authority, the phase-2 spec and its approval.

**Mutation controls:**

| Mutation | Targeted tests |
|---|---|
| unresolved references accepted | 1 failed |
| author may approve | 1 failed |
| phase flags unchecked | 1 failed |
| limits unchecked | 1 failed, 1 passed |
| staged closure unchecked | 1 failed |
| placement venv not required | 1 failed, 1 passed |
| inherited descriptor allowed | 1 failed |
| plan tracer/roots unchecked | 1 failed |
| output outside phase root allowed | 1 failed |
| gate binding unchecked | 4 failed |
| witness exit unchecked | 1 failed |
| first failure does not stop the phase | 1 failed |

All 12 guard removals make a targeted test fail.
