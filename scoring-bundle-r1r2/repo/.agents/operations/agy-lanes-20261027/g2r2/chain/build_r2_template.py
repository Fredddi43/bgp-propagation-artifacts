#!/usr/bin/env python3
"""Build the R2 execution template, its read inventory and the r2_exec spec from artifacts that already exist.

Run on the cluster AFTER the G4 label artifact exists. Reads no label content (build_inventory only stats/hashes the label ref
file; it never parses it: `ref != plan['labels']` is skipped by the follower). Refs are {path, sha256} of existing files.

usage: build_r2_template.py --evidence-dir E --labels LABELS.json --seal SEAL --arm-spec AS --review REVIEW --go-file GO
         --source-root S --closure C --runner RUNNER --out-dir OUT [--access-log LOG]
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import r2_plan  # noqa: E402

F = "<FORECAST_ROOT>"
PUB = F + "/data-custodian/g1-freeze-20261028T184148Z"
AMENDED = F + "/newperiod-g2-inference-v1-20261027/amend/amended-freeze.json"
EXT = F + "/occurrence-final-v1/sizing-binding-v6b/extension-decision.json"
SLICE = F + "/occurrence-final-v1/slice-rules/issue-time-slice-rule-v6b.json"
T = F + "/data-custodian/newperiod-inputs-v1/primary-issue-time-v1"
BINDING = F + "/newperiod-g2-inference-v1-20261027/docs/pre_R2_implementation_binding.json"
LOG = F + "/data-custodian/newperiod-identification-v1/access-log.jsonl"


def ref(p):
    p = Path(p)
    return {"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}


def main(argv=None):
    a = argparse.ArgumentParser()
    for n in ("evidence-dir", "labels", "seal", "arm-spec", "review", "go-file", "source-root", "closure", "runner", "out-dir"):
        a.add_argument("--" + n, required=True)
    a.add_argument("--access-log", default=LOG)
    a.add_argument("--work", help="fresh r2_exec work dir (default <out-dir>/work)")
    x = a.parse_args(argv)
    E = Path(x.evidence_dir)
    group = lambda g: ref(f"{PUB}/{g}.json")  # noqa: E731
    fams = ("h1", "h3", "timing", "history", "ordinary")
    controls = {
        "freeze": ref(AMENDED), "seal": ref(x.seal), "arm_spec": ref(x.arm_spec), "labels": ref(x.labels),
        "count_freeze": group("count"), "membership_freezes": {g: group(g) for g in fams},
        "evidence": {g: ref(E / f"evidence-{g}.json") for g in fams},
        "stable_freeze": group("stable"), "stable_evidence": ref(E / "evidence-stable.json"),
        "origin_freeze": group("origin"), "origin_evidence": ref(E / "evidence-origin.json"),
        "baseline_freeze": group("baseline"), "baseline_evidence": ref(E / "evidence-baseline.json"),
        "extension_decision": ref(EXT), "slice_rules": ref(SLICE),
        "issue_time_tables": {"30": ref(f"{T}/issue_projections-d30/attempt/output/issue-time-table.json"),
                              "60": ref(f"{T}/issue_projections-d60/attempt/output/issue-time-table.json")},
        "full_retention_review": ref(x.review), "pre_R2_implementation_binding": ref(BINDING),
        "source_closure": ref(x.closure),
    }
    # D-A30: the sealed predictions digests stand in for re-hashing ~400 GB, and predictions files are never opened or parsed here
    freeze_arms = {a["arm_id"]: a for a in json.loads(Path(AMENDED).read_bytes())["arms"]}
    for row in json.loads(Path(x.seal).read_bytes())["arms"]:
        path = freeze_arms[row["arm_id"]]["predictions_path"]
        r2_plan.KNOWN_SHA[path] = row["predictions_sha256"]
        r2_plan.OPAQUE.add(path)
    # D-A30b: the inventory walk does two serial NFS stat() calls per input file (~320k files). Pre-stat them with a thread pool and
    # answer Path.is_file()/Path.stat().st_size for exactly those paths from the table (same os.stat results); other paths are untouched.
    import os
    from concurrent.futures import ThreadPoolExecutor
    paths = set()
    for mp in sorted({a["manifest_path"] for a in freeze_arms.values()}):
        for row in json.loads(Path(mp).read_bytes())["events"]:
            if row.get("input_path"):
                paths.add(row["input_path"])

    def one(path):
        try:
            st = os.stat(path)
            return path, (st.st_mode, st.st_size)
        except OSError:
            return path, None
    with ThreadPoolExecutor(max_workers=128) as pool:
        table = dict(pool.map(one, sorted(paths)))
    import stat as statmod
    real_is_file, real_stat = Path.is_file, Path.stat

    class Sized:
        def __init__(self, size):
            self.st_size = size

    def is_file(self, *a, **k):
        hit = table.get(str(self), False)
        return real_is_file(self, *a, **k) if hit is False else (hit is not None and statmod.S_ISREG(hit[0]))

    def stat(self, *a, **k):
        hit = table.get(str(self), False)
        return real_stat(self, *a, **k) if (hit is False or hit is None or a or k) else Sized(hit[1])
    Path.is_file, Path.stat = is_file, stat
    src = Path(x.source_root)
    extra = [src / "src/bgbench/forecast_custodian_eval.py", src / "src/bgbench/forecast_retrospective_scoring.py"]
    template, inventory = r2_plan.build_template(controls, source_root=src, access_log=x.access_log, extra_paths=extra)
    out = Path(x.out_dir)
    out.mkdir(parents=True, exist_ok=False)
    tp, ip = out / "r2-template.json", out / "r2-inventory.json"
    tp.write_text(json.dumps(template, sort_keys=True, indent=1) + "\n")
    ip.write_text(json.dumps(inventory, sort_keys=True, indent=1) + "\n")
    spec = {"go_file": x.go_file, "work": x.work or str(out / "work"), "template": ref(tp),
            "inventory": inventory, "runner": ref(x.runner),
            # D-A26 / D-A27 / D-A28 in-process accelerations (r2_exec.py); cutoff = 2026-10-29T01:36:00Z, before the seal verification began
            "fast_authorize_cutoff_epoch": 1793237760,
            "input_projection_cache": F + "/newperiod-g2-inference-v1-20261027/r2-proj-cache",
            "fast_json_predictions": True}
    sp = out / "r2-exec-spec.json"
    sp.write_text(json.dumps(spec, sort_keys=True, indent=1) + "\n")
    print(json.dumps({"template": ref(tp), "inventory_files": len(inventory), "inventory_bytes": sum(i["size_bytes"] for i in inventory),
                      "bounds": template["bounds"], "spec": ref(sp)}, indent=1))


if __name__ == "__main__":
    main()
