#!/usr/bin/env python3
"""G3 one-batch seal with PARALLEL per-arm verification (q54 proposal; serial path stays g3_seal.py).

Byte-identical output contract: the seal document written here has EXACTLY the keys, key order and values
that forecast_custody.seal() writes (spec_path, spec_sha256, sealed_at, arms, all_retained_predictions_verified,
outcome_files_opened) - the only run-dependent value is the sealed_at timestamp, identical in that respect to a
serial run. Every arm is verified by forecast_custody.verify_arm UNCHANGED, in its own process, results returned
in spec['arms'] order (futures map). verify_arm is pure (reads only the arm's frozen artifacts; opens no label).

Why: the freeze's 346 arms re-hash ~33.9 TB through verify_arm (each arm re-hashes every test input of its
manifest; origin valid arms carry ~1.33 TB of inputs each). Single-core sha256 on <BATCH_HOST> measures
1.44 GB/s -> serial ~6.5-12 h; 48-64 workers on the same box measure 16.8 GB/s aggregate hot-cache -> ~1 h.

ONE-SHOT property preserved: seal document is written with forecast_custody.write_once (open 'x'); any arm
verification error aborts before ANY write, exactly like the serial seal.
"""
import argparse
import json
import os
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from common import require, sha, write_new


def _preflight(a, forecast_custody):
    require(sha(a.freeze) == a.expected_freeze_sha256, "freeze.json differs from its anchor")
    spec = json.loads(a.freeze.read_bytes())
    arms = spec["arms"]
    require(len(arms) == a.expected_arms, f"freeze has {len(arms)} arms, expected {a.expected_arms}")
    missing = [x["arm_id"] for x in arms
               if not (Path(x["predictions_path"]).is_file() and Path(x["commitment_path"]).is_file())]
    require(not missing, f"{len(missing)} arms lack predictions/commitment (first: {missing[:5]}); G2 is incomplete")
    require(not a.out.exists(), "seal output already exists")
    return spec


def main(argv=None):
    from bgbench import forecast_custody
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--freeze", type=Path, required=True, help="global freeze.json (executable arms only)")
    p.add_argument("--expected-freeze-sha256", required=True, help="externally anchored hash of freeze.json")
    p.add_argument("--expected-arms", type=int, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--workers", type=int, default=40, help="processes for standard arms (predictions below the big threshold)")
    p.add_argument("--big-workers", type=int, default=6, help="concurrent big-prediction arms (each peaks ~60-80 GB RSS while its predictions JSON parses)")
    p.add_argument("--big-threshold-gb", type=float, default=4.0, help="predictions file size (GB) above which an arm runs on the big pool")
    a = p.parse_args(argv)
    spec = _preflight(a, forecast_custody)
    # seal() prologue (anchor digest + protocol/ledger hashes), identical to forecast_custody.seal()
    spec_obj, spec_digest = forecast_custody.hashed_json(a.freeze)
    if spec_digest != a.expected_freeze_sha256:
        raise SystemExit("REFUSED: Retention spec changed from its independently anchored freeze digest")
    for name in ('scientific_protocol', 'exposure_ledger'):
        if forecast_custody.sha(spec_obj[name + '_path']) != spec_obj[name + '_sha256']:
            raise SystemExit("REFUSED: Frozen protocol/exposure ledger changed; explicit revision required")
    arms = spec_obj["arms"]
    big = [i for i, x in enumerate(arms)
           if Path(x["predictions_path"]).stat().st_size > a.big_threshold_gb * (1 << 30)]
    small = [i for i in range(len(arms)) if i not in set(big)]
    print(json.dumps({"parallel_seal": "start", "arms": len(arms), "big_arms": len(big),
                      "big_workers": a.big_workers, "workers": a.workers}), flush=True)
    results = [None] * len(arms)

    def run_pool(idxs, workers):
        if not idxs:
            return
        with ProcessPoolExecutor(max_workers=workers) as ex:   # fork: children inherit the verified imports
            for i, res in zip(idxs, ex.map(forecast_custody.verify_arm, (arms[i] for i in idxs), chunksize=1)):
                results[i] = res                               # first exception propagates here: no write happens

    run_pool(big, a.big_workers)
    run_pool(small, a.workers)
    require(all(r is not None for r in results), "internal: missing verification result (fail-closed)")
    receipt = {'spec_path': str(a.freeze.resolve()), 'spec_sha256': spec_digest,
               'sealed_at': datetime.now(timezone.utc).isoformat(), 'arms': results,
               'all_retained_predictions_verified': True, 'outcome_files_opened': False}
    forecast_custody.write_once(a.out, receipt)
    out_receipt = {"kind": "g3_seal_receipt", "seal": str(a.out.resolve()), "seal_sha256": sha(a.out),
                   "freeze": str(a.freeze.resolve()), "freeze_sha256": a.expected_freeze_sha256, "arms": len(arms),
                   "retained_failures": len(spec.get("retained_failures", [])), "labels_opened": False,
                   "verification": {"mode": "parallel", "big_arms": len(big), "big_workers": a.big_workers,
                                    "workers": a.workers, "pid": os.getpid()}}
    write_new(a.out.with_name(a.out.stem + ".receipt.json"), out_receipt)
    print(json.dumps(out_receipt))


if __name__ == "__main__":
    main()
