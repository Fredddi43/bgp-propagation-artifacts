# BGP propagation and recovery: review artifacts

This package contains code and derived data for the five-year measurement study of BGP origin changes, recovery, route leaks and withdrawal waves. The measurement period is January 2022 through August 2026. Forecast experiments use 2023–2025.

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
| `figures/` | Figure images and available CSV source tables |
| `docs/benchmark/` | Data card and label limitations |
| `MANIFEST.json` | File sizes and SHA-256 checksums |

Each checkpoint filename ending in `_model.pt` contains a saved model state, feature normalization and its training-selected threshold. Checkpoint availability varies across experiments. Evaluation tables also cover experiments whose checkpoints were not retained. These are research checkpoints, not deployed models.

The package does not include raw MRT archives, raw third-party catalogues, CAIDA relationship files, private route-server dumps, bulk graph tensors, credentials or internal job logs. Rebuilding graph tensors requires replaying the relevant public archives and obtaining the topology inputs. This package supports inspecting the saved measurements and recomputing the principal tables and figures without that ingest step; it is not a complete raw-data snapshot.

## Quick start

Use Python 3.12. From the repository root:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt -e '.[dev,plots]'
python restore_data.py
export BGBENCH_DATA_ROOT="$PWD/data"
export BGBENCH_WORK_ROOT="$PWD/work"
python -m pytest -q tests
python scripts/paper_numbers.py > work/five-year-numbers.md
```

`restore_data.py` verifies the published files and rejoins large files split for the anonymous mirror. It uses only the Python standard library. It creates `work/` for analysis outputs. See [REPRODUCE.md](REPRODUCE.md) for figures and data interpretation.

Code is MIT-licensed. Derived data retain the applicable upstream terms and citation requirements; see [the data card](docs/benchmark/data-card.md). The anonymized source snapshot contains no original git history or author metadata. Public routing prefixes, AS numbers, collector names and event times are preserved because they define the measurements.
