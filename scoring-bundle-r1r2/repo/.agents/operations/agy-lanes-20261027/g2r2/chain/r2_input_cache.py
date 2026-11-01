"""D-A27 (R2 side): answer forecast_custodian_eval.default_input_loader(raw) from the parallel projection table.

The table (input_projection_cache.py) maps sha256(raw) -> the exact dict default_input_loader returned for those bytes. A hit returns
a fresh copy of that dict; any miss (or a missing table) calls the real function. The evaluator still reads and hash-verifies every
input through the runner's Reader before this loader sees the bytes, so only the torch.load work is skipped.
"""
import hashlib
import json
from pathlib import Path


def load_table(cache_dir):
    table = {}
    for shard in sorted(Path(cache_dir).glob("shard-*.json")):
        doc = json.loads(shard.read_bytes())
        if doc["entries"] != len(doc["table"]):
            raise ValueError(f"{shard} is truncated")
        table.update(doc["table"])
    return table


def install(evaluator, cache_dir):
    table = load_table(cache_dir)
    real = evaluator.default_input_loader

    def loader(raw):
        hit = table.get(hashlib.sha256(raw).hexdigest())
        if hit is None:
            return real(raw)
        return {"event_id": hit["event_id"], "asn": list(hit["asn"]), "seed_asns": list(hit["seed_asns"])}

    evaluator.default_input_loader = loader
    return len(table)
