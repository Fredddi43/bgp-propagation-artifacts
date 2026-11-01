#!/usr/bin/env python3
"""Which inputs of each R1 scoring task still exist on disk? Metadata and stat() only; no label bytes are read."""
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

ARRAY = Path("<FORECAST_ROOT>/r1-release-parallel-v11-20261024/control-v1/scoring-array")
OUT = Path("<FORECAST_ROOT>/r1-rank-sidecar-20261101/work/inventory.json")


def main():
    topology = json.loads((ARRAY / "topology.json").read_bytes())
    tasks = json.loads((ARRAY / "tasks-ready.json").read_bytes())
    manifests = {}
    rows = []
    for key, cell in sorted(topology["cells"].items()):
        ref = tasks["tasks"][key]
        # metadata only: the envelope's 'metadata' block (labels, data_paths); prediction is a path+digest.
        envelope = json.loads(Path(ref["path"]).read_bytes())
        metadata = envelope["metadata"]
        data_paths = metadata["data_paths"]
        missing_data = [p for p in data_paths if not os.path.exists(p)]
        missing_labels = [p for p in metadata["labels"] if not os.path.exists(p)]
        side = metadata["context"]["side"]
        kind = "stable" if "stable_context" in side else "h3" if "h3_context" in side else (
            "curve" if cell["payload"] in ("curve_npz", "count_npz") else "membership")
        # where do the missing graph files point?
        targets = Counter()
        for p in missing_data[:5000]:
            if os.path.islink(p):
                link = os.readlink(p)
                targets[str(Path(link).parent.parent.parent)] += 1
            else:
                targets[str(Path(p).parent)] += 1
        manifest = cell.get("reference_manifest", {}).get("path") if kind == "h3" else cell.get("manifest_path")
        rows.append({"cell_id": key, "kind": kind, "format": cell["format"],
                     "prediction_exists": os.path.exists(cell["predictions_path"]),
                     "prediction_bytes": envelope["prediction"]["bytes"],
                     "manifest": manifest, "data_paths": len(data_paths), "missing_data": len(missing_data),
                     "missing_data_link_roots": dict(targets), "labels": list(metadata["labels"]),
                     "missing_labels": missing_labels})
        del envelope
        print(json.dumps({k: rows[-1][k] for k in ("cell_id", "kind", "prediction_exists", "data_paths",
                                                     "missing_data")}), flush=True)
    summary = defaultdict(Counter)
    for r in rows:
        s = summary[r["kind"]]
        s["cells"] += 1
        s["prediction_missing"] += not r["prediction_exists"]
        s["data_incomplete"] += r["missing_data"] > 0
        s["labels_missing"] += bool(r["missing_labels"])
        s["replayable"] += r["prediction_exists"] and r["missing_data"] == 0 and not r["missing_labels"]
    OUT.write_text(json.dumps({"summary": summary, "cells": rows}, indent=1, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=1, sort_keys=True))


if __name__ == "__main__":
    sys.exit(main())
