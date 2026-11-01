#!/usr/bin/env python3
"""G3 one-batch seal, SHARDED across nodes with per-group input-hash memoization (D-A24).

Same contract as g3_seal.py / g3_seal_parallel.py: every arm is verified by forecast_custody.verify_arm UNCHANGED, and the seal
document has exactly the keys, key order and values forecast_custody.seal() writes (only sealed_at differs per run).

Why: arms with the same manifest_sha256 re-hash the SAME test input files (e.g. the 10 origin valid arms of one horizon each
re-hash ~1.3 TB). Hashing is NFS-bound (~0.5 GB/s per reader), so the one-process seal needs many hours. Here
  * `verify`  : task K of N takes the manifest groups j with j % N == K, verifies each arm with verify_arm, and writes one result
                file per arm. Inside a task forecast_custody.sha is wrapped with a memo keyed on (path, st_size, st_mtime_ns,
                st_ino); a path is hashed once per task and re-used for later arms of the group. The memoised digest equals what a
                re-read would return as long as the file is unchanged, which the key checks (stat before and after the first read).
  * `assemble`: requires a result file for every arm of the freeze, builds the seal receipt in freeze order, and writes it with
                forecast_custody.write_once (open 'x', one-shot), plus the same .receipt.json as g3_seal_parallel.py.
No labels are opened. No arm is skipped: assemble refuses on any missing result, and any verify exception writes no result.
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from common import require, sha, write_new


def _load(a, forecast_custody):
    require(sha(a.freeze) == a.expected_freeze_sha256, "freeze.json differs from its anchor")
    spec_obj, spec_digest = forecast_custody.hashed_json(a.freeze)
    require(spec_digest == a.expected_freeze_sha256, "REFUSED: Retention spec changed from its independently anchored freeze digest")
    arms = spec_obj["arms"]
    require(len(arms) == a.expected_arms, f"freeze has {len(arms)} arms, expected {a.expected_arms}")
    return spec_obj, spec_digest, arms


def _groups(arms):
    g = {}
    for i, arm in enumerate(arms):
        g.setdefault(arm["manifest_sha256"], []).append(i)
    return [g[k] for k in sorted(g)]


def _memo_sha(forecast_custody):
    orig = forecast_custody.sha
    cache = {}

    def memo(path):
        p = Path(path)
        st0 = p.stat()
        key = (str(p), st0.st_size, st0.st_mtime_ns, st0.st_ino)
        if key in cache:
            return cache[key]
        digest = orig(path)
        st1 = p.stat()
        require((st1.st_size, st1.st_mtime_ns, st1.st_ino) == key[1:], f"{path} changed while hashing")
        cache[key] = digest
        return digest
    forecast_custody.sha = memo
    return cache


def _warm(forecast_custody, arm, cache, threads):
    """Pre-hash the group's test inputs with a thread pool (NFS reads are latency-bound per stream) so verify_arm's own sha() calls
    hit the memo. Only fills the memo through the same stat-checked function verify_arm uses; digests are compared by verify_arm."""
    from concurrent.futures import ThreadPoolExecutor
    manifest, _ = forecast_custody.hashed_json(arm['manifest_path'])
    paths = [row['input_path'] for row in manifest['events'] if row['split'] == 'test']
    with ThreadPoolExecutor(max_workers=threads) as ex:
        list(ex.map(forecast_custody.sha, paths))


def cmd_verify(a, forecast_custody):
    require(0 <= a.shard < a.shards, "shard out of range")
    spec_obj, _, arms = _load(a, forecast_custody)
    for name in ('scientific_protocol', 'exposure_ledger'):
        require(forecast_custody.sha(spec_obj[name + '_path']) == spec_obj[name + '_sha256'],
                "REFUSED: Frozen protocol/exposure ledger changed; explicit revision required")
    groups = [g for j, g in enumerate(_groups(arms)) if j % a.shards == a.shard]
    cache = _memo_sha(forecast_custody)
    a.results.mkdir(parents=True, exist_ok=True)
    done = 0
    for g in groups:
        _warm(forecast_custody, arms[g[0]], cache, a.threads)
        for i in (reversed(g) if a.reverse else g):
            out = a.results / f"{i:04d}.json"
            if out.is_file():
                continue
            res = forecast_custody.verify_arm(arms[i])
            tmp = out.with_suffix(".tmp")
            tmp.write_text(json.dumps({"index": i, "result": res}, sort_keys=True))
            os.replace(tmp, out)
            done += 1
            print(json.dumps({"shard": a.shard, "arm": arms[i]["arm_id"], "done": done, "hashed_files": len(cache)}), flush=True)
    print(json.dumps({"shard": a.shard, "complete": True, "arms": done, "groups": len(groups)}), flush=True)


def cmd_assemble(a, forecast_custody):
    spec_obj, spec_digest, arms = _load(a, forecast_custody)
    results = []
    for i in range(len(arms)):
        f = a.results / f"{i:04d}.json"
        require(f.is_file(), f"missing verification result for arm {i} {arms[i]['arm_id']}")
        d = json.loads(f.read_bytes())
        require(d["index"] == i and d["result"]["arm_id"] == arms[i]["arm_id"], f"result {i} does not match its arm")
        r = d["result"]
        results.append({k: r[k] for k in ('arm_id', 'commitment_sha256', 'predictions_sha256', 'events')})   # verify_arm key order
    require(not a.out.exists(), "seal output already exists")
    receipt = {'spec_path': str(a.freeze.resolve()), 'spec_sha256': spec_digest,
               'sealed_at': datetime.now(timezone.utc).isoformat(), 'arms': results,
               'all_retained_predictions_verified': True, 'outcome_files_opened': False}
    forecast_custody.write_once(a.out, receipt)
    out_receipt = {"kind": "g3_seal_receipt", "seal": str(a.out.resolve()), "seal_sha256": sha(a.out),
                   "freeze": str(a.freeze.resolve()), "freeze_sha256": a.expected_freeze_sha256, "arms": len(arms),
                   "retained_failures": len(spec_obj.get("retained_failures", [])), "labels_opened": False,
                   "verification": {"mode": "sharded-memo", "groups": len(_groups(arms)), "pid": os.getpid()}}
    write_new(a.out.with_name(a.out.stem + ".receipt.json"), out_receipt)
    print(json.dumps(out_receipt))


def main(argv=None):
    from bgbench import forecast_custody
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("verify", "assemble"))
    p.add_argument("--freeze", type=Path, required=True)
    p.add_argument("--expected-freeze-sha256", required=True)
    p.add_argument("--expected-arms", type=int, required=True)
    p.add_argument("--results", type=Path, required=True, help="directory of per-arm verification results")
    p.add_argument("--shard", type=int, default=0)
    p.add_argument("--shards", type=int, default=1)
    p.add_argument("--threads", type=int, default=64)
    p.add_argument("--reverse", action="store_true", help="verify a group's arms in reverse order (twin task; finished arms are skipped)")
    p.add_argument("--out", type=Path, help="seal.json (assemble only)")
    a = p.parse_args(argv)
    if a.mode == "verify":
        cmd_verify(a, forecast_custody)
    else:
        require(a.out is not None, "--out required for assemble")
        cmd_assemble(a, forecast_custody)


if __name__ == "__main__":
    main()
