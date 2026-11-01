# Review packet: class (d) code transport + host D0 plan / D1 size census (LOCAL; nothing run on the host)

- Author: claude-opus-5-5, session <SESSION_ID> (`/root/opus_implementation`).
- It builds on adapter-r2 (pins 5eb25c10, under review) and verifier-r2 (pins 2a861eb0, CODEPASS 46c72360). Both are
  byte-checked against their pins and unchanged.
- It reuses the reviewed patterns: `stage_b8.py` for transport, f19d1066 for fetch.
- **Not done:** no ssh, no host read or write, no job, no label, prediction, per-event or report content read. The R1
  final evaluation (317830) is untouched.
- **Execution also requires the adapter-r2 CODEPASS.** Without it, no transport approval should be issued.

## Files

| File | Role |
|---|---|
| `stage_code.py` | One exclusive transport to the fresh `B/r1-posteval-classd-v1`. |
| `phases.py` | D0, D1 and the fetch request. |
| `test_host_phases.py` | Tests. |
| `mutation_controls.py` | Negative controls. |

`stage_code.py` details:
- **Transported files (5):** `code/adapter-r2/{adapter.py, run_adapter.py}` and
  `code/verifier-r2/{verify_r1.py, run_verify.py, pins.json}`.
  - This is the layout `adapter.load_verifier` expects.
  - `run_verify.py` rides along so the class (b) verifier run needs no second transport. Staging it authorizes no
    run.
- **Directories:** it also makes an empty `out/`.
- **Remote program:** base `python3.12 -I -S -B`. It asserts <USER>@<BATCH_HOST>, not Slurm.
- **Write rules:**
  - `dest` must not exist;
  - every sha and size is checked before `mkdir`;
  - `O_EXCL|O_NOFOLLOW`, fsync, 0444;
  - readback requires the exact file set, mode 0444, owner and sha, and an empty `out/`;
  - `stage-complete.json` is written last.

`phases.py` details:
- **D0** runs `run_adapter.py plan` in place.
  - Interpreter: `B`-venv `python -I -B` (numpy 2.5.2, the reviewed `_virtualenv` hook).
  - The host paths are fixed constants: seal `r1-seal-17f81575….json`, ledger, spec, `results/report.json`, the
    manifests d30/d60 and gate `training-integration-v6b-both.json`.
  - `--report-sha256` comes **only** from the executed captures: `requests.census(evidence/census.json)` must judge
    terminal success, and `requests.complete(evidence/capture-k2a.json.gz)` must be the passed final evaluation. The
    report sha is the one that `complete.json` binds. If either capture is absent, D0 refuses.
- **D1** runs `run_adapter.py census` with `--plan-sha256` taken from D0's recorded result. It is stat only: type and
  size per allowlisted path.
- **One attempt per phase:**
  - an exclusive intent record is written before ssh, and a result record after;
  - a failure is recorded and never retried;
  - the output sha is taken by `sha256sum` on the host in the same ssh.
- **fetch-request** builds the f19 request for `out/plan.json` and `out/census.json` at the recorded shas. If a
  result record is absent, it refuses.
- **The approval gate checks:**
  - an independent reviewer (no author session or worker);
  - scope `r1-posteval-classd-d0-d1-v1`;
  - `phases_authorized == ['d0','d1']`;
  - `tool_sha256`;
  - exact `host_paths` and `dest`;
  - `attempt_limit_per_phase` 1 and retry false;
  - label, prediction, per-event and **`d2_authorized` all false**.

`stage_code.py check` (local, no ssh):

```
tool_sha256 05de557954dfe37a82abe608fbdb8bade45b5331ac37ba93c450e2b6ab7c6392
code/adapter-r2/adapter.py      4ad7cfcd75f21a2b5608dd1e72d0e0c03404d129998e18e243d861b0bd9dd174
code/adapter-r2/run_adapter.py  e21e73be8f94c2cf22e89a2035897de6ab2824b0a723c51b7f6a11d01b900b3f
code/verifier-r2/pins.json      2a861eb0490e2b9b364c6130f1872a8c6b0663605455197c00cf07249a3459eb
code/verifier-r2/run_verify.py  36ab00c542e01867454f03af05d991cded0db8d61717bf5cd440930b883750dd
code/verifier-r2/verify_r1.py   5ed5229fe571a6a58c2274a34bbbd6bfa8fb20f53468672d59c0a4938bcd9ebf
```

`phases.py show`: tool_sha256 `71983db4f9a77f624a9d828ae78763e861b524acd32c68a52fb4255852ba340e`.

## Exact steps (each once, no retry, stop and report on any refusal; repo-root `.venv/bin/python -I -B`)

**Preconditions:**
- adapter-r2 CODEPASS;
- the R1 eval is terminal and successful;
- K1 and K2a have been executed under bdf45c60 and ed2059c5.

| Step | Command (from `.agents/operations/r1-posteval-verification-20261022`) | Needs |
|---|---|---|
| T1 | `classd-host/stage_code.py stage --approval <T> --approval-sha256 <sha>` | transport approval T |
| T2 | `classd-host/stage_code.py readback --approval <T> --approval-sha256 <sha>` (read only; **before** D0, since it requires an empty `out/`) | T |
| D0 | `classd-host/phases.py d0 --approval <P> --approval-sha256 <sha>` | phase approval P, captures present |
| D1 | `classd-host/phases.py d1 --approval <P> --approval-sha256 <sha>` | P, D0 recorded success |
| F | `classd-host/phases.py fetch-request > classd-host/request-fetch-d0d1.json`, then from `.agents/operations`: f19 `r1-prerequisite-evidence-20261021/capture_metadata.py r1-posteval-verification-20261022/classd-host/request-fetch-d0d1.json r1-posteval-verification-20261022/classd-host/evidence-d0d1.json.gz` | named in P |

**Expected sizes:**
- `plan.json`: 66 cells, about 7,086 tensor entries. That is paths and shas, estimated at about 2 MB (7,086 × about 250 B), under f19's 16 MiB
  per-file cap.
- `census.json`: the same entries with sizes.
- Neither file holds any label, prediction value or metric.

**After F**, the author publishes the actual census figures:
- tensor bytes per horizon;
- the maximum file;
- prediction and rule bytes;
- any missing or non-regular entries.

That publication is the input to the D2 review.

## D2 (PROPOSED ONLY; separate review after F; nothing here authorizes it)

**What it does:**
- It runs `run_adapter.py rescore` over the plan, the report, `results/per_event/` and the staged source tree
  (`--source-manifest` 7f35bd22).
- That reads R1 labels and committed predictions, which is class (d).

**Placement:**
- A Slurm array of 2 tasks, one per horizon, each with `--cells-file`.
- Partition `cpu`, 1 CPU each (the code is single-threaded), no `--nodelist`, well within the 5000-CPU user cap.

**Sizing:**
- `--mem` per task = 2 × that horizon's **measured** tensor bytes from D1 + 4 GiB.
- `--time` 2 h. The arithmetic is about 0.6 s per cell, measured locally.
- If D1 shows a horizon over 200 GiB, D2 is re-proposed instead.

**Rules:**
- Output goes to the exclusive `out/rescore-d{30,60}.json`, with findings only, and is fetched by f19.
- One attempt, no retry.

## Tests

| Suite | Result |
|---|---|
| `test_host_phases.py` | 31 passed |
| `ruff check` | pass |

**Transport:**
- the local files equal both frozen pins;
- a changed pin refuses;
- approval refusals (7): author session, author worker, tool, dest, run, attempts, a file sha;
- the remote program, run locally with the host and user patched:
  - it stages once with 0444 and reads back;
  - a second stage refuses;
  - wrong bytes refuse before `dest` exists;
  - readback refuses a stray output file, a stray `out/` directory and a writable file.

**Phases:**
- the report sha comes only from the captures, and an absent capture refuses;
- the exact commands carry every anchor;
- both commands parse under adapter-r2's real `run_adapter` argparse, with exact argument values;
- one attempt with records;
- a failure is recorded and never retried;
- the fetch request uses only recorded shas;
- `main d1` takes the plan sha from the D0 record, and a wrong approval anchor refuses;
- approval refusals (6): author, d2, phases, host path, labels, tool;
- no ssh without an approval.

**`mutation_controls.py`:** 11/11 detected.

| Mutation | Targeted tests |
|---|---|
| code bytes not bound to frozen pins | 1 failed |
| transport approval independence dropped | 1 failed |
| remote hash pre-check dropped | 1 failed |
| remote extra output unchecked | 1 failed |
| remote files left writable | 1 failed |
| remote mode not read back | 1 failed |
| d1 plan sha not from the d0 record | 1 failed |
| host report path unchecked by approval | 1 failed |
| report sha without approved captures | 1 failed |
| phase may be repeated | 2 failed |
| D2 may be approved here | 1 failed |

"Remote extra output unchecked" was undetected at first: the file-set check already catches a stray *file*. The
`out/` listing guard matters for a stray *directory*, and a test for that was added.

**Not authorized by any of this:** D2, labels, predictions, per-event or report content, N or protected-2026 data,
any install or venv write, copying GB data over the link, and any retry.
