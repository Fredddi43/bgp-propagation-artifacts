"""Align retained event-table AS counts to their already onset-aligned sets.

This migration does not reconstruct membership. Recovery tables require the
separate transition replay. Run only against a copied data root.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import polars as pl


def repair(root: Path, baseline: Path | None = None) -> list[dict]:
    records = []
    for path in sorted((root / "eventset").glob("*/events.parquet")):
        if path.parent.name.endswith("_recovery"):
            continue
        source = baseline / path.relative_to(root) if baseline else path
        old_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        table = pl.read_parquet(source)
        targets = [c[5:] for c in table.columns if c.startswith("asns_") and "set_" + c[5:] in table.columns]
        changed = {t: table.filter(pl.col("asns_" + t).ne_missing(pl.col("set_" + t).list.len())).height for t in targets}
        table = table.with_columns([pl.col("set_" + t).list.len().alias("asns_" + t) for t in targets])
        table.write_parquet(path, compression="zstd")
        summary_path = path.parent / "summary.json"
        if summary_path.exists():
            summary = json.loads(summary_path.read_text())
            ok = table.filter(pl.col("error").is_null())
            if ok.height and ok["asns_final_2h"].drop_nulls().len():
                summary["asns_final_p50_p90"] = [float(ok["asns_final_2h"].quantile(q)) for q in (0.5, 0.9)]
            summary["extent_count_definition"] = "cardinality_of_onset_aligned_set"
            summary_path.write_text(json.dumps(summary, indent=1) + "\n")
        records.append({"table": str(path.relative_to(root)), "rows": table.height,
                        "changed_counts": changed, "before_sha256": old_hash,
                        "after_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    return records


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_root", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--baseline-root", type=Path)
    args = parser.parse_args()
    records = repair(args.data_root, args.baseline_root)
    args.report.write_text(json.dumps(records, indent=2) + "\n")
    print(json.dumps({"tables": len(records), "changed": sum(sum(r["changed_counts"].values()) for r in records)}))
