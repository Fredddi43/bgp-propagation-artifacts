#!/usr/bin/env python3
"""D-A39 follow-up: tiny synthetic tests for the checkpoint byte binding of r2_rescore_secondary.py.

Everything here is local and label-free: synthetic pickles in temp directories, no <CLUSTER_STORAGE> path is read or written, no label table
exists anywhere near these tests, and r2_checkpoint.py is only read (never written). Coverage: binding success (write-time capture,
read-time derivation, dry-run ready accepted by verify_approval, open run passes pre_label); modified legacy bytes of unchanged
size; rolling part and manifest modification in both manifest formats; a checkpoint saved by the older code accepted and derived
without recomputation; missing stage; duplicated membership stage; and that every rejection happens BEFORE any label could open
(the D-A39 marker is never written, pre_label never passes, and the guarded label consume refuses). Round-1 review probes: the
open-mode cache miss is refused before the preparation function or saver runs; every attempt-12 receipt (never collapsed by name)
and a rolling shadow are refused before loading; manifests are size-bounded and must name the stage with a finite bounded part
structure of regular in-ceiling files; receipts bind canonical absolute paths and the full rolling artifact structure.

Run: python3 test_r2_rescore_binding.py
"""
import contextlib
import copy
import io
import json
import pickle
import sys
import tempfile
import traceback
import types
from pathlib import Path

CHAIN = Path(__file__).resolve().parent
sys.path.insert(0, str(CHAIN))

import r2_checkpoint                      # the pinned checkpoint module (read-only here)
import r2_float32_scoring as real_float32
import r2_rescore_secondary as d39        # the driver under test (this copy)

LEGACY_SPECS = [("baseline", 11, {"lane": "baseline", "pad": "a" * 4096}),
                ("counts", 12, {"lane": "counts", "pad": "b" * 256}),
                ("stable", 13, {"lane": "stable", "pad": "c" * 2048})]
MEMBER_ARGS = (1, 2, 3, 4, 5)


def make_legacy_file(ckpt_dir, name, arg, payload):
    fp = r2_checkpoint._digest({"stage": name, "code": r2_checkpoint.code_fingerprint(stage=name),
                                "args": [] if arg is None else [arg], "kwargs": {}})
    blob = pickle.dumps({"fingerprint": fp, "stage": name}) + pickle.dumps(payload, protocol=5)
    path = ckpt_dir / f"{name}-{fp[:24]}.pkl"
    path.write_bytes(blob)
    return path, fp


@contextlib.contextmanager
def fixture(tmp):
    """Synthetic attempt-12 checkpoint files + the driver's view of them (LEGACY, save floor), restored afterwards."""
    saved = (d39.LEGACY, d39.SAVE_FREE_FLOOR, dict(d39.STATE))
    ckpt = tmp / "r2-ckpt"
    ckpt.mkdir(parents=True)
    legacy = {}
    for name, arg, payload in LEGACY_SPECS:
        path, _ = make_legacy_file(ckpt, name, arg, payload)
        legacy.setdefault(name, {})[path.name] = path.stat().st_size
    for arg in MEMBER_ARGS:
        path, _ = make_legacy_file(ckpt, "members", arg, {"family": f"fam{arg}", "pad": "a" * 4096})
        legacy.setdefault("members", {})[path.name] = path.stat().st_size
    d39.LEGACY = {k: legacy[k] for k in ("baseline", "counts", "members", "stable")}
    d39.SAVE_FREE_FLOOR = -r2_checkpoint.PART_BYTES   # the free-space guard is orthogonal here: make it always pass
    d39.install_checkpoint_wrap()
    try:
        yield ckpt
    finally:
        d39.LEGACY, d39.SAVE_FREE_FLOOR = saved[0], saved[1]
        d39.STATE.clear()
        d39.STATE.update(saved[2])


def reset_state(mode, records):
    d39.STATE.update(mode=mode, stages=[], families=[], float32_installs=0, refuse_installs=0, d39_marker_written=False,
                     pre_label_passed=False, binding=None, approved_binding=None,
                     registry={k: [] for k in d39.EXPECTED_CALLS}, records=str(records))


def forbidden(_arg=None):
    raise AssertionError("stage recomputed instead of loading its checkpoint")


def origin_ready():
    return {"origin": "prepared in the dry run", "pad": "o" * 1024}


def run_stage(name, arg, ckpt, function=None):
    return r2_checkpoint.wrap(function or forbidden, name, str(ckpt), None)(*(() if arg is None else (arg,)))


def run_all_stages(ckpt):
    for name, arg, _payload in LEGACY_SPECS:
        run_stage(name, arg, ckpt)
    for arg in MEMBER_ARGS:
        run_stage("members", arg, ckpt)
    run_stage("origin", None, ckpt, function=origin_ready)
    return copy.deepcopy(json.loads(json.dumps(d39.STATE["stages"])))   # the ready.json view of the stages


def rolling_base_of(stage_info):
    manifest = str(stage_info["checkpoint"]["manifest"])
    return manifest[: -len(".manifest.json")]


def stub_float32_check():
    """Replace only check_prepared (it needs real sealed cells): the binding, gates and marker under test stay real code."""
    ok = {"arms_checked": 1, "rows_checked": 1, "float64_mismatch_rows": 0, "float32_mismatch_rows": 0}
    stub = types.ModuleType("r2_float32_scoring")
    stub.__file__, stub.MARK, stub.OLD, stub.NEW = real_float32.__file__, real_float32.MARK, real_float32.OLD, real_float32.NEW
    stub.patch = real_float32.patch
    stub.check_prepared = lambda members, origin, stable: {k: dict(ok) for k in ("members", "origin", "stable")}
    sys.modules["r2_float32_scoring"] = stub
    d39.STATE["membership_modules"] = [types.SimpleNamespace(scoring=types.SimpleNamespace(**{real_float32.MARK: True}))]


@contextlib.contextmanager
def approved_against(stages, tmp, tamper=None):
    """A synthetic dry-run ready.json + approval file accepted by the driver's own verify_approval (the real function)."""
    stages = copy.deepcopy(stages)      # tampering must not touch the caller's stage records
    items, binding = d39.binding_of(stages)
    ready = {"kind": "D-A39_secondary_rescore_dry_run_v1", "status": "ready, labels not opened", "labels_opened": False,
             "target_records": d39.TARGET, "reader": {"label_reads": 0},
             "driver": d39.ref(Path(d39.__file__)),
             "float32_scoring": {"module": d39.ref(CHAIN / "r2_float32_scoring.py")},
             "parallel_scoring": {"module": d39.ref(CHAIN / "r2_parallel_scoring.py"), "options": dict(d39.PARALLEL_ADAPTER_OPTIONS),
                                  "hard_cap": 8, "installs": []},
             "code": {"r2_checkpoint.py": d39.ref(CHAIN / "r2_checkpoint.py")},
             "checkpoint_binding": {"sha256": binding, "items": items}, "stages": stages}
    if tamper == "strip-bindings":            # a ready.json as the OLDER driver wrote it: no checkpoint receipts at all
        for stage in ready["stages"]:
            stage.pop("checkpoint", None)
        ready.pop("checkpoint_binding")
    if tamper == "misreport-binding":
        ready["checkpoint_binding"]["sha256"] = "0" * 64
    if tamper == "stale-adapter":           # the parallel scoring adapter file changed after the dry run
        ready["parallel_scoring"]["module"]["sha256"] = "0" * 64
    if tamper == "wrong-options":           # the fixed adapter options differ from the recorded ones
        ready["parallel_scoring"]["options"] = {"max_workers": 16, "min_parallel_rows": 8192, "chunks_per_worker": 4}
    if tamper == "no-adapter-binding":      # a ready.json written before the adapter existed is not acceptable
        ready.pop("parallel_scoring")
    ready_path = tmp / "ready.json"
    ready_path.write_text(json.dumps(ready))
    approval = {**d39.APPROVAL_FIELDS, "approved_by": "synthetic-test-owner", "approval_record": "unit test fixture",
                "dry_run_ready": {"path": str(ready_path), "sha256": d39.sha_file(ready_path)}}
    approval_path = tmp / "approval.json"
    approval_path.write_text(json.dumps(approval))
    yield d39.verify_approval(approval_path)


def pre_label_open(marker_dir):
    """Drive the real pre_label through the real D-A39 marker open, exactly as the evaluator does right before the label read."""
    marker_dir.mkdir(exist_ok=True)
    marker_class = d39.make_marker_class(d39.pre_label)
    marker = marker_class(str(marker_dir / "second-label-read-D-A39.json"))
    return marker.open("x")


def label_item():
    return {"kind": "label", "path": "/synthetic/labels-not-present.json", "sha256": d39.LABELS_SHA}


# ------------------------------------------------------------------------ tests


def test_binding_success_write_and_read():
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw).resolve()
        with fixture(tmp) as ckpt:
            reset_state("dry-run", tmp / "records")
            stages = run_all_stages(ckpt)
            items, binding = d39.binding_of(stages)
            assert len(items) == sum(d39.EXPECTED_CALLS.values()) == 9, items
            origin = [s for s in stages if s["stage"] == "origin"][0]
            assert origin["source"] == "computed" and origin["checkpoint"]["format"] == "rolling-saved"
            names = {Path(a["path"]).name for a in origin["checkpoint"]["artifacts"]}
            assert any(n.endswith(".manifest.json") for n in names) and len(names) == 2   # manifest + one part
            assert all(a["sha256"] and a["bytes"] > 0 for a in origin["checkpoint"]["artifacts"])
            # write-time digests are self-consistent: the manifest records them and re-reading derives exactly the same digests
            base = rolling_base_of(origin)
            reread, receipt = d39.load_rolling(r2_checkpoint, base, "origin", origin["fingerprint"])
            assert receipt["manifest_attests_parts"] is True
            assert sorted(a["sha256"] for a in receipt["artifacts"]) == sorted(a["sha256"] for a in origin["checkpoint"]["artifacts"])
            assert reread == origin_ready()
            # format compatibility: r2_checkpoint's OWN _RollingReader loads the driver-written parts
            info = json.loads(Path(f"{base}.manifest.json").read_text())
            assert info["fingerprint"] == origin["fingerprint"] and isinstance(info["parts"], int)
            assert pickle.load(r2_checkpoint._RollingReader(base, info["parts"])) == origin_ready()
            # and the approval + pre_label of a fresh open run accept the same bytes
            records = tmp / "records"
            with approved_against(stages, tmp) as (approval, approval_ref):
                assert approval_ref["checkpoint_binding_sha256"] == binding
                assert d39.STATE["approved_binding"]["sha256"] == binding
            reset_state("open", records)
            run_all_stages(ckpt)
            stub_float32_check()
            d39.STATE["approved_binding"] = {"sha256": binding, "items": items}
            d39.STATE["approval_ok"] = True
            try:
                stream = pre_label_open(records)
                stream.close()
            finally:
                sys.modules["r2_float32_scoring"] = real_float32
            assert d39.STATE["pre_label_passed"] is True and d39.STATE["d39_marker_written"] is True
            assert (records / "second-label-read-D-A39.json").is_file()   # marker open succeeded: bindings matched exactly


def test_modified_legacy_bytes_same_size_rejected_before_label():
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw).resolve()
        with fixture(tmp) as ckpt:
            reset_state("dry-run", tmp / "records")
            stages = run_all_stages(ckpt)
            with approved_against(stages, tmp) as (_approval, approval_ref):
                pass
            items, binding = d39.binding_of(stages)
            # modify one membership checkpoint's bytes: same file size, still a loadable pickle, header untouched
            victim = next(p for p in ckpt.glob("members-*.pkl") if b"a" * 128 in p.read_bytes())
            blob = victim.read_bytes()
            at = blob.index(b"a" * 128)
            tampered = blob[:at] + b"b" * 128 + blob[at + 128:]
            assert len(tampered) == len(blob) and tampered != blob
            victim.write_bytes(tampered)
            decoder = pickle.Unpickler(io.BytesIO(tampered))          # it still loads: header intact, only the payload bytes moved
            decoder.load()
            assert isinstance(decoder.load(), dict)
            records = tmp / "records"
            reset_state("open", records)
            run_all_stages(ckpt)                       # loads pass (size and header checks): the bytes differ only by digest
            d39.STATE["approved_binding"] = {"sha256": binding, "items": items}
            try:
                raised = pre_label_open(records)
            except ValueError as error:
                raised = None
            else:
                raise AssertionError("pre_label accepted legacy bytes that differ from the approved dry run")
            assert not (records / "second-label-read-D-A39.json").exists(), "the marker must not be written"
            assert d39.STATE["d39_marker_written"] is False and not d39.STATE.get("pre_label_passed")
            consumed = []
            guarded = d39.make_guarded_consume(lambda item, purpose, **kw: consumed.append(item) or "never")
            try:
                guarded(label_item(), "synthetic label read")
            except ValueError as error:
                assert "label read before the D-A39 marker" in str(error)
            else:
                raise AssertionError("the guarded consume allowed a label read after the rejected binding")
            assert consumed == []


def test_rolling_part_and_manifest_changes_rejected():
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw).resolve()
        ckpt = tmp / "r2-ckpt"
        ckpt.mkdir()
        saved_floor = d39.SAVE_FREE_FLOOR
        d39.SAVE_FREE_FLOOR = -r2_checkpoint.PART_BYTES
        try:
            base = ckpt / "origin-abc0123"
            result = {"origin": "saved bytes", "pad": "z" * 5000}
            receipt = d39.save_rolling(r2_checkpoint, base, "origin", "ab" * 32, result)
            assert receipt["status"] == "saved"
            manifest = json.loads(Path(f"{base}.manifest.json").read_text())
            assert manifest["parts"] == receipt["parts"] == 1 and len(manifest["parts_sha256"]) == 1
            # a modified part (same size) is caught AT LOAD by the manifest's recorded digest
            part = Path(f"{base}.part0000")
            original_bytes, changed = part.read_bytes(), bytearray(part.read_bytes())
            changed[100] ^= 0x01
            part.write_bytes(bytes(changed))
            try:
                d39.load_rolling(r2_checkpoint, base, "origin", "ab" * 32)
            except ValueError as error:
                assert "differ from the digests their manifest" in str(error)
            else:
                raise AssertionError("a modified rolling part loaded against its manifest digests")
            part.write_bytes(original_bytes)
            info = {"stage": "origin", "fingerprint": "ab" * 32, "source": "checkpoint-rolling",
                    "checkpoint": {"format": "rolling-read", "manifest": str(base) + ".manifest.json", "artifacts": receipt["artifacts"]}}
            item_before = d39.stage_binding(info)
            # a manifest rewritten to record another stage is refused AT LOAD (round-1 review gap 3)
            manifest_raw = Path(f"{base}.manifest.json").read_text()
            assert '"stage": "origin"' in manifest_raw
            Path(f"{base}.manifest.json").write_text(manifest_raw.replace('"stage": "origin"', '"stage": "onigin"', 1))
            try:
                d39.load_rolling(r2_checkpoint, base, "origin", "ab" * 32)
            except ValueError as error:
                assert "records stage" in str(error)
            else:
                raise AssertionError("a manifest recording a different stage loaded")
            # a byte-level manifest rewrite that keeps the same fields still changes the manifest digest: the binding catches it
            Path(f"{base}.manifest.json").write_text(manifest_raw + " ")
            _result, after = d39.load_rolling(r2_checkpoint, base, "origin", "ab" * 32)
            item_after = d39.stage_binding({**info, "checkpoint": after})
            assert item_before != item_after, "a modified manifest must change the byte binding"
        finally:
            d39.SAVE_FREE_FLOOR = saved_floor


def test_old_format_manifest_accepted_and_derived_without_recomputation():
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw).resolve()
        with fixture(tmp) as ckpt:
            reset_state("dry-run", tmp / "records")
            # pre-save the origin checkpoint exactly as the OLDER code did: parts via _RollingWriter, manifest without part digests
            fp = r2_checkpoint._digest({"stage": "origin", "code": r2_checkpoint.code_fingerprint(stage="origin"), "args": [], "kwargs": {}})
            base = ckpt / f"origin-{fp[:24]}"
            writer = r2_checkpoint._RollingWriter(base)
            pickle.dump(origin_ready(), writer, protocol=5)
            parts = writer.close()
            Path(f"{base}.manifest.json").write_text(json.dumps({"fingerprint": fp, "stage": "origin", "parts": parts}))
            called = []
            run_stage("origin", None, ckpt, function=lambda: called.append(1) or origin_ready())
            assert called == [], "an existing rolling checkpoint must be loaded, never recomputed"
            origin = d39.STATE["stages"][-1]
            assert origin["source"] == "checkpoint-rolling" and origin["checkpoint"]["manifest_attests_parts"] is False
            derived = {Path(a["path"]).name: (a["bytes"], a["sha256"]) for a in origin["checkpoint"]["artifacts"]}
            assert len(derived) == parts + 1 and any(n.endswith(".manifest.json") for n in derived)
            # a part modified after the old dry run (same size) is caught by the binding comparison, not by the manifest
            for name in derived:
                if not name.endswith(".manifest.json"):
                    part = ckpt / name
                    blob = bytearray(part.read_bytes())
                    blob[len(blob) // 2] ^= 0x01
                    part.write_bytes(bytes(blob))
            result_after, after = d39.load_rolling(r2_checkpoint, str(base), "origin", fp)
            assert result_after.get("origin") == "prepared in the dry run"      # loads fine: the old manifest attests nothing
            derived_after = {Path(a["path"]).name: a["sha256"] for a in after["artifacts"]}
            assert any(derived_after[n] != digest for n, (_size, digest) in derived.items()), "the tampered part must change a digest"
            info = {"stage": "origin", "fingerprint": fp, "source": "checkpoint-rolling"}
            before = d39.stage_binding({**info, "checkpoint": origin["checkpoint"]})
            after_binding = d39.stage_binding({**info, "checkpoint": after})
            assert before != after_binding, "tampered old-format parts must change the byte binding the dry run approved"


def test_rolling_reader_matches_multi_part_semantics():
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw).resolve()
        ckpt = tmp / "r2-ckpt"
        ckpt.mkdir()
        saved_floor, saved_part = d39.SAVE_FREE_FLOOR, r2_checkpoint.PART_BYTES
        d39.SAVE_FREE_FLOOR, r2_checkpoint.PART_BYTES = -64 << 20, 64
        try:
            base = ckpt / "origin-many"
            result = {"payload": list(range(500)), "text": "q" * 1000}
            receipt = d39.save_rolling(r2_checkpoint, base, "origin", "cd" * 32, result)
            assert receipt["parts"] > 4, receipt["parts"]
            reread, read_receipt = d39.load_rolling(r2_checkpoint, base, "origin", "cd" * 32)
            assert reread == result and read_receipt["manifest_attests_parts"] is True
            pinned = pickle.load(r2_checkpoint._RollingReader(base, receipt["parts"]))   # the pinned reader sees identical bytes
            assert pinned == result
            assert [a["bytes"] for a in read_receipt["artifacts"][1:]] == [a["bytes"] for a in receipt["artifacts"][1:]]
            assert [a["sha256"] for a in read_receipt["artifacts"][1:]] == [a["sha256"] for a in receipt["artifacts"][1:]]
        finally:
            d39.SAVE_FREE_FLOOR, r2_checkpoint.PART_BYTES = saved_floor, saved_part


def test_missing_and_duplicated_stage_rejected_before_label():
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw).resolve()
        with fixture(tmp) as ckpt:
            reset_state("dry-run", tmp / "records")
            stages = run_all_stages(ckpt)
            with approved_against(stages, tmp):
                pass
            items, binding = d39.binding_of(stages)
            records = tmp / "records"

            # missing stage: only four membership families prepared
            reset_state("open", records)
            for name, arg, _payload in LEGACY_SPECS:
                run_stage(name, arg, ckpt)
            for arg in MEMBER_ARGS[:4]:
                run_stage("members", arg, ckpt)
            run_stage("origin", None, ckpt, function=origin_ready)
            d39.STATE["approved_binding"] = {"sha256": binding, "items": items}
            try:
                pre_label_open(records)
                raise AssertionError("a missing stage passed pre_label")
            except ValueError as error:
                assert "must have run exactly as expected" in str(error) or "differ from the expected calls" in str(error)
            assert not (records / "second-label-read-D-A39.json").exists()

            # duplicated stage: five membership calls but only four distinct fingerprints
            records2 = tmp / "records2"
            reset_state("open", records2)
            for name, arg, _payload in LEGACY_SPECS:
                run_stage(name, arg, ckpt)
            for arg in (MEMBER_ARGS[0], MEMBER_ARGS[0], *MEMBER_ARGS[1:4]):   # five calls, four distinct fingerprints
                run_stage("members", arg, ckpt)
            run_stage("origin", None, ckpt, function=origin_ready)
            d39.STATE["approved_binding"] = {"sha256": binding, "items": items}
            try:
                pre_label_open(records2)
                raise AssertionError("a duplicated membership fingerprint passed pre_label")
            except ValueError as error:
                assert "distinct fingerprints" in str(error) or "differ from the approved dry run" in str(error)
            assert not (records2 / "second-label-read-D-A39.json").exists()


def test_binding_helpers_reject_malformed_or_absent_bindings():
    stage = {"stage": "origin", "fingerprint": "ef" * 32, "source": "computed",
             "checkpoint": {"format": "rolling-saved", "manifest": "/synthetic/origin.manifest.json",
                            "artifacts": [{"path": "/synthetic/origin.manifest.json", "bytes": 10, "sha256": "0" * 64},
                                          {"path": "/synthetic/origin.part0000", "bytes": 20, "sha256": "1" * 64}]}}
    assert d39.stage_binding(stage)
    unbound = {k: v for k, v in stage.items() if k != "checkpoint"}
    try:
        d39.stage_binding(unbound)
    except ValueError as error:
        assert "does not bind the bytes" in str(error)
    else:
        raise AssertionError("a stage without checkpoint artifacts was accepted")
    for tamper in (lambda a: a[0].pop("sha256"), lambda a: a.append({"path": "/synthetic/x", "bytes": 1, "sha256": "nope"})):
        broken = copy.deepcopy(stage)
        tamper(broken["checkpoint"]["artifacts"])
        try:
            d39.stage_binding(broken)
        except ValueError:
            pass
        else:
            raise AssertionError("an incomplete artifact entry was accepted")
    assert d39.stage_binding(stage) != d39.stage_binding(copy.deepcopy(stage) | {"fingerprint": "fe" * 32})
    # the dry-run ready accepted only because every stage binds bytes: strip them and verify_approval refuses
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw).resolve()
        with fixture(tmp) as ckpt:
            reset_state("dry-run", tmp / "records")
            stages = run_all_stages(ckpt)
            try:
                with approved_against(stages, tmp, tamper="strip-bindings"):
                    raise AssertionError("verify_approval accepted an old-format ready.json without byte bindings")
            except ValueError as error:
                assert "does not bind the bytes" in str(error)
            try:
                with approved_against(stages, tmp, tamper="misreport-binding"):
                    raise AssertionError("verify_approval accepted a mismatched checkpoint_binding field")
            except ValueError as error:
                assert "differs from its own stage records" in str(error)


def test_parallel_adapter_binding_refuses_drift():
    """verify_approval must bind the adapter file hash and the fixed options from the dry-run ready record."""
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw).resolve()
        with fixture(tmp) as ckpt:
            reset_state("dry-run", tmp / "records")
            stages = run_all_stages(ckpt)
            with approved_against(stages, tmp):  # control: adapter hash + fixed options accepted
                pass
            for tamper, expected in (("stale-adapter", "parallel scoring adapter changed"),
                                     ("wrong-options", "parallel scoring options differ")):
                try:
                    with approved_against(stages, tmp, tamper=tamper):
                        raise AssertionError(f"verify_approval accepted tampered {tamper}")
                except ValueError as error:
                    assert expected in str(error), error
            try:
                with approved_against(stages, tmp, tamper="no-adapter-binding"):
                    raise AssertionError("verify_approval accepted a ready.json without the adapter binding")
            except KeyError:
                pass  # a ready record that predates the adapter is refused, not silently tolerated


def test_guarded_label_consume_gate():
    consumed = []
    guarded = d39.make_guarded_consume(lambda item, purpose, **kw: consumed.append(item["kind"]) or "read")
    data_item = {"kind": "metadata", "path": "/synthetic/data", "sha256": "2" * 64}
    guarded(data_item, "non-label stays untouched")
    assert consumed == ["metadata"]
    d39.STATE.update(mode="dry-run", d39_marker_written=False, pre_label_passed=False)
    try:
        guarded(label_item(), "dry-run label read")
    except d39.LabelGuard:
        pass
    else:
        raise AssertionError("a dry run consumed a label")
    d39.STATE.update(mode="open")
    for written, passed in ((False, False), (True, False), (False, True)):
        d39.STATE.update(d39_marker_written=written, pre_label_passed=passed)
        try:
            guarded(label_item(), "label read before the gate opened")
        except ValueError as error:
            assert "label read before the D-A39 marker" in str(error)
        else:
            raise AssertionError("a label read passed the gate without marker+pre_label")
    d39.STATE.update(d39_marker_written=True, pre_label_passed=True)
    assert guarded(label_item(), "the approved read") == "read"
    assert consumed == ["metadata", "label"]


def test_open_mode_cache_miss_refuses_before_function_and_save():
    """Round-1 review gap 1: the label-opening run must refuse a missing preparation BEFORE invoking the preparation function
    or saving anything (the pre-label no-recompute check stays as defense in depth)."""
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw).resolve()
        with fixture(tmp) as ckpt:
            reset_state("dry-run", tmp / "records")
            run_all_stages(ckpt)                                        # the dry run computes origin and saves its checkpoint
            for path in ckpt.glob("origin-*"):                          # the label-opening run now faces an origin cache miss
                path.unlink()
            calls, saves = [], []
            original_save = d39.save_rolling
            d39.save_rolling = lambda *a, **k: (saves.append(1), {"status": "save-failed", "error": "spy"})[1]
            try:
                reset_state("open", tmp / "records")
                run_stage("origin", None, ckpt, function=lambda: (calls.append("ran"), origin_ready())[1])
            except ValueError as error:
                assert "refuses to recompute stage origin" in str(error)
            else:
                raise AssertionError("open mode recomputed a preparation instead of refusing")
            finally:
                d39.save_rolling = original_save
            assert calls == [] and saves == [], "the preparation function and the saver must never be called"
            assert not list(ckpt.glob("origin-*")), "the refusal must not leave a checkpoint behind"
            reset_state("dry-run", tmp / "records")                     # the same miss stays allowed in dry-run mode: it computes
            run_stage("origin", None, ckpt, function=origin_ready)
            assert d39.STATE["stages"][-1]["source"] == "computed"


def test_nonfinal_membership_source_receipts_checked():
    """Round-1 review gap 2: every attempt-12 receipt is checked individually — a NON-FINAL membership family loaded from a
    rolling checkpoint is rejected even with the final one legacy — and a rolling shadow of an attempt-12 checkpoint is refused
    before anything is loaded."""
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw).resolve()
        with fixture(tmp) as ckpt:
            reset_state("dry-run", tmp / "records")
            stages = run_all_stages(ckpt)
            members = [s for s in stages if s["stage"] == "members"]
            assert len(members) == 5
            for tampered, position in (("checkpoint-rolling", 0), ("checkpoint-rolling", 3)):   # first and middle, final stays legacy
                broken = json.loads(json.dumps(stages))
                target = [s for s in broken if s["stage"] == "members"][position]
                target["source"] = tampered
                try:
                    d39.binding_of(broken)
                except ValueError as error:
                    assert "attempt-12 checkpoint" in str(error) and "members" in str(error)
                else:
                    raise AssertionError(f"binding_of collapsed the {tampered} source of a non-final membership family")
            # the same collapse in pre_label's own per-run check
            reset_state("open", tmp / "records")
            run_all_stages(ckpt)
            d39.STATE["stages"][3]["source"] = "checkpoint-rolling"     # the first members receipt, non-final
            try:
                pre_label_open(tmp / "records")
                raise AssertionError("pre_label accepted a rolled first-membership receipt")
            except ValueError as error:
                assert "attempt-12 checkpoints not all used" in str(error)
            # a rolling manifest planted over a membership checkpoint is refused before loading
            reset_state("dry-run", tmp / "records")
            fp = r2_checkpoint._digest({"stage": "members", "code": r2_checkpoint.code_fingerprint(stage="members"),
                                        "args": [MEMBER_ARGS[1]], "kwargs": {}})
            shadow = ckpt / f"members-{fp[:24]}.manifest.json"
            shadow.write_text(json.dumps({"fingerprint": fp, "stage": "members", "parts": 999999999}))
            before = len(d39.STATE["stages"])
            try:
                run_stage("members", MEMBER_ARGS[1], ckpt)
                raise AssertionError("a rolling shadow of an attempt-12 checkpoint loaded")
            except ValueError as error:
                assert "shadow the attempt-12 checkpoint" in str(error)
            assert len(d39.STATE["stages"]) == before, "the shadow refusal must happen before any load"


def test_manifest_and_part_bounds_refused_before_reads():
    """Round-1 review gap 3: load_rolling must validate stage, object-ness, a bounded manifest size and a bounded finite part
    structure before reading or opening any part list; parts must be regular files within the admitted part size."""
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw).resolve()
        ckpt = tmp / "r2-ckpt"
        ckpt.mkdir()
        floor, part_bytes = d39.SAVE_FREE_FLOOR, r2_checkpoint.PART_BYTES
        d39.SAVE_FREE_FLOOR = -part_bytes
        try:
            base = ckpt / "origin-abc0123"
            d39.save_rolling(r2_checkpoint, base, "origin", "ab" * 32, {"pad": "z" * 500})
            manifest_path = Path(f"{base}.manifest.json")
            good = json.loads(manifest_path.read_text())
            assert good["stage"] == "origin"
            probes = [
                (dict(good, stage="not-origin"), "records stage"),
                (dict(good, parts=10 ** 9), "from 1 to"),
                (dict(good, parts=0), "from 1 to"),
                (dict(good, parts="3"), "from 1 to"),
                (dict(good, parts=None), "from 1 to"),
            ]
            for doc, marker in probes:
                manifest_path.write_text(json.dumps(doc))
                try:
                    d39.load_rolling(r2_checkpoint, base, "origin", "ab" * 32)
                except ValueError as error:
                    assert marker in str(error), (marker, error)
                else:
                    raise AssertionError(f"manifest {doc} loaded")
            manifest_path.write_text(json.dumps([good["fingerprint"]]))
            try:
                d39.load_rolling(r2_checkpoint, base, "origin", "ab" * 32)
            except ValueError as error:
                assert "not a JSON object" in str(error)
            else:
                raise AssertionError("a non-object manifest loaded")
            manifest_path.write_text("[" + " " * (d39.MANIFEST_MAX_BYTES + 16))
            try:
                d39.load_rolling(r2_checkpoint, base, "origin", "ab" * 32)
            except ValueError as error:
                assert "manifest ceiling" in str(error)
            else:
                raise AssertionError("an over-sized manifest was parsed")
            manifest_path.write_text(json.dumps(good))
            part = Path(f"{base}.part0000")
            payload, moved = part.read_bytes(), ckpt / "kept.part"
            part.rename(moved)
            part.mkdir()                                                # a directory cannot be a checkpoint part
            try:
                d39.load_rolling(r2_checkpoint, base, "origin", "ab" * 32)
            except ValueError as error:
                assert "is missing" in str(error) or "not a regular file" in str(error)
            else:
                raise AssertionError("a non-regular part loaded")
            part.rmdir()
            r2_checkpoint.PART_BYTES = 64                               # admitted part-size ceiling
            part.write_bytes(b"x" * 500)
            try:
                d39.load_rolling(r2_checkpoint, base, "origin", "ab" * 32)
            except ValueError as error:
                assert "exceeds the admitted part size" in str(error)
            else:
                raise AssertionError("a part over the admitted size loaded")
            part.unlink()
            part.write_bytes(payload)
            r2_checkpoint.PART_BYTES = part_bytes                        # restored ceiling: the honest checkpoint loads again
            result, receipt = d39.load_rolling(r2_checkpoint, base, "origin", "ab" * 32)
            assert result == {"pad": "z" * 500} and receipt["manifest_attests_parts"] is True
        finally:
            d39.SAVE_FREE_FLOOR, r2_checkpoint.PART_BYTES = floor, part_bytes


def test_receipt_paths_and_rolling_structure_are_bound():
    """Round-1 review gap 4: identical digests at different directories must bind differently; the rolling receipt structure
    (one manifest, contiguous ordered parts, no duplicate or non-canonical paths) is validated in receipt validation."""
    info = {"stage": "origin", "fingerprint": "ab" * 32, "source": "checkpoint-rolling",
            "checkpoint": {"format": "rolling-read", "manifest": "/one/origin.manifest.json",
                           "artifacts": [{"path": "/one/origin.manifest.json", "bytes": 10, "sha256": "0" * 64},
                                         {"path": "/one/origin.part0000", "bytes": 20, "sha256": "1" * 64}]}}
    moved = json.loads(json.dumps(info))
    for artifact in moved["checkpoint"]["artifacts"]:
        artifact["path"] = artifact["path"].replace("/one/", "/two/")
    moved["checkpoint"]["manifest"] = "/two/origin.manifest.json"
    assert d39.stage_binding(info) != d39.stage_binding(moved), "directories must be bound, not only basenames"
    probes = [
        (lambda c: c["artifacts"].append({"path": "/one/second.manifest.json", "bytes": 1, "sha256": "2" * 64}),
         "exactly one manifest"),
        (lambda c: c["artifacts"].append(dict(c["artifacts"][1])), "duplicate artifact path"),
        (lambda c: c["artifacts"][1].update(path="/one/origin.part0001"), "contiguous parts"),
        (lambda c: c["artifacts"][1].update(path="/one//origin.part0000"), "non-canonical absolute path"),
        (lambda c: c["artifacts"][1].update(path="one/origin.part0000"), "non-canonical absolute path"),
        (lambda c: c.update(format="attempt12-single-pkl"), "exactly one .pkl"),
    ]
    for mutate, marker in probes:
        broken = json.loads(json.dumps(info))
        mutate(broken["checkpoint"])
        try:
            d39.stage_binding(broken)
        except ValueError as error:
            assert marker in str(error), (marker, error)
        else:
            raise AssertionError(f"structural probe {marker} was accepted")
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw).resolve()
        with fixture(tmp) as ckpt:
            reset_state("dry-run", tmp / "records")
            stages = run_all_stages(ckpt)
            items, binding = d39.binding_of(stages)
            relocated = json.loads(json.dumps(stages))                  # same nine stage identities and digests, other directory
            for stage in relocated:
                if "manifest" in stage["checkpoint"]:
                    stage["checkpoint"]["manifest"] = "/relocated" + stage["checkpoint"]["manifest"]
                for artifact in stage["checkpoint"]["artifacts"]:
                    artifact["path"] = "/relocated" + artifact["path"]
            relocated_items, relocated_binding = d39.binding_of(relocated)
            assert relocated_binding != binding and len(relocated_items) == len(items) == 9


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
