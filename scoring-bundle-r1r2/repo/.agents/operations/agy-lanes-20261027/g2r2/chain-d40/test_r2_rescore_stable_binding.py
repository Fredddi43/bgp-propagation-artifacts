#!/usr/bin/env python3
"""D-A40: synthetic tests for the checkpoint byte binding, the marker chain, the approval binding and the pre-label checks of
r2_rescore_stable.py, adapted from chain-d39-v2's test_r2_rescore_binding.py.

Everything here is local and label-free: synthetic pickles in temp directories, no <CLUSTER_STORAGE> path is read or written, no label table
exists anywhere near these tests, and r2_checkpoint.py is only read (never written). The synthetic attempt-12 checkpoints are counts,
five membership families and stable (.pkl); origin and baseline are rolling checkpoints saved beforehand, as D-A39 left them. The
synthetic stable checkpoint holds real-shaped stable cells, so pre_label runs the REAL float64 decision check and the REAL
empty-forecast pairing check. D-A39's approved binding is simulated by the fixture's own dry-run binding.

Coverage: binding success in both modes and equality with the D-A39 binding (refused otherwise, in both modes); a missing
checkpoint refused in both modes before anything is computed or saved; modified bytes, missing/duplicated stages, rolled attempt-12
receipts and shadows refused before the label; the unchanged rolling-checkpoint readers; the stable pre-checks (unpaired empty
forecasts, a float64 decision mismatch) refused before the label; the marker chain (attempt-12 AND D-A39 markers, read through the
Reader, fields checked, new D-A40 marker path); the execute preflight; and the approval binding (D-A40 fields, ready.json by sha256,
scope, patch module, marker reads, pre-check, binding). Every rejection happens BEFORE any label could open.

Run: python3 test_r2_rescore_stable_binding.py
"""
import contextlib
import copy
import hashlib
import io
import json
import pickle
import sys
import tempfile
import traceback
import types
from pathlib import Path

CHAIN = Path(__file__).resolve().parent
ROOT = next(p for p in CHAIN.parents if (p / "src" / "bgbench").is_dir())
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(CHAIN))

import r2_checkpoint                      # the pinned checkpoint module (read-only here)
import r2_rescore_stable as d40           # the driver under test
import r2_stable_not_scorable as ns
import test_r2_stable_not_scorable as cells_kit   # synthetic stable cell builders only

STABLE_PREPARED = {"cells": {"n": cells_kit.neural_cell(cells_kit.EVENTS),
                             "p": cells_kit.baseline_cell(cells_kit.EVENTS, "persistence", "stable-persistence-d30")},
                   "evidence": {"input_only": True}, "available": {"30": ["e1", "e5", "e6"]}}
LEGACY_SPECS = [("counts", 12, {"lane": "counts", "pad": "b" * 256})]
MEMBER_ARGS = (1, 2, 3, 4, 5)
ROLLING_SPECS = [("origin", None, {"origin": "prepared by D-A39", "pad": "o" * 1024}),
                 ("baseline", 11, {"lane": "baseline", "pad": "a" * 4096})]


def fingerprint(name, arg):
    return r2_checkpoint._digest({"stage": name, "code": r2_checkpoint.code_fingerprint(stage=name),
                                  "args": [] if arg is None else [arg], "kwargs": {}})


def make_legacy_file(ckpt_dir, name, arg, payload):
    fp = fingerprint(name, arg)
    blob = pickle.dumps({"fingerprint": fp, "stage": name}) + pickle.dumps(payload, protocol=5)
    path = ckpt_dir / f"{name}-{fp[:24]}.pkl"
    path.write_bytes(blob)
    return path, fp


@contextlib.contextmanager
def fixture(tmp, stable=STABLE_PREPARED):
    """Synthetic checkpoints as D-A39 left them + the driver's view of them; module constants and state restored afterwards."""
    saved = (d40.LEGACY, d40.SAVE_FREE_FLOOR, d40.D39_CHECKPOINT_BINDING_SHA, dict(d40.STATE))
    ckpt = tmp / "r2-ckpt"
    ckpt.mkdir(parents=True)
    legacy = {}
    for name, arg, payload in [*LEGACY_SPECS, ("stable", 13, stable)]:
        path, _ = make_legacy_file(ckpt, name, arg, payload)
        legacy.setdefault(name, {})[path.name] = path.stat().st_size
    for arg in MEMBER_ARGS:
        path, _ = make_legacy_file(ckpt, "members", arg, {"family": f"fam{arg}", "pad": "a" * 4096})
        legacy.setdefault("members", {})[path.name] = path.stat().st_size
    d40.LEGACY = {k: legacy[k] for k in ("counts", "members", "stable")}
    d40.SAVE_FREE_FLOOR = -r2_checkpoint.PART_BYTES   # the free-space guard is orthogonal here: make it always pass
    for name, arg, payload in ROLLING_SPECS:          # D-A39's rolling checkpoints (origin, baseline)
        fp = fingerprint(name, arg)
        assert d40.save_rolling(r2_checkpoint, ckpt / f"{name}-{fp[:24]}", name, fp, payload)["status"] == "saved"
    d40.install_checkpoint_wrap()
    ns.reset()
    try:
        yield ckpt
    finally:
        d40.LEGACY, d40.SAVE_FREE_FLOOR, d40.D39_CHECKPOINT_BINDING_SHA = saved[0], saved[1], saved[2]
        d40.STATE.clear()
        d40.STATE.update(saved[3])
        ns.reset()


def reset_state(mode, records):
    ns.reset()
    d40.STATE.update(mode=mode, stages=[], families=[], not_in_scope=[], not_scorable_installs=0, refuse_installs=0,
                     marker_written=False, pre_label_passed=False, binding=None, approved_binding=None,
                     registry={k: [] for k in d40.EXPECTED_CALLS}, records=str(records), approval_ok=False,
                     stable_modules=[installed_stable()])


def installed_stable():
    """A stand-in for the stable consumer as composition_components leaves it: both scoring entry points carry the rule."""
    marked = lambda *a, **k: None
    setattr(marked, ns.MARK, True)
    return types.SimpleNamespace(persistence=marked, m=types.SimpleNamespace(score_cell=marked))


def forbidden(_arg=None):
    raise AssertionError("stage computed instead of loading its checkpoint")


def run_stage(name, arg, ckpt, function=None):
    return r2_checkpoint.wrap(function or forbidden, name, str(ckpt), None)(*(() if arg is None else (arg,)))


def run_all_stages(ckpt):
    for name, arg, _payload in ROLLING_SPECS:
        run_stage(name, arg, ckpt)
    for name, arg, _payload in LEGACY_SPECS:
        run_stage(name, arg, ckpt)
    for arg in MEMBER_ARGS:
        run_stage("members", arg, ckpt)
    run_stage("stable", 13, ckpt)
    return copy.deepcopy(json.loads(json.dumps(d40.STATE["stages"])))   # the ready.json view of the stages


def simulate_d39_binding(ckpt, tmp):
    """The fixture's own (dry-run) binding stands in for the binding D-A39 was approved on."""
    reset_state("dry-run", tmp / "probe")
    stages = run_all_stages(ckpt)
    _items, binding = d40.binding_of(stages)
    d40.D39_CHECKPOINT_BINDING_SHA = binding
    return stages, binding


def marker_record(pinned):
    return {**pinned, "record": {"unblinded_utc": "2026-10-31T08:45:51Z", "seal_sha256": d40.SEAL_SHA,
                                 "labels_sha256": d40.LABELS_SHA, "custody_spec_sha256": d40.FREEZE_SHA, "out": "/synthetic"}}


@contextlib.contextmanager
def approved_against(stages, tmp, tamper=None, approval_tamper=None):
    """A synthetic dry-run ready.json + approval file accepted by the driver's own verify_approval (the real function)."""
    stages = copy.deepcopy(stages)      # tampering must not touch the caller's stage records
    items, binding = d40.binding_of(stages)
    ready = {"kind": "D-A40_stable_rescore_dry_run_v1", "status": "ready, labels not opened", "labels_opened": False,
             "d40_marker_written": False, "target_records": d40.TARGET, "reader": {"label_reads": 0}, "scope": copy.deepcopy(d40.SCOPE),
             "driver": d40.ref(Path(d40.__file__)),
             "float32_scoring": {"module": d40.ref(CHAIN / "r2_float32_scoring.py")},
             "not_scorable": {"module": d40.ref(CHAIN / "r2_stable_not_scorable.py"), "rule": ns.RULE},
             "parallel_scoring": {"module": d40.ref(CHAIN / "r2_parallel_scoring.py"), "options": dict(d40.PARALLEL_ADAPTER_OPTIONS),
                                  "hard_cap": 8, "installs": ["stable.scoring", "stable.original"]},
             "code": {name: d40.ref(CHAIN / name) for name in d40.CODE_FILES},
             "attempt12_marker": marker_record(d40.MARKER), "d39_marker": marker_record(d40.D39_MARKER),
             "empty_forecast_check": ns.check_prepared([STABLE_PREPARED]),
             "checkpoint_binding": {"sha256": binding, "items": items}, "stages": stages}
    if tamper:
        tamper(ready)
    ready_path = tmp / "ready.json"
    ready_path.write_text(json.dumps(ready))
    approval = {**d40.APPROVAL_FIELDS, "approved_by": "synthetic-test-owner", "approval_record": "unit test fixture",
                "dry_run_ready": {"path": str(ready_path), "sha256": d40.sha_file(ready_path)}}
    if approval_tamper:
        approval_tamper(approval)
    approval_path = tmp / "approval.json"
    approval_path.write_text(json.dumps(approval))
    yield d40.verify_approval(approval_path)


def pre_label_open(marker_dir):
    """Drive the real pre_label through the real D-A40 marker open, exactly as the evaluator does right before the label read."""
    marker_dir.mkdir(exist_ok=True)
    marker_class = d40.make_marker_class(d40.pre_label)
    marker = marker_class(str(marker_dir / d40.D40_MARKER_NAME))
    return marker.open("x")


def label_item():
    return {"kind": "label", "path": "/synthetic/labels-not-present.json", "sha256": d40.LABELS_SHA}


def expect(error_type, fragment, fn, *args):
    try:
        fn(*args)
    except error_type as error:
        assert fragment in str(error), (fragment, str(error))
        return error
    raise AssertionError(f"expected {error_type.__name__} containing {fragment!r}")


def assert_no_label_possible(records):
    assert not (records / d40.D40_MARKER_NAME).exists(), "the marker must not be written"
    assert d40.STATE["marker_written"] is False and not d40.STATE.get("pre_label_passed")
    consumed = []
    guarded = d40.make_guarded_consume(lambda item, purpose, **kw: consumed.append(item) or "never")
    try:
        guarded(label_item(), "synthetic label read")
    except (ValueError, d40.LabelGuard):
        pass
    else:
        raise AssertionError("the guarded consume allowed a label read after a rejected pre-label check")
    assert consumed == []


# ------------------------------------------------------------------------ binding, both modes


def test_binding_success_dry_and_open_equal_to_d39():
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw).resolve()
        with fixture(tmp) as ckpt:
            stages, binding = simulate_d39_binding(ckpt, tmp)
            assert len(stages) == sum(d40.EXPECTED_CALLS.values()) == 9
            assert {s["source"] for s in stages} == {"checkpoint-attempt12", "checkpoint-rolling"}     # nothing computed
            assert sorted(s["stage"] for s in stages if s["source"] == "checkpoint-rolling") == ["baseline", "origin"]
            records = tmp / "records-dry"
            reset_state("dry-run", records)
            run_all_stages(ckpt)
            expect(d40.DryRunReady, "", pre_label_open, records)
            assert d40.STATE["pre_label_passed"] is True and d40.STATE["marker_written"] is False
            assert not (records / d40.D40_MARKER_NAME).exists()
            assert d40.STATE["binding"]["sha256"] == binding == d40.D39_CHECKPOINT_BINDING_SHA
            assert d40.STATE["decision_check"]["stable"]["arms_checked"] == 1
            assert d40.STATE["empty_forecast_check"]["paired"] is True
            assert ns.EXPECTED == {"stable-neural-d30-s0": frozenset({"e2", "e3", "e4"}),
                                   "stable-persistence-d30": frozenset({"e2", "e3", "e4"})}
            with approved_against(stages, tmp) as (_approval, approval_ref):
                assert approval_ref["checkpoint_binding_sha256"] == binding
            records = tmp / "records-open"
            reset_state("open", records)
            run_all_stages(ckpt)
            d40.STATE.update(approved_binding={"sha256": binding, "items": d40.binding_of(stages)[0]}, approval_ok=True)
            pre_label_open(records).close()
            assert d40.STATE["pre_label_passed"] is True and d40.STATE["marker_written"] is True
            assert (records / d40.D40_MARKER_NAME).is_file()


def test_binding_other_than_d39_refused_in_both_modes_before_label():
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw).resolve()
        with fixture(tmp) as ckpt:
            stages, binding = simulate_d39_binding(ckpt, tmp)
            d40.D39_CHECKPOINT_BINDING_SHA = "0" * 64
            for mode in ("dry-run", "open"):
                records = tmp / f"records-{mode}"
                reset_state(mode, records)
                run_all_stages(ckpt)
                d40.STATE.update(approved_binding={"sha256": binding, "items": d40.binding_of(stages)[0]}, approval_ok=True)
                expect(ValueError, "differ from the binding D-A39 was approved on", pre_label_open, records)
                assert_no_label_possible(records)


def test_cache_miss_refused_in_both_modes_before_compute_or_save():
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw).resolve()
        with fixture(tmp) as ckpt:
            for path in ckpt.glob("origin-*"):                          # D-A39's origin preparation is gone
                path.unlink()
            calls, saves = [], []
            original_save = d40.save_rolling
            d40.save_rolling = lambda *a, **k: (saves.append(1), {"status": "save-failed", "error": "spy"})[1]
            try:
                for mode in ("dry-run", "open"):
                    reset_state(mode, tmp / "records")
                    expect(ValueError, "D-A40 refuses to compute stage origin", run_stage, "origin", None, ckpt,
                           lambda: calls.append(mode))
            finally:
                d40.save_rolling = original_save
            assert calls == [] and saves == [], "the preparation function and the saver must never be called"
            assert not list(ckpt.glob("origin-*")), "the refusal must not leave a checkpoint behind"


def test_modified_legacy_bytes_same_size_rejected_before_label():
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw).resolve()
        with fixture(tmp) as ckpt:
            stages, binding = simulate_d39_binding(ckpt, tmp)
            items, _ = d40.binding_of(stages)
            victim = next(p for p in ckpt.glob("members-*.pkl") if b"a" * 128 in p.read_bytes())
            blob = victim.read_bytes()
            at = blob.index(b"a" * 128)
            tampered = blob[:at] + b"b" * 128 + blob[at + 128:]
            assert len(tampered) == len(blob) and tampered != blob
            victim.write_bytes(tampered)
            decoder = pickle.Unpickler(io.BytesIO(tampered))          # it still loads: header intact, only the payload bytes moved
            decoder.load()
            assert isinstance(decoder.load(), dict)
            for mode in ("dry-run", "open"):
                records = tmp / f"records-{mode}"
                reset_state(mode, records)
                run_all_stages(ckpt)                   # loads pass (size and header checks): the bytes differ only by digest
                d40.STATE.update(approved_binding={"sha256": binding, "items": items}, approval_ok=True)
                expect(ValueError, "differ from the binding D-A39 was approved on", pre_label_open, records)
                assert_no_label_possible(records)


def test_missing_and_duplicated_stage_rejected_before_label():
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw).resolve()
        with fixture(tmp) as ckpt:
            stages, binding = simulate_d39_binding(ckpt, tmp)
            items, _ = d40.binding_of(stages)
            records = tmp / "records"
            reset_state("open", records)                               # missing stage: only four membership families prepared
            for name, arg, _payload in [*ROLLING_SPECS, *LEGACY_SPECS]:
                run_stage(name, arg, ckpt)
            for arg in MEMBER_ARGS[:4]:
                run_stage("members", arg, ckpt)
            run_stage("stable", 13, ckpt)
            d40.STATE.update(approved_binding={"sha256": binding, "items": items}, approval_ok=True)
            expect(ValueError, "must have run exactly as expected", pre_label_open, records)
            assert_no_label_possible(records)
            records2 = tmp / "records2"                                 # duplicated stage: five calls, four distinct fingerprints
            reset_state("open", records2)
            for name, arg, _payload in [*ROLLING_SPECS, *LEGACY_SPECS]:
                run_stage(name, arg, ckpt)
            for arg in (MEMBER_ARGS[0], MEMBER_ARGS[0], *MEMBER_ARGS[1:4]):
                run_stage("members", arg, ckpt)
            run_stage("stable", 13, ckpt)
            d40.STATE.update(approved_binding={"sha256": binding, "items": items}, approval_ok=True)
            try:
                pre_label_open(records2)
                raise AssertionError("a duplicated membership fingerprint passed pre_label")
            except ValueError as error:
                assert "distinct fingerprints" in str(error) or "differ from the" in str(error)
            assert_no_label_possible(records2)


def test_nonfinal_membership_source_receipts_and_shadow_refused():
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw).resolve()
        with fixture(tmp) as ckpt:
            stages, _binding = simulate_d39_binding(ckpt, tmp)
            for position in (0, 3):                                      # first and middle membership receipts, final stays legacy
                broken = json.loads(json.dumps(stages))
                [s for s in broken if s["stage"] == "members"][position]["source"] = "checkpoint-rolling"
                expect(ValueError, "attempt-12 checkpoint", d40.binding_of, broken)
            reset_state("open", tmp / "records")
            run_all_stages(ckpt)
            first_member = next(i for i, s in enumerate(d40.STATE["stages"]) if s["stage"] == "members")
            d40.STATE["stages"][first_member]["source"] = "checkpoint-rolling"
            expect(ValueError, "attempt-12 checkpoints not all used", pre_label_open, tmp / "records")
            reset_state("dry-run", tmp / "records")                      # a rolling manifest planted over a membership checkpoint
            fp = fingerprint("members", MEMBER_ARGS[1])
            (ckpt / f"members-{fp[:24]}.manifest.json").write_text(json.dumps({"fingerprint": fp, "stage": "members", "parts": 999999999}))
            before = len(d40.STATE["stages"])
            expect(ValueError, "shadow the attempt-12 checkpoint", run_stage, "members", MEMBER_ARGS[1], ckpt)
            assert len(d40.STATE["stages"]) == before, "the shadow refusal must happen before any load"


# ------------------------------------------------------------------------ stable pre-checks before the label


def test_unpaired_empty_forecasts_refused_before_label():
    events = cells_kit.EVENTS + [("e7", "available", [], [12, 13], [0.1, 0.2], [])]
    unpaired = {"cells": {"n": cells_kit.neural_cell(events),
                          "k": cells_kit.baseline_cell(events, "history-knn-mean", "stable-knn-d30", extra={"e7": [12]})},
                "evidence": {"input_only": True}, "available": {"30": ["e1", "e5", "e6", "e7"]}}
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw).resolve()
        with fixture(tmp, stable=unpaired) as ckpt:
            simulate_d39_binding(ckpt, tmp)
            for mode in ("dry-run", "open"):
                records = tmp / f"records-{mode}"
                reset_state(mode, records)
                stages = run_all_stages(ckpt)
                d40.STATE.update(approved_binding={"sha256": d40.D39_CHECKPOINT_BINDING_SHA, "items": d40.binding_of(stages)[0]},
                                 approval_ok=True)
                expect(ValueError, "stable empty-forecast pre-check failed", pre_label_open, records)
                assert_no_label_possible(records)
                assert ns.EXPECTED == {}, "nothing may be frozen from a failed pre-check"


def test_float64_decision_mismatch_refused_before_label():
    mismatched = copy.deepcopy(STABLE_PREPARED)
    row = next(p for p in mismatched["cells"]["n"]["predictions"] if p["event_id"] == "e1")
    row["predicted_asns"] = [1]                                          # p(2)=0.8 >= 0.5 but 2 is not committed
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw).resolve()
        with fixture(tmp, stable=mismatched) as ckpt:
            simulate_d39_binding(ckpt, tmp)
            records = tmp / "records"
            reset_state("dry-run", records)
            run_all_stages(ckpt)
            expect(ValueError, "unpatched (float64) stable scoring would refuse a committed decision", pre_label_open, records)
            assert_no_label_possible(records)


def test_rule_must_be_installed_before_label():
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw).resolve()
        with fixture(tmp) as ckpt:
            simulate_d39_binding(ckpt, tmp)
            records = tmp / "records"
            reset_state("dry-run", records)
            d40.STATE["stable_modules"] = [installed_stable(), types.SimpleNamespace(persistence=lambda: 0,
                                                                                     m=types.SimpleNamespace(score_cell=lambda: 0))]
            run_all_stages(ckpt)
            expect(ValueError, "not-scorable rule is not installed", pre_label_open, records)
            assert_no_label_possible(records)


# ------------------------------------------------------------------------ the unchanged rolling readers (as in D-A39)


def test_rolling_part_and_manifest_changes_rejected():
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw).resolve()
        ckpt = tmp / "r2-ckpt"
        ckpt.mkdir()
        saved_floor = d40.SAVE_FREE_FLOOR
        d40.SAVE_FREE_FLOOR = -r2_checkpoint.PART_BYTES
        try:
            base = ckpt / "origin-abc0123"
            receipt = d40.save_rolling(r2_checkpoint, base, "origin", "ab" * 32, {"origin": "saved bytes", "pad": "z" * 5000})
            assert receipt["status"] == "saved"
            part = Path(f"{base}.part0000")
            original_bytes, changed = part.read_bytes(), bytearray(part.read_bytes())
            changed[100] ^= 0x01
            part.write_bytes(bytes(changed))
            expect(ValueError, "differ from the digests their manifest", d40.load_rolling, r2_checkpoint, base, "origin", "ab" * 32)
            part.write_bytes(original_bytes)
            info = {"stage": "origin", "fingerprint": "ab" * 32, "source": "checkpoint-rolling",
                    "checkpoint": {"format": "rolling-read", "manifest": str(base) + ".manifest.json", "artifacts": receipt["artifacts"]}}
            item_before = d40.stage_binding(info)
            manifest_raw = Path(f"{base}.manifest.json").read_text()
            Path(f"{base}.manifest.json").write_text(manifest_raw.replace('"stage": "origin"', '"stage": "onigin"', 1))
            expect(ValueError, "records stage", d40.load_rolling, r2_checkpoint, base, "origin", "ab" * 32)
            Path(f"{base}.manifest.json").write_text(manifest_raw + " ")
            _result, after = d40.load_rolling(r2_checkpoint, base, "origin", "ab" * 32)
            assert item_before != d40.stage_binding({**info, "checkpoint": after}), "a modified manifest must change the binding"
        finally:
            d40.SAVE_FREE_FLOOR = saved_floor


def test_old_format_manifest_loaded_and_derived_without_computation():
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw).resolve()
        with fixture(tmp) as ckpt:
            for path in ckpt.glob("origin-*"):                           # replace D-A39's origin with the OLDER code's format
                path.unlink()
            reset_state("dry-run", tmp / "records")
            fp = fingerprint("origin", None)
            base = ckpt / f"origin-{fp[:24]}"
            writer = r2_checkpoint._RollingWriter(base)
            pickle.dump({"origin": "older format"}, writer, protocol=5)
            parts = writer.close()
            Path(f"{base}.manifest.json").write_text(json.dumps({"fingerprint": fp, "stage": "origin", "parts": parts}))
            run_stage("origin", None, ckpt)                              # `forbidden` would raise if it were computed
            origin = d40.STATE["stages"][-1]
            assert origin["source"] == "checkpoint-rolling" and origin["checkpoint"]["manifest_attests_parts"] is False
            derived = {Path(a["path"]).name: a["sha256"] for a in origin["checkpoint"]["artifacts"]}
            part = ckpt / f"{base.name}.part0000"
            blob = bytearray(part.read_bytes())
            blob[len(blob) // 2] ^= 0x01
            part.write_bytes(bytes(blob))
            _result, after = d40.load_rolling(r2_checkpoint, str(base), "origin", fp)
            assert {Path(a["path"]).name: a["sha256"] for a in after["artifacts"]} != derived
            info = {"stage": "origin", "fingerprint": fp, "source": "checkpoint-rolling"}
            assert d40.stage_binding({**info, "checkpoint": origin["checkpoint"]}) != d40.stage_binding({**info, "checkpoint": after})


def test_rolling_reader_matches_multi_part_semantics():
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw).resolve()
        ckpt = tmp / "r2-ckpt"
        ckpt.mkdir()
        saved_floor, saved_part = d40.SAVE_FREE_FLOOR, r2_checkpoint.PART_BYTES
        d40.SAVE_FREE_FLOOR, r2_checkpoint.PART_BYTES = -64 << 20, 64
        try:
            base = ckpt / "origin-many"
            result = {"payload": list(range(500)), "text": "q" * 1000}
            receipt = d40.save_rolling(r2_checkpoint, base, "origin", "cd" * 32, result)
            assert receipt["parts"] > 4, receipt["parts"]
            reread, read_receipt = d40.load_rolling(r2_checkpoint, base, "origin", "cd" * 32)
            assert reread == result and read_receipt["manifest_attests_parts"] is True
            assert pickle.load(r2_checkpoint._RollingReader(base, receipt["parts"])) == result
            assert [a["sha256"] for a in read_receipt["artifacts"][1:]] == [a["sha256"] for a in receipt["artifacts"][1:]]
        finally:
            d40.SAVE_FREE_FLOOR, r2_checkpoint.PART_BYTES = saved_floor, saved_part


def test_manifest_and_part_bounds_refused_before_reads():
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw).resolve()
        ckpt = tmp / "r2-ckpt"
        ckpt.mkdir()
        floor, part_bytes = d40.SAVE_FREE_FLOOR, r2_checkpoint.PART_BYTES
        d40.SAVE_FREE_FLOOR = -part_bytes
        try:
            base = ckpt / "origin-abc0123"
            d40.save_rolling(r2_checkpoint, base, "origin", "ab" * 32, {"pad": "z" * 500})
            manifest_path = Path(f"{base}.manifest.json")
            good = json.loads(manifest_path.read_text())
            for doc, marker in ((dict(good, stage="not-origin"), "records stage"), (dict(good, parts=10 ** 9), "from 1 to"),
                                (dict(good, parts=0), "from 1 to"), (dict(good, parts="3"), "from 1 to")):
                manifest_path.write_text(json.dumps(doc))
                expect(ValueError, marker, d40.load_rolling, r2_checkpoint, base, "origin", "ab" * 32)
            manifest_path.write_text("[" + " " * (d40.MANIFEST_MAX_BYTES + 16))
            expect(ValueError, "manifest ceiling", d40.load_rolling, r2_checkpoint, base, "origin", "ab" * 32)
            manifest_path.write_text(json.dumps(good))
            r2_checkpoint.PART_BYTES = 64
            expect(ValueError, "exceeds the admitted part size", d40.load_rolling, r2_checkpoint, base, "origin", "ab" * 32)
            r2_checkpoint.PART_BYTES = part_bytes
            result, receipt = d40.load_rolling(r2_checkpoint, base, "origin", "ab" * 32)
            assert result == {"pad": "z" * 500} and receipt["manifest_attests_parts"] is True
        finally:
            d40.SAVE_FREE_FLOOR, r2_checkpoint.PART_BYTES = floor, part_bytes


def test_receipt_paths_and_rolling_structure_are_bound():
    info = {"stage": "origin", "fingerprint": "ab" * 32, "source": "checkpoint-rolling",
            "checkpoint": {"format": "rolling-read", "manifest": "/one/origin.manifest.json",
                           "artifacts": [{"path": "/one/origin.manifest.json", "bytes": 10, "sha256": "0" * 64},
                                         {"path": "/one/origin.part0000", "bytes": 20, "sha256": "1" * 64}]}}
    moved = json.loads(json.dumps(info).replace("/one/", "/two/"))
    assert d40.stage_binding(info) != d40.stage_binding(moved), "directories must be bound, not only basenames"
    for mutate, marker in ((lambda c: c["artifacts"].append(dict(c["artifacts"][1])), "duplicate artifact path"),
                           (lambda c: c["artifacts"][1].update(path="/one/origin.part0001"), "contiguous parts"),
                           (lambda c: c["artifacts"][1].update(path="one/origin.part0000"), "non-canonical absolute path"),
                           (lambda c: c.update(format="attempt12-single-pkl"), "exactly one .pkl")):
        broken = json.loads(json.dumps(info))
        mutate(broken["checkpoint"])
        expect(ValueError, marker, d40.stage_binding, broken)
    expect(ValueError, "does not bind the bytes", d40.stage_binding, {k: v for k, v in info.items() if k != "checkpoint"})


# ------------------------------------------------------------------------ label guard, marker chain, execute preflight


def test_guarded_label_consume_gate():
    consumed = []
    guarded = d40.make_guarded_consume(lambda item, purpose, **kw: consumed.append(item["kind"]) or "read")
    guarded({"kind": "metadata", "path": "/synthetic/data", "sha256": "2" * 64}, "non-label stays untouched")
    assert consumed == ["metadata"]
    saved = dict(d40.STATE)
    try:
        d40.STATE.update(mode="dry-run", marker_written=False, pre_label_passed=False)
        expect(d40.LabelGuard, "D-A40 dry run", guarded, label_item(), "dry-run label read")
        d40.STATE.update(mode="open")
        for written, passed in ((False, False), (True, False), (False, True)):
            d40.STATE.update(marker_written=written, pre_label_passed=passed)
            expect(ValueError, "label read before the D-A40 marker", guarded, label_item(), "label read before the gate opened")
        d40.STATE.update(marker_written=True, pre_label_passed=True)
        assert guarded(label_item(), "the approved read") == "read"
        assert consumed == ["metadata", "label"]
    finally:
        d40.STATE.clear()
        d40.STATE.update(saved)


class MarkerReader:
    """Stands in for the runner's Reader behind BoundPath.read_bytes: inventory-only, sha256-checked, every read recorded."""

    def __init__(self, inventory):
        self.inventory, self.reads = dict(inventory), []

    def consume(self, path):
        assert path in self.inventory, f"read outside the inventory: {path}"
        raw = Path(path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != self.inventory[path]:
            raise ValueError("Source hash differs")
        self.reads.append(path)
        return raw


@contextlib.contextmanager
def marker_world(tmp, attempt12=True, d39=True, d39_fields=None, extra_unblinded=False, extra_label_read=False, pin_drift=False):
    saved = {k: getattr(d40, k) for k in ("MARKER", "D39_TARGET", "D39_MARKER", "D39_MARKER_OUT", "PRIMARY")}
    saved_state = dict(d40.STATE)
    amend, second, records = tmp / "amend", tmp / "arms" / "rescore-secondary-D-A39", tmp / "arms" / "rescore-stable-D-A40"
    for directory in (amend, second, records):
        directory.mkdir(parents=True)
    d40.PRIMARY = {"path": str(tmp / "attempt" / "primary.json"), "sha256": "9" * 64, "size_bytes": 1}
    d40.D39_TARGET, d40.D39_MARKER_OUT = str(second), str(second / "primary-recomputed-D-A39.json")
    first_path, second_path = amend / f"unblinded-{d40.SEAL_SHA}.json", second / "second-label-read-D-A39.json"
    first_doc = {"unblinded_utc": "2026-10-30T06:00:00Z", "seal_sha256": d40.SEAL_SHA, "labels_sha256": d40.LABELS_SHA,
                 "custody_spec_sha256": d40.FREEZE_SHA, "out": d40.PRIMARY["path"]}
    second_doc = {"unblinded_utc": "2026-10-31T08:45:51Z", "seal_sha256": d40.SEAL_SHA, "labels_sha256": d40.LABELS_SHA,
                  "custody_spec_sha256": d40.FREEZE_SHA, "out": d40.D39_MARKER_OUT, **(d39_fields or {})}
    inventory = {}
    for path, doc, present in ((first_path, first_doc, attempt12), (second_path, second_doc, d39)):
        raw = json.dumps(doc, indent=2).encode()
        inventory[str(path)] = hashlib.sha256(raw).hexdigest()
        if present:
            path.write_bytes(raw)
    if pin_drift:
        second_path.write_bytes(second_path.read_bytes() + b" ")             # same fields, different bytes than pinned
    if extra_unblinded:
        (amend / f"unblinded-{'f' * 64}.json").write_text("{}")
    if extra_label_read:
        (second / "third-label-read-D-A40.json").write_text("{}")
    d40.MARKER = {"path": str(first_path), "sha256": inventory[str(first_path)], "size_bytes": 0}
    d40.D39_MARKER = {"path": str(second_path), "sha256": inventory[str(second_path)], "size_bytes": 0}
    reader = MarkerReader(inventory)

    class BoundPath(type(Path())):
        def read_bytes(self):
            return reader.consume(str(self))

    private = types.SimpleNamespace(UNBLINDED_PREFIX="unblinded-",
                                    _marker_for=lambda seal, sha: BoundPath(seal["spec_path"]).parent / f"unblinded-{sha}.json")
    d40.STATE["records"] = str(records)
    refuse = d40.make_refuse(private, d40.make_marker_class(lambda marker: None))
    try:
        yield (lambda: refuse({"spec_path": str(amend / "freeze.json")}, d40.SEAL_SHA)), reader, (first_path, second_path, records)
    finally:
        for key, value in saved.items():
            setattr(d40, key, value)
        d40.STATE.clear()
        d40.STATE.update(saved_state)


def test_marker_chain_requires_attempt12_and_d39_markers_through_the_reader():
    with tempfile.TemporaryDirectory() as raw:
        with marker_world(Path(raw).resolve() / "ok") as (refuse, reader, (first, second, records)):
            marker = refuse()
            assert str(marker) == str(records / "third-label-read-D-A40.json") and type(marker).__name__ == "D40Marker"
            assert reader.reads == [str(first), str(second)]                  # both markers read through the Reader, in order
            assert d40.STATE["d39_marker_record"]["out"].endswith("primary-recomputed-D-A39.json")
            assert not marker.exists()                                         # refuse returns the path; the evaluator writes it
        cases = [(dict(attempt12=False), "exactly the attempt-12 one-opening marker"),
                 (dict(extra_unblinded=True), "exactly the attempt-12 one-opening marker"),
                 (dict(d39=False), "exactly the D-A39 second-label-read marker"),
                 (dict(extra_label_read=True), "exactly the D-A39 second-label-read marker"),
                 (dict(d39_fields={"labels_sha256": "0" * 64}), "D-A39 marker content differs"),
                 (dict(d39_fields={"custody_spec_sha256": "0" * 64}), "D-A39 marker content differs"),
                 (dict(d39_fields={"out": "/elsewhere/primary-recomputed-D-A39.json"}), "D-A39 marker content differs"),
                 (dict(pin_drift=True), "Source hash differs")]
        for i, (kwargs, fragment) in enumerate(cases):
            with marker_world(Path(raw).resolve() / f"case{i}", **kwargs) as (refuse, reader, (_f, _s, records)):
                expect(ValueError, fragment, refuse)
                assert not (records / d40.D40_MARKER_NAME).exists()


def test_execute_preflight_refusals_before_records():
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw).resolve()
        saved = {k: getattr(d40, k) for k in ("ARMS", "TARGET", "D39_MARKER")}
        saved_state = dict(d40.STATE)
        try:
            arms = tmp / "arms"
            (arms / "rescore-secondary-D-A39").mkdir(parents=True)
            marker = arms / "rescore-secondary-D-A39" / "second-label-read-D-A39.json"
            marker.write_text("x" * 7)
            d40.ARMS, d40.TARGET = str(arms), str(arms / "rescore-stable-D-A40")
            d40.D39_MARKER = {"path": str(marker), "sha256": "0" * 64, "size_bytes": 7}
            run = tmp / "run"
            run.mkdir()
            d40.STATE.update(mode="dry-run", run_dir=str(run))
            records = run / "records-dry-run"
            plan = {"records": str(records), "primary_output": str(records / "primary-recomputed-D-A40.json"),
                    "result_output": str(records / "stable-result.json"), "primary_scores_output": str(records / "primary-scores.json"),
                    "labels": {"sha256": d40.LABELS_SHA}, "seal": {"sha256": d40.SEAL_SHA},
                    "freeze": {"path": str(tmp / "freeze.json"), "sha256": d40.FREEZE_SHA}, "access_log": str(tmp / "log.jsonl"),
                    "bounds": {"output_file_bytes": 10, "output_total_bytes": 100, "access_log_bytes": 1}}
            other = arms / "rescore-other"
            other.mkdir()
            expect(ValueError, "re-scoring directories must be exactly", d40.d40_execute, None, plan, None, None, None)
            other.rmdir()
            Path(d40.TARGET).mkdir()
            expect(ValueError, "D-A40 re-scoring records already exist", d40.d40_execute, None, plan, None, None, None)
            Path(d40.TARGET).rmdir()
            marker.write_text("x" * 8)
            expect(ValueError, "D-A39 second-label-read marker must exist", d40.d40_execute, None, plan, None, None, None)
            marker.unlink()
            expect(ValueError, "D-A39 second-label-read marker must exist", d40.d40_execute, None, plan, None, None, None)
            wrong = dict(plan, result_output=str(records / "secondary-result.json"))
            expect(ValueError, "fixed D-A40 output artifacts", d40.d40_execute, None, wrong, None, None, None)
            assert not records.exists(), "no refusal may create the records directory"
        finally:
            for key, value in saved.items():
                setattr(d40, key, value)
            d40.STATE.clear()
            d40.STATE.update(saved_state)


# ------------------------------------------------------------------------ approval binding


def test_approval_binding():
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw).resolve()
        with fixture(tmp) as ckpt:
            stages, binding = simulate_d39_binding(ckpt, tmp)
            with approved_against(stages, tmp) as (approval, approval_ref):        # control: accepted
                assert approval["deviation"] == "D-A40" and approval_ref["checkpoint_binding_sha256"] == binding
                assert d40.STATE["approved_binding"]["sha256"] == binding
            approval_cases = [
                (lambda a: a.update(deviation="D-A39"), "approval field deviation"),
                (lambda a: a.update(third_label_read_authorized=False), "approval field third_label_read_authorized"),
                (lambda a: a.pop("third_label_read_authorized"), "approval field third_label_read_authorized"),
                (lambda a: a.update(scope="secondary lanes only"), "approval field scope"),
                (lambda a: a.update(records=d40.TARGET.replace("D-A40", "D-A39")), "approval field records"),
                (lambda a: a.update(labels_sha256="0" * 64), "approval field labels_sha256"),
                (lambda a: a.update(primary_json_sha256="0" * 64), "approval field primary_json_sha256"),
                (lambda a: a.update(approved_by="two words"), "approved_by"),
                (lambda a: a["dry_run_ready"].update(sha256="0" * 64), "bind the dry run's ready.json by sha256"),
            ]
            for tamper, fragment in approval_cases:
                try:
                    with approved_against(stages, tmp, approval_tamper=tamper):
                        raise AssertionError(f"verify_approval accepted: {fragment}")
                except ValueError as error:
                    assert fragment in str(error), (fragment, str(error))
            unpaired = ns.check_prepared([{"cells": {"a": cells_kit.neural_cell(cells_kit.EVENTS),
                                                     "b": dict(cells_kit.neural_cell(cells_kit.EVENTS[:1] + cells_kit.EVENTS[2:]),
                                                               arm_id="other")}}])
            ready_cases = [
                (lambda r: r.update(kind="D-A39_secondary_rescore_dry_run_v1"), "dry-run ready record"),
                (lambda r: r.update(target_records=d40.TARGET + "-other"), "dry-run ready record"),
                (lambda r: r.update(d40_marker_written=True), "dry-run ready record"),
                (lambda r: r["scope"].update(scored=["stable", "counts"]), "scope differs"),
                (lambda r: r["not_scorable"]["module"].update(sha256="0" * 64), "not-scorable patch changed"),
                (lambda r: r["not_scorable"].update(rule="another rule"), "not-scorable patch changed"),
                (lambda r: r["float32_scoring"]["module"].update(sha256="0" * 64), "float32 decision check changed"),
                (lambda r: r["parallel_scoring"]["module"].update(sha256="0" * 64), "parallel scoring adapter changed"),
                (lambda r: r["parallel_scoring"].update(options={"max_workers": 16, "min_parallel_rows": 8192,
                                                                 "chunks_per_worker": 4}), "parallel scoring options differ"),
                (lambda r: r["code"].pop("r2_stable_not_scorable.py"), "chain code changed"),
                (lambda r: r["code"]["r2_exec.py"].update(sha256="0" * 64), "chain code changed"),
                (lambda r: r["d39_marker"].update(record=None), "did not read the d39_marker"),
                (lambda r: r["d39_marker"].update(sha256="0" * 64), "did not read the d39_marker"),
                (lambda r: r["attempt12_marker"]["record"].update(labels_sha256="0" * 64), "did not read the attempt12_marker"),
                (lambda r: r.update(empty_forecast_check=unpaired), "empty-forecast pre-check did not pass"),
                (lambda r: r["checkpoint_binding"].update(sha256="0" * 64), "differs from its own stage records"),
            ]
            for tamper, fragment in ready_cases:
                try:
                    with approved_against(stages, tmp, tamper=tamper):
                        raise AssertionError(f"verify_approval accepted a tampered ready.json: {fragment}")
                except ValueError as error:
                    assert fragment in str(error), (fragment, str(error))
            d40.D39_CHECKPOINT_BINDING_SHA = "0" * 64                              # a dry run on other bytes than D-A39's
            try:
                with approved_against(stages, tmp):
                    raise AssertionError("verify_approval accepted a binding other than D-A39's")
            except ValueError as error:
                assert "differs from the one D-A39 was approved on" in str(error)


if __name__ == "__main__":
    names = sorted(name for name in globals() if name.startswith("test_"))
    failures = 0
    for name in names:
        try:
            globals()[name]()
            print(f"PASS {name}", flush=True)
        except Exception:
            failures += 1
            print(f"FAIL {name}", flush=True)
            traceback.print_exc()
    print(f"{len(names) - failures}/{len(names)} tests passed")
    raise SystemExit(1 if failures else 0)
