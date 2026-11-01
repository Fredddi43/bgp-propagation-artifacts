# R1 rank sidecar

A compact representation of the R1 (retrospective, 1 Sep to 31 Dec 2025) forecast rankings. For every cell it
covers, it is lossless for every ranking metric the R1 evaluator reports. The R1 raw forecasts, that is every
candidate probability and committed set of every R1 cell, take 432 GB and are not in the anonymous release. With this
sidecar and the released per-event score tables, anyone can recompute AP, P@k, recall@k, the coverage ceiling and the
event accounting of every covered R1 cell and event, using the released evaluator, and compare the results with the
released values.

**Status (2026-11-01):** built on the cluster, not yet part of any release. It covers 1,008 of the 1,032
committed R1 cells that report ranking metrics: 998 built, plus 10 alias cells that use their parent's rows. The
other 24 are named gaps, because their committed forecasts are no longer on disk (see "What is missing"). The 34
remaining committed cells (curve and count models) report no ranking metric. All three files together take
121,421,400 bytes (about 121 MB), compared with 432 GB of raw forecasts.

## Why a few integers per event are enough

The evaluator's ranking metric (`src/bgbench/forecast_ranking.py`, `event_ranking_metrics`, metric version
`ranking-v1`, file SHA-256 `4cea491ad7665b3ca57c4b07b2376b41643452dbe44734f7781b49540d840c97`, as pinned in the R1
source manifest) works as follows:

1. Candidates already in the input-seen set are removed. The remaining `ranked` candidates are ordered by descending
   score.
2. Equal scores form a tie group. Every metric is the exact expectation over random orders inside each tie group, so
   no tie-breaking rule matters.
3. The new members are `target - input_seen`, and there are `R` of them. AP divides by `R`, including new members the
   candidate generator never offered. P@k divides by `k`, recall@k by `R`, and the coverage ceiling is
   `(new members ranked) / R`. Events with `R = 0` are ineligible, with all of these set to `None`. A `no_input` or
   `technical_failure` abstention ranks nothing.

So each metric depends only on the following, for every tie group that holds at least one new member:

* the group's first rank position (`start`, 0-based),
* its size (`size`),
* the number of new members in it (`relevant`),

plus `R`, `ranked` and the status. Tie groups without a new member add nothing to AP, P@k or recall@k. Splitting or
merging them does not change any value, because the harmonic sums and hit counts depend only on where each group with
new members starts. The budgets are k = 5, 10, 20, 50, the evaluator's defaults, which every R1 scorer uses.

## Files (`sidecar/`)

| File | One row per | Columns |
|---|---|---|
| `cells.parquet` | committed R1 cell (1,066) | `cell_index`, `cell_id`, `format`, `scorer_path` (`membership`, `panel` = H3, `stable`, `curve` = no ranking metric), `alias_of`, `rank_rows_from` (the `cell_index` whose event rows this cell uses: itself, or the parent of an alias), `role_json`, `predictions_sha256`, `commitment_sha256` (the seal's bindings of the withheld raw forecasts), `per_event_file`, `per_event_sha256` (as in the R1 report), `verification` (below), `replay_reproduced_per_event_sha256`, counts |
| `events.parquet` | (cell, event) with ranking metrics | `cell_index`, `event_id`, `status`, `new_members` (R), `ranked`, `set_id`, `starts`, `sizes`, `relevant` (lists, one entry per tie group holding new members, in rank order) |
| `sets.parquet` | distinct (event, target, input-seen) | `set_id`, `event_id`, `target_asns`, `input_seen_asns` (sorted ASN lists: the `target` and `input_seen` arguments of the evaluator's ranking call; for `direct_fields_exact` cells, of the mirrored call, with the target from the source table) |
| `MANIFEST.json` | | SHA-256, size and row count of the three files; the R1 report, seal, ledger, spec, topology, `forecast_ranking.py` and source event table digests they belong to; the build and merge script digests; the cell count per verification mode |

`new_members` is always `len(target_asns - input_seen_asns)` of the event's set, and the checker verifies this. The
sidecar does not say which new member sits in which group. The metrics do not need that, and storing it would mean
one row per ranked new member (about 78 million).

## How it was built (`build/build_sidecar.py`)

The R1 evaluation scored the 1,056 non-alias cells in a 64-lane Slurm array. Each lane read a task envelope
(`scoring-array/lane-NNN/task-NNNN.json`, which holds the cell, its scoring context and the parent-verified metadata),
the cell's prediction bytes and its bound label files, and ran the pinned driver's scorer. The build replays these
tasks with the pinned R1 source tree. Every source file is checked against the topology's digests and imported from
source, never from a cached `.pyc`. The one change is that `event_ranking_metrics` is wrapped: the wrapper returns
the unchanged function's result and records, from the evaluator's own `_clean_ranking` and `_tie_groups` on the same
arguments, the tie groups that hold new members. Each captured event is checked as it is recorded: the metrics
recomputed from the captured groups alone (with `expected_average_precision` and `expected_hits_at`) must equal the
call's result. Each cell is checked once more after scoring, as follows.

* `replay_byte_exact`: all inputs of the task still exist. The replayed per-event rows, serialised as the R1 worker
  did it, must hash to the cell's `per_event_sha256` in the released R1 report, so the replay reproduces the released
  file byte for byte. Every captured call must also map to exactly one released row, and the row's ranking fields must
  equal the call's result.
* `direct_fields_exact`: the cell's label tensors are no longer on disk (see "What is missing"). The build makes the
  scorer's own ranking call on the committed forecast rows, mirroring `score_membership` lines 95-96 and
  `score_panel` lines 264-267 of `forecast_retrospective_scoring.py`. Candidates, scores, seeds and status come from
  the committed rows. For H3 cells, the aligned panel rows come from the pinned `aligned_rows`, which reads no labels.
  The 2-h target sets come from `set_final_2h` of the source event table that the R1 cohort manifests pin
  (`occurrence-final-v1/development-data/eventset/2025_leak/events.parquet`, SHA-256
  `2862855d49683b464d3d4b9bd9679cec22c7cec4365ff4be7e19dd33638840f8`). Every ranking field of every released row
  must equal the recomputed value exactly. For membership cells, every target-dependent decision field the released
  row carries must match too: Jaccard, true size, new TP/FP/FN, precision and recall. They are recomputed as
  `score_membership` does, with the pinned `membership_metrics` for model rows. This checks each event's target set
  beyond what the ranking fields show.
* `not_rebuilt_inputs_missing`: curve and count cells (adapted Chronos, zero-shot TSFM, count models) whose
  prediction files are gone. They report no ranking metric, so the sidecar needs nothing from them.
* `not_built_committed_forecast_missing`: ranking cells whose committed forecast file is no longer on disk. The
  sidecar has no event rows for them. `cells.parquet` names them, and the checker reports them as gaps.

Per cell, the build writes `work/events/<cell>.parquet`, `work/sets/<cell>.parquet` and `work/done/<cell>.json`
(atomically), so a rerun skips finished cells. `merge` combines them into `sidecar/`.

### The build that produced `sidecar/`

| Step | Slurm job | Wall time | Resources |
|---|---|---|---|
| dry run, one cell per scorer path | 52753044, 52753272 | 4 s to 9 min per cell | up to 37 GB RSS (stable replay) |
| inventory of surviving inputs (`build/inventory.py`) | 52753197 | 12 min 55 s | 1 CPU |
| run 1, 64 lanes (superseded; kept in `work/run1/`) | 52753340 | 20.1 min | 5.8 CPU-hours, max RSS 37.6 GB |
| run 2, 64 lanes, final script (all records) | 52753673 | 9.7 min | 5.7 CPU-hours, 6.1 element-hours, max RSS 38.2 GB |
| merge | 52753933 | 1 min 52 s | 10.3 GB RSS |

The replay script that wrote all 1,056 cell records is `build/build_sidecar-d3b2fdbe.py` (SHA-256
`d3b2fdbe9df4904bd489df9af824ec843d98143c4ab89cc57e47df1681a2f5c3`). `build/build_sidecar.py` (`48a16f83…`) differs
from it only in two lines of `merge` (schema inference and recording its own digest). Commands of the final build, each started from
`<SUBMIT_HOST>` in `/tmp` (paths relative to this directory):

```bash
sbatch --export=NIL --array=0-63 build/replay.sbatch   # one element per original R1 scoring lane
sbatch --export=NIL build/merge.sbatch
```

| Verification | Cells (aliases counted with their parent) | Fields checked at build |
|---|---|---|
| `replay_byte_exact` | 68: the 44 transfer-secondary cells on the 28-event "built" population, and the 24 stable-peer cells | per-event file reproduced byte for byte, plus every ranking field against its call |
| `direct_fields_exact` | 940: 698 membership + 232 H3, plus 10 aliases | every released ranking field, plus every target-dependent decision field of membership rows |
| `not_built_committed_forecast_missing` | 24 | none (gap) |
| `not_rebuilt_inputs_missing` | 34 curve/count cells | none (no ranking metric) |

**Determinism:** runs 1 and 2 were two separate Slurm arrays, with each lane on the same node in both. Their
per-cell `events` and `sets` parquet files are byte-identical for all 998 cells both runs built
(`build/compare_runs.py`). Run 1 used an earlier script version (`000fdeee…`) that stopped on the 24 missing
forecasts instead of recording them; its scoring path is unchanged.

## Checking it (`scripts/r1_rank_sidecar_check.py` in the repository)

```bash
python -I -B scripts/r1_rank_sidecar_check.py --sidecar <sidecar dir> \
    --per-event <released per_event dir> --report <released report.json> \
    [--mode entry|groups] [--workers N] [--src <dir holding bgbench/>] [--out result.json]
```

The checker first verifies the per-event files against the report's digests and the sidecar files against
`MANIFEST.json`. For every (cell, event), it then rebuilds a ranking with the sidecar's tie structure and recomputes
the metrics with the evaluator:

* `--mode entry` (default) calls `event_ranking_metrics` itself, unchanged. The synthetic ranking has candidates
  1..`ranked`, one score per tie group, and new members in the first `relevant` slots of each group. Unranked new
  members are extra target ASes outside the candidates.
* `--mode groups` calls `expected_average_precision` and `expected_hits_at` on the group sizes directly.

Every ranking field present in a released row must be equal: `average_precision`, `precision_at`, `recall_at`,
`coverage_ceiling`, `new_members`, `new_members_ranked`, `ranked`, `eligible`, `ranking_status` and
`metric_version`. Requirements: Python 3.12 or later, `numpy`, `polars`, and the repository's `src/` (only
`forecast_ranking.py` and its import `forecast_analysis.py` are used; the checker refuses to pass if
`forecast_ranking.py` differs from the pinned bytes). A copy of the checker is in `check/` next to this README.

### Result (2026-11-01, `--mode entry`, all 1,066 cells)

| | cluster node (Slurm 52754109) | workstation |
|---|---|---|
| environment | Python 3.12.8, numpy 2.5.2, polars 1.44.1, pinned R1 `src/` | Python 3.12.15, numpy 2.5.4, polars 2.0.0, repository `src/` (same `forecast_ranking.py` bytes) |
| per-event files hashed against the report | 1,066 of 1,066, 0 mismatches | 1,066 of 1,066, 0 mismatches |
| ranking cells compared (including 10 aliases) | 1,008 | 1,008 |
| ranking rows compared (eligible) | 3,473,224 (2,524,482) | 3,473,224 (2,524,482) |
| fields compared | 32,193,080 | 32,193,080 |
| mismatches | **0** | **0** |
| sidecar rows checked against their target/input-seen sets | 3,437,794, 0 mismatches | 3,437,794, 0 mismatches |
| gaps reported by name | 24 cells, 85,032 ranking rows (57,492 eligible) | the same 24 cells |
| cells without ranking metrics | 34 | 34 |
| wall time / CPU time, 8 workers | 14 min 26 s / 1 h 51 min | 32 min 46 s / 2 h 32 min (load average about 30 on 16 cores from other jobs) |
| peak memory | under 0.41 GB per process | 1.89 GB for the whole process tree (parent plus 8 workers); parent 0.39 GB |

Resource requirements: a few CPU-hours in total, spread over any number of workers. Memory is about 0.2 to 0.4 GB
per worker plus the parent. Disk: 121 MB for the sidecar, plus the 17 GB of released per-event files, which the check
reads in full. `--mode groups` makes the same comparison, 32,193,080 fields with 0 mismatches, in 3 min 18 s wall and
26 CPU-minutes on the workstation (8 workers). It skips building the synthetic ranking and calls the evaluator's
metric functions directly. The result files are in `check/`: `cluster-check-entry.json`, `local-check-entry.json`
and `local-check-groups.json`.

## What is missing, and what it means

The R1 evaluation ran on 23 October 2026 and was released on 24 October. By 1 November, several of its input trees were no longer on the
cluster (`build/inventory.py`, `work/inventory.json`, which uses only `stat()`):

| Gone | Used by | Consequence here |
|---|---|---|
| `occurrence-final-v1/graph-shards/` (the R1 test tensors behind the `graphs/2025-v6*` symlinks), `occurrence-final-v1/history-inputs-v1/{delay900,delay1800,withhold}-d{30,60}`, the H1/H3 panel tensors under `occurrence-final-compressed-v2/history-expanded-panel-inputs-astra-compressed-v2/` | the label side (`target_asns`) of 954 non-alias cells | the 930 of them whose forecasts survive (698 membership, 232 H3) are built with `direct_fields_exact`: targets from the pinned source table instead of the tensors. That this is the same target is checked by every released ranking field and, for the 698 membership cells, by every target-dependent decision field. The other 24 are the next row |
| `occurrence-final-v1/history-online-baselines-v1/` (committed forecasts) | 24 cells: the history-kNN online baselines (mean and median, matched and native, d30 and d60) of the `delay-900`, `delay-1800` and `withhold` history-sensitivity families | **not covered.** Their ranking metrics stay in the released per-event files but cannot be recomputed from this sidecar. These cells appear in the per-cell summaries of the R1 facts. No file under `paper/generated/` names them. Covering them needs the forecast files back (a copy or restore); regenerating them would be new predictions, not the committed ones |
| `occurrence-final-v1/retro-chronos-v6b/` (curve and count forecasts) | 34 curve and count cells | none for this sidecar: they report no ranking metric |

The stable-peer cells and the 28-event transfer-secondary population kept all their inputs and were replayed byte
for byte.

The 940 `direct_fields_exact` cells (930 built, plus 10 aliases) depend on one assumption: the evaluator's target
for each event is `set_final_2h` of the pinned source table. Three things support it. The R1 cohort manifests name
that table, with that digest, as their only source. Its sizes equal the released `true_size` of every event of every
membership cell that reports it. And every ranking and decision field of every released row matches exactly. What
these cells do not have, unlike the 68 replayed cells, is a byte-level proof that the deleted tensors held the same
target arrays.
