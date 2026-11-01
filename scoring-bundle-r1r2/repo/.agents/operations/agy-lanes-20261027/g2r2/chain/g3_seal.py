#!/usr/bin/env python3
"""G3: the one-batch custody seal over the frozen retention list (forecast_custody.seal). Opens no label.

Preflight lists every frozen arm whose predictions or commitment file is missing and refuses before sealing.
The seal itself re-verifies each arm (model/manifest/gate/input hashes, commitment, prediction schema, population).
"""
import argparse
import json
from pathlib import Path

from common import require, sha, write_new


def main(argv=None):
    from bgbench import forecast_custody
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--freeze", type=Path, required=True, help="global freeze.json (executable arms only)")
    p.add_argument("--expected-freeze-sha256", required=True, help="externally anchored hash of freeze.json")
    p.add_argument("--expected-arms", type=int, required=True, help="number of committed_for_prediction roles (400 - not_executable)")
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args(argv)
    require(sha(a.freeze) == a.expected_freeze_sha256, "freeze.json differs from its anchor")
    spec = json.loads(a.freeze.read_bytes())
    arms = spec["arms"]
    require(len(arms) == a.expected_arms, f"freeze has {len(arms)} arms, expected {a.expected_arms}")
    missing = [x["arm_id"] for x in arms
               if not (Path(x["predictions_path"]).is_file() and Path(x["commitment_path"]).is_file())]
    require(not missing, f"{len(missing)} arms lack predictions/commitment (first: {missing[:5]}); G2 is incomplete")
    require(not a.out.exists(), "seal output already exists")
    forecast_custody.seal(a.freeze, a.out, expected_spec_sha256=a.expected_freeze_sha256)
    receipt = {"kind": "g3_seal_receipt", "seal": str(a.out.resolve()), "seal_sha256": sha(a.out),
               "freeze": str(a.freeze.resolve()), "freeze_sha256": a.expected_freeze_sha256, "arms": len(arms),
               "retained_failures": len(spec.get("retained_failures", [])), "labels_opened": False}
    write_new(a.out.with_name(a.out.stem + ".receipt.json"), receipt)
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
