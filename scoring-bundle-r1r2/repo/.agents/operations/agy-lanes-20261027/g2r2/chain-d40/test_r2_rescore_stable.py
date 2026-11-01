#!/usr/bin/env python3
"""Synthetic tests for the finish() completion gates of r2_rescore_stable.py (D-A40), adapted from chain-d39-v2's
test_r2_rescore_secondary.py. No labels, no cluster paths: a fake reader feeds small in-memory attempt-12 primary/scores bytes, real
persist_object writes under a tmp records dir, and finish is called directly. D-A40 additions: the stable-only family gate, the
not-in-scope stub gate and stub behaviour, and the stable not-scorable accounting gate. Run: python3 test_r2_rescore_stable.py"""
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
import r2_rescore_stable as mod
import r2_stable_not_scorable as ns


class FakeReader:
    def __init__(self, old_primary, old_scores):
        self.label_reads, self.read_bytes = 1, 4096
        self.objects = {mod.PRIMARY["path"]: json.dumps(old_primary).encode(),
                        mod.PRIMARY_SCORES["path"]: json.dumps(old_scores).encode()}

    def bytes(self, ref, purpose):
        return self.objects[ref["path"]]


def stub_result(name):
    return {"kind": "D-A40_family_not_in_scope", "deviation": "D-A40", "family": name, "status": mod.NOT_IN_SCOPE, "scored": False}


def stable_cell(arm, horizon, excluded, scored=("e1", "e3"), censored=1):
    rows = [{"event_id": eid, "jaccard": 0.5} for eid in scored]
    return {"status": "scored", "role": {"horizon_seconds": horizon, "variant": "stable"}, "rows": rows,
            "reference_events": len(rows) + censored + len(excluded), "scorable_events": len(rows), "censored_events": censored,
            "input_status_counts": {"available": 2, "unavailable_no_input": 1 + len(excluded)},
            ns.FIELD: {"rule": ns.RULE, "count": len(excluded), "event_ids": list(excluded),
                       "input_status_counts": {"unavailable_no_input": len(excluded)} if excluded else {}}}


def make_result():
    return {"kind": "newperiod_all_retained_R2_evaluation_v1", "primary": {"metrics": {"delta": 1.0}},
            "counts": stub_result("counts"),
            "membership": {f: stub_result(f"membership-{f}") for f in mod.EXPECTED_MEMBERSHIP_FAMILIES},
            # cell bookkeeping a successful stable family legitimately reports (no_input / censored): science, not failure
            "stable": {"kind": "newperiod_stable_secondary_v1", "cells": {
                "arm-a-d30": stable_cell("arm-a-d30", 30, ["e2"]), "arm-b-d30": stable_cell("arm-b-d30", 30, ["e2"]),
                "arm-c-d60": stable_cell("arm-c-d60", 60, []),
                "arm-x": {"status": "not_estimable", "role": {"horizon_seconds": 30}, "failure_chain": ["x"]}}},
            "origin": stub_result("origin"), "additional_baselines": stub_result("additional_baselines"),
            "covered_secondary_families": list(mod.EXPECTED_COVERED_SECONDARY_FAMILIES),
            "full_newperiod_coverage": True, "actual_execution_authorized": False}


def wrapper_records(result):
    return [{"arm_id": name, "path": "score_cell", "horizon_seconds": cell["role"]["horizon_seconds"],
             "count": cell[ns.FIELD]["count"], "event_ids": cell[ns.FIELD]["event_ids"]}
            for name, cell in result["stable"]["cells"].items() if cell.get("status") == "scored"]


def add_family(records, name, out=None):
    entry = {"family": name, "status": "scored", "seconds": 0.1}
    try:
        entry["persisted"] = mod.persist_object(Path(records) / "families", name, out or {"family": name, "note": "synthetic"})
    except Exception as error:
        entry["persist_error"] = repr(error)[:300]
    mod.STATE["families"].append(entry)
    return entry


def fresh(tmp, families=mod.EXPECTED_FAMILY_ENTRIES, not_in_scope=mod.NOT_IN_SCOPE_ENTRIES):
    mod.STATE.clear()
    mod.STATE.update({"mode": "open", "stages": [{"stage": "counts", "source": "checkpoint-attempt12"}], "families": [],
                      "not_in_scope": [{"family": n, "status": mod.NOT_IN_SCOPE, "scored": False} for n in not_in_scope],
                      "not_scorable_installs": 2, "refuse_installs": 1, "marker_written": True, "pre_label_passed": True,
                      "registry": {k: [] for k in mod.EXPECTED_CALLS}, "t0": time.time(),
                      "run_dir": str(tmp / "run"), "spec_ref": {"path": str(tmp / "spec.json"), "sha256": "0" * 64},
                      "labels_path": "<CLUSTER_STORAGE>/labels.json", "log_start_bytes": 0, "approval_ok": True,
                      "approval_ref": {"path": "<CLUSTER_STORAGE>/approval.json", "sha256": "1" * 64},
                      "attempt12_marker_record": {"unblinded_utc": "2026-10-30T00:00:00Z"},
                      "d39_marker_record": {"unblinded_utc": "2026-10-31T08:45:51Z"},
                      "decision_check": {"stable": {"arms_checked": 1, "rows_checked": 1, "float64_mismatch_rows": 0,
                                                    "float32_mismatch_rows": 0}},
                      "empty_forecast_check": {"paired": True, "rule": ns.RULE},
                      "records": str(tmp / "records")})
    records = tmp / "records"
    records.mkdir(parents=True)
    (records / mod.D40_MARKER_NAME).write_text(json.dumps({"third_label_read": True}))
    old_primary = {"kind": "custodian_primary_v1", "unblinded_marker": mod.MARKER["path"], "metrics": {"delta": 1.0}}
    (records / "primary-recomputed-D-A40.json").write_text(json.dumps(
        {**old_primary, "unblinded_marker": str(records / mod.D40_MARKER_NAME)}, sort_keys=True))
    old_scores = {"kind": "newperiod_primary_computed_scores_v1", "primary_report_path": mod.PRIMARY["path"],
                  "arms": {"m": {"30": [[{"event_id": "e1"}]]}}, "metrics_recomputed": False}
    (records / "primary-scores.json").write_text(json.dumps(
        {**old_scores, "primary_report_path": str(records / "primary-recomputed-D-A40.json")}, sort_keys=True))
    plan = {"kind": "newperiod_single_R2_execution_v1", "records": str(records),
            "primary_output": str(records / "primary-recomputed-D-A40.json"),
            "primary_scores_output": str(records / "primary-scores.json"),
            "result_output": str(records / "stable-result.json"),
            "labels": {"path": "<CLUSTER_STORAGE>/labels.json", "sha256": mod.LABELS_SHA}, "seal": {"path": "<CLUSTER_STORAGE>/seal.json", "sha256": mod.SEAL_SHA},
            "freeze": {"path": "<CLUSTER_STORAGE>/freeze.json", "sha256": mod.FREEZE_SHA},
            "bounds": {"output_file_bytes": 1 << 30, "output_total_bytes": 7 << 30, "access_log_bytes": 1 << 20}}
    for name in families:
        add_family(records, name)
    receipts = [{"path": str(records / "primary-scores.json"), "sha256": "2" * 64, "size_bytes": 10, "bound_bytes": 99}]
    result = make_result()
    ns.reset()
    ns.RECORDS.extend(wrapper_records(result))
    return plan, FakeReader(old_primary, old_scores), records, result, receipts


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
        tmp = Path(tempfile.mkdtemp(prefix="d40-"))
        try:
            fn(tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            ns.reset()
    return test


@with_dir
def test_success(tmp):
    plan, reader, records, result, receipts = fresh(tmp)
    out = call(plan, reader, records, result, receipts)
    assert out["passed"] is True and out["completion_gate"]["blocking"] == {}, out["completion_gate"]
    written = json.loads(Path(plan["result_output"]).read_bytes())
    assert written["header"]["kind"] == "newperiod_stable_rescore_D-A40_v1" and written["header"]["scope"] == mod.SCOPE
    assert written["header"]["completion_gate"]["families"]["missing"] == []
    durable_gate, returned_gate = written["header"]["completion_gate"], out["completion_gate"]
    for key in ("expected_families", "families", "expected_not_in_scope", "not_in_scope", "composition", "stable_not_scorable",
                "primary_equality", "blocking"):   # durable == returned on success
        assert durable_gate[key] == returned_gate[key], key
    assert durable_gate["expected_families"] == ["stable"] and len(durable_gate["expected_not_in_scope"]) == 8
    completion = json.loads((records / "completion.json").read_bytes())
    assert completion["passed"] is True and completion["blocking"] == {} and completion["label_reads"] == 1
    assert completion["deviation"] == "D-A40" and sorted(completion["not_in_scope"]) == sorted(mod.NOT_IN_SCOPE_ENTRIES)
    assert completion["stable_not_scorable"] == {
        "arm-a-d30": {"horizon_seconds": 30, "not_scorable": 1, "event_ids": ["e2"]},
        "arm-b-d30": {"horizon_seconds": 30, "not_scorable": 1, "event_ids": ["e2"]},
        "arm-c-d60": {"horizon_seconds": 60, "not_scorable": 0, "event_ids": []}}
    assert written["header"]["stable_not_scorable"]["rule"] == ns.RULE
    assert out["completion"]["sha256"] == mod.sha_file(records / "completion.json")
    assert written["header"]["label_reads_this_run"] == 1 and out["label_reads"] == 1
    assert written["header"]["d40_marker"]["path"].endswith("/third-label-read-D-A40.json")
    assert Path(out["stable_result"]["path"]).read_bytes().endswith(b"\n")
    assert (records / "stable-result-raw.pkl.part0000").is_file() and (records / "stable-result-raw.manifest.json").is_file()
    assert sorted(p.name for p in (records / "families").iterdir()) == ["stable.manifest.json", "stable.pkl.part0000"]
    assert written["secondary"]["counts"]["status"] == mod.NOT_IN_SCOPE and out["failed_families"] == []


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
def test_stable_only_family_gate(tmp):
    plan, reader, records, result, receipts = fresh(tmp / "missing", families=())
    assert '"families_missing": ["stable"]' in expect_refused("missing stable", plan, reader, records, result, receipts)
    plan, reader, records, result, receipts = fresh(tmp / "duplicate")
    mod.STATE["families"].append(dict(mod.STATE["families"][0]))
    assert '"families_duplicate": ["stable"]' in expect_refused("duplicate stable", plan, reader, records, result, receipts)
    for extra in ("counts", "membership-h1", "origin", "additional_baselines", "stable2"):   # any other SCORED family is unexpected
        plan, reader, records, result, receipts = fresh(tmp / f"extra-{extra}")
        add_family(records, extra)
        refused = expect_refused(f"scored {extra}", plan, reader, records, result, receipts)
        assert f'"families_unexpected": ["{extra}"]' in refused, refused


@with_dir
def test_not_in_scope_gate(tmp):
    for name in mod.NOT_IN_SCOPE_ENTRIES:
        plan, reader, records, result, receipts = fresh(tmp / f"missing-{name}",
                                                        not_in_scope=[n for n in mod.NOT_IN_SCOPE_ENTRIES if n != name])
        assert f'"not_in_scope_missing": ["{name}"]' in expect_refused(f"stub {name} missing", plan, reader, records, result, receipts)
        plan, reader, records, result, receipts = fresh(tmp / f"dup-{name}", not_in_scope=[*mod.NOT_IN_SCOPE_ENTRIES, name])
        assert f'"not_in_scope_duplicate": ["{name}"]' in expect_refused(f"stub {name} twice", plan, reader, records, result, receipts)
    for odd in ("stable", "membership-<unnamed>"):
        plan, reader, records, result, receipts = fresh(tmp / f"odd-{odd}", not_in_scope=[*mod.NOT_IN_SCOPE_ENTRIES, odd])
        assert f'"not_in_scope_unexpected": ["{odd}"]' in expect_refused(f"stub {odd}", plan, reader, records, result, receipts)


def test_out_of_scope_stub_never_touches_its_arguments():
    mod.STATE["not_in_scope"] = []

    class Untouchable:
        def __getattr__(self, name):
            raise AssertionError(f"the stub touched its argument ({name})")

        def __getitem__(self, key):
            raise AssertionError(f"the stub read its argument ({key!r})")

    module = types.SimpleNamespace(score_counts=lambda *a, **k: (_ for _ in ()).throw(AssertionError("real scorer ran")),
                                   evaluate=lambda *a, **k: (_ for _ in ()).throw(AssertionError("real scorer ran")))
    mod.out_of_scope(module, "score_counts", "counts")
    stub = module.score_counts
    mod.out_of_scope(module, "score_counts", "counts")                         # idempotent
    assert module.score_counts is stub
    out = module.score_counts(Untouchable(), Untouchable(), Untouchable())     # e.g. (prepared, label_table, score_curves)
    assert out == {"kind": "D-A40_family_not_in_scope", "deviation": "D-A40", "family": "counts", "status": mod.NOT_IN_SCOPE,
                   "scored": False}
    mod.out_of_scope(module, "evaluate", "membership", key=lambda args: args[0]["family"])
    assert module.evaluate({"family": "h3"}, Untouchable())["family"] == "membership-h3"
    assert module.evaluate(Untouchable(), Untouchable())["family"] == "membership-<unnamed>"   # never raises after the label read
    assert [e["family"] for e in mod.STATE["not_in_scope"]] == ["counts", "membership-h3", "membership-<unnamed>"]


@with_dir
def test_persist_error_and_not_persisted(tmp):
    plan, reader, records, result, receipts = fresh(tmp / "error")
    entry = mod.STATE["families"][0]
    entry["persist_error"] = "OSError(28, 'No space left on device')"
    del entry["persisted"]
    refused = expect_refused("persist_error stable", plan, reader, records, result, receipts)
    assert '"families_persist_error": ["stable"]' in refused and '"families_not_persisted": ["stable"]' not in refused, refused
    plan, reader, records, result, receipts = fresh(tmp / "missing")
    del mod.STATE["families"][0]["persisted"]
    assert '"families_not_persisted": ["stable"]' in expect_refused("no persisted", plan, reader, records, result, receipts)
    plan, reader, records, result, receipts = fresh(tmp / "tampered")
    (records / "families" / "stable.manifest.json").write_text('{"parts": 9, "bytes": 1}')
    assert '"families_not_persisted": ["stable"]' in expect_refused("tampered manifest", plan, reader, records, result, receipts)


@with_dir
def test_part_bytes_integrity(tmp):
    for case in ("truncated", "mutated", "wrong_name"):
        plan, reader, records, result, receipts = fresh(tmp / case)
        part = records / "families" / "stable.pkl.part0000"
        size = part.stat().st_size
        if case == "truncated":
            part.write_bytes(b"")
        elif case == "mutated":
            data = bytearray(part.read_bytes())
            data[0] ^= 0xFF
            part.write_bytes(bytes(data))
            assert part.stat().st_size == size
        else:
            part.rename(records / "families" / "stable.pkl.partXXXX")
        refused = expect_refused(case, plan, reader, records, result, receipts)
        assert '"families_not_persisted": ["stable"]' in refused, refused


@with_dir
def test_scoring_exception_stays_honestly_failed(tmp):
    plan, reader, records, result, receipts = fresh(tmp, families=())

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
    assert failed_out["kind"] == "D-A40_stable_family_failed" and "Boom" in failed_out["error"]
    assert (records / "families" / "stable.manifest.json").is_file()   # the failure record is durable
    result["stable"] = failed_out                                         # what the runner composes when stable raised
    refused = expect_refused("failed family", plan, reader, records, result, receipts)
    assert '"families_failed": ["stable"]' in refused and "stable_not_scorable" not in refused, refused
    written = json.loads(Path(plan["result_output"]).read_bytes())
    assert written["header"]["completion_gate"]["blocking"]["families_failed"] == ["stable"]
    completion = json.loads((records / "completion.json").read_bytes())
    assert completion["passed"] is False and completion["blocking"]["families_failed"] == ["stable"]


@with_dir
def test_stable_exclusion_accounting_gate(tmp):
    def refused_for(label, mutate):
        plan, reader, records, result, receipts = fresh(tmp / label)
        mutate(result)
        return expect_refused(label, plan, reader, records, result, receipts)

    cells = lambda r: r["stable"]["cells"]
    assert '"stable_not_scorable_missing_record": ["arm-a-d30"]' in refused_for(
        "no-record", lambda r: cells(r)["arm-a-d30"].pop(ns.FIELD))
    assert '"stable_not_scorable_inconsistent_accounting": ["arm-a-d30"]' in refused_for(
        "count", lambda r: cells(r)["arm-a-d30"][ns.FIELD].update(count=2))
    assert '"stable_not_scorable_inconsistent_accounting": ["arm-a-d30"]' in refused_for(
        "scored-anyway", lambda r: cells(r)["arm-a-d30"]["rows"].append({"event_id": "e2", "jaccard": 0.0}))
    assert '"stable_not_scorable_inconsistent_accounting": ["arm-c-d60"]' in refused_for(
        "sum", lambda r: cells(r)["arm-c-d60"].update(reference_events=99))
    unpaired = refused_for("unpaired", lambda r: cells(r).update({"arm-b-d30": stable_cell("arm-b-d30", 30, ["e9"])}))
    assert '"stable_not_scorable_unpaired_horizons": ["30"]' in unpaired, unpaired
    plan, reader, records, result, receipts = fresh(tmp / "records")
    ns.RECORDS.append(dict(ns.RECORDS[0]))                                  # one cell scored twice through the wrapper
    assert "stable_not_scorable_wrapper_records" in expect_refused("records", plan, reader, records, result, receipts)
    plan, reader, records, result, receipts = fresh(tmp / "malformed")      # a check that cannot run blocks, never crashes
    result["stable"]["cells"]["arm-a-d30"]["role"] = "not-a-dict"
    assert "stable_not_scorable_check_error" in expect_refused("malformed", plan, reader, records, result, receipts)
    assert json.loads((records / "completion.json").read_bytes())["passed"] is False


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
    result["stable"]["by_horizon_pair"] = {(2026, 30): 0.5}            # tuple key: json.dumps raises TypeError, fallback stringifies
    out = call(plan, reader, records, result, receipts)
    written = json.loads(Path(plan["result_output"]).read_bytes())
    assert written["header"]["json_value_notes"]["dict_keys_stringified"] is True
    assert written["secondary"]["stable"]["by_horizon_pair"] == {"(2026, 30)": 0.5}
    assert out["passed"] is True
    plan, reader, records, result, receipts = fresh(tmp / "collision")
    result["stable"]["mixed"] = {"1": "a", 1: "b"}                     # str(1) == "1": the fallback must refuse, not drop an entry
    refused = expect_refused("collision", plan, reader, records, result, receipts)
    assert "collide" in refused and not Path(plan["result_output"]).exists()
    assert (records / "stable-result-raw.manifest.json").is_file()     # durable raw result survives the refusal


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
    mod.STATE["marker_written"] = False
    try:
        call(plan, reader, records, result, receipts)
        raise AssertionError("marker guard gone")
    except ValueError as guard:
        assert "exactly one label read" in str(guard)
    mod.STATE["marker_written"] = True
    call(plan, reader, records, result, receipts)
    digest = Path(plan["result_output"]).read_bytes()
    ns.RECORDS[:] = wrapper_records(result)
    try:                                                            # same records dir: the once-only target path holds
        call(plan, reader, records, result, receipts)
        raise AssertionError("once-only result path gone")
    except mod.CompletionRefused as refused:
        assert "stable-result.json" in str(refused) and "completion.json" in str(refused), refused
    assert Path(plan["result_output"]).read_bytes() == digest       # never overwritten


def test_scope_constants():
    assert mod.EXPECTED_FAMILY_ENTRIES == ("stable",)
    assert set(mod.NOT_IN_SCOPE_ENTRIES) | set(mod.EXPECTED_FAMILY_ENTRIES) == set(mod.ALL_FAMILY_ENTRIES)
    assert len(mod.ALL_FAMILY_ENTRIES) == 9 and len(mod.NOT_IN_SCOPE_ENTRIES) == 8
    assert mod.SCOPE == {"scored": ["stable"], "prepared_not_scored": list(mod.NOT_IN_SCOPE_ENTRIES), "status_of_others": mod.NOT_IN_SCOPE}
    assert mod.TARGET.endswith("/arms/000/rescore-stable-D-A40") and mod.D40_MARKER_NAME == "third-label-read-D-A40.json"
    assert mod.APPROVAL_FIELDS["deviation"] == "D-A40" and mod.APPROVAL_FIELDS["third_label_read_authorized"] is True
    assert mod.APPROVAL_FIELDS["scope"] == "stable lane only" and mod.APPROVAL_FIELDS["records"] == mod.TARGET
    assert all(p.startswith("[D-A40 ") for p in (mod.DRY_PREFIX, mod.OPEN_PREFIX, mod.LABEL_PREFIX))


def test_pinned_constants_match_originals():
    relative = Path(".agents/operations/newperiod-single-r2-persistence-20261024")
    pinned = next((p / relative for p in Path(__file__).resolve().parents if (p / relative).is_dir()), None)
    assert pinned is not None, ("pinned .agents/operations/newperiod-single-r2-persistence-20261024 sources not found above this test"
                                " — this drift test must assert their presence, never skip")
    compose_path = pinned / "components/composition/compose.py"
    origin_path = pinned / "components/origin/consumer.py"
    membership_path = pinned / "components/composition/components/membership/consumer.py"
    stable_path = pinned / "components/composition/components/stable/consumer.py"
    runner_path = pinned / "runner.py"
    for path in (compose_path, origin_path, membership_path, stable_path, runner_path):
        assert path.is_file() and path.stat().st_size > 0, f"missing pinned source: {path}"
    compose = compose_path.read_text()
    families_line = next(line for line in compose.splitlines() if line.startswith("FAMILIES ="))
    assert ast.literal_eval(families_line.split("=", 1)[1]) == mod.EXPECTED_MEMBERSHIP_FAMILIES
    assert "'covered_secondary_families': ['counts', *FAMILIES, 'stable']" in compose
    assert "'membership': membership," in compose and "'stable': modules['stable'].evaluate(" in compose
    assert "secondary=score_counts(prepared,captured[0],original_score_curves)" in \
        (pinned / "components/composition/components/count/evaluate.py").read_text()     # the counts call the stub replaces
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
