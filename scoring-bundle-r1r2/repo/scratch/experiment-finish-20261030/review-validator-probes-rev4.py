"""Independent synthetic final-PASS probes; never touches scientific data."""
import hashlib
import importlib.util
import json
from pathlib import Path
import pickle
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("rev4_mock_review", HERE / "audit/test_validate_final_data.py")
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)
t.VALIDATOR = str(HERE / "review-validator-snapshot-rev4.py")
vspec = importlib.util.spec_from_file_location("rev4_validator_review", t.VALIDATOR)
v = importlib.util.module_from_spec(vspec)
vspec.loader.exec_module(v)

def dump(p, obj):
    data = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    Path(p).write_bytes(data)
    return hashlib.sha256(data).hexdigest()

def show(name, lp, want):
    rc, summary, _ = t.run(lp, "--require-complete")
    assert rc == want, (name, summary)
    print(json.dumps({"probe": name, "exit": rc, "summary": summary["summary"]}))

with tempfile.TemporaryDirectory(prefix="review-rev4-fixture-", dir=HERE) as tmp:
    t.TMP = tmp
    root, lp = t.build("baseline")
    show("production-shaped_baseline", lp, 0)
    doc = json.loads((Path(root) / "target/secondary-result.json").read_bytes())
    assert t.prod.binding_of(doc["header"]["stages"]) == v.binding_of(doc["header"]["stages"])
    print(json.dumps({"probe": "production_and_validator_binding_algorithms", "result": "identical"}))

    root, lp = t.build("raw-primary-missing")
    target = Path(root) / "target"
    comp = json.loads((target / "completion.json").read_bytes())
    raw = pickle.loads((target / "secondary-result-raw.pkl.part0000").read_bytes())
    raw["primary"] = {}
    comp["raw_result"] = t.persist(str(target), "secondary-result-raw", pickle.dumps(raw, protocol=5))
    dump(target / "completion.json", comp)
    show("aggregate_primary_empty_but_recomputed_primary_and_sidecars_intact", lp, 0)

    root, lp = t.build("json-science-changed")
    target = Path(root) / "target"
    docpath = target / "secondary-result.json"
    doc = json.loads(docpath.read_bytes())
    identity = next(iter(doc["secondary"]["counts"]["cells"]))
    doc["secondary"]["counts"]["cells"][identity]["status"] = "changed_only_in_JSON"
    doc["secondary"]["kind"] = "wrong_scientific_kind_only_in_JSON"
    comp = json.loads((target / "completion.json").read_bytes())
    comp["secondary_result"].update(sha256=dump(docpath, doc), bytes=docpath.stat().st_size)
    dump(target / "completion.json", comp)
    show("JSON_cell_status_and_envelope_kind_diverge_from_raw_and_sidecars", lp, 0)
