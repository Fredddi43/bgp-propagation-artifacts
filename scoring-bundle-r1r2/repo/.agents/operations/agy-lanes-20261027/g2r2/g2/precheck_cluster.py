#!/usr/bin/env python3
"""Read-only pre-freeze check of the production identities the local dry runs cannot exercise (no fixtures exist for them).

Local side: the constants the pinned runners compare against (bgbench.forecast_recipes, reviewed_calibration.RULE,
reviewed_fit.STAGE/OUTPUT) and the refs in the bound G1 arms. Cluster side (ssh <BATCH_HOST>, sha256sum/ls only, no payload,
no ledger content): the same files hash to the same values, and the namespaces the runners require exist and agree.
Exit code 1 and a MISMATCH line for every difference.
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(HERE.parents[1] / "g1"))
B = "<FORECAST_ROOT>"


import os


def remote(cmd):
    # <BATCH_HOST> is the runbook host; BGB_SSH_HOST redirects the read-only checks when it is unreachable
    # (<BATCH_HOST> mounts the same <CLUSTER_STORAGE> NFS — identical paths, verified 2026-10-28).
    return subprocess.run(["ssh", os.environ.get("BGB_SSH_HOST", "<BATCH_HOST>"), cmd], capture_output=True, text=True).stdout


def main():
    from bgbench import forecast_recipes as r
    import incremental_draft as inc
    groups, _ = inc.load_current_state()
    neural = next(a for a in groups["primary"] if a["role"].get("family") == "neural")
    h1 = groups["h1"][0]
    sd = neural["slice_decisions"]
    frozen_plan = next(a for a in groups["primary"] if a["role"].get("training") == "frozen_2025")["provenance"]["plan"]
    checks = [("SLICE_RULE_SHA256 vs primary slice_rules", r.SLICE_RULE_SHA256, sd["slice_rules"]),
              ("SLICE_RULE_SHA256 vs h1 slice_rules", r.SLICE_RULE_SHA256, h1["slice_decisions"]["slice_rules"]),
              ("FROZEN2025 plan", r.FROZEN2025_PLAN_SHA256, frozen_plan),
              ("FROZEN2025 publication", "66c2ce8c04aabd80236e2576b29d19a913f67d82706d8c37250de41638583def",
               sd["publications"]["frozen_2025"]),
              ("core calibration publication (updated)", sd["publications"]["updated"]["sha256"], sd["publications"]["updated"]),
              ("h1 calibration publication", h1["calibration_publication"]["sha256"], h1["calibration_publication"])]
    bad = 0
    sums = {}
    for line in remote("sha256sum " + " ".join(c[2]["path"] for c in checks)).splitlines():
        digest, path = line.split(None, 1)
        sums[path.strip()] = digest
    for name, constant, ref in checks:
        actual = sums.get(ref["path"])
        ok = actual == constant == ref["sha256"]
        bad += not ok
        print(("OK       " if ok else "MISMATCH ") + name, constant[:12], (actual or "missing")[:12])
    recipe_local = subprocess.run(["sha256sum", str(REPO / "docs/paper/forecasting-improvement-20261017/NEWPERIOD-CORE-RECIPE-v1.json")],
                                  capture_output=True, text=True).stdout.split()[0]
    ok = recipe_local == r.NCORE_RECIPE_SHA256
    bad += not ok
    print(("OK       " if ok else "MISMATCH ") + "NCORE_RECIPE_SHA256 vs NEWPERIOD-CORE-RECIPE-v1.json", r.NCORE_RECIPE_SHA256[:12], recipe_local[:12])
    snap = f"{B}/newperiod-development-v1/training-source-{r.NCORE_SNAPSHOT_SHA256}"
    ok = bool(remote(f"test -d {snap} && echo y").strip())
    bad += not ok
    print(("OK       " if ok else "MISMATCH ") + "NCORE_SNAPSHOT training-source dir exists")
    for fam, stage_name, out_suffix in (("h1", "newperiod-h1-transport-v1-20261023", "newperiod-development-v1/campaigns/h1-v1"),
                                        ("timing", "newperiod-timing-transport-v1-20261023", "newperiod-development-v1/campaigns/timing-v1")):
        pkg = json.loads(remote(f"cat {B}/{stage_name}/package.json") or "{}")
        ok = pkg.get("stage") == f"{B}/{stage_name}" and pkg.get("output") == f"{B}/{out_suffix}" and bool(remote(f"test -d {B}/{out_suffix} && echo y").strip() or fam == "timing")
        print(("OK       " if ok else "MISMATCH ") + f"{fam} runner constants STAGE/OUTPUT vs package.json: {pkg.get('output')}")
        bad += not ok
    h1_model = h1["model_path"]
    ok = h1_model.startswith(f"{B}/newperiod-development-v1/campaigns/h1-v1/")
    print(("OK       " if ok else "MISMATCH ") + f"h1 bound arm model_path namespace ({h1_model.split('/campaigns/')[1].split('/')[0]}) vs runner fit.OUTPUT h1-v1")
    bad += not ok
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
