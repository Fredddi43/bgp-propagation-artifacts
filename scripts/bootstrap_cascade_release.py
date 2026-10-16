"""Paired event bootstrap for the final 2025 cascade sensitivity comparisons."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import polars as pl


METRICS = ("event_id", "cascade_jaccard", "persist_jaccard")


def summarize(table: pl.DataFrame, *, resamples: int = 2000, seed: int = 0):
    rows = table.select(sorted(METRICS)).sort("event_id")
    if not rows.height or rows["event_id"].n_unique() != rows.height:
        raise ValueError("Expected nonempty unique event-level predictions")
    cascade = rows["cascade_jaccard"].to_numpy()
    persistence = rows["persist_jaccard"].to_numpy()
    if not np.isfinite(cascade).all() or not np.isfinite(persistence).all():
        raise ValueError("Nonfinite Jaccard values")
    differences = cascade - persistence
    draws = np.random.default_rng(seed).integers(0, rows.height, size=(resamples, rows.height))
    means = differences[draws].mean(axis=1)
    return {
        "event_ids": rows["event_id"].to_list(), "events": rows.height,
        "metric_columns": list(METRICS),
        "metric_content_sha256": hashlib.sha256(rows.write_json().encode()).hexdigest(),
        "cascade_jaccard_mean": float(cascade.mean()),
        "persistence_jaccard_mean": float(persistence.mean()),
        "mean_paired_difference": float(differences.mean()),
        "paired_difference_ci95": np.quantile(means, [0.025, 0.975], method="linear").tolist(),
    }


def run(root: Path):
    plan = json.loads((root / "nongraph-plan.json").read_text())
    reports = []
    for index in range(49, 60):
        task = plan[index]
        if task["kind"] != "cascade" or task["year"] != 2025:
            raise ValueError("Frozen cascade configuration mapping changed")
        folder = root / "nongraph-final/2025" / f"{index:03d}_cascade"
        if not (folder / "complete.json").exists():
            raise RuntimeError(f"Cascade {index} has not completed")
        sources = list(folder.glob("cascade_vs_persistence_*.parquet"))
        if len(sources) != 1:
            raise RuntimeError(f"Expected exactly one prediction table in {folder}")
        source = sources[0]
        reports.append({"task_index": index, "configuration": task["args"],
                        "source_rows": "analysis/nongraph/" + source.relative_to(root / "nongraph-final").as_posix(),
                        "source_rows_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                        **summarize(pl.read_parquet(source))})
    result = {"schema_version": 1, "comparison": "cascade_minus_persistence_jaccard",
              "resampling_unit": "event", "paired": True, "resamples": 2000,
              "seed": 0, "seed_reset_per_configuration": True,
              "interval": "two_sided_percentile_95", "quantile_method": "linear",
              "event_order": "event_id_ascending", "configurations": reports}
    destination = root / "nongraph-cascade-bootstrap.json"
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, indent=1, allow_nan=False))
    temporary.replace(destination)
    print(json.dumps([{key: row[key] for key in ("task_index", "events", "mean_paired_difference", "paired_difference_ci95")} for row in reports], indent=1))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_root", type=Path)
    run(parser.parse_args().run_root)
