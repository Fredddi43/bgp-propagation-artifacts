# Review packet: class (d) reconstruction adapter + host read request (LOCAL; synthetic and held metadata only)

- Author: claude-opus-5-5, session <SESSION_ID> (`/root/opus_implementation`).
- Governing documents: contract 48238fc3, addendum-1 7c161f63 §4-§6, root adopted-rules.
- It is separate from the frozen packets: capture f2b223ee, verifier bac7f440 and K2c 57e6dc3d are all unchanged.
  The verifier is loaded read-only and byte-checked against its own pins.
- **Not done:** no prediction, label, report, per-event, manifest or gate content read; no host action; no job
  submitted; no number. The R1 final evaluation (317830) is untouched.

## What it does

**`adapter.py` selects, binds and decodes. Every metric comes from the frozen verifier's `rescore_event` /
`compare_event`.**

**`fixed_cells`:**
- It takes exactly the protocol-fixed set:
  - the 46 analysis cells from the verifier's `derive_arms` over the ledger's R-core/R-gbdt/R-base runs;
  - the 62 retrospective-14 cells from `retro14_groups` over the seal.
- The union is 66. On the real held seal and ledger that is 40 R-core neural, 20 R-transfer repaired and 6
  deterministic baselines (mean matched and native, median matched).
- Each cell must be:
  - committed `forecast_rows_json`, not secondary;
  - on gate 7e48955b (a single gate for all cells);
  - on the horizon's manifest, 45865cdf (d30) or f885a805 (d60);
  - the sealed R1 population f5f212ba;
  - carrying a prediction sha.
- An extra pre-planned cell can come only from a frozen list file (`--extra-cells`). P1 is still pending, so that
  list is empty now. Any other cell refuses.

**`plan`, the exact allowlist:**
- per cell: predictions {path, sha} from the seal; the per-event file {name, sha} from the report, or
  `{scoring_failed}`; the decision-rule ref from the spec (40 learned core cells; none for transfer or baselines,
  as in `score_frozen`); the manifest and the gate;
- per horizon: test-target tensors {path, sha}. The paths are the manifest rows' `graph_path` (the
  `forecast_train.graph_path` rule). The shas are the gate's inputs for that manifest (custody `gate_inputs`).
  Rows, the sealed population and the gate inputs must be identical sets.
- The manifest and gate bytes are checked against their bound shas before parsing.
- Inputs not captured yet stay `null`; nothing is guessed.

**`census`:** lstat only, giving type and size of every allowlisted prediction, rule and tensor file. Paths must be
under the forecasting root; missing or non-regular files are listed.

**`rescore_cell`, all under kind `rescored_from_labels`:**
- The prediction, per-event and rule bytes are each hash-bound.
- The id sets of predictions, labels and per-event rows must be identical. An extra event, such as N or other data,
  fails.
- Candidates and seeds must equal the label tensor's, except a native-union baseline's candidates, as in
  `score_membership`.
- The rule `global_threshold` must equal the row threshold.
- Rules need the event's `history_signature`.
- Every per-event value is recomputed and compared under V1: AP and P@10 within tolerance; jaccard, `new_tp`,
  eligibility, new members, slice membership and the two-threshold Jaccard exact.
- A cell without a per-event file (a scoring failure) is reported as such. Nothing is substituted.

**Labels:** the staged, reviewed `forecast_train.load_partition` (ebf066a2) decodes them, loaded in place from the
staged source tree and byte-checked (addendum §5 allows reuse of input mechanics). It uses the gate's expected
hashes, with no extra graph dirs, exactly as `score_frozen` does.

**Chain to the report aggregates:**
- The per-event rows are proven equal to labels plus predictions here.
- The frozen verifier recomputes every C1-C4 and retrospective-14 aggregate from the same hash-bound rows.
- Together: report ← per-event rows ← committed predictions + released R1 labels.

R1 stays exploratory. The 1066/90 accounting and any actual scoring failures are carried as they are.

## Tests (synthetic; plus real held label-free metadata for the selection)

| Suite | Result |
|---|---|
| `test_adapter.py` | 32 passed |
| `ruff check` | pass |

- **Real seal/ledger/spec:** exactly 66 (40/20/6), all transfer cells `repaired`, 40 cells with decision rules.
- **Selection refusals (7):** uncommitted, another gate for every cell, another manifest, another population,
  another payload, an unknown (N) extra, a secondary extra.
- **Frozen verifier:** a changed byte refuses.
- **Plan:**
  - unknown inputs give null;
  - every path and sha is bound;
  - a scoring failure is recorded;
  - refusals: gate sha, manifest sha, a missing gate input, a gate not passed, a row without `graph_path`, the
    population.
- **Census:** stat only (unreadable files are still sized); outside-root and missing paths are flagged; refuses
  without a tensor allowlist.
- **Rescore,** against rows produced by the staged `score_membership` (test oracle only):
  - learned and baseline cells agree on every value;
  - 10 named disagreements: a changed label, an added new member, prediction sha, per-event sha, rules sha,
    candidate order, seeds, rule threshold, an extra label event, a missing signature;
  - a scoring-failed cell is reported, not substituted.
- **CLI `plan`** on the held metadata gives 66 cells, null tensors and per-event refs, and paths under the root.
  `census` then refuses (no allowlist yet) and writes nothing.
- **Label reader:** refuses another `forecast_train.py`; with the staged one it calls `load_partition` (test split,
  no graph dirs, the gate's hashes) and reduces events to the four needed fields.

**`mutation_controls.py`:** all 10 detected.

| Mutation | Targeted tests |
|---|---|
| gate binding dropped | 1 failed |
| population binding dropped | 1 failed |
| gate bytes unchecked | 1 failed |
| gate inputs not equal to population | 1 failed |
| prediction bytes unchecked | 1 failed |
| candidate alignment dropped | 2 failed |
| rule threshold unchecked | 1 failed |
| label population unchecked | 1 failed |
| frozen verifier pin dropped | 1 failed |
| label reader bytes unchecked | 1 failed |

"Gate binding dropped" was undetected until the `other-gate` case moved all cells. The single-gate rule had been
masking it.

## Host request (PROPOSED; nothing submitted; each phase needs its own exact independent approval)

**Preconditions:**
- the R1 final evaluation is terminal;
- K1, K2 (report + manifests) and K2c have been executed under their approvals;
- the code is staged.

**Code staging (planned, not implemented):**
- `adapter.py`, `run_adapter.py`, `verifier/verify_r1.py` and `verifier/pins.json` go to a fresh
  `B/r1-posteval-classd-v1/code/`.
- They are written exclusively at 0444 with readback, by a reviewed transport in the `stage_b8.py` pattern.

**Python and inputs:**
- Interpreter: `<RESULTS_ROOT>/work/<PROJECT>/venv/bin/python -I -B` (numpy 2.5.2 as the verifier
  requires; torch for `load_partition`).
- All inputs are read in place on the host; nothing GB-scale crosses the link.

| Phase | Class | Inputs (host paths; every one sha-checked) | Output (fresh `B/r1-posteval-classd-v1/out/`, exclusive; fetched with f19) |
|---|---|---|---|
| D0 `plan` | label-free metadata | seal `…/custody/r1-access/r1-seal-17f81575….json` 6412d726; ledger `control-v1/prepared/evaluation/ledger.json` ec445b8d; spec `control-v1/prepared/spec.json` 17f81575; `results/report.json` (sha from K2a); manifests 45865cdf/f885a805; gate `occurrence-final-v1/manifests/training-integration-v6b-both.json` 7e48955b | `plan.json` (66 cells; about 7,086 tensor entries) |
| D1 `census` | stat only | every allowlisted prediction, rule and tensor path | `census.json`: files, bytes, maximum, non-regular |
| D2 `rescore` | **R1 labels + committed predictions** (class d) | plan + report + `results/per_event/<66 files>` + the staged source `B/r1-release-assembly-v7-20261022/source/src` | `rescore-d30.json`, `rescore-d60.json` |

**D2 resources, from measured and synthetic cost (not guessed):**
- Arithmetic is about 0.6 s per cell (3,543 events × 300 tie-heavy candidates, measured locally), so about 1 min
  for all 66.
- The cost is decoding the tensors, so memory and time are fixed from D1's measured bytes before D2 is approved.
- Proposal: a Slurm array of 2 tasks (one per horizon, `--cells-file` per horizon) on partition `cpu`.
  - 1 CPU each; the code is single-threaded.
  - `--mem` = 2 × the measured tensor bytes of that horizon + 4 GiB.
  - `--time` 2 h.
  - No `--nodelist`; within the 5000-CPU user cap.
- One attempt, no retry. A refusal or mismatch is reported, never repaired.

**Not authorized by any of this:** N or protected-2026 data, other cells, refits, new statistics, manuscript use
before the verifier's run passes its own review.
