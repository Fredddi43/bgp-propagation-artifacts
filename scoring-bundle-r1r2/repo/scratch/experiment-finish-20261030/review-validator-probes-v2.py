"""Additional independent synthetic probes; no production data or code is changed."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("audit_mock_review", HERE / "audit/test_validate_final_data.py")
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)
t.VALIDATOR = str(HERE / "review-validator-snapshot-v2.py")

def digest(data):
    return hashlib.sha256(data).hexdigest()

def dump(p, obj):
    data = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    Path(p).write_bytes(data)
    return digest(data)

def rerender(root, doc):
    target = Path(root) / "target"
    docpath = target / "secondary-result.json"
    sha = dump(docpath, doc)
    completion = json.loads((target / "completion.json").read_bytes())
    completion["secondary_result"].update(sha256=sha, bytes=docpath.stat().st_size)
    dump(target / "completion.json", completion)

def prove(lp, name):
    rc, summary, _ = t.run(lp, "--require-complete", "--inventory")
    assert rc == 0, (name, rc, summary)
    print(json.dumps({"probe": name, "exit": rc, "summary": summary["summary"]}))

with tempfile.TemporaryDirectory(prefix="review-v2-fixture-", dir=HERE) as tmp:
    t.TMP = tmp
    root, lp = t.build("invalid-approval")
    prove(lp, "approval_missing_required_freeze_records_and_authorization_fields")

    root, lp = t.build("unbound-ready-stages")
    target = Path(root) / "target"
    doc = json.loads((target / "secondary-result.json").read_bytes())
    for stage in doc["header"]["stages"]:
        stage["fingerprint"] = digest(stage["fingerprint"].encode())
        if "checkpoint" not in stage:
            if stage["stage"] == "origin":
                stage["source"] = "checkpoint-rolling"
                stage["checkpoint"] = {"format": "rolling-read", "artifacts": stage["save"]["artifacts"]}
            else:
                stage["checkpoint"] = {"format": "attempt12-single-pkl",
                                       "artifacts": [{k: stage[k] for k in ("path", "bytes", "sha256")} ]}
    approval = json.loads((Path(root) / "approval.json").read_bytes())
    ready_path = Path(approval["dry_run_ready"]["path"])
    ready = json.loads(ready_path.read_bytes())
    ready["stages"] = copy.deepcopy(doc["header"]["stages"])
    ready["stages"][0]["checkpoint"]["artifacts"][0]["sha256"] = "0" * 64
    ready["checkpoint_binding"] = {"sha256": "0" * 64, "items": ["invalid binding"]}
    approval["dry_run_ready"]["sha256"] = dump(ready_path, ready)
    approval_sha = dump(Path(root) / "approval.json", approval)
    ref = {"path": str(Path(root) / "approval.json"), "sha256": approval_sha}
    intent = json.loads((target / "intent.json").read_bytes())
    intent["approval"] = ref
    dump(target / "intent.json", intent)
    doc["header"]["approval"] = ref
    rerender(root, doc)
    prove(lp, "nested64digit_stage_receipts_differ_from_approved_ready_and_binding_is_invalid")

    root, lp = t.build("marker-tamper")
    dump(Path(root) / "target/second-label-read-D-A39.json", {})
    prove(lp, "D-A39_marker_changed_without_updating_header_marker_receipt")

    root, lp = t.build("primary-inequality")
    target = Path(root) / "target"
    doc = json.loads((target / "secondary-result.json").read_bytes())
    p = target / "primary-recomputed-D-A39.json"
    primary = json.loads(p.read_bytes())
    primary["unexpected_scientific_change"] = 123
    doc["header"]["primary_comparison"]["recomputed"]["sha256"] = dump(p, primary)
    rerender(root, doc)
    prove(lp, "different_recomputed_primary_accepted_with_stale_true_equality_claim")
