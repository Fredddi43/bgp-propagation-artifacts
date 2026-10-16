# Reproduce measurements

Run the quick start in the README first. All commands below run from the repository root with the environment active and `BGBENCH_DATA_ROOT` set to the absolute `data/` path.

## Event tables

```python
import polars as pl

events = pl.read_parquet("data/eventset/2024/events.parquet")
events = events.filter(pl.col("error").is_null())
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

Directories ending in `_leak`, `_withdrawal` and `_recovery` contain different event families, not interchangeable samples. The five-year measurement window and the three-year forecasting benchmark have different scope. The 2026 observation window ends in August. Use the stored temporal split, including its partial-year boundary.

## Tables and figures

```bash
python scripts/paper_numbers.py > work/five-year-numbers.md
python scripts/rpki_figures.py work/figures 2022 2023 2024 2025 2026 \
  --exclude-reason rpki_invalid_sample \
  --frontier 2023=_labelled,2024=_labelled,2025=_labelled_frozen2505,2026=_labelled_frozen2505
python scripts/recovery_figure.py work/figures 2022 2023 2024 2025 2026 \
  --pairs 2023=_labelled,2024=_labelled,2025=_labelled,2026=_labelled
python scripts/beacon_trend.py work/figures
```

The year-specific suffixes select the catalogue population for recovery pairs and frontier measurements. The `_frozen2505` frontier variants use the fixed RoVista series selected for later years. The fact sheet prints multiple populations and available sensitivity variants; not every row appears in the paper.

The existing fact sheet in `docs/paper/` is a retained research snapshot. Regenerate it from the released data for current tables. The exported figure images are the paper's retained images. Floating-point reductions, library versions and plotting versions can change the last digits or image bytes on regeneration.

## Models and rebuilding

Install the optional `ml` dependencies to inspect model states. The model definitions are in `gnn_train.py`, `gat_train.py`, `tgn_train.py` and `dyrep_train.py`. Files under `data/tgn/*/*/_results/` preserve experiment names, observation horizons, test-event metrics and retained checkpoints. Checkpoint `mu`, `sd`, `threshold`, `tag`, `delta_s` and `n_types` values describe the saved normalization and configuration.

The checkpoints alone do not contain their full input graphs. `bgbench --help` lists the ingest, replay, graph construction and training commands. Rebuilding those inputs requires the public MRT archives, the event manifests and the upstream topology/RPKI data. Large graph tensors and per-message replay directories are not part of this package. No training or large archive download runs during the quick start.
