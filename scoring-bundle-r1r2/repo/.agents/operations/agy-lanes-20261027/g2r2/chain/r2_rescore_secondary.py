#!/usr/bin/env python3
"""D-A39: one disclosed re-scoring of the R2 secondary lanes (counts, five membership families, stable, origin, additional baselines).

Why. R2 attempt 12 (job 52700052) opened the label table once, wrote arms/000/attempt/primary.json (sha256 849e0645...) and
primary-scores.json, then failed in the membership consumer's score_membership on the float32/float64 edge of D-A36 (arm gru-d30-s2).
No secondary outcome was computed. <AUTHOR> approved (2026-10-30, D-A39) ONE disclosed second label read for the secondary lanes only;
primary.json stays THE primary result.

What this driver does. It runs the pinned R2 runner exactly as r2_exec.py does (r2_exec.main is called unchanged, so every reviewed
patch D-A26..D-A38 is installed by r2_exec itself, in its own order) and adds one layer, hooked at two points of r2_exec.main:
`amend_wiring.engage_runner` (to get the exec'd runner module) and the runner's `run` (called by r2_exec after it installed its
patches). The layer:
  * replaces the runner's `execute` (which accepts only arms/000/attempt): same bounds / same-filesystem / free-space / exclusive
    records checks, but the records directory is arms/000/rescore-secondary-D-A39 (open mode) and must not exist; arms/000/attempt,
    the one-opening marker, freeze, seal and labels are only read (through the Reader, hash-checked, logged), never written;
  * installs r2_float32_scoring.py (D-A39 patch) on the membership consumer;
  * loads the attempt-12 preparation checkpoints (old single-file .pkl format; see LEGACY) after recomputing their fingerprint, and
    computes the origin preparation (its attempt-12 save failed at the 16 GiB RLIMIT_FSIZE) and saves it in the rolling format of
    r2_checkpoint.py with a free-space guard, so the label-opening run loads it;
  * replaces, in the runner's private evaluator copy only, `refuse_second_opening`: instead of refusing because the attempt-12 marker
    exists, it requires that exactly that marker exists (read through the Reader; its seal/labels/out fields checked) and returns a
    NEW marker path inside the D-A39 records directory, which the unchanged evaluator writes exclusively right before its label read;
  * runs, immediately before that label read, a label-free decision check over every prepared membership/origin/stable cell and
    refuses unless the patched comparison reproduces every committed decision (so the scoring cannot fail on it after the read);
  * prefixes every access-log purpose of the run with "[D-A39 ...]" (the label rows with the approval text); the Reader's own label
    rule (purpose 'Custodian label table', at most one label read) is unchanged; a guard refuses any label read in dry-run mode and any
    label read before the D-A39 marker exists;
  * after the read: each secondary family is scored in isolation (a family that raises is recorded as failed, the others continue)
    and persisted as soon as it is done; the complete result is pickled, the recomputed primary is compared with primary.json, and
    secondary-result.json is written with a header (D-A39, primary.json sha, label/seal/freeze sha).

Modes:
  --dry-run                                    everything up to, NOT including, the label opening; writes ready.json and stops.
  --open-labels-D-A39 --approval FILE          the one label-opening run; FILE is the owner's approval (see APPROVAL_FIELDS) and must
                                               bind the dry run's ready.json by sha256.
Run inside the Slurm allocation via r2_rescore_secondary.sbatch (it sets the cleared environment the runner checks).
"""
import argparse
import hashlib
import json
import os
import pickle
import socket
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "g2"))

F = "<FORECAST_ROOT>"
RUNS = F + "/newperiod-g2-inference-v1-20261027"          # run dirs must be direct children: r2_exec derives the D-A33 sidecar from it
ROOT = F + "/data-custodian/single-R2-v1"                   # == runner.ROOT
ATTEMPT = ROOT + "/arms/000/attempt"
TARGET = ROOT + "/arms/000/rescore-secondary-D-A39"
BASE_SPEC = {"path": RUNS + "/r2-run-20261030-a17/r2-exec-spec.json",
             "sha256": "6f36f538ccfcce33df2e9396752fdb95503d3d6925babdca2340c384ed20ab13"}
PRIMARY = {"path": ATTEMPT + "/primary.json", "sha256": "849e064518d1aa7e0b1c61c4c5836acd75864de12dce0278dab75918493e9ac1",
           "size_bytes": 133902}
PRIMARY_SCORES = {"path": ATTEMPT + "/primary-scores.json",
                  "sha256": "af9656ac8e1961eccbda75c590e5c8361a640229127dc122e79611d0365cef59", "size_bytes": 53912612}
MARKER = {"path": RUNS + "/amend/unblinded-8ede1a58a437559ea1fb5259edd60141e1a8312ae286a978e7e4554e19a6014f.json",
          "sha256": "882deb925bf72dc16d0d5abcea066e7e32dc01bdd205e691d7bf2e817d9e1b13", "size_bytes": 719}
LABELS_SHA = "20e3044fa439866512d618d540dcefad1516151bc3f63ac482ee480bb6303447"
SEAL_SHA = "8ede1a58a437559ea1fb5259edd60141e1a8312ae286a978e7e4554e19a6014f"
FREEZE_SHA = "921fc9bb06888e39b2399735cd2bc673506116375b5be84ce16dfee59b33beaa"
ATTEMPT_FILES = ["intent.json", "primary-scores.json", "primary.json"]

# Attempt-12 checkpoints (r2-ckpt/, old format: pickle({"fingerprint", "stage"}) then pickle(result), one file), name -> bytes as
# printed by r2-52700052.out. Their key: attempt 12 ran the 02:50Z r2_checkpoint.py (per-stage key code_fingerprint(stage), single
# .pkl writer), whose code_fingerprint reads r2_checkpoint.py FROM DISK at call time; the file was replaced at 06:09:23Z by the
# current version (sha 97382e4a...), before the first of these stages (baseline, 06:13Z) ran. Hence their fingerprint is exactly what
# the CURRENT r2_checkpoint computes (_digest of stage, code_fingerprint(stage), non-callable args); verified offline for counts
# (959aaa80fd44...). The origin stage ran first (intermediate file) and its save failed; it is recomputed here.
LEGACY = {
    "baseline": {"baseline-ad753ced838eb812dcc44f64.pkl": 275334364},
    "counts": {"counts-959aaa80fd4471fa978b3e43.pkl": 10972},
    "members": {"members-1dc1eba251a8c5065f29ebdd.pkl": 3898663813, "members-125c784dc89ccc5380d85442.pkl": 8758133323,
                "members-41d7a100dc90759763379813.pkl": 3352991403, "members-84ddd286f969b77b98ef221e.pkl": 5797143995,
                "members-51e89096eddb87691d10b61f.pkl": 772719845},
    "stable": {"stable-8b2ded7e985a2611c5bbe7e6.pkl": 1479268630},
}
EXPECTED_CALLS = {"origin": 1, "baseline": 1, "counts": 1, "members": 5, "stable": 1}
CHECKPOINT_SHA = "97382e4abe67240152e5c01763eb970b0fc5c32eedfb77f0e7453d3dcb580be4"   # r2_checkpoint.py the keys depend on
SAVE_FREE_FLOOR = 200 << 30   # origin save aborts (parts removed) rather than take the shared volume below this
DRY_PREFIX = "[D-A39 dry run, labels not opened] "
OPEN_PREFIX = "[D-A39 secondary re-score] "
LABEL_PREFIX = ("[D-A39 approved second label read, secondary lanes only; primary of record stays attempt/primary.json "
                "849e064518d1] ")
APPROVAL_FIELDS = {"deviation": "D-A39", "second_label_read_authorized": True, "scope": "secondary lanes only",
                   "labels_sha256": LABELS_SHA, "seal_sha256": SEAL_SHA, "freeze_sha256": FREEZE_SHA,
                   "primary_json_sha256": PRIMARY["sha256"], "records": TARGET}

STATE = {"mode": None, "stages": [], "families": [], "float32_installs": 0, "refuse_installs": 0, "d39_marker_written": False,
         "pre_label_passed": False, "registry": {k: [] for k in EXPECTED_CALLS}, "t0": time.time()}


class DryRunReady(BaseException):
    """Raised at the D-A39 marker write in dry-run mode: every label-free step is done, the label table is not opened."""


class LabelGuard(BaseException):
    pass


def need(ok, why):
    if not ok:
        raise ValueError("D-A39: " + why)


def sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 24), b""):
            h.update(block)
    return h.hexdigest()


def ref(path):
    return {"path": str(Path(path).resolve()), "sha256": sha_file(path)}


def say(**fields):
    print(json.dumps({"d_a39": fields, "t": round(time.time() - STATE["t0"], 1)}, sort_keys=True, default=str), flush=True)


# ------------------------------------------------------------------------------------------------------------------ checkpoints

class _HashingReader:
    def __init__(self, stream):
        self.stream, self.h, self.n = stream, hashlib.sha256(), 0

    def read(self, n=-1):
        data = self.stream.read(n)
        self.h.update(data)
        self.n += len(data)
        return data

    def readline(self, limit=-1):
        data = self.stream.readline(limit)
        self.h.update(data)
        self.n += len(data)
        return data

    def readinto(self, buffer):
        k = self.stream.readinto(buffer)
        self.h.update(memoryview(buffer)[:k])
        self.n += k
        return k


def load_legacy(path, name, fingerprint):
    need(path.name in LEGACY[name], f"unexpected checkpoint file {path}")
    need(path.stat().st_size == LEGACY[name][path.name], f"{path} size differs from attempt 12's saved size")
    with path.open("rb") as raw:
        stream = _HashingReader(raw)
        header = pickle.load(stream)
        need(header == {"fingerprint": fingerprint, "stage": name}, f"{path} header does not carry the recomputed fingerprint")
        result = pickle.load(stream)
        need(stream.read() == b"", f"{path} has trailing bytes")
    return result, {"path": str(path), "bytes": stream.n, "sha256": stream.h.hexdigest(), "format": "attempt12-single-pkl"}


def save_rolling(r2_checkpoint, base, name, fingerprint, result):
    """r2_checkpoint's rolling format (parts + manifest, loadable by its wrap), with a free-space check before every part."""
    class Guarded(r2_checkpoint._RollingWriter):
        def _open(self):
            free = os.statvfs(Path(base).parent)
            need(free.f_bavail * free.f_frsize - r2_checkpoint.PART_BYTES > SAVE_FREE_FLOOR, "free space below the save floor")
            super()._open()
    writer = None
    try:
        writer = Guarded(base)
        pickle.dump(result, writer, protocol=5)
        parts = writer.close()
        tmp = Path(f"{base}.manifest.tmp")
        tmp.write_text(json.dumps({"fingerprint": fingerprint, "stage": name, "parts": parts}))
        os.replace(tmp, f"{base}.manifest.json")
        size = sum(Path(f"{base}.part{i:04d}").stat().st_size for i in range(parts))
        return {"status": "saved", "manifest": f"{base}.manifest.json", "parts": parts, "bytes": size}
    except Exception as error:   # a failed save never fails the run; partial parts are removed
        if writer is not None and writer.stream:
            writer.stream.close()
        for part in Path(base).parent.glob(Path(base).name + ".part*"):
            part.unlink()
        return {"status": "save-failed", "error": repr(error)[:300]}


def install_checkpoint_wrap():
    import r2_checkpoint
    need(hashlib.sha256(Path(r2_checkpoint.__file__).read_bytes()).hexdigest() == CHECKPOINT_SHA,
         "r2_checkpoint.py changed: the attempt-12 checkpoint keys would not be recomputed")
    original_wrap = r2_checkpoint.wrap

    def wrap(function, name, ckpt_dir, code_key):
        inner = original_wrap(function, name, ckpt_dir, code_key)

        def wrapped(*args, **kwargs):
            started = time.time()
            fingerprint = r2_checkpoint._digest({"stage": name, "code": r2_checkpoint.code_fingerprint(stage=name),
                                                 "args": [a for a in args if not callable(a)],
                                                 "kwargs": {k: v for k, v in kwargs.items() if not callable(v)}})
            base = Path(ckpt_dir) / f"{name}-{fingerprint[:24]}"
            info = {"stage": name, "fingerprint": fingerprint}
            if Path(f"{base}.manifest.json").is_file():
                result = inner(*args, **kwargs)
                info.update(source="checkpoint-rolling", manifest=f"{base}.manifest.json")
            elif Path(f"{base}.pkl").is_file():
                result, legacy = load_legacy(Path(f"{base}.pkl"), name, fingerprint)
                info.update(source="checkpoint-attempt12", **legacy)
            else:
                need(name not in LEGACY, f"no attempt-12 checkpoint for stage {name} at {base}.pkl: inputs or code differ")
                result = function(*args, **kwargs)
                info.update(source="computed", save=save_rolling(r2_checkpoint, base, name, fingerprint, result))
            info["seconds"] = round(time.time() - started, 1)
            STATE["registry"][name].append(result)
            STATE["stages"].append(info)
            say(stage=info)
            return result

        wrapped._d_a37 = True
        return wrapped

    r2_checkpoint.wrap = wrap


# ---------------------------------------------------------------------------------------------------------- evaluator layer

def make_marker_class(pre_label):
    class D39Marker(type(Path())):
        def open(self, mode="r", *args, **kwargs):
            if mode == "x":
                pre_label(self)                     # dry run: raises DryRunReady here, before anything is written or read
                stream = super().open(mode, *args, **kwargs)
                STATE["d39_marker_written"] = True
                return stream
            return super().open(mode, *args, **kwargs)
    return D39Marker


def make_refuse(private, marker_class):
    def refuse_second_opening(seal, seal_sha256):
        original = private._marker_for(seal, seal_sha256)          # runner's BoundPath beside the freeze
        need(str(original) == MARKER["path"] and seal_sha256 == SEAL_SHA, "marker path/seal differ from attempt 12")
        found = sorted(str(p) for p in original.parent.glob(private.UNBLINDED_PREFIX + "*.json"))
        need(found == [MARKER["path"]], f"exactly the attempt-12 one-opening marker must exist, found {found}")
        record = json.loads(original.read_bytes())                  # BoundPath.read_bytes: Reader, inventory sha, access log
        need(record.get("seal_sha256") == SEAL_SHA and record.get("labels_sha256") == LABELS_SHA
             and record.get("out") == PRIMARY["path"], "attempt-12 marker content differs")
        STATE["attempt12_marker_record"] = {k: record.get(k) for k in ("unblinded_utc", "seal_sha256", "labels_sha256", "out")}
        return marker_class(Path(STATE["records"]) / "second-label-read-D-A39.json")
    refuse_second_opening._d_a39 = True
    return refuse_second_opening


def private_primary_hook(original_private_primary, marker_class):
    def private_primary(original):
        private = original_private_primary(original)
        if not getattr(private.__dict__.get("refuse_second_opening"), "_d_a39", False):
            private.refuse_second_opening = make_refuse(private, marker_class)
            STATE["refuse_installs"] += 1
        return private
    private_primary._d_a39 = True
    return private_primary


def persist_object(directory, name, value):
    """Pickle in parts below RLIMIT_FSIZE (0600, exclusive), manifest last."""
    directory = Path(directory)
    directory.mkdir(mode=0o700, exist_ok=True)
    digest, part_bytes = hashlib.sha256(), 6 << 30
    state = {"fd": None, "room": 0, "parts": 0, "size": 0}

    class Writer:
        def write(self, data):
            view = memoryview(data)
            while len(view):
                if state["room"] == 0:
                    if state["fd"] is not None:
                        os.fsync(state["fd"])
                        os.close(state["fd"])
                    state["fd"] = os.open(directory / f"{name}.pkl.part{state['parts']:04d}", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    state["room"] = part_bytes
                    state["parts"] += 1
                written = os.write(state["fd"], view[:state["room"]])
                digest.update(view[:written])
                state["room"] -= written
                state["size"] += written
                view = view[written:]
            return len(data)

    if isinstance(value, bytes):
        Writer().write(value)
        kind = "raw-bytes"
    else:
        pickle.dump(value, Writer(), protocol=5)
        kind = "pickle5"
    if state["fd"] is not None:
        os.fsync(state["fd"])
        os.close(state["fd"])
    manifest = {"name": name, "parts": state["parts"], "bytes": state["size"], "sha256_of_concatenated_parts": digest.hexdigest(), "format": kind}
    with os.fdopen(os.open(directory / f"{name}.manifest.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
        json.dump(manifest, stream, sort_keys=True)
    return manifest


def isolate(module, attribute, label, key=None):
    """After the label read: a scoring function that raises is recorded as failed (no value is invented), the others continue,
    and every family result is persisted as soon as it exists."""
    function = getattr(module, attribute)
    if getattr(function, "_d_a39_isolated", False):
        return

    def wrapped(*args, **kwargs):
        name = label if key is None else f"{label}-{key(args)}"
        started = time.time()
        try:
            out, status = function(*args, **kwargs), "scored"
        except Exception as error:
            traceback.print_exc()
            out = {"kind": "D-A39_secondary_family_failed", "family": name, "status": "failed", "error": repr(error)[:4000],
                   "traceback": traceback.format_exc()[-8000:]}
            status = "failed"
        entry = {"family": name, "status": status, "seconds": round(time.time() - started, 1)}
        try:
            entry["persisted"] = persist_object(Path(STATE["records"]) / "families", name, out)
        except Exception as error:
            entry["persist_error"] = repr(error)[:300]
        STATE["families"].append(entry)
        say(family=entry)
        return out

    wrapped._d_a39_isolated = True
    setattr(module, attribute, wrapped)


def install_layer(runner):
    import r2_float32_scoring
    marker_class = make_marker_class(pre_label)
    r2exec_scientific_modules = runner.scientific_modules        # r2_exec's wrapper (installs module.components when called)

    def scientific_modules(plan):
        evaluator, custody = r2exec_scientific_modules(plan)
        r2exec_components = runner.components

        def components():
            loaded = r2exec_components()
            composition = loaded["composition"]
            inner = composition.components                       # r2_exec's composition_components (D-A36/D-A38/D-A37)
            if not getattr(inner, "_d_a39", False):
                def composition_components():
                    modules = inner()
                    r2_float32_scoring.patch(modules["membership"])
                    STATE["float32_installs"] += 1
                    STATE["membership_modules"] = STATE.get("membership_modules", []) + [modules["membership"]]
                    if not getattr(modules["count"].private_primary, "_d_a39", False):
                        modules["count"].private_primary = private_primary_hook(modules["count"].private_primary, marker_class)
                    isolate(modules["membership"], "evaluate", "membership", key=lambda args: args[0]["family"])
                    isolate(modules["stable"], "evaluate", "stable")
                    isolate(modules["count"], "score_counts", "counts")
                    return modules
                composition_components._d_a39 = True
                composition.components = composition_components
            isolate(loaded["origin"], "evaluate", "origin")
            isolate(loaded["baseline"], "evaluate", "additional_baselines")
            return loaded

        runner.components = components
        return evaluator, custody

    runner.scientific_modules = scientific_modules
    original_log_function = runner.log_function

    def log_function(path, limit):
        log = original_log_function(path, limit)
        prefix = DRY_PREFIX if STATE["mode"] == "dry-run" else OPEN_PREFIX

        def d39_log(source_path, purpose):
            if str(source_path) == STATE.get("labels_path"):
                need(STATE["mode"] == "open" and STATE["d39_marker_written"], "label access-log row outside the approved read")
                return log(source_path, LABEL_PREFIX + purpose)
            return log(source_path, prefix + purpose)
        return d39_log

    runner.log_function = log_function

    def execute(*args, **kwargs):          # the pinned run() swallows the traceback: print it, re-raise unchanged
        try:
            return d39_execute(runner, *args, **kwargs)
        except BaseException:
            traceback.print_exc()
            raise
    runner.execute = execute


def pre_label(marker):
    """Immediately before the label read (inside the evaluator, after every label-free check)."""
    import r2_float32_scoring
    need(Path(marker).parent == Path(STATE["records"]) and not Path(marker).exists(), "D-A39 marker path")
    calls = {k: len(v) for k, v in STATE["registry"].items()}
    need(calls == EXPECTED_CALLS, f"every preparation stage must have run exactly as expected: {calls}")
    sources = {s["stage"]: s["source"] for s in STATE["stages"]}
    need(all(sources[k] == "checkpoint-attempt12" for k in LEGACY), f"attempt-12 checkpoints not all used: {sources}")
    check = r2_float32_scoring.check_prepared(members=STATE["registry"]["members"], origin=STATE["registry"]["origin"],
                                              stable=STATE["registry"]["stable"])
    STATE["decision_check"] = check
    say(decision_check={k: {x: v[x] for x in ("arms_checked", "rows_checked", "float64_mismatch_rows", "float32_mismatch_rows")}
                        for k, v in check.items()})
    need(check["members"]["arms_checked"] > 0 and check["members"]["float32_mismatch_rows"] == 0,
         "patched (float32) membership scoring would refuse a committed decision")
    need(check["origin"]["float64_mismatch_rows"] == 0 and check["stable"]["float64_mismatch_rows"] == 0,
         "unpatched origin/stable scoring would refuse a committed decision")
    modules = STATE.get("membership_modules", [])
    need(modules and all(getattr(m.scoring, r2_float32_scoring.MARK, False) for m in modules), "float32 scoring not installed")
    STATE["registry"] = {k: [None] * len(v) for k, v in STATE["registry"].items()}   # drop references: the runner owns the objects
    STATE["pre_label_passed"] = True
    if STATE["mode"] == "dry-run":
        raise DryRunReady()
    need(STATE["mode"] == "open" and STATE.get("approval_ok") is True, "label opening without the verified approval")


# ------------------------------------------------------------------------------------------------------------------- execute

def d39_execute(runner, plan, reader, original, custody):
    import shutil
    records = Path(plan["records"])
    expected = Path(TARGET) if STATE["mode"] == "open" else Path(STATE["run_dir"]) / "records-dry-run"
    need(records == expected and records.resolve() == records, f"records must be {expected}")
    need(plan["primary_output"] == str(records / "primary-recomputed-D-A39.json") and plan["result_output"] == str(records / "secondary-result.json")
         and plan["primary_scores_output"] == str(records / "primary-scores.json"), "fixed D-A39 output artifacts required")
    need(plan["labels"]["sha256"] == LABELS_SHA and plan["seal"]["sha256"] == SEAL_SHA and plan["freeze"]["sha256"] == FREEZE_SHA,
         "labels/seal/freeze differ from attempt 12")
    b = plan["bounds"]
    need(type(b["output_file_bytes"]) is int and b["output_file_bytes"] > 0
         and b["output_total_bytes"] >= 6 * b["output_file_bytes"] + b["access_log_bytes"], "extra score-file reservation absent")
    need(not records.exists() and records.parent.is_dir(), "existing D-A39 records forbid repetition")
    target = Path(TARGET)
    need(not target.exists() and target.parent.is_dir(), "D-A39 re-scoring records already exist: one re-scoring only")
    device = Path(plan["freeze"]["path"]).parent.stat().st_dev
    need(device == Path(plan["access_log"]).parent.stat().st_dev == records.parent.stat().st_dev == target.parent.stat().st_dev,
         "marker/log/results must share the admitted filesystem")
    need(shutil.disk_usage(records.parent).free >= b["output_total_bytes"] + (64 << 30), "actual storage reservation unavailable")
    need(sorted(os.listdir(ATTEMPT)) == ATTEMPT_FILES, "attempt-12 records directory changed")
    reader.bytes({"path": PRIMARY["path"], "sha256": PRIMARY["sha256"]}, "D-A39: attempt-12 primary.json (primary of record) present")
    STATE["records"] = str(records)
    STATE["labels_path"] = plan["labels"]["path"]
    STATE["log_start_bytes"] = Path(plan["access_log"]).stat().st_size
    records.mkdir()
    runner.exclusive(records / "intent.json", {"deviation": "D-A39", "mode": STATE["mode"], "seal": plan["seal"], "labels": plan["labels"],
                                               "freeze": plan["freeze"], "resources": plan["resources"], "primary_of_record": PRIMARY,
                                               "approval": STATE.get("approval_ref"), "automatic_retry_authorized": False})
    consume = reader.consume

    def guarded_consume(item, purpose, *, hash_only=False):
        if item["kind"] == "label":
            if STATE["mode"] != "open":
                raise LabelGuard("D-A39 dry run: label read refused")
            need(STATE["d39_marker_written"] and STATE["pre_label_passed"], "label read before the D-A39 marker")
        return consume(item, purpose, hash_only=hash_only)
    reader.consume = guarded_consume
    score_receipts = []
    try:
        result = runner.evaluate(plan, reader, original, custody, runner.components(), score_receipts=score_receipts)
    except DryRunReady:
        return dry_run_ready(runner, plan, reader, records)
    need(STATE["mode"] == "open", "evaluation completed outside open mode")
    return finish(runner, plan, reader, records, result, score_receipts)


def common_record(plan, reader):
    import r2_float32_scoring
    log_now = Path(plan["access_log"]).stat().st_size
    return {"job_id": os.environ.get("SLURM_JOB_ID"), "node": socket.gethostname(), "elapsed_seconds": round(time.time() - STATE["t0"], 1),
            "run_dir": STATE["run_dir"], "spec": STATE["spec_ref"], "labels": plan["labels"], "seal": plan["seal"], "freeze": plan["freeze"],
            "primary_of_record": PRIMARY, "attempt12_marker": {**MARKER, "record": STATE.get("attempt12_marker_record")},
            "target_records": TARGET, "stages": STATE["stages"], "decision_check": STATE.get("decision_check"),
            "float32_scoring": {"module": ref(r2_float32_scoring.__file__), "installs": STATE["float32_installs"],
                                "old": r2_float32_scoring.OLD, "new": r2_float32_scoring.NEW},
            "refuse_second_opening_installs": STATE["refuse_installs"], "driver": ref(__file__),
            "code": {name: ref(HERE / name) for name in ("r2_exec.py", "r2_checkpoint.py", "r2_parallel_origin.py", "r2_float32_decision.py",
                                                         "r2_stable_persistence.py", "r2_input_cache.py", "r2_fast_authorize.py",
                                                         "r2_fast_json.py", "amend_wiring.py", "d60_only.py")},
            "access_log": {"path": plan["access_log"], "bytes_at_execute": STATE["log_start_bytes"], "bytes_now": log_now,
                           "open_run_admissible": log_now + plan["bounds"]["access_log_bytes"] <= plan["bounds"]["output_file_bytes"]},
            "reader": {"label_reads": reader.label_reads, "bytes_read": reader.read_bytes, "unique_verified_objects": len(reader.verified),
                       "input_loads": reader.input_loads, "input_view_reuses": reader.input_reuses},
            "disk_free_bytes": os.statvfs(STATE["records"]).f_bavail * os.statvfs(STATE["records"]).f_frsize}


def dry_run_ready(runner, plan, reader, records):
    need(reader.label_reads == 0 and not STATE["d39_marker_written"] and STATE["pre_label_passed"], "dry run state")
    ready = {"kind": "D-A39_secondary_rescore_dry_run_v1", "status": "ready, labels not opened", "labels_opened": False,
             "d39_marker_written": False, **common_record(plan, reader),
             "approval_fields_required": {**APPROVAL_FIELDS, "approved_by": "<name, no whitespace>",
                                          "approval_record": "<where/when the approval was given>",
                                          "dry_run_ready": {"path": str(records / "ready.json"), "sha256": "<sha256 of this file>"}}}
    receipt = runner.exclusive(records / "ready.json", ready)
    STATE["ready_ref"] = receipt
    say(ready=receipt, status="ready, labels not opened")
    return {"passed": True, "dry_run": True, "labels_opened": False, "label_reads": reader.label_reads, "ready": receipt,
            "outcome_release_authorized": False}


# ------------------------------------------------------------------------------------------------------------------- finish

def _walk(value, counts):
    import numpy as np
    stack = [value]
    while stack:
        v = stack.pop()
        if isinstance(v, dict):
            stack.extend(v.values())
        elif isinstance(v, (list, tuple)):
            stack.extend(v)
        elif isinstance(v, float):
            if v != v or v in (float("inf"), float("-inf")):
                counts["non_finite_floats"] = counts.get("non_finite_floats", 0) + 1
        elif isinstance(v, (np.generic, np.ndarray, set, frozenset)):
            counts[type(v).__name__] = counts.get(type(v).__name__, 0) + 1


def _default(value):
    import numpy as np
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def _stringify_keys(value):
    if isinstance(value, dict):
        return {k if isinstance(k, str) else str(k): _stringify_keys(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_stringify_keys(v) for v in value]
    return value


def _canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=True).encode()).hexdigest()


def _diff(a, b, path="", out=None):
    out = out if out is not None else {"paths": [], "count": 0, "max_abs_numeric": 0.0}
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out["count"] += 1
                if len(out["paths"]) < 200:
                    out["paths"].append(f"{path}/{k} (missing on one side)")
            else:
                _diff(a[k], b[k], f"{path}/{k}", out)
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            _diff(x, y, f"{path}[{i}]", out)
    elif a != b and not (isinstance(a, float) and isinstance(b, float) and a != a and b != b):
        out["count"] += 1
        if len(out["paths"]) < 200:
            out["paths"].append(path)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
            out["max_abs_numeric"] = max(out["max_abs_numeric"], abs(float(a) - float(b)))
    return out


def compare_primary(reader, plan, score_receipts):
    """The recomputed primary (same code, same inputs, seed 1701) against attempt 12's primary.json; primary.json stays the result."""
    old_raw = reader.bytes({"path": PRIMARY["path"], "sha256": PRIMARY["sha256"]}, "D-A39: attempt-12 primary.json for the recomputation comparison")
    new_raw = Path(plan["primary_output"]).read_bytes()
    old, new = json.loads(old_raw), json.loads(new_raw)
    drop = lambda d, key: {k: v for k, v in d.items() if k != key}
    out = {"attempt12": PRIMARY, "recomputed": {"path": plan["primary_output"], "sha256": hashlib.sha256(new_raw).hexdigest()},
           "raw_bytes_identical": old_raw == new_raw, "canonical_sha256": {"attempt12": _canonical(old), "recomputed": _canonical(new)},
           "canonical_identical_except_unblinded_marker": _canonical(drop(old, "unblinded_marker")) == _canonical(drop(new, "unblinded_marker")),
           "expected_difference": ["unblinded_marker (path of the D-A39 marker)"], "diff": _diff(old, new)}
    old_scores_raw = reader.bytes({"path": PRIMARY_SCORES["path"], "sha256": PRIMARY_SCORES["sha256"]},
                                  "D-A39: attempt-12 primary-scores.json for the recomputation comparison")
    new_scores_raw = Path(plan["primary_scores_output"]).read_bytes()
    old_scores, new_scores = json.loads(old_scores_raw), json.loads(new_scores_raw)
    out["scores"] = {"attempt12": PRIMARY_SCORES, "recomputed": score_receipts[0] if score_receipts else None,
                     "canonical_identical_except_primary_report_path":
                         _canonical(drop(old_scores, "primary_report_path")) == _canonical(drop(new_scores, "primary_report_path")),
                     "diff": _diff(drop(old_scores, "primary_report_path"), drop(new_scores, "primary_report_path"))}
    return out


def finish(runner, plan, reader, records, result, score_receipts):
    errors, report = [], {}
    need(reader.label_reads == 1 and STATE["d39_marker_written"], "exactly one label read after the D-A39 marker")
    try:
        report["raw_result"] = persist_object(records, "secondary-result-raw", result)
    except Exception as error:
        errors.append("raw pickle: " + repr(error)[:500])
    try:
        report["primary_comparison"] = compare_primary(reader, plan, score_receipts)
    except Exception as error:
        traceback.print_exc()
        errors.append("primary comparison: " + repr(error)[:500])
    try:
        import r2_float32_scoring
        secondary = {k: v for k, v in result.items() if k != "primary"}
        counts = {}
        _walk(secondary, counts)
        header = {"kind": "newperiod_secondary_rescore_D-A39_v1", "deviation": "D-A39",
                  "primary_of_record": PRIMARY, "primary_result_note": "primary.json of attempt 12 is the primary result; the primary "
                  "recomputed here is a consistency check only", "labels": plan["labels"], "seal": plan["seal"], "freeze": plan["freeze"],
                  "approval": STATE.get("approval_ref"), "attempt12_marker": MARKER,
                  "d39_marker": ref(records / "second-label-read-D-A39.json"), "label_reads_this_run": reader.label_reads,
                  "job_id": os.environ.get("SLURM_JOB_ID"),
                  "float32_scoring": {"module": ref(r2_float32_scoring.__file__), "old": r2_float32_scoring.OLD, "new": r2_float32_scoring.NEW},
                  "decision_check": STATE.get("decision_check"), "stages": STATE["stages"], "families": STATE["families"],
                  "primary_comparison": report.get("primary_comparison"),
                  "recomputed_primary": {"path": plan["primary_output"], "sha256": sha_file(plan["primary_output"])},
                  "recomputed_primary_scores": score_receipts[0] if score_receipts else None,
                  "json_value_notes": counts, "outcome_release_authorized": False}
        document = {"header": header, "secondary": secondary}
        try:
            encoded = json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=True, default=_default)
        except TypeError:   # a non-string/mixed-type dict key: write every key as str(key), and say so
            header["json_value_notes"]["dict_keys_stringified"] = True
            encoded = json.dumps(_stringify_keys(document), sort_keys=True, separators=(",", ":"), allow_nan=True, default=_default)
        encoded = (encoded + "\n").encode()
        bound = plan["bounds"]["output_file_bytes"]
        if len(encoded) <= bound:
            with Path(plan["result_output"]).open("xb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            report["secondary_result"] = {"path": plan["result_output"], "sha256": hashlib.sha256(encoded).hexdigest(), "bytes": len(encoded)}
        else:
            report["secondary_result"] = {"split": persist_object(records, "secondary-result-json", encoded), "bytes": len(encoded),
                                          "sha256": hashlib.sha256(encoded).hexdigest(), "note": "larger than RLIMIT_FSIZE: bytes pickled in parts"}
        report["json_value_notes"] = counts
    except Exception as error:
        traceback.print_exc()
        errors.append("secondary-result.json: " + repr(error)[:500])
    failed = [f["family"] for f in STATE["families"] if f["status"] != "scored"]
    comparison = report.get("primary_comparison") or {}
    return {"passed": not errors and not failed and len(score_receipts) == 1, "deviation": "D-A39", "records": str(records),
            "label_reads": reader.label_reads, "families": STATE["families"], "failed_families": failed, "errors": errors,
            "secondary_result": report.get("secondary_result"), "raw_result": report.get("raw_result"),
            "primary_recomputation_identical_except_marker": comparison.get("canonical_identical_except_unblinded_marker"),
            "primary_scores_identical_except_path": (comparison.get("scores") or {}).get("canonical_identical_except_primary_report_path"),
            "bytes_read": reader.read_bytes, "outcome_release_authorized": False}


# ---------------------------------------------------------------------------------------------------------------------- main

def verify_approval(path):
    path = Path(path)
    need(path.is_absolute() and path.resolve() == path and path.is_file() and 0 < path.stat().st_size <= 1 << 20, "approval file")
    raw = path.read_bytes()
    approval = json.loads(raw)
    for key, value in APPROVAL_FIELDS.items():
        need(approval.get(key) == value, f"approval field {key} must be {value!r}")
    who = approval.get("approved_by")
    need(isinstance(who, str) and who and not any(c.isspace() for c in who), "approval approved_by (no whitespace)")
    need(isinstance(approval.get("approval_record"), str) and approval["approval_record"], "approval approval_record")
    dry = approval.get("dry_run_ready")
    need(isinstance(dry, dict) and set(dry) == {"path", "sha256"} and Path(dry["path"]).is_file() and sha_file(dry["path"]) == dry["sha256"],
         "approval must bind the dry run's ready.json by sha256")
    ready = json.loads(Path(dry["path"]).read_bytes())
    need(ready.get("kind") == "D-A39_secondary_rescore_dry_run_v1" and ready.get("status") == "ready, labels not opened"
         and ready.get("labels_opened") is False and ready["reader"]["label_reads"] == 0 and ready.get("target_records") == TARGET,
         "dry-run ready record")
    need(ready["driver"]["sha256"] == sha_file(__file__), "the driver changed since the dry run: dry-run again")
    import r2_float32_scoring
    need(ready["float32_scoring"]["module"]["sha256"] == sha_file(r2_float32_scoring.__file__), "float32 patch changed since the dry run")
    need(all(ready["code"][n]["sha256"] == sha_file(HERE / n) for n in ready["code"]), "chain code changed since the dry run")
    return approval, {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()}


def stage(mode, run_dir, approval, approval_ref):
    import g2_exec
    base = json.loads(g2_exec.bound(BASE_SPEC))
    template = json.loads(g2_exec.bound(base["template"]))
    need(template["labels"]["sha256"] == LABELS_SHA and template["seal"]["sha256"] == SEAL_SHA and template["freeze"]["sha256"] == FREEZE_SHA
         and template["records"] == ATTEMPT, "base template differs from attempt 12")
    records = Path(TARGET) if mode == "open" else run_dir / "records-dry-run"
    template.update(records=str(records), primary_output=str(records / "primary-recomputed-D-A39.json"),
                    result_output=str(records / "secondary-result.json"), primary_scores_output=str(records / "primary-scores.json"))
    template_ref = g2_exec.write_new(run_dir / "template.json", template)
    STATE["labels_path"] = template["labels"]["path"]
    inventory = list(base["inventory"])
    known = {x["path"] for x in inventory}
    for extra in (PRIMARY, PRIMARY_SCORES, MARKER):
        need(extra["path"] not in known and Path(extra["path"]).stat().st_size == extra["size_bytes"], f"inventory extra {extra['path']}")
        inventory.append({"path": extra["path"], "sha256": extra["sha256"], "size_bytes": extra["size_bytes"], "kind": "metadata"})
    if mode == "open":
        go = Path(approval_ref["path"])
        reviewer = {"reviewer_model": "human-approval", "reviewer_worker": "D-A39-approval-" + approval["approved_by"],
                    "reviewer_session": "go-file-" + approval_ref["sha256"][:16]}
    else:
        go = run_dir / "D-A39-DRY-RUN.txt"
        go.write_text("D-A39 dry run: every label-free step up to the label opening; no label read is authorized or performed.\n")
        reviewer = {"reviewer_model": "none-dry-run", "reviewer_worker": "D-A39-dry-run-driver",
                    "reviewer_session": "go-file-" + sha_file(go)[:16]}
    spec = {**base, "go_file": str(go), "work": str(run_dir / "work"), "template": template_ref, "inventory": inventory, "reviewer": reviewer,
            "d_a39": {"mode": mode, "base_spec": BASE_SPEC, "records": str(records), "approval": approval_ref}}
    return g2_exec.write_new(run_dir / "spec.json", spec)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--open-labels-D-A39", dest="open_labels", action="store_true")
    p.add_argument("--approval", type=Path)
    a = p.parse_args(argv)
    if a.dry_run == a.open_labels:
        raise SystemExit("REFUSED: exactly one of --dry-run / --open-labels-D-A39")
    if a.open_labels and a.approval is None:
        raise SystemExit("REFUSED: --open-labels-D-A39 requires --approval FILE")
    if a.dry_run and a.approval is not None:
        raise SystemExit("REFUSED: --approval belongs to --open-labels-D-A39")
    need("SLURM_JOB_ID" in os.environ, "run inside the Slurm allocation")
    mode = "open" if a.open_labels else "dry-run"
    STATE["mode"] = mode
    approval, approval_ref = (None, None)
    if mode == "open":
        approval, approval_ref = verify_approval(a.approval)
        STATE["approval_ok"] = True
        STATE["approval_ref"] = approval_ref
        need(not Path(TARGET).exists(), "D-A39 re-scoring records already exist")
    run_dir = Path(RUNS) / f"r2-rescore-D-A39-{mode}-{os.environ['SLURM_JOB_ID']}"
    run_dir.mkdir()
    STATE["run_dir"] = str(run_dir)
    spec_ref = stage(mode, run_dir, approval, approval_ref)
    STATE["spec_ref"] = spec_ref
    say(mode=mode, run_dir=str(run_dir), spec=spec_ref)

    install_checkpoint_wrap()
    import amend_wiring
    import r2_exec
    original_engage = amend_wiring.engage_runner

    def engage_runner(runner_module, freeze_raw):
        engaged = original_engage(runner_module, freeze_raw)
        original_run = runner_module.run

        def run(pref, aref):          # called by r2_exec.main after it installed every reviewed patch
            install_layer(runner_module)
            return original_run(pref, aref)
        runner_module.run = run
        STATE["runner"] = runner_module
        return engaged

    amend_wiring.engage_runner = engage_runner
    r2_exec.main(["--spec", spec_ref["path"]])
    if mode == "dry-run":
        need(STATE.get("ready_ref") is not None, "dry run did not reach the ready state")
        print(json.dumps({"d_a39_dry_run": "ready, labels not opened", "ready": STATE["ready_ref"]}), flush=True)


if __name__ == "__main__":
    main()
