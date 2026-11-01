# chain-d40: D-A40 stable-lane-only re-scoring (the third label read)

D-A39 (job 52728251) scored every R2 secondary family except stable, which failed in the pinned evaluator
(`forecast_custodian_eval._jaccard`: "Empty target and prediction: Jaccard undefined on a scorable event"). On 2026-10-31T23:24Z
<AUTHOR> approved ONE disclosed third label read for the stable-peer lane only, with this rule: an event whose stable-peer target AND
forecast are both empty is NOT SCORABLE in the stable lane; it is excluded from that lane's scored events and counted; nothing else
changes. `primary.json` of attempt 12 stays the primary result.

## Files

| File | What |
|---|---|
| `r2_rescore_stable.py` | The D-A40 driver, derived from `chain-d39-v2/r2_rescore_secondary.py` (its docstring lists every change). |
| `r2_stable_not_scorable.py` | The rule, installed only on the stable consumer's `persistence` and its private `m.score_cell`. |
| `r2_rescore_stable.sbatch` | The Slurm job (`--export=NIL`, job name `r2-d-a40`, same resources as D-A39). |
| `test_r2_stable_not_scorable.py`, `test_r2_rescore_stable.py`, `test_r2_rescore_stable_binding.py` | New/adapted tests. |
| `test_r2_parallel_integration.py` | Adapted to the D-A40 attach points (stable only). |

Every other file is a byte-identical copy of `chain-d39-v2` (the checkpoint keys hash several of them by name and content). The
D-A39 driver, its sbatch and its two driver tests are not copied.

## Run (cluster)

The directory must be deployed at
`<RESULTS_ROOT>/nobackup/g2-chain-20261029T001120Z/repo/.agents/operations/agy-lanes-20261027/g2r2/chain-d40`
(the `CHAIN` path in the sbatch). Slurm does not create the log directory:

```bash
mkdir -p <FORECAST_ROOT>/newperiod-g2-inference-v1-20261027/r2-rescore-D-A40-logs
```

**1. Dry run** (label-free; stops right before the label opening):

```bash
sbatch --export=NIL <RESULTS_ROOT>/nobackup/g2-chain-20261029T001120Z/repo/.agents/operations/agy-lanes-20261027/g2r2/chain-d40/r2_rescore_stable.sbatch dry-run
```

It writes `newperiod-g2-inference-v1-20261027/r2-rescore-D-A40-dry-run-<jobid>/records-dry-run/ready.json`. The dry run refuses
unless every preparation loads from its checkpoint with the exact byte binding D-A39 was approved on (`2eeaaaea98a1...`), both
the attempt-12 and the D-A39 markers read back as pinned, the committed non-baseline stable cells reproduce their decisions in
float64, and every committed stable cell of a horizon forecasts nothing on the same events.

**2. Approval file** (the owner writes it after reading `ready.json`; `ready.json` carries this template under
`approval_fields_required`). Suggested path:
`<FORECAST_ROOT>/newperiod-g2-inference-v1-20261027/r2-rescore-D-A40-approval/APPROVAL-D-A40.json`

```json
{"deviation": "D-A40", "third_label_read_authorized": true, "scope": "stable lane only",
 "labels_sha256": "20e3044fa439866512d618d540dcefad1516151bc3f63ac482ee480bb6303447",
 "seal_sha256": "8ede1a58a437559ea1fb5259edd60141e1a8312ae286a978e7e4554e19a6014f",
 "freeze_sha256": "921fc9bb06888e39b2399735cd2bc673506116375b5be84ce16dfee59b33beaa",
 "primary_json_sha256": "849e064518d1aa7e0b1c61c4c5836acd75864de12dce0278dab75918493e9ac1",
 "records": "<FORECAST_ROOT>/data-custodian/single-R2-v1/arms/000/rescore-stable-D-A40",
 "approved_by": "<name, no whitespace>", "approval_record": "<where/when the approval was given>",
 "dry_run_ready": {"path": "<absolute path of ready.json>", "sha256": "<sha256sum of ready.json>"}}
```

**3. The one label-opening run:**

```bash
sbatch --export=NIL <RESULTS_ROOT>/nobackup/g2-chain-20261029T001120Z/repo/.agents/operations/agy-lanes-20261027/g2r2/chain-d40/r2_rescore_stable.sbatch open-labels-D-A40 <FORECAST_ROOT>/newperiod-g2-inference-v1-20261027/r2-rescore-D-A40-approval/APPROVAL-D-A40.json
```

Records go to `data-custodian/single-R2-v1/arms/000/rescore-stable-D-A40/` (must not exist; created exclusively): `intent.json`,
the marker `third-label-read-D-A40.json` (written right before the one label read), `primary-recomputed-D-A40.json` and
`primary-scores.json` (consistency check against attempt 12), `families/stable.*`, `stable-result-raw.*`, `stable-result.json`,
`completion.json`, and the runner's `done.json` on success only. The other eight family entries are prepared but not scored and
are recorded as "not in D-A40 scope".

## Tests (local, label-free)

```bash
cd .agents/operations/agy-lanes-20261027/g2r2/chain-d40
<REPO>/.venv/bin/python -B -m pytest -q -p no:cacheprovider
```
