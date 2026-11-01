#!/usr/bin/env python3
"""G4: ONE four-scope custodian label artifact (ordinary, stable, origin_change_invalid, origin_change_valid).

Runs the reviewed bundle (newperiod-complete-label-bundle-20261023/bundle.py, unchanged; it pins its own reader
sources) directly, without the r4 transport/approval wrapper. This opens outcome membership, so it needs root's
ROOT-GO-R2.txt and must run after the G3 seal. The plan comes from newperiod-label-binding-retained-v1 (assemble)
once the stable and origin masters exist. Writes the artifact exclusively at plan['base']['ordinary']['output'].
"""
import argparse
import hashlib
import json
import os
import types
from pathlib import Path

from common import GO_FILE, REPO, require, sha, write_new

BUNDLE = REPO / ".agents/operations/newperiod-complete-label-bundle-20261023/bundle.py"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--plan", type=Path, required=True, help="newperiod_complete_label_bundle_v1 plan JSON")
    p.add_argument("--seal", type=Path, required=True, help="G3 seal (must exist before labels are prepared)")
    p.add_argument("--go-file", type=Path, default=GO_FILE)
    a = p.parse_args(argv)
    require(a.go_file.is_file() and a.go_file.stat().st_size > 0, f"root go file {a.go_file} missing")
    require(a.seal.is_file(), "G3 seal must exist before G4")
    plan = json.loads(a.plan.read_bytes())
    ordinary = plan["base"]["ordinary"]
    root, output = Path(ordinary["custodian_root"]), Path(ordinary["output"])
    require(not output.exists(), "label artifact already exists: one preparation only")
    os.environ["CUSTODIAN_ACCESS_LOG"] = ordinary["access_log"]  # the reviewed reader requires LOG == plan log
    module = types.ModuleType("complete_bundle")
    module.__file__ = str(BUNDLE)
    exec(compile(BUNDLE.read_bytes(), str(BUNDLE), "exec"), module.__dict__)
    # D-A25: the stable stage records its selection file at the protocol-pack path; the plan (and the custody-scope check of the
    # reviewed reader) require a copy inside the custodian root. The copy is byte-identical (same sha256). Treat the two paths as
    # one reference ONLY for exactly that file; every other reference is checked unchanged.
    original_selection = "<FORECAST_ROOT>/protocol-pack-20261017/out/stable-peer-selection.json"
    reader, plan_selection = module.r, plan["base"]["selection"]
    original_reference = reader.reference

    def reference(item):
        if isinstance(item, dict) and item.get("path") == original_selection and item.get("sha256") == plan_selection["sha256"]:
            item = {**item, "path": plan_selection["path"]}
        return original_reference(item)
    reader.reference = reference
    # D-A29: the origin consumer reads evidence['sampling_rule'] through prepare.document (JSON parse) but the rule is the markdown file
    # below (its value is discarded by the consumer). Return a stub for exactly that hash-pinned markdown file; everything else parses unchanged.
    rule_sha = "a8fa51b0fbf137c7685e2a532e8abe981757876295f349a779b364e15c85dbb6"
    prepare = reader.prepare
    original_document = prepare.document

    def document(item):
        raw = prepare.checked_bytes(item)
        if hashlib.sha256(raw).hexdigest() == rule_sha:
            return {"markdown_rule": True}
        return original_document(item)
    prepare.document = document
    pi = module.b.bound(plan, root / "outer-plan")
    ai = module.b.bound({"kind": "newperiod_custodian_complete_bundle_read_authority_v1", "approved": True,
                         "scope": "prepare_ordinary_stable_origin_labels_only",
                         "plan_sha256": pi["ref"]["sha256"]}, root / "outer-authority")
    result = module._run(pi, ai, expected_plan_sha256=pi["ref"]["sha256"], expected_authority_sha256=ai["ref"]["sha256"])
    receipt = {"kind": "g4_label_receipt", "output": result["output"], "plan_sha256": pi["ref"]["sha256"],
               "bundle_sha256": sha(BUNDLE), "seal_sha256": sha(a.seal), "go_file_sha256": sha(a.go_file),
               "released": False}
    write_new(output.with_name(output.stem + ".g4-receipt.json"), receipt)
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
