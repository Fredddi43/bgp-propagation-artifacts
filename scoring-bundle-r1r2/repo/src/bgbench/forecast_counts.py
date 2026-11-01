"""Exact observed count contexts for matched-horizon curve baselines.

Counts are evaluated from real first-observation timestamps. No future point is
interpolated into a short context. Protected periods require custodian export;
the CLI here only builds retrospective development datasets.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from .forecast_protocol import INPUT_CUTOFF_RULE, INPUT_CUTOFF_RULE_ID, available_at_expr, check_timestamp_precision, utc


def relative_first_times(membership, onset):
    """Per-AS (label, input) times in seconds after onset, aligned by ASN.

    Label time: pooled raw first_seen (truth). Input time: per-collector
    availability (forecast_protocol.available_at) BEFORE pooling, so a
    whole-second record counts in a context only from ts + 1 s.
    """
    import polars as pl
    check_timestamp_precision(membership, ts_column="first_seen")
    table = (membership.with_columns(available=available_at_expr("first_seen"))
             .group_by("asn").agg(pl.col("first_seen").min(), pl.col("available").min()).sort("asn"))
    rel = lambda column: [(utc(t) - onset).total_seconds() for t in table[column].to_list()]
    return rel("first_seen"), rel("available")


def count_context(first_seen_seconds, cutoff_seconds, bin_seconds=1):
    if cutoff_seconds <= 0 or bin_seconds <= 0:
        raise ValueError("Positive cutoff and bin width required")
    grid = np.arange(0, cutoff_seconds, bin_seconds, dtype=float)
    grid = np.append(grid, float(cutoff_seconds))
    observations = np.asarray(first_seen_seconds, dtype=float)
    if not np.isfinite(observations).all():
        raise ValueError("Nonfinite first-observation timestamp")
    # Discard future values before constructing any context statistic.
    observations = np.sort(observations[observations <= cutoff_seconds])
    return grid, np.searchsorted(observations, grid, side="right")


def build(manifest_path, data_root, out, bin_seconds=1):
    import polars as pl
    manifest_path, data_root, out = map(Path, (manifest_path, data_root, out))
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("locked_test") or manifest.get("protected_test"):
        raise ValueError("Protected count inputs require the custodian workflow")
    if any(utc(r["onset"]).year >= 2026 for r in manifest["events"]):
        raise ValueError("This preparation is restricted to pre-2026 retrospective data")
    out.mkdir(parents=True, exist_ok=False)
    horizons = np.array([300, 900, 3600, 7200], dtype=float)
    events, contexts, targets, sources = [], [], [], []
    for row in sorted(manifest["events"], key=lambda r: r["event_id"]):
        onset = utc(row["onset"])
        issue = utc(row["issue_time"])
        cutoff = (issue - onset).total_seconds()
        if cutoff != manifest["delta_s"]:
            raise ValueError("Count preparation requires a fixed observation horizon")
        path = data_root / ("events_replay_" + manifest["family"]) / row["event_id"] / "membership.parquet"
        relative, available = relative_first_times(pl.read_parquet(path), onset)
        # Context (input) on availability time; truth (label) on raw first_seen.
        grid, context = count_context(available, cutoff, bin_seconds)
        truth = np.searchsorted(np.sort(relative), horizons, side="right")
        contexts.append(context)
        targets.append(truth)
        events.append({"event_id": row["event_id"], "split": row["split"], "onset": onset.isoformat(),
                       "issue_time": issue.isoformat(), "incident_id": row["incident_id"]})
        sources.append({"event_id": row["event_id"], "path": str(path),
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    np.savez_compressed(out / "counts.npz", context=np.asarray(contexts), target=np.asarray(targets),
                        context_seconds=grid, target_seconds=horizons,
                        event_ids=np.array([e["event_id"] for e in events]))
    receipt = {"manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
               "data_sha256": hashlib.sha256((out / "counts.npz").read_bytes()).hexdigest(),
               "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "context_definition": "cumulative distinct-AS first sightings on exact observed-time grid; no interpolation",
               "bin_seconds": bin_seconds, "delta_s": manifest["delta_s"],
               "collector_scope": "pooled canonical membership", "events": events, "sources": sources,
               "timestamp_precision": "Grid resolution is not a claim about source timestamp precision; "
                                      "whole-second sources admitted iff ts + 1 s <= issue",
               "input_cutoff_rule": INPUT_CUTOFF_RULE}
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return {"out": str(out), "events": len(events), "context_points": len(grid),
            "data_sha256": receipt["data_sha256"]}


def export_partitions(dataset, manifest_path, out, bin_seconds=None):
    """Preparation-only operation: physically separate fit inputs from test labels."""
    dataset, manifest_path, out = map(Path, (dataset, manifest_path, out))
    receipt = json.loads((dataset / "receipt.json").read_text())
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    if sha(dataset / "counts.npz") != receipt["data_sha256"] or sha(manifest_path) != receipt["manifest_sha256"]:
        raise ValueError("Count data or manifest digest mismatch")
    if (receipt.get("input_cutoff_rule") or {}).get("id") != INPUT_CUTOFF_RULE_ID:
        raise ValueError(f"Count dataset was not built under cutoff rule {INPUT_CUTOFF_RULE_ID}")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("locked_test") or manifest.get("protected_test"):
        raise ValueError("Protected export must run inside the designated custodian workflow")
    data = np.load(dataset / "counts.npz", allow_pickle=False)
    ids = data["event_ids"].tolist()
    by_id = {r["event_id"]: r for r in manifest["events"]}
    if len(by_id) != len(ids) or len(set(ids)) != len(ids) or set(ids) != set(by_id):
        raise ValueError("Count/manifest population mismatch")
    grid = data["context_seconds"]
    points = np.arange(len(grid))
    if bin_seconds is not None:
        if bin_seconds <= 0 or grid[-1] % bin_seconds:
            raise ValueError("Coarser regular bins must divide the observation cutoff")
        requested = np.arange(0, grid[-1] + bin_seconds, bin_seconds)
        points = np.searchsorted(grid, requested)
        if (points >= len(grid)).any() or not np.array_equal(grid[points], requested):
            raise ValueError("Rebinning may select only exact existing observations")
        grid = grid[points]
    out.mkdir(parents=True, exist_ok=False)
    parts = {}
    for split in ("train", "validation", "test"):
        indices = np.array([i for i, eid in enumerate(ids) if by_id[eid]["split"] == split])
        if not len(indices):
            raise ValueError("Empty count split")
        inputs, labels = out / f"{split}-inputs.npz", out / f"{split}-labels.npz"
        np.savez_compressed(inputs, context=data["context"][indices][:, points], context_seconds=grid,
                            event_ids=data["event_ids"][indices], target_seconds=data["target_seconds"])
        np.savez_compressed(labels, target=data["target"][indices], event_ids=data["event_ids"][indices])
        parts[split] = {"inputs": inputs.name, "inputs_sha256": sha(inputs),
                        "labels": labels.name, "labels_sha256": sha(labels), "events": len(indices)}
    result = {"protocol": manifest["protocol"], "manifest_sha256": sha(manifest_path),
              "source_dataset_sha256": receipt["data_sha256"], "delta_s": receipt["delta_s"],
              "bin_seconds": bin_seconds or receipt["bin_seconds"], "source_grid_indices": points.tolist(), "parts": parts,
              "protected_test": False, "preparation_reads_all_retrospective_labels": True,
              "input_cutoff_rule": INPUT_CUTOFF_RULE_ID}
    (out / "partitions.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", dest="manifest_path", type=Path, required=True)
    p.add_argument("--data-root", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--bin-seconds", type=int, default=1)
    print(json.dumps(build(**vars(p.parse_args()))))
