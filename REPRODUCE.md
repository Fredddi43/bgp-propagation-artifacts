# Reproduce measurements

Run the quick start in the README first. All commands below run from the repository root with the environment active and `BGBENCH_DATA_ROOT` set to the absolute `data/` path.

## Event tables

```python
import polars as pl

events = pl.read_parquet("data/eventset/2024/events.parquet")
events = events.filter(
    pl.col("error").is_null()
    & (pl.col("reason").fill_null("") != "rpki_invalid_sample")
)
test = events.filter(pl.col("split") == "test")
test = test.with_columns(
    (pl.col("set_d30s").list.set_intersection(pl.col("set_final_2h")).list.len()
     / pl.col("set_d30s").list.set_union(pl.col("set_final_2h")).list.len().clip(1)
    ).alias("jaccard_30s")
)
print(test.select(pl.col("jaccard_30s").mean()))
```

`set_d30s`, `set_d1m`, `set_d5m` and `set_d15m` are affected AS sets at the observation horizons. `set_T5m`, `set_T15m`, `set_T60m` and `set_final_2h` hold the target sets. The sets are public AS numbers, not anonymized author identifiers. Rows with a non-null `error` record failed replays and must be excluded from measurements. Preserve the supplied `split` column.

The origin-change paper population excludes `reason == "rpki_invalid_sample"`. Those rows form the separate label-free invalid stratum. A combined table without this filter does not reproduce the paper population. RPKI validity describes authorization status; an invalid origin change is not necessarily a hijack.

Directories ending in `_leak` and `_withdrawal` contain different event families. The primary recovery comparison uses matching `_hijack_first_transition` and `_recovery_first_transition` tables. Both retain first observed post-identifier origin transitions per session. Older `_recovery` and `_recovery_run_sensitivity` files describe different membership definitions and do not reproduce that comparison. The five-year measurement window and the three-year forecasting benchmark have different scope. The 2026 observation window ends in August. Use the stored temporal split, including its partial-year boundary.

Withdrawal path loss requires a latest-prior RIB no more than seven days old for every one of the ten replay collectors. Only the 50 events from 2024 and six from 2025 satisfy this requirement in the retained archives. Unsupported events remain in the tables with an explicit error and null measurement labels. The `withdrawal_baseline` contract retains the complete snapshot inventory, original and revised rows, and an independent source audit. Public verification reconstructs the original tables and checks the exact eligibility decisions and released bytes. All 2024 event bytes were unchanged, preserving the withdrawal transfer evaluation; the six supported 2025 events are in the training split and do not establish a test-set floor.

## Tables and figures

```bash
python scripts/paper_numbers.py --recovery-tag recovery_first_transition > work/five-year-numbers.md
python scripts/rpki_figures.py work/figures 2023 2024 2025 2026 \
  --exclude-reason rpki_invalid_sample \
  --frontier 2023=_labelled,2024=_labelled,2025=_labelled_frozen2505,2026=_labelled_frozen2505
python scripts/recovery_figure.py work/figures 2022 2023 2024 2025 2026 \
  --recovery-tag recovery_first_transition \
  --pairs 2023=_labelled,2024=_labelled,2025=_labelled,2026=_labelled
python scripts/beacon_trend.py work/figures
python scripts/paper_recovery_tables.py "$BGBENCH_DATA_ROOT" work/tables
python scripts/paper_frontier_tables.py "$BGBENCH_DATA_ROOT" work/tables
python scripts/paper_propagation_tables.py "$BGBENCH_DATA_ROOT" work/tables
```

The recovery table generator also reports exclusions by source error, shared-event component counts, and a sensitivity analysis that excludes source windows crossing midnight. Generated fact JSONs record hashes of the source files.

The headline plot also writes `rpki_headline_data.json` with the plotted values and populations. `recovery_pairs_data.json` records source hashes, CDF observations and histogram bins. Recovery timing uses continuous replay timestamps; its CDF excludes undefined timing for empty sets. The reach-ratio panel displays zero return reach explicitly and excludes zero hijack reach, with counts in the legend. Pair confidence intervals resample connected groups of shared hijack/return events rather than treating reused events as independent.

The year-specific suffixes select the catalogue population for recovery pairs and frontier measurements. The `_frozen2505` frontier variants use the fixed RoVista series selected for later years. The fact sheet prints multiple populations and available sensitivity variants; not every row appears in the paper.

### Forecast comparisons and supporting figures

After the README's numerical verification passes, regenerate the forecast facts,
paired model comparisons and two year-specific ladder figures from the released
results:

```bash
python scripts/compare_graph_models.py "$BGBENCH_DATA_ROOT" \
  "$BGBENCH_DATA_ROOT/expected-verification.json" work/graph_paired_comparisons.json
python scripts/forecast_paper_facts.py "$BGBENCH_DATA_ROOT" \
  "$BGBENCH_DATA_ROOT/expected-verification.json" \
  "$BGBENCH_DATA_ROOT/analysis/expected-graph-auxiliary.json" \
  work/forecast-facts.json \
  --nongraph-manifest "$BGBENCH_DATA_ROOT/expected-verification.json"
python scripts/ladder_figure.py 2024 work/figures/ladder-2024 \
  --nongraph-root "$BGBENCH_DATA_ROOT/analysis/nongraph" \
  --nongraph-plan "$BGBENCH_DATA_ROOT/analysis/nongraph-plan.json" --require-complete
python scripts/ladder_figure.py 2025 work/figures/ladder-2025 \
  --nongraph-root "$BGBENCH_DATA_ROOT/analysis/nongraph" \
  --nongraph-plan "$BGBENCH_DATA_ROOT/analysis/nongraph-plan.json" --require-complete
```

The ladder generator writes a PNG, the plotted numeric CSV and a source-hash
sidecar. It requires all four learned architectures, the historical baseline and
the type-prior cascade, matches their test-event IDs, and checks their common
persistence reference. The cascade is restricted to the graph test cohort for
these figures. Foundation models forecast counts only and are reported separately
in the forecast facts and manuscript table.

The paired comparison file uses 2,000 event-bootstrap resamples with seed zero
and unadjusted 95% percentile intervals. Its comparisons concern models evaluated
on identical event IDs; separate intervals for gains over persistence do not test
the difference between models. The facts collector reads the complete declared
model and auxiliary manifests rather than discovering whichever results happen to
exist. These commands reuse saved predictions and do not retrain models.

`docs/paper/generated/` contains the manuscript's generated numeric tables and supporting facts. The figure directory contains only figures included in the manuscript and their available numeric sidecars. Floating-point reductions, library versions and plotting versions can change the last digits or image bytes on regeneration.

## Models and rebuilding

The quick start installs CPU-only PyTorch and the `ml` dependencies to read saved probability evidence, instantiate graph models and inspect their states. The model definitions are in `gnn_train.py`, `gat_train.py`, `tgn_train.py` and `dyrep_train.py`. Files under `data/tgn/*/*/_results/` preserve experiment names, observation horizons, test-event metrics and retained checkpoints. Checkpoint `mu`, `sd`, `threshold`, `tag`, `delta_s` and `n_types` values describe the saved normalization and configuration.

The checkpoints alone do not contain their full input graphs. `bgbench --help` lists the ingest, replay, graph construction and training commands. Rebuilding those inputs requires the public MRT archives, the event manifests and the upstream topology/RPKI data. Large graph tensors and per-message replay directories are not part of this package. No training or large archive download runs during the quick start.

The final origin models were rebuilt with canonical replay membership, which stops an origin path at its first actor occurrence. Their retained training inputs still carried `measurement_version = 2`. After those fits, the exported builder advanced the origin cache marker to version 3 so that it rejects older version-2 caches that may contain the previous all-hop membership. This marker change does not alter numerical construction or model computation: with identical source inputs, options and numerical environment, fresh version-3 origin tensors have the same numerical contents as the corrected final version-2 tensors. Leak and withdrawal caches remain at version 2. Rebuild origin tensors in a fresh output directory; changing an old cache's version field cannot repair its contents.

Fresh training is not a bit-for-bit reproduction guarantee. The omitted replay and upstream inputs must be reconstructed, archive availability can change, and CPU/GPU kernels and library versions can change floating-point results. Use the recorded event cohorts, input hashes and run-time package versions to compare a reconstruction with the retained experiment. The verification workflow above instead checks the released predictions and measurements directly.

`data/expected-verification.json` declares the required measurements and model cohorts. The frozen event-ID tables check population completeness, while the collector-specific target tables retain full observed AS sets for checking per-collector scores. The public contract binds those derived targets to their released file hashes. Source hashes in their provenance identify the original inputs; raw replay files remain external to this package.

The 16 main-comparison probability files cover four architectures, 2024 and 2025, and 30 s and 60 s observations. They permit independent checks of candidate labels, average precision and thresholded prediction sets. Other runs retain exact membership/count predictions and weights; their intermediate probability tensors remain outside the package.

Model result CSVs retain predicted AS sets as JSON lists. The verifier independently
recomputes membership overlap, precision and recall against the full observed
targets, including ASes outside the candidate graph. Count forecasts retain their
horizon targets and quantiles for checking extent errors, observed-seed floors and
interval coverage. Their evaluation mask excludes count targets at or before the
observation cutoff.

Five early model-input tables originally had missing values in four redundant `asns_d*` count columns. The released tables fill those values from the corresponding `set_d*` lists; training and scoring used the lists and are unchanged. The `derived_count_bridge` entry in the verification contract identifies the transformation and its independent audit. Original count-column sidecars let the verifier reconstruct the exact decoded training tables and check their original content hashes. The bridge retains migration-time byte hashes, while the audit binds the released bytes after reencoding and anonymization.

The final archive-boundary correction has a separate `boundary_input_bridge` contract. It preserves explicit before/after rows and proves that 97 non-graph tasks consumed unchanged inputs. The 2025 prefix-floor baseline is the one affected task and was rerun after an event with unavailable source coverage was excluded. The release selects that versioned result; the retained original completion is historical provenance. The verifier reconstructs pre-boundary inputs before applying the earlier four-count bridge. Original completion hashes are preserved, and public verification hashes bind the anonymized files.

Run-time input and code hashes identify the analysis snapshot before anonymization. `MANIFEST.json` binds the released bytes. Generated manuscript facts and figure sidecars use `inputs_sha256` or `source_sha256` for the released data bytes and preserve the original digests in `pre_anonymization_*`. Collector-target provenance likewise distinguishes its original materialized hashes from the hashes of the released target files.

`data/analysis/nongraph/` separates parameter variants and includes saved cascade predictions, curve forecasts and prefix predictions. The numerical verifier checks these against the corresponding event targets and reported bootstrap intervals. Its output lists every declared table checked and any failure; a nonzero exit code means the package has not passed.

Rebuilding non-graph models needs additional optional environments. Prefix models
use scikit-learn/joblib; Moirai uses `uni2ts` and `gluonts`; TimesFM uses `timesfm`;
Chronos fine-tuning uses `chronos-forecasting` and `peft`, with PyTorch. Use the exact
package versions and model identifiers recorded in the final summaries and
`reproduction.json`, rather than assuming one environment fits every model.
`scripts/tsfm_curves.py` selects TimesFM's reference attention implementation to
keep padded short-context forecasts finite. The small numerical-verification
workflow above does not download these base models or rerun training.
