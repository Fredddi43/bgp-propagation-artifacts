"""Independent regression and JSON-cap boundary probes on tiny synthetic artifacts."""
import hashlib
import importlib.util
import json
from pathlib import Path
import pickle
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("rev5_mock_review", HERE / "audit/test_validate_final_data.py")
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)
t.VALIDATOR = str(HERE / "review-validator-snapshot-rev5.py")
vspec = importlib.util.spec_from_file_location("rev5_validator_review", t.VALIDATOR)
v = importlib.util.module_from_spec(vspec)
vspec.loader.exec_module(v)

def dump(p, obj):
    data = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    Path(p).write_bytes(data)
    return hashlib.sha256(data).hexdigest()

def show(name, lp, want, *args):
    rc, summary, entries = t.run(lp, "--require-complete", *args)
    assert rc == want, (name, summary)
    print(json.dumps({"probe": name, "exit": rc, "summary": summary["summary"]}))
    return entries

with tempfile.TemporaryDirectory(prefix="review-rev5-fixture-", dir=HERE) as tmp:
    t.TMP = tmp
    root, lp = t.build("baseline")
    show("production-shaped_baseline", lp, 0)
    docpath = Path(root) / "target/secondary-result.json"
    doc = json.loads(docpath.read_bytes())
    assert t.prod.binding_of(doc["header"]["stages"]) == v.binding_of(doc["header"]["stages"])
    print(json.dumps({"probe": "production_validator_binding_equality", "result": "identical"}))
    show("cap_exact_actual_document_bytes", lp, 0, "--json-deep-cap", str(docpath.stat().st_size))
    show("cap_one_byte_below_document", lp, 1, "--json-deep-cap", str(docpath.stat().st_size - 1))

    root, lp = t.build("raw-primary-missing")
    target = Path(root) / "target"
    comp = json.loads((target / "completion.json").read_bytes())
    raw = pickle.loads((target / "secondary-result-raw.pkl.part0000").read_bytes())
    raw["primary"] = {}
    comp["raw_result"] = t.persist(str(target), "secondary-result-raw", pickle.dumps(raw, protocol=5))
    dump(target / "completion.json", comp)
    entries = show("empty_aggregate_primary_rejected", lp, 1)
    assert next(e for e in entries if e.get("check") == "tierC:aggregate-envelope")["primary_matches_recomputed"] is False

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
    show("JSON_only_scientific_changes_rejected", lp, 1)

    root, lp = t.build("missing-run", drop_target=True)
    show("actual_run_missing_cannot_final_PASS", lp, 1)

    # A legal tuple/set/non-finite/mixed-key projection remains accepted after a full value check.
    root, lp = t.build("projection-types")
    target = Path(root) / "target"
    raw = pickle.loads((target / "secondary-result-raw.pkl.part0000").read_bytes())
    raw["counts"]["projection_example"] = {"sequence": (1, 2), "set": {3, 1}, "nan": float("nan"),
                                             "mixed_keys": {1: "one", "a": "A"}}
    docpath = target / "secondary-result.json"
    doc = json.loads(docpath.read_bytes())
    section = raw["counts"]
    receipt = t.persist(str(target / "families"), "counts", pickle.dumps(section, protocol=5))
    next(e for e in doc["header"]["families"] if e["family"] == "counts")["persisted"] = receipt
    projected = t.prod._stringify_keys({k: value for k, value in raw.items() if k != "primary"})
    # This fixture contains only stdlib non-JSON types, whose producer rule is sorted(set).
    doc["secondary"] = json.loads(json.dumps(projected, sort_keys=True, allow_nan=True,
                                               default=lambda value: sorted(value)))
    comp = json.loads((target / "completion.json").read_bytes())
    comp["raw_result"] = t.persist(str(target), "secondary-result-raw", pickle.dumps(raw, protocol=5))
    comp["secondary_result"].update(sha256=dump(docpath, doc), bytes=docpath.stat().st_size)
    dump(target / "completion.json", comp)
    show("legal_tuple_set_nan_mixed_key_projection", lp, 0)
