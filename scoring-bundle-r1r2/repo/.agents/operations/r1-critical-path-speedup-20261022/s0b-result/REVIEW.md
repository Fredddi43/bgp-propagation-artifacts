# S0b result: the single approved host run and the budget inputs it supports

- Approval: `workers/opus-takeover-20261021/review/o1-s0b-assembly-r2-frozen-review/s0b-execution-approval.json`
  (2c46b0a3, reviewer 4ba6111c).
- Preconditions verified before the run:
  - pins c6e6259e and every package file;
  - tool 2994d965, program a43dcd27;
  - `run-records/` absent;
  - S0 records d7bc2ea4 / aa657886 untouched.
- Run: one ssh at 08:37:36Z (intent) to 08:41:26Z (result) on <BATCH_HOST> (AMD EPYC 7601, 128 CPUs, python 3.12.8, numpy 2.5.2). No retry.

## Raw records (`s0b-host-timing/run-records/`)

| File | sha256 |
|---|---|
| intent.json | 7f963d64bb382e24cab6b23352656a59eed30a09546063c1e867b67adb8671b9 |
| result.json | 9bfd31cc76550ab4697c9b0d0898df5a08a4b56fdbef876ec9ffad4de7095004 |

- **rc 0, `complete` true, 10 parts, stderr empty, `torch_imported` false.**
- 221 s elapsed, max RSS 4.9 GiB, host load ~1.2-2.1 before and after.

## Host / local ratios (`ratios.py` → `s0b-ratios.json`)

- Same program, against `evidence/local-run.jsonl`.
- Ratio = host speed / local speed; lower means a slower host.

| Measurement (all sizes incl. 116 KB rows and curve rows) | Ratio |
|---|---|
| `check_forecast_rows` under tracemalloc (pre-label validation) | **0.709-0.744** |
| `check_forecast_rows` plain (post-label re-parse) | **0.553-0.617** |
| `json.loads` (O1 post-label decode) | 0.493-0.536 |
| driver `evaluate_retrospective` | 0.473-0.546 |
| sha256 in memory | 0.765 |

## Budget inputs: the r2 model recomputed per stage

These are inputs only. **No limit is proposed or approved.**

- A stage uses a measured factor only where S0b measured its dominant work.
- Every other stage keeps the r2 assumption 0.45-1.0 and says so.

| Stage | r2 (assumed) h | With S0b h | Factor |
|---|---|---|---|
| eval re-verify | 3.76-4.13 | same | measured on host (live v7) |
| pre-label validation | 13.4-37.1 | **18.06-23.54** | measured 0.709-0.744 |
| post-label re-parse (D-1) | 4.8-12.7 | **7.86-10.36** | measured 0.553-0.617 |
| scoring | 0.94-25.77 | same | assumption (needs torch) |
| partition decode, cached | 1.17-3.99 | same | assumption (`torch.load` unmeasured) |
| analysis bootstrap | ≤ 0.1 | same | assumption (`retrospective_14` unmeasured) |
| **eval process total** | 24.15-83.80 | **31.78-67.89** | |

**If O1 is adopted** (only after its CODEPASS):
- the post-label stage becomes 2.30-2.63 h at the measured `json.loads` factor;
- the total becomes **26.22-60.16 h**.

**Still unmeasured:** membership scoring, `retrospective_14`, `torch.load`, B1 storage/NFS reads, B2 decoded-object
building, and H3/stable payload kinds.

**Note:** the local rates in r2's evidence come from the same laptop as `local-run.jsonl`. The factor is applied to
those rates unchanged.

**Live-v7 consequence (no action):**
- At the measured host speed, pre-label validation alone is 18-23 h.
- The 12 h alarm (~10:29Z) is therefore expected to fire before the label opening, which agrees with the live loop observations.

## Tests

`test_ratios.py`: 2 passed. The output regenerates exactly, and only the supported stages use a measured factor.
