# N-core calibration CPU execution r3: actual bindings + operator packet

Author: opus 55ef4bc5 (assigned by root ROOT-ASSIGNMENTS-V2). Independent reviewer: review2 (7f4c18c0). 55ef does not
review this packet. Local work only; nothing has been executed remotely.

## What this adds to the reviewed r2 wrapper (execute.py 7cc1dac5, unchanged) and producer (calibrate.py b8265789, unchanged)

1. **Exact source stage** (`build_stage.py`): the producer's repository-relative layout under the wrapper's STAGE.
   * `src/bgbench/**/*.py` comes from git `fc6e1a7f`.
   * The exception is `src/bgbench/forecast_release.py`, which is the 40 fits' snapshot release guard `75019bb6`
     (git blob of `8f547e87`). The producer requires the staged guard to equal both the fit snapshot's guard and the
     `release_authorization` the fits recorded (ledger `9b4388e5`, manifests[*].release_authorization.release_guard_sha256
     = `75019bb6`). Against `fc6e1a7f`'s file, only import formatting and `'gbdt_fit'` in OPERATIONS differ.
     Nothing on the calibration path uses `gbdt_fit`.
   * The fit snapshot `training-source-dae04f85` is reproduced locally: commit `8f547e87`'s `src/**/*.py` plus the
     driver and job script hash to `dae04f85` with `snapshot_digest`'s formula (asserted in the build).
   * The driver `scripts/forecast_newperiod_campaign.py` = `a2dbd83b` = the ledger's `driver_sha256`.
   * 97 files; source_files digest `0d48ce65`.
2. **Functional proof on the staged tree.** The r2 wrapper's own suite (`test_execute.py`, including the 40 genuine
   tiny development fits through the unchanged producer under the bounded wrapper) runs on a throwaway copy of the
   stage, with `PYTHONPATH=stage/src` so every imported bgbench module is the staged one, including the snapshot-era
   release guard. Result: **16 passed**.
3. **Remote packet** (`packet.py`, `run_calibration.py`, fixed job script):
   * STAGE `newperiod-core-calibration-source-v1`;
   * CONTROL `newperiod-core-calibration-control-v1` (`calibrate.sbatch`, plan/approvals/review and two `.sha256`
     files, records/);
   * OUTPUT `campaigns/core-calibration-v1` (producer only).
   * The job is `cpu`, 8 CPUs, 64 GiB, 12 h, no requeue. It runs the private interpreter `-I -B` with the exact thread
     variables, and stdout goes to `records/execute.stdout`.
   * Bounds:
     - metadata 128 MiB;
     - tensor 512 MiB (= the graph file cap);
     - prediction 512 MiB;
     - output 64 MiB (also RLIMIT_FSIZE).
   * Free floor 64 GiB.
4. **Two root authorities, each step once, no retry:**
   * **phase A:** preflight (namespaces absent, fresh df), exact stage upload (remote per-file sha, 0444/0555), job
     script, `sbatch --hold`, held readback;
   * **phase B:** review2 signs the producer approval and execution approval bound to the plan carrying the ACTUAL job
     id. Then a local re-check against the staged wrapper's `authority()`, write-once control upload with readback,
     held readback again, fresh df, `scontrol release` (once), wait (wall + 2 h), and a bounded capture: the stdout
     JSON only, plus stderr size/sha/last line.

## Inputs bound

| What | Path | sha256 |
|---|---|---|
| ledger | `campaigns/core-v1/ledger.json` | `9b4388e5` (root all40 assessment cf79a052) |
| slice rule | `occurrence-final-v1/slice-rules/issue-time-slice-rule-v6b.json` | `0291d789` (= `forecast_recipes.SLICE_RULE_SHA256`) |
| private runtime | `newperiod-gate-private-v1` | python `62f0c11a`, placement `838fa32c` |

## Tests

`test_packet.py`: 7 pass.
- The stage reproduces the snapshot and pins.
- The job script matches the wrapper's scheduler/thread checks.
- The remote unpack stages exact files and refuses a tampered archive or an existing namespace.
- The control upload is write-once.
- Held-identity refusals.
- Filled plan + approvals pass the staged wrapper's own `authority()`; reviewer `/root`, a forbidden flag, wrong
  bounds and a wrong plan are refused.
- The staged producer's `checked_approval` + `checked_imports` pass with the staged src only.

## Not covered / for review2 to decide

- The resource sizing (8 CPU / 64 GiB / 12 h) is not measured. The validation tensors of both horizons are read once
  per fit by the unchanged producer. Any bound overrun refuses (fail-closed, no retry).
- The joint-storage row is negligible (stage ~2 MB, output <= 64 MiB). Root passes the current phase minimum as
  `models_minimum_bytes`.
- No learned-inference freeze, scoring or protected read. An independent E1-E5 assessment of the publication is still
  required before any freeze.
