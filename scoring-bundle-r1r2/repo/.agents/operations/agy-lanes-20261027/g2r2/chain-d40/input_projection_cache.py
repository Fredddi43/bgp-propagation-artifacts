#!/usr/bin/env python3
"""D-A27: parallel precompute of the evaluator's per-input projection (forecast_custodian_eval.default_input_loader).

The pinned R2 evaluation reads every test input of every manifest once and runs default_input_loader (a torch.load of a ~10 MB
label-free graph file, ~0.08 s) in one process: >10 h for ~270k files. This script runs that SAME function on the SAME bytes in
parallel array tasks and stores {sha256(raw): {event_id, asn, seed_asns}}. r2_input_cache.install (R2 only) answers
default_input_loader(raw) from this table keyed on sha256(raw) and falls back to the real function on any miss, so a wrong or
missing entry can only cost time, never change a value. Label-free inputs only; no label, prediction or score is read.

  build --shard K --shards N : shard K of N over the sorted unique (path, sha256) test inputs of the freeze's manifests
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

SRC = sys.argv[sys.argv.index("--src") + 1] if "--src" in sys.argv else None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--freeze", type=Path, required=True)
    p.add_argument("--src", required=True, help="staged source root's src dir (the R2 runner's own bgbench)")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--shard", type=int, required=True)
    p.add_argument("--shards", type=int, required=True)
    a = p.parse_args()
    sys.path.insert(0, a.src)
    from bgbench import forecast_custodian_eval as ev
    arms = json.loads(a.freeze.read_bytes())["arms"]
    rows = {}
    for path in sorted({x["manifest_path"] for x in arms}):
        for row in json.loads(Path(path).read_bytes())["events"]:
            if (row.get("split") == "test" and row.get("input_path") and row.get("input_sha256")
                    and row.get("input_status", "available") == "available"):   # the evaluator skips the others (placeholder inputs)
                rows[row["input_path"]] = row["input_sha256"]
    mine = [(k, rows[k]) for i, k in enumerate(sorted(rows)) if i % a.shards == a.shard]
    table = {}
    for path, digest in mine:
        raw = Path(path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise SystemExit(f"input differs from its manifest hash: {path}")
        table[digest] = ev.default_input_loader(raw)
    a.out.mkdir(parents=True, exist_ok=True)
    tmp = a.out / f"shard-{a.shard:03d}.json.tmp"
    tmp.write_text(json.dumps({"shard": a.shard, "shards": a.shards, "entries": len(table), "table": table}, sort_keys=True))
    tmp.rename(a.out / f"shard-{a.shard:03d}.json")
    print(json.dumps({"shard": a.shard, "files": len(mine), "entries": len(table)}))


if __name__ == "__main__":
    main()
