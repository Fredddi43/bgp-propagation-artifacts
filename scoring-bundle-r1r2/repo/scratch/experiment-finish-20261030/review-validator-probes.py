"""Read-only validator probes using synthetic local files, never scientific data."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import pickle
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("validator_review", HERE / "review-validator-snapshot.py")
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
proofs = []

with tempfile.TemporaryDirectory(prefix="review-fixture-", dir=HERE) as tmp:
    root = Path(tmp)
    v.ROOT = str(root)
    v.TARGET = str(root / "missing-run")
    v.tier_a = lambda *args, **kwargs: (v.say("synthetic:controls", True) or {})
    sys.argv = ["validator"]
    with contextlib.redirect_stdout(io.StringIO()) as output:
        result = v.main()
    assert result == 0 and '"summary": "PASS"' in output.getvalue()
    proofs.append({"probe": "missing_D-A39_run", "actual_exit": result,
                   "actual_summary": "PASS", "pending": v.RESULTS[-1]["check"]})

    big = root / "large.json"
    big.write_text(json.dumps({"header": {"kind": "valid"}, "secondary": "x" * (9 << 20)}, sort_keys=True))
    try:
        v.read_json_head(big)
    except json.JSONDecodeError:
        proofs.append({"probe": "valid_9MiB_json_header", "actual": "JSONDecodeError"})
    else:
        raise AssertionError("large-document defect no longer reproduces")

    target = root / "synthetic-run"
    target.mkdir()
    v.TARGET = str(target)
    for name in ("intent.json", "primary-recomputed-D-A39.json", "primary-scores.json", "second-label-read-D-A39.json"):
        (target / name).write_text("{}")
    fam = target / "families"
    fam.mkdir()
    for name in v.FAMILIES:
        blob = pickle.dumps({}, protocol=5)
        (fam / (name + ".pkl.part0000")).write_bytes(blob)
        manifest = {"name": name, "parts": 1, "bytes": len(blob), "format": "pickle5",
                    "sha256_of_concatenated_parts": hashlib.sha256(blob).hexdigest()}
        (fam / (name + ".manifest.json")).write_text(json.dumps(manifest))
    header = {"kind": "wrong-kind", "primary_of_record": {"sha256": v.PIN["primary"][1]},
              "label_reads_this_run": 1, "labels": {"sha256": v.LABELS["sha256"]},
              "seal": {"sha256": v.PIN["seal"][1]}, "freeze": {"sha256": v.PIN["amended_freeze"][1]},
              "families": [{"family": "counts", "status": "scored", "persist_error": "failed"}] * 9,
              "outcome_release_authorized": False,
              "decision_check": {"members": {"float32_mismatch_rows": 0}, "origin": {"float64_mismatch_rows": 0},
                                 "stable": {"float64_mismatch_rows": 0}},
              "primary_comparison": {"canonical_identical_except_unblinded_marker": False},
              "completion_gate": {"blocking": {"primary_identical_except_marker": False}}}
    (target / "secondary-result.json").write_text(json.dumps({"header": header, "secondary": {}}))
    (target / "completion.json").write_text(json.dumps({"passed": False, "blocking": {"failure": True}}))
    v.RESULTS.clear()
    with contextlib.redirect_stdout(io.StringIO()):
        v.tier_c(deep=True)
    assert all(r["ok"] is True for r in v.RESULTS)
    proofs.append({"probe": "failed_completion_empty_science_duplicate_families_wrong_kind_no_aggregate",
                   "actual_tierC": "all checks PASS even with --deep", "checks": len(v.RESULTS)})

    (target / "secondary-result.json").unlink()
    v.RESULTS.clear()
    with contextlib.redirect_stdout(io.StringIO()):
        v.tier_c(deep=True)
    assert all(r["ok"] is not False for r in v.RESULTS)
    proofs.append({"probe": "missing_secondary_json_and_split_parts", "actual": "pending only; no failure"})

    old_target = root / "old-input"
    old_target.write_bytes(b"123")
    link = root / "swapped-symlink"
    link.symlink_to(old_target)
    v.CUTOFF_NS = 10**30  # isolate link behavior from unrelated timestamp check
    v.SELF_HASHED.clear()
    v.RESULTS.clear()
    with contextlib.redirect_stdout(io.StringIO()):
        v.tier_b({"inventory": [{"kind": "input", "path": str(link), "size_bytes": 3, "sha256": "x" * 64}]})
    assert v.RESULTS[-1]["ok"] is True
    proofs.append({"probe": "symlink_input", "actual": "PASS by following target stamps"})

for proof in proofs:
    print(json.dumps(proof, sort_keys=True))
