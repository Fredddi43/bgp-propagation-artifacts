#!/usr/bin/env python3
"""Synthetic tests for the finish() completion gates of r2_rescore_secondary.py (D-A39). No labels, no cluster paths: a fake
reader feeds small in-memory attempt-12 primary/scores bytes, real persist_object writes under a tmp records dir, and finish is
called directly. Run: python3 test_r2_rescore_secondary.py"""
import ast
import json
import shutil
import sys
import tempfile
import time
import traceback
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r2_rescore_secondary as mod


class FakeReader:
    def __init__(self, old_primary, old_scores):
        self.label_reads, self.read_bytes = 1, 4096
        self.objects = {mod.PRIMARY["path"]: json.dumps(old_primary).encode(),
                        mod.PRIMARY_SCORES["path"]: json.dumps(old_scores).encode()}

    def bytes(self, ref, purpose):
        return self.objects[ref["path"]]


def make_result():
    return {"kind": "newperiod_all_retained_R2_evaluation_v1", "primary": {"metrics": {"delta": 1.0}},
            "counts": {"kind": "counts_report"},
            # cell bookkeeping a successful family legitimately reports (no_input / unavailable / censored): science, not failure
            "membership": {f: {"family": f, "cells": {"arm-a": {"status": "scored"}, "arm-b": {"status": "no_input"}},
                               "unavailable_rows": ["unavailable_no_input"], "censored_truth_rows": 0}
                           for f in mod.EXPECTED_MEMBERSHIP_FAMILIES},
            "stable": {"kind": "newperiod_stable_secondary_v1", "cells": {"arm-a": {"status": "scored"}}},
            "origin": {"kind": "origin_report"}, "additional_baselines": {"kind": "baseline_report"},
            "covered_secondary_families": list(mod.EXPECTED_COVERED_SECONDARY_FAMILIES),
            "full_newperiod_coverage": True, "actual_execution_authorized": False}


def add_family(records, name, out=None):
    entry = {"family": name, "status": "scored", "seconds": 0.1}
    try:
        entry["persisted"] = mod.persist_object(Path(records) / "families", name, out or {"family": name, "note": "synthetic"})
    except Exception as error:
        entry["persist_error"] = repr(error)[:300]
    mod.STATE["families"].append(entry)
    return entry


def fresh(tmp, families=mod.EXPECTED_FAMILY_ENTRIES):
    mod.STATE.clear()
    mod.STATE.update({"mode": "open", "stages": [{"stage": "counts", "source": "checkpoint-attempt12"}], "families": [],
                      "float32_installs": 1, "refuse_installs": 1, "d39_marker_written": True, "pre_label_passed": True,
                      "registry": {k: [] for k in mod.EXPECTED_CALLS}, "t0": time.time(),
                      "run_dir": str(tmp / "run"), "spec_ref": {"path": str(tmp / "spec.json"), "sha256": "0" * 64},
                      "labels_path": "<CLUSTER_STORAGE>/labels.json", "log_start_bytes": 0, "approval_ok": True,
                      "approval_ref": {"path": "<CLUSTER_STORAGE>/approval.json", "sha256": "1" * 64},
                      "attempt12_marker_record": {"unblinded_utc": "2026-10-30T00:00:00Z"},
                      "decision_check": {k: {"arms_checked": 1, "rows_checked": 1, "float64_mismatch_rows": 0,
                                             "float32_mismatch_rows": 0} for k in ("members", "origin", "stable")},
                      "records": str(tmp / "records")})
    records = tmp / "records"
    records.mkdir(parents=True)
    (records / "second-label-read-D-A39.json").write_text(json.dumps({"second_label_read": True}))
    old_primary = {"kind": "custodian_primary_v1", "unblinded_marker": mod.MARKER["path"], "metrics": {"delta": 1.0}}
    (records / "primary-recomputed-D-A39.json").write_text(json.dumps(
        {**old_primary, "unblinded_marker": str(records / "second-label-read-D-A39.json")}, sort_keys=True))
    old_scores = {"kind": "newperiod_primary_computed_scores_v1", "primary_report_path": mod.PRIMARY["path"],
                  "arms": {"m": {"30": [[{"event_id": "e1"}]]}}, "metrics_recomputed": False}
    (records / "primary-scores.json").write_text(json.dumps(
        {**old_scores, "primary_report_path": str(records / "primary-recomputed-D-A39.json")}, sort_keys=True))
    plan = {"kind": "newperiod_single_R2_execution_v1", "records": str(records),
            "primary_output": str(records / "primary-recomputed-D-A39.json"),
            "primary_scores_output": str(records / "primary-scores.json"),
            "result_output": str(records / "secondary-result.json"),
            "labels": {"path": "<CLUSTER_STORAGE>/labels.json", "sha256": mod.LABELS_SHA}, "seal": {"path": "<CLUSTER_STORAGE>/seal.json", "sha256": mod.SEAL_SHA},
            "freeze": {"path": "<CLUSTER_STORAGE>/freeze.json", "sha256": mod.FREEZE_SHA},
            "bounds": {"output_file_bytes": 1 << 30, "output_total_bytes": 7 << 30, "access_log_bytes": 1 << 20}}
    for name in families:
        add_family(records, name)
    receipts = [{"path": str(records / "primary-scores.json"), "sha256": "2" * 64, "size_bytes": 10, "bound_bytes": 99}]
    return plan, FakeReader(old_primary, old_scores), records, make_result(), receipts


def call(plan, reader, records, result, receipts):
    return mod.finish(None, plan, reader, records, result, receipts)


def expect_refused(label, plan, reader, records, result, receipts):
    try:
        out = call(plan, reader, records, result, receipts)
    except mod.CompletionRefused as refused:
        return str(refused)
    raise AssertionError(f"{label}: finish returned passed={out.get('passed')} but must refuse")


def with_dir(fn):
    def test():
        tmp = Path(tempfile.mkdtemp(prefix="d39-", dir="<AGENT_TMP>")) if Path("<AGENT_TMP>").is_dir() \
            else Path(tempfile.mkdtemp(prefix="d39-"))
        try:
            fn(tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return test


@with_dir
def test_success(tmp):
    plan, reader, records, result, receipts = fresh(tmp)
    out = call(plan, reader, records, result, receipts)
    assert out["passed"] is True and out["completion_gate"]["blocking"] == {}, out["completion_gate"]
    written = json.loads(Path(plan["result_output"]).read_bytes())
    assert written["header"]["completion_gate"]["families"]["missing"] == []
    durable_gate, returned_gate = written["header"]["completion_gate"], out["completion_gate"]
    for key in ("expected_families", "families", "composition", "primary_equality", "blocking"):   # durable == returned on success
        assert durable_gate[key] == returned_gate[key], key
    completion = json.loads((records / "completion.json").read_bytes())
    assert completion["passed"] is True and completion["blocking"] == {} and completion["label_reads"] == 1
    assert out["completion"]["sha256"] == mod.sha_file(records / "completion.json")
    assert written["header"]["label_reads_this_run"] == 1 and out["label_reads"] == 1
    assert Path(out["secondary_result"]["path"]).read_bytes().endswith(b"\n")
    assert (records / "secondary-result-raw.pkl.part0000").is_file() and (records / "secondary-result-raw.manifest.json").is_file()
    # the fixture families carry no_input / unavailable_no_input / censored bookkeeping and still score as success
    assert "no_input" in json.dumps(result["membership"]) and out["failed_families"] == []


@with_dir
def test_primary_equality_false(tmp):
    for variant in ("primary", "scores"):
        plan, reader, records, result, receipts = fresh(tmp / variant)
        path = Path(plan["primary_output"] if variant == "primary" else plan["primary_scores_output"])
        mutated = json.loads(path.read_bytes())
        (mutated["metrics"] if variant == "primary" else mutated["arms"])["delta"] = 999.0
        path.write_text(json.dumps(mutated, sort_keys=True))
        refused = expect_refused(variant, plan, reader, records, result, receipts)
        key = "primary_identical_except_marker" if variant == "primary" else "scores_identical_except_report_path"
        assert key in refused, refused
        written = json.loads(Path(plan["result_output"]).read_bytes())     # the durable gate must show the refusal reason too
        assert written["header"]["completion_gate"]["blocking"][key] is False, written["header"]["completion_gate"]["blocking"]
        assert json.loads((records / "completion.json").read_bytes())["blocking"][key] is False
    plan, reader, records, result, receipts = fresh(tmp / "receipts")
    assert "score_receipts" in expect_refused("receipts", plan, reader, records, result, receipts[:0])
    assert "score_receipts" in expect_refused("two receipts", plan, reader, records, result, receipts + receipts)


@with_dir
def test_missing_each_family(tmp):
    for name in mod.EXPECTED_FAMILY_ENTRIES:
        plan, reader, records, result, receipts = fresh(tmp / name, [n for n in mod.EXPECTED_FAMILY_ENTRIES if n != name])
        refused = expect_refused(f"missing {name}", plan, reader, records, result, receipts)
        assert f'"families_missing": ["{name}"]' in refused, refused


@with_dir
def test_duplicate_each_family(tmp):
    for name in mod.EXPECTED_FAMILY_ENTRIES:
        plan, reader, records, result, receipts = fresh(tmp / name)
        duplicate = next(e for e in mod.STATE["families"] if e["family"] == name)
        mod.STATE["families"].append(dict(duplicate))   # the same family scored and persisted twice
        refused = expect_refused(f"duplicate {name}", plan, reader, records, result, receipts)
        assert f'"families_duplicate": ["{name}"]' in refused, refused


@with_dir
def test_unexpected_family(tmp):
    for extra in ("membership-extra6", "stable2"):
        plan, reader, records, result, receipts = fresh(tmp / extra)
        add_family(records, extra)
        refused = expect_refused(f"unexpected {extra}", plan, reader, records, result, receipts)
        assert f'"families_unexpected": ["{extra}"]' in refused, refused


@with_dir
def test_persist_error_and_not_persisted(tmp):
    for name in mod.EXPECTED_FAMILY_ENTRIES:
        plan, reader, records, result, receipts = fresh(tmp / name)
        entry = next(e for e in mod.STATE["families"] if e["family"] == name)
        entry["persist_error"] = "OSError(28, 'No space left on device')"
        del entry["persisted"]
        refused = expect_refused(f"persist_error {name}", plan, reader, records, result, receipts)
        assert f'"families_persist_error": ["{name}"]' in refused and f'"families_not_persisted": ["{name}"]' not in refused, refused
    plan, reader, records, result, receipts = fresh(tmp / "missing")
    del next(e for e in mod.STATE["families"] if e["family"] == "origin")["persisted"]
    assert '"families_not_persisted": ["origin"]' in expect_refused("no persisted", plan, reader, records, result, receipts)
    plan, reader, records, result, receipts = fresh(tmp / "tampered")
    (records / "families" / "stable.manifest.json").write_text('{"parts": 9, "bytes": 1}')
    assert '"families_not_persisted": ["stable"]' in expect_refused("tampered manifest", plan, reader, records, result, receipts)
    (records / "families" / "stable.manifest.json").write_text(json.dumps(
        next(e for e in mod.STATE["families"] if e["family"] == "stable")["persisted"], sort_keys=True))
    next(records.glob("families/stable.pkl.part*")).unlink()
    assert '"families_not_persisted": ["stable"]' in expect_refused("lost part", plan, reader, records, result, receipts)


@with_dir
def test_part_bytes_integrity(tmp):
    for case in ("truncated", "mutated", "wrong_name"):
        plan, reader, records, result, receipts = fresh(tmp / case)
        part = records / "families" / "stable.pkl.part0000"
        size = part.stat().st_size
        if case == "truncated":
            part.write_bytes(b"")                                        # review reproduction: zero-byte part
        elif case == "mutated":
            data = bytearray(part.read_bytes())
            data[0] ^= 0xFF
            part.write_bytes(bytes(data))                                # same name and size, different bytes
            assert part.stat().st_size == size
        else:
            part.rename(records / "families" / "stable.pkl.partXXXX")    # a part still matches the old glob count, wrong name
        refused = expect_refused(case, plan, reader, records, result, receipts)
        assert '"families_not_persisted": ["stable"]' in refused, refused


@with_dir
def test_scoring_exception_stays_honestly_failed(tmp):
    plan, reader, records, result, receipts = fresh(tmp, [n for n in mod.EXPECTED_FAMILY_ENTRIES if n != "stable"])

    class Boom(RuntimeError):
        pass

    module = types.SimpleNamespace()

    def evaluate(*args, **kwargs):
        raise Boom("stable scoring exploded")
    module.evaluate = evaluate
    mod.isolate(module, "evaluate", "stable")
    failed_out = module.evaluate()          # the wrapper records, never re-raises, and persists the failure record
    entry = mod.STATE["families"][-1]
    assert entry["status"] == "failed" and "persist_error" not in entry
    assert failed_out["kind"] == "D-A39_secondary_family_failed" and "Boom" in failed_out["error"]
    assert (records / "families" / "stable.manifest.json").is_file()   # the failure record is durable
    assert "Boom" in b"".join(p.read_bytes() for p in sorted((records / "families").glob("stable.pkl.part*"))).decode(errors="replace")
    refused = expect_refused("failed family", plan, reader, records, result, receipts)
    assert '"families_failed": ["stable"]' in refused, refused
    written = json.loads(Path(plan["result_output"]).read_bytes())     # honest report is still written, durable gate carries blocking
    assert written["header"]["completion_gate"]["blocking"]["families_failed"] == ["stable"]
    completion = json.loads((records / "completion.json").read_bytes())
    assert completion["passed"] is False and completion["blocking"]["families_failed"] == ["stable"]
    recorded = next(f for f in written["header"]["families"] if f["family"] == "stable")
    assert recorded["status"] == "failed" and (records / "secondary-result-raw.manifest.json").is_file()


@with_dir
def test_isolate_membership_naming(tmp):
    plan, reader, records, result, receipts = fresh(tmp)
    module = types.SimpleNamespace(evaluate=lambda prepared, table: {"ok": True})
    mod.isolate(module, "evaluate", "membership", key=lambda args: args[0]["family"])
    module.evaluate({"family": "h1"}, {})
    assert mod.STATE["families"][-1]["family"] == "membership-h1"      # matches the pinned family names in EXPECTED_FAMILY_ENTRIES


@with_dir
def test_composition_mismatch(tmp):
    plan, reader, records, result, receipts = fresh(tmp / "keys")
    del result["origin"]
    assert '"composition_missing_key": ["origin"]' in expect_refused("missing key", plan, reader, records, result, receipts)
    plan, reader, records, result, receipts = fresh(tmp / "membership")
    result["membership"] = {f: {} for f in (*mod.EXPECTED_MEMBERSHIP_FAMILIES, "extra6")}
    assert "composition_membership_families" in expect_refused("six families", plan, reader, records, result, receipts)
    plan, reader, records, result, receipts = fresh(tmp / "covered")
    result["covered_secondary_families"] = ["counts", "h1", "h3", "timing", "history", "ordinary", "stable"]
    assert "composition_covered_secondary_families" in expect_refused("covered list", plan, reader, records, result, receipts)


@with_dir
def test_json_key_fallback(tmp):
    plan, reader, records, result, receipts = fresh(tmp)
    result["counts"]["by_horizon_pair"] = {(2026, 30): 0.5}            # tuple key: json.dumps raises TypeError, fallback stringifies
    out = call(plan, reader, records, result, receipts)
    written = json.loads(Path(plan["result_output"]).read_bytes())
    assert written["header"]["json_value_notes"]["dict_keys_stringified"] is True
    assert written["secondary"]["counts"]["by_horizon_pair"] == {"(2026, 30)": 0.5}
    assert out["passed"] is True
    plan, reader, records, result, receipts = fresh(tmp / "collision")
    result["counts"]["mixed"] = {"1": "a", 1: "b"}                     # str(1) == "1": the fallback must refuse, not drop an entry
    refused = expect_refused("collision", plan, reader, records, result, receipts)
    assert "collide" in refused and not Path(plan["result_output"]).exists()
    assert (records / "secondary-result-raw.manifest.json").is_file()  # durable raw result survives the refusal


@with_dir
def test_guards_preserved(tmp):
    plan, reader, records, result, receipts = fresh(tmp)
    reader.label_reads = 2
    try:
        call(plan, reader, records, result, receipts)
        raise AssertionError("label guard gone")
    except ValueError as guard:
        assert "exactly one label read" in str(guard)
    reader.label_reads = 1
    mod.STATE["d39_marker_written"] = False
    try:
        call(plan, reader, records, result, receipts)
        raise AssertionError("marker guard gone")
    except ValueError as guard:
        assert "exactly one label read" in str(guard)
    mod.STATE["d39_marker_written"] = True
    call(plan, reader, records, result, receipts)
    digest = Path(plan["result_output"]).read_bytes()
    try:                                                            # same records dir: the once-only target path holds
        call(plan, reader, records, result, receipts)
        raise AssertionError("once-only result path gone")
    except mod.CompletionRefused as refused:
        assert "secondary-result.json" in str(refused) and "completion.json" in str(refused), refused
    assert Path(plan["result_output"]).read_bytes() == digest       # never overwritten


def test_pinned_constants_match_originals():
    relative = Path(".agents/operations/newperiod-single-r2-persistence-20261024")
    pinned = next((p / relative for p in Path(__file__).resolve().parents if (p / relative).is_dir()), None)
    assert pinned is not None, ("pinned .agents/operations/newperiod-single-r2-persistence-20261024 sources not found above this test"
                                " — this drift test must assert their presence, never skip")
    compose_path = pinned / "components/composition/compose.py"
    origin_path = pinned / "components/origin/consumer.py"
    membership_path = pinned / "components/composition/components/membership/consumer.py"
    runner_path = pinned / "runner.py"
    for path in (compose_path, origin_path, membership_path, runner_path):
        assert path.is_file() and path.stat().st_size > 0, f"missing pinned source: {path}"
    compose = compose_path.read_text()
    families_line = next(line for line in compose.splitlines() if line.startswith("FAMILIES ="))
    assert ast.literal_eval(families_line.split("=", 1)[1]) == mod.EXPECTED_MEMBERSHIP_FAMILIES
    assert "'covered_secondary_families': ['counts', *FAMILIES, 'stable']" in compose
    assert "'membership': membership," in compose and "'stable': modules['stable'].evaluate(" in compose
    origin = origin_path.read_text()
    assert "FAMILIES=('origin_change_invalid','origin_change_valid')" in origin
    membership = membership_path.read_text()
    assert "FAMILIES=('h1','h3','timing','history','ordinary')" in membership and "family=prepared['family']" in membership
    runner = runner_path.read_text()
    assert "result['origin']=origin.evaluate(" in runner
    assert "result['additional_baselines']=components['baseline'].evaluate(" in runner
    assert "result['covered_secondary_families']+=['additional_baselines',*origin.FAMILIES]" in runner


def main():
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith("test_") and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}", flush=True)
        except Exception:
            failed += 1
            print(f"FAIL {name}", flush=True)
            traceback.print_exc()
    print(f"{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
