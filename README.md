# BGP Propagation and Return Paths: review artifacts

This package contains code and derived data for the five-year measurement study of BGP origin changes, recovery, route leaks and withdrawal waves. The measurement period is January 2022 through August 2026. Forecast experiments use 2023–2025; beacon snapshots extend through September 2026.

## Contents

| Path | Contents |
|---|---|
| `src/bgbench/`, `rust/` | Ingest, identification, replay, validation, measurement and forecast implementations |
| `scripts/` | Analysis, table and figure scripts |
| `workflow/` | Example workflow configurations, with local data paths |
| `data/eventset/` | Event identifiers, temporal splits, affected AS sets at observation and target horizons, RPKI validity, recovery pairs and measurement summaries |
| `data/inventory/` | Replay selections and manifests |
| `data/rpki/` | Derived RPKI beacon reach tables |
| `data/tgn/*/*/_results/` | Retained graph-model checkpoints, training summaries and per-event evaluation tables |
| `data/analysis/` | Corrected auxiliary and non-graph evaluations, with separate parameter variants |
| `data/verification/` | Small derived verification targets and source provenance |
| `figures/` | Figure images and available CSV source tables |
| `docs/benchmark/` | Data card and label limitations |
| `MANIFEST.json` | File sizes and SHA-256 checksums |

Each checkpoint filename ending in `_model.pt` contains a saved model state, feature normalization and its training-selected threshold. The verification manifest declares the required graph checkpoints. Prefix-model states and the Chronos adapter are stored with their non-graph results and reproduction metadata.

The package does not include raw MRT archives, raw third-party catalogues, CAIDA relationship files, private route-server dumps, bulk graph tensors, credentials or internal job logs. Rebuilding graph tensors requires replaying the relevant public archives and obtaining the topology inputs. This package supports inspecting the saved measurements and recomputing the principal tables and figures without that ingest step; it is not a complete raw-data snapshot.

## Quick start

Use Python 3.12 and a C/C++ build toolchain. If no binary wheel is available,
`pybgpkit-parser` builds from source and needs Rust/Cargo on `PATH`; its parser
dependency requires [Rust 1.87 or newer](https://github.com/bgpkit/bgpkit-parser/blob/v0.18.0/Cargo.toml).
Use a current stable Rust toolchain for that build. Install the pinned dependencies
below: older Parquet readers may not support the released files.

From the repository root:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install torch==2.14.0 --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r requirements.txt -e '.[dev,plots,ml]'
python restore_data.py
export BGBENCH_DATA_ROOT="$PWD/data"
export BGBENCH_WORK_ROOT="$PWD/work"
python -m pytest -q tests
python scripts/verify_corrected_release.py data \
  --manifest data/expected-verification.json --output work/verification.json
python scripts/paper_numbers.py --recovery-tag recovery_first_transition > work/five-year-numbers.md
```

`restore_data.py` verifies the published files and rejoins large files split for the anonymous mirror. It uses only the Python standard library. It creates `work/` for analysis outputs. See [REPRODUCE.md](REPRODUCE.md) for figures and data interpretation.

The numerical verifier checks the declared event populations, set counts, paired recovery statistics and model summaries. It recomputes membership and count scores from saved predictions and full observed targets, and ranking scores for the main graph comparisons from retained probabilities. CPU-only PyTorch reads those saved files; PyTorch Geometric supports the graph regression tests. Verification needs no GPU. These checks validate the released measurements and aggregation; they do not perform fresh model inference or reconstruct the raw archives.

Code is MIT-licensed. Derived data retain the applicable upstream terms and citation requirements; see [the data card](docs/benchmark/data-card.md). The anonymized source snapshot contains no original git history or author metadata. Public routing prefixes, AS numbers, collector names and event times are preserved because they define the measurements.
