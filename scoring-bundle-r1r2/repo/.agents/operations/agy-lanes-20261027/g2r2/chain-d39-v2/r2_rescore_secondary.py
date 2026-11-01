#!/usr/bin/env python3
"""D-A39: one disclosed re-scoring of the R2 secondary lanes (counts, five membership families, stable, origin, additional baselines).

Why. R2 attempt 12 (job 52700052) opened the label table once, wrote arms/000/attempt/primary.json (sha256 849e0645...) and
primary-scores.json, then failed in the membership consumer's score_membership on the float32/float64 edge of D-A36 (arm gru-d30-s2).
The pinned counts.evaluate_with_counts scores counts after primary and BEFORE membership, so attempt 12 had already computed the counts
family when membership crashed; what was never computed to completion, persisted or released is a complete secondary report.
<AUTHOR> approved (2026-10-30, D-A39) ONE disclosed second label read for the secondary lanes only;
primary.json stays THE primary result.

What this driver does. It runs the pinned R2 runner exactly as r2_exec.py does (r2_exec.main is called unchanged, so every reviewed
patch D-A26..D-A38 is installed by r2_exec itself, in its own order) and adds one layer, hooked at two points of r2_exec.main:
`amend_wiring.engage_runner` (to get the exec'd runner module) and the runner's `run` (called by r2_exec after it installed its
patches). The layer:
  * replaces the runner's `execute` (which accepts only arms/000/attempt): same bounds / same-filesystem / free-space / exclusive
    records checks, but the records directory is arms/000/rescore-secondary-D-A39 (open mode) and must not exist; arms/000/attempt,
    the one-opening marker, freeze, seal and labels are only read (through the Reader, hash-checked, logged), never written;
  * installs r2_float32_scoring.py (D-A39 patch) on the membership consumer;
  * points each secondary consumer's OWN `scoring` and `original` references (membership, and stable/origin/baseline `m`) at
    PRIVATE copies whose pure scorers are the r2_parallel_scoring adapters — the already-selected score_membership (membership:
    float32; the others float64) and per_event_rows — with fixed options max_workers 8 / min_parallel_rows 8192 / chunks_per_worker 4;
    shared bgbench modules, the primary evaluator and m.original.evaluate_new_period are never mutated, the wrappers are inert
    before the label, and the adapter hash plus options are recorded in ready.json and bound by the approval;
  * loads the attempt-12 preparation checkpoints (old single-file .pkl format; see LEGACY) after recomputing their fingerprint, and
    computes the origin preparation (its attempt-12 save failed at the 16 GiB RLIMIT_FSIZE) and saves it in the rolling format of
    r2_checkpoint.py with a free-space guard, so the label-opening run loads it;
  * binds the preparation bytes: every stage records the SHA256/size of the exact checkpoint bytes it was prepared from, at its
    canonical absolute path — the legacy .pkl hashed as it is read, every rolling part captured while writing (or, for a checkpoint
    the older code saved, hashed as it is read) plus a size-bounded manifest that must name the exact stage and fingerprint and a
    bounded, contiguous set of regular part files — the dry run records all nine bindings in ready.json, the approval binds that
    file, and every stage's name, fingerprint and artifact path/size/digest must match the approved dry run exactly (all nine
    receipts individually — the five membership families never collapsed by name — none missing or duplicated, byte-identical
    artifacts at identical paths, a rolling shadow of an attempt-12 checkpoint refused before loading, nothing recomputed: the
    label-opening run refuses a missing preparation before computing or saving it) before any label access;
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
    secondary-result.json is written with a header (D-A39, primary.json sha, label/seal/freeze sha). Completion additionally
    requires, against families fixed from the pinned runner/components call sites (never from what ran): exactly the nine expected
    family entries (counts, five membership families, stable, origin, additional_baselines) each scored once, each persisted result
    intact on disk (expected ordered regular part files, total byte length and concatenated SHA-256 matching its manifest) with no
    persist_error; the composition keys and covered-secondary-families the pinned call sites produce; and the recomputed primary
    and primary-scores canonically identical to attempt 12's except the D-A39 marker path / report path, with one score receipt.
    A family that raised stays honestly failed. The scientific blocking verdict is built before encoding, so secondary-result.json's
    header carries completion_gate.blocking; a separate exclusive completion.json then persists the FINAL gate, including any write
    failure, before the run reports success or refuses. If anything blocks, finish keeps every durable artifact (raw pickle, family
    files, completion.json, and secondary-result.json when it could be written) and raises CompletionRefused, so the job cannot
    report success; primary.json of attempt 12 stays THE primary result either way.

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
import re
import socket
import stat
import sys
import time
import traceback
from pathlib import Path, PurePosixPath

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
# .pkl writer), whose code_fingerprint reads r2_checkpoint.py FROM DISK at the START of each stage; the file was replaced at
# 06:09:23Z by the current version (sha 97382e4a...). The origin stage ran first and its save failed (observed 06:08:46Z); baseline
# started right after it, BEFORE the replacement, so its key hashes the old file and it is recomputed here (see the note in LEGACY).
# counts (saved 06:13:15Z), members and stable started after the replacement, so their fingerprint is exactly what the CURRENT
# r2_checkpoint computes (_digest of stage, code_fingerprint(stage), non-callable args); verified offline for counts (959aaa80fd44...).
# The origin stage is recomputed here as well (rolling save).
LEGACY = {
    # "baseline" is NOT an attempt-12 checkpoint here (2026-10-31, dry run 52714019 refused on it): attempt 12 computed the baseline
    # key at the START of that stage, right after the origin save failed and BEFORE r2_checkpoint.py was replaced at 06:09:23Z, so its
    # key hashes the old r2_checkpoint.py (baseline-ad753ced...); counts, members and stable started after 06:09:23Z and keep their
    # attempt-12 keys. Baseline is therefore prepared label-free in the dry run like origin (computed, rolling save, byte-bound) and
    # loaded from that rolling checkpoint by the label-opening run.
    "counts": {"counts-959aaa80fd4471fa978b3e43.pkl": 10972},
    "members": {"members-1dc1eba251a8c5065f29ebdd.pkl": 3898663813, "members-125c784dc89ccc5380d85442.pkl": 8758133323,
                "members-41d7a100dc90759763379813.pkl": 3352991403, "members-84ddd286f969b77b98ef221e.pkl": 5797143995,
                "members-51e89096eddb87691d10b61f.pkl": 772719845},
    "stable": {"stable-8b2ded7e985a2611c5bbe7e6.pkl": 1479268630},
}
EXPECTED_CALLS = {"origin": 1, "baseline": 1, "counts": 1, "members": 5, "stable": 1}

# Expected secondary families and composition keys, fixed from the pinned call sites in
# .agents/operations/newperiod-single-r2-persistence-20261024 (verified against those files on 2026-10-30, never derived from
# whatever families happened to run): compose.py FAMILIES = ('h1','h3','timing','history','ordinary') (line 16) and the
# composition result keys 'counts'/'membership' (one entry per family, line 82-85)/'stable' (line 86) with
# covered_secondary_families = ['counts', *FAMILIES, 'stable'] (line 87); runner.py evaluate() adds result['origin'] from the
# single origin.evaluate call over origin.consumer.FAMILIES = ('origin_change_invalid','origin_change_valid') (runner.py line 272,
# origin/consumer.py line 17), adds result['additional_baselines'] from the single baseline.evaluate call (runner.py line 273)
# and extends covered_secondary_families with ['additional_baselines', *origin.FAMILIES] (runner.py line 274). The isolation
# wrapper records each membership call as "membership-<family>" (prepared['family'], membership consumer.py line 327).
EXPECTED_MEMBERSHIP_FAMILIES = ("h1", "h3", "timing", "history", "ordinary")
EXPECTED_ORIGIN_STRATA = ("origin_change_invalid", "origin_change_valid")
EXPECTED_SECONDARY_KEYS = {"counts", "membership", "stable", "origin", "additional_baselines"}
EXPECTED_FAMILY_ENTRIES = ("additional_baselines", "counts", "membership-h1", "membership-h3", "membership-history",
                           "membership-ordinary", "membership-timing", "origin", "stable")
EXPECTED_COVERED_SECONDARY_FAMILIES = ["counts", *EXPECTED_MEMBERSHIP_FAMILIES, "stable", "additional_baselines",
                                       *EXPECTED_ORIGIN_STRATA]
CHECKPOINT_SHA = "97382e4abe67240152e5c01763eb970b0fc5c32eedfb77f0e7453d3dcb580be4"   # r2_checkpoint.py the keys depend on
SAVE_FREE_FLOOR = 200 << 30   # origin save aborts (parts removed) rather than take the shared volume below this
MANIFEST_MAX_BYTES = 1 << 20   # a manifest is fingerprints + stage + part digests/sizes: megabytes already mean malformed metadata
PARTS_MAX = 1024               # 1024 parts x PART_BYTES dwarfs the 16 GiB origin preparation: more is malformed metadata, not a checkpoint
DRY_PREFIX = "[D-A39 dry run, labels not opened] "
OPEN_PREFIX = "[D-A39 secondary re-score] "
LABEL_PREFIX = ("[D-A39 approved second label read, secondary lanes only; primary of record stays attempt/primary.json "
                "849e064518d1] ")
APPROVAL_FIELDS = {"deviation": "D-A39", "second_label_read_authorized": True, "scope": "secondary lanes only",
                   "labels_sha256": LABELS_SHA, "seal_sha256": SEAL_SHA, "freeze_sha256": FREEZE_SHA,
                   "primary_json_sha256": PRIMARY["sha256"], "records": TARGET}
PARALLEL_ADAPTER_OPTIONS = {"max_workers": 8, "min_parallel_rows": 8192, "chunks_per_worker": 4}   # fixed; recorded and dry-run-bound

STATE = {"mode": None, "stages": [], "families": [], "float32_installs": 0, "refuse_installs": 0, "d39_marker_written": False,
         "pre_label_passed": False, "registry": {k: [] for k in EXPECTED_CALLS}, "binding": None, "approved_binding": None,
         "parallel_installs": [], "t0": time.time()}


class DryRunReady(BaseException):
    """Raised at the D-A39 marker write in dry-run mode: every label-free step is done, the label table is not opened."""


class LabelGuard(BaseException):
    pass


class CompletionRefused(BaseException):
    """finish wrote every durable artifact it could, but the completion gate did not pass: the run must not report success."""


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
    return result, {"format": "attempt12-single-pkl",
                    "artifacts": [{"path": str(path), "bytes": stream.n, "sha256": stream.h.hexdigest()}]}


class _HashingRollingReader:
    """Reads r2_checkpoint's rolling parts with the same read/readinto/readline semantics as its _RollingReader, hashing every
    part's bytes as they are read: a rolling checkpoint saved earlier (by this version or by the older code) turns into a verified
    byte receipt while it is unpickled, with no second pass over the multi-GiB output and nothing recomputed. Every part must be
    an existing regular file within the admitted part size before the first byte of anything is opened."""

    def __init__(self, base, parts, part_ceiling):
        self.paths = [Path(f"{base}.part{i:04d}") for i in range(parts)]
        self.streams = []
        for path in self.paths:
            need(path.is_file(), f"rolling checkpoint is missing {path}")
            status = path.stat()
            need(stat.S_ISREG(status.st_mode), f"rolling checkpoint part {path} is not a regular file")
            need(status.st_size <= part_ceiling, f"rolling checkpoint part {path} exceeds the admitted part size {part_ceiling}")
            self.streams.append(_HashingReader(path.open("rb")))
        self.index = 0

    def read(self, n=-1):
        out = []
        while n != 0:
            stream = self.streams[self.index]
            data = stream.read(n if n and n > 0 else -1)
            if data:
                out.append(data)
                if n and n > 0:
                    n -= len(data)
                    if n == 0:
                        break
                    continue
            if self.index + 1 >= len(self.streams):
                break
            stream.stream.close()
            self.index += 1
        return b"".join(out)

    def readinto(self, buffer):
        data = self.read(len(buffer))
        buffer[:len(data)] = data
        return len(data)

    def readline(self, limit=-1):
        out = bytearray()
        while True:
            byte = self.read(1)
            if not byte:
                break
            out += byte
            if byte == b"\n" or (limit and 0 < limit <= len(out)):
                break
        return bytes(out)

    def close(self):
        for stream in self.streams:
            stream.stream.close()

    def receipts(self):
        return [{"path": str(p), "sha256": s.h.hexdigest(), "bytes": s.n} for p, s in zip(self.paths, self.streams)]


def load_rolling(r2_checkpoint, base, name, fingerprint):
    """Load a rolling checkpoint (parts + manifest in r2_checkpoint's format; old manifests carry only fingerprint, stage and
    part count, new ones also record every part's sha256/size). The manifest is size-bounded, must name this exact stage and
    fingerprint, and must record a finite part count before any part is opened; every part must be a regular file within the
    admitted part size. Every part and the manifest are hashed while being read, so the result always comes with its byte
    receipt; a manifest that records part digests must be met by exactly those bytes."""
    manifest_path = Path(f"{base}.manifest.json")
    need(manifest_path.stat().st_size <= MANIFEST_MAX_BYTES,
         f"checkpoint manifest {manifest_path} is larger than the {MANIFEST_MAX_BYTES}-byte manifest ceiling")
    manifest_raw = manifest_path.read_bytes()
    manifest = json.loads(manifest_raw)
    need(isinstance(manifest, dict), f"checkpoint manifest {manifest_path} is not a JSON object")
    need(manifest.get("stage") == name, f"checkpoint {manifest_path} records stage {manifest.get('stage')!r}, not {name!r}")
    need(manifest.get("fingerprint") == fingerprint, f"checkpoint {manifest_path} does not match its key")
    parts = manifest.get("parts")
    need(isinstance(parts, int) and not isinstance(parts, bool) and 0 < parts <= PARTS_MAX,
         f"{manifest_path} records {parts!r} parts: must be an integer from 1 to {PARTS_MAX}")
    reader = _HashingRollingReader(base, parts, r2_checkpoint.PART_BYTES)
    try:
        result = pickle.load(reader)
        need(reader.read() == b"", f"{base} has trailing bytes after the pickled result")
        receipts = reader.receipts()
    finally:
        reader.close()
    artifacts = [{"path": str(manifest_path), "sha256": hashlib.sha256(manifest_raw).hexdigest(), "bytes": len(manifest_raw)}] + receipts
    recorded, recorded_sizes = manifest.get("parts_sha256"), manifest.get("parts_sizes")
    if recorded is not None:
        need(isinstance(recorded, list) and len(recorded) == parts
             and all(receipts[i]["sha256"] == recorded[i] for i in range(parts)),
             f"rolling checkpoint parts differ from the digests their manifest {manifest_path} records")
    if recorded_sizes is not None:
        need(isinstance(recorded_sizes, list) and len(recorded_sizes) == parts
             and all(receipts[i]["bytes"] == recorded_sizes[i] for i in range(parts)),
             f"rolling checkpoint parts differ from the sizes their manifest {manifest_path} records")
    for receipt in receipts:
        need(Path(receipt["path"]).stat().st_size == receipt["bytes"], f"{receipt['path']} changed while it was being read")
    return result, {"format": "rolling-read", "manifest": str(manifest_path), "parts": parts,
                    "manifest_attests_parts": recorded is not None, "artifacts": artifacts}


def save_rolling(r2_checkpoint, base, name, fingerprint, result):
    """r2_checkpoint's rolling format (parts + manifest, loadable by its _RollingReader and wrap), with a free-space check before
    every part. The sha256/size of every part is captured while writing — the giant saved output is never re-read or re-hashed —
    and recorded in the manifest (extra manifest keys are ignored by r2_checkpoint); the manifest's own sha256/size go into the
    returned receipt so the run can bind the exact bytes it saved."""
    tapped = []

    class Tapping:
        def __init__(self, stream):
            self.stream, self.h, self.n = stream, hashlib.sha256(), 0

        def write(self, data):
            self.stream.write(data)
            self.h.update(data)
            self.n += len(data)
            return len(data)

        def close(self):
            self.stream.close()

    class Guarded(r2_checkpoint._RollingWriter):
        def _open(self):
            free = os.statvfs(Path(base).parent)
            need(free.f_bavail * free.f_frsize - r2_checkpoint.PART_BYTES > SAVE_FREE_FLOOR, "free space below the save floor")
            super()._open()
            self.stream = Tapping(self.stream)
            tapped.append(self.stream)

    writer = None
    try:
        writer = Guarded(base)
        pickle.dump(result, writer, protocol=5)
        parts = writer.close()
        need(len(tapped) == parts, f"{len(tapped)} part streams were written for {parts} parts")
        manifest_doc = json.dumps({"fingerprint": fingerprint, "stage": name, "parts": parts,
                                   "parts_sha256": [t.h.hexdigest() for t in tapped], "parts_sizes": [t.n for t in tapped]})
        tmp = Path(f"{base}.manifest.tmp")
        tmp.write_text(manifest_doc)
        os.replace(tmp, f"{base}.manifest.json")
        need(sum(Path(f"{base}.part{i:04d}").stat().st_size for i in range(parts)) == sum(t.n for t in tapped),
             "saved part sizes differ from the bytes that were written")
        manifest_raw = manifest_doc.encode()
        artifacts = [{"path": f"{base}.manifest.json", "sha256": hashlib.sha256(manifest_raw).hexdigest(), "bytes": len(manifest_raw)}]
        artifacts += [{"path": f"{base}.part{i:04d}", "sha256": t.h.hexdigest(), "bytes": t.n} for i, t in enumerate(tapped)]
        return {"status": "saved", "manifest": f"{base}.manifest.json", "parts": parts, "bytes": sum(t.n for t in tapped),
                "artifacts": artifacts}
    except Exception as error:   # a failed save never fails the run; partial parts are removed
        if writer is not None and writer.stream:
            writer.stream.close()
        for part in Path(base).parent.glob(Path(base).name + ".part*"):
            part.unlink()
        return {"status": "save-failed", "error": repr(error)[:300]}


def stage_binding(info):
    """One stage's byte binding: its exact name and fingerprint plus the sha256/size of every artifact it was prepared from (the
    attempt-12 .pkl, or the manifest plus every rolling part). Artifact entries bind the CANONICAL ABSOLUTE path, size and digest:
    receipts at different directories never match, a rolling receipt must carry exactly one manifest and the contiguous ordered
    parts it names, paths may not repeat, and a stage that cannot name the exact bytes (and place) it came from is never ready
    and never opens a label."""
    need(isinstance(info, dict) and isinstance(info.get("stage"), str) and isinstance(info.get("fingerprint"), str)
         and re.fullmatch(r"[0-9a-f]{64}", info["fingerprint"]), f"stage entry without a name or fingerprint: {str(info)[:160]}")
    checkpoint = info.get("checkpoint")
    need(isinstance(checkpoint, dict) and isinstance(checkpoint.get("format"), str),
         f"stage {info['stage']} does not bind the bytes it was prepared from")
    artifacts = checkpoint["artifacts"] if isinstance(checkpoint.get("artifacts"), list) else []
    need(artifacts, f"stage {info['stage']} binds no checkpoint bytes")
    entries, paths = [], []
    for artifact in artifacts:
        need(isinstance(artifact, dict) and isinstance(artifact.get("path"), str)
             and PurePosixPath(artifact["path"]).is_absolute() and str(PurePosixPath(artifact["path"])) == artifact["path"]
             and isinstance(artifact.get("sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", artifact["sha256"])
             and isinstance(artifact.get("bytes"), int) and not isinstance(artifact["bytes"], bool) and artifact["bytes"] >= 0,
             f"stage {info['stage']} binds an incomplete artifact or a non-canonical absolute path: {str(artifact)[:160]}")
        paths.append(artifact["path"])
        entries.append(f"{artifact['path']}|{artifact['bytes']}|{artifact['sha256']}")
    need(len(set(paths)) == len(paths), f"stage {info['stage']} binds a duplicate artifact path")
    entries.sort()
    if checkpoint["format"] == "attempt12-single-pkl":
        need(len(artifacts) == 1 and paths[0].endswith(".pkl"), f"stage {info['stage']}: an attempt-12 checkpoint is exactly one .pkl")
    else:
        need(checkpoint["format"] in ("rolling-read", "rolling-saved"), f"stage {info['stage']}: unknown checkpoint format")
        manifests = [p for p in paths if p.endswith(".manifest.json")]
        need(len(manifests) == 1, f"stage {info['stage']}: a rolling checkpoint binds exactly one manifest, found {len(manifests)}")
        parts = sorted(p for p in paths if p != manifests[0])
        stem = manifests[0][: -len(".manifest.json")]
        need(0 < len(parts) <= PARTS_MAX and parts == [f"{stem}.part{i:04d}" for i in range(len(parts))],
             f"stage {info['stage']}: rolling parts are not the 1..{PARTS_MAX} contiguous parts {stem}.part0000.. named by {manifests[0]}")
    return f"{info['stage']}|{info['fingerprint']}|" + ",".join(entries)


def binding_of(stages):
    """The run's full preparation byte binding: every stage name, fingerprint and artifact digest, canonically ordered and hashed.
    Exactly the nine preparation calls (origin, baseline, counts, five membership families with five distinct fingerprints, stable),
    every attempt-12 lane loaded from its attempt-12 checkpoint."""
    items = sorted(stage_binding(s) for s in stages)
    counts = {}
    for s in stages:
        counts[s["stage"]] = counts.get(s["stage"], 0) + 1
    need(counts == EXPECTED_CALLS, f"stages differ from the expected calls: {counts}")
    members = {s["fingerprint"] for s in stages if s["stage"] == "members"}
    need(len(members) == EXPECTED_CALLS["members"], f"the membership families must carry {EXPECTED_CALLS['members']} distinct fingerprints, got {len(members)}")
    attempt12 = [s for s in stages if s.get("stage") in LEGACY]   # EVERY receipt, never one entry collapsed per stage name
    not_legacy = sorted(f"{s.get('stage')}:{s.get('fingerprint')[:12]}:{s.get('source')}" for s in attempt12
                        if s.get("source") != "checkpoint-attempt12")
    need(not not_legacy, f"every attempt-12 lane receipt (all {EXPECTED_CALLS['members']} membership families included) must "
                         f"load from its attempt-12 checkpoint, violating receipts: {not_legacy}")
    return items, hashlib.sha256("\n".join(items).encode()).hexdigest()


def install_checkpoint_wrap():
    import r2_checkpoint
    need(hashlib.sha256(Path(r2_checkpoint.__file__).read_bytes()).hexdigest() == CHECKPOINT_SHA,
         "r2_checkpoint.py changed: the attempt-12 checkpoint keys would not be recomputed")

    def wrap(function, name, ckpt_dir, code_key):
        def wrapped(*args, **kwargs):
            started = time.time()
            fingerprint = r2_checkpoint._digest({"stage": name, "code": r2_checkpoint.code_fingerprint(stage=name),
                                                 "args": [a for a in args if not callable(a)],
                                                 "kwargs": {k: v for k, v in kwargs.items() if not callable(v)}})
            base = Path(ckpt_dir) / f"{name}-{fingerprint[:24]}"
            info = {"stage": name, "fingerprint": fingerprint}
            need(not (name in LEGACY and Path(f"{base}.manifest.json").is_file()),
                 f"a rolling checkpoint at {base}.manifest.json would shadow the attempt-12 checkpoint of stage {name}: refused before loading")
            if Path(f"{base}.manifest.json").is_file():
                result, checkpoint = load_rolling(r2_checkpoint, base, name, fingerprint)   # every byte hashed as it is unpickled
                info.update(source="checkpoint-rolling", checkpoint=checkpoint)
            elif Path(f"{base}.pkl").is_file():
                result, checkpoint = load_legacy(Path(f"{base}.pkl"), name, fingerprint)     # every byte hashed as it is unpickled
                info.update(source="checkpoint-attempt12", checkpoint=checkpoint)
            else:
                need(name not in LEGACY, f"no attempt-12 checkpoint for stage {name} at {base}.pkl: inputs or code differ")
                need(STATE["mode"] != "open", f"open mode refuses to recompute stage {name}: no checkpoint at {base}.pkl or "
                     f"{base}.manifest.json — the preparation is refused before anything is computed or saved")
                result = function(*args, **kwargs)
                save = save_rolling(r2_checkpoint, base, name, fingerprint, result)          # every byte hashed as it is written
                info.update(source="computed", save=save)
                if save["status"] == "saved":
                    info["checkpoint"] = {"format": "rolling-saved", "manifest": save["manifest"], "artifacts": save["artifacts"]}
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


def install_parallel_adapters(consumer, lane):
    """Point ONE secondary consumer's own `scoring` and `original` references at PRIVATE copies whose
    score_membership / per_event_rows are the r2_parallel_scoring adapters (review-parallel-r2 scope).

    The shared bgbench modules, the primary evaluator and `m.original.evaluate_new_period` are never
    mutated (only the consumer's attribute is rebound); membership's copy wraps the ALREADY-selected
    float32 score_membership, origin/stable/baseline keep float64 scoring. Inert before the label: these
    functions run only in post-join scoring. Idempotent per module; every new wrap is recorded.
    Options are the fixed PARALLEL_ADAPTER_OPTIONS; the adapter file is hashed in common_record and
    bound by verify_approval."""
    import r2_parallel_scoring
    for attribute, factory in (("scoring", r2_parallel_scoring.parallel_scoring_module),
                               ("original", r2_parallel_scoring.parallel_original_module)):
        module = getattr(consumer, attribute)
        private = factory(module, **PARALLEL_ADAPTER_OPTIONS)
        if private is not module:
            setattr(consumer, attribute, private)
            STATE["parallel_installs"].append(f"{lane}.{attribute}")


def install_layer(runner):
    import r2_float32_scoring
    marker_class = make_marker_class(pre_label)
    r2exec_scientific_modules = runner.scientific_modules        # r2_exec's wrapper (installs module.components when called)

    def scientific_modules(plan):
        evaluator, custody = r2exec_scientific_modules(plan)
        r2exec_components = runner.components

        def components():
            loaded = r2exec_components()
            install_parallel_adapters(loaded["origin"].m, "origin")
            install_parallel_adapters(loaded["baseline"].m, "baseline")
            composition = loaded["composition"]
            inner = composition.components                       # r2_exec's composition_components (D-A36/D-A38/D-A37)
            if not getattr(inner, "_d_a39", False):
                def composition_components():
                    modules = inner()
                    r2_float32_scoring.patch(modules["membership"])     # selected float32 scoring FIRST
                    install_parallel_adapters(modules["membership"], "membership")   # then private parallel wrappers of it
                    install_parallel_adapters(modules["stable"].m, "stable")
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
    attempt12 = [s for s in STATE["stages"] if s.get("stage") in LEGACY]   # EVERY receipt, never one entry collapsed per stage name
    need(all(s.get("source") == "checkpoint-attempt12" for s in attempt12),
         f"attempt-12 checkpoints not all used: {[(s.get('stage'), s.get('fingerprint')[:12], s.get('source')) for s in attempt12 if s.get('source') != 'checkpoint-attempt12']}")
    items, binding = binding_of(STATE["stages"])   # every stage name, fingerprint and artifact digest of this run
    STATE["binding"] = {"sha256": binding, "items": items}
    if STATE["mode"] == "open":
        # No label access until this exact comparison against the approved dry run's ready stages passes.
        approved = STATE.get("approved_binding")
        need(approved is not None, "the approved dry-run checkpoint binding is absent")
        need(all(s.get("source") != "computed" for s in STATE["stages"]),
             "the label-opening run recomputed a preparation instead of loading the checkpoint the dry run verified")
        if binding != approved["sha256"]:
            differ = [d for d, r in zip(approved["items"], items) if d != r] or ["the stage sets themselves differ"]
            need(False, "preparation bytes differ from the approved dry run: " + json.dumps(differ[:4])[:1500])
    say(checkpoint_binding={"sha256": binding, "stages": len(items), "compared_with_dry_run": STATE["mode"] == "open"})
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

def make_guarded_consume(consume):
    """The reader.consume replacement installed for the run: a label read is refused outside open mode, and refused in open mode
    until the D-A39 marker exists and pre_label (which includes the exact dry-run byte-binding comparison) has passed."""

    def guarded_consume(item, purpose, *, hash_only=False):
        if item["kind"] == "label":
            if STATE["mode"] != "open":
                raise LabelGuard("D-A39 dry run: label read refused")
            need(STATE["d39_marker_written"] and STATE["pre_label_passed"], "label read before the D-A39 marker")
        return consume(item, purpose, hash_only=hash_only)
    return guarded_consume


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
    reader.consume = make_guarded_consume(reader.consume)
    score_receipts = []
    try:
        result = runner.evaluate(plan, reader, original, custody, runner.components(), score_receipts=score_receipts)
    except DryRunReady:
        return dry_run_ready(runner, plan, reader, records)
    need(STATE["mode"] == "open", "evaluation completed outside open mode")
    return finish(runner, plan, reader, records, result, score_receipts)


def common_record(plan, reader):
    import r2_float32_scoring
    import r2_parallel_scoring
    log_now = Path(plan["access_log"]).stat().st_size
    return {"job_id": os.environ.get("SLURM_JOB_ID"), "node": socket.gethostname(), "elapsed_seconds": round(time.time() - STATE["t0"], 1),
            "run_dir": STATE["run_dir"], "spec": STATE["spec_ref"], "labels": plan["labels"], "seal": plan["seal"], "freeze": plan["freeze"],
            "primary_of_record": PRIMARY, "attempt12_marker": {**MARKER, "record": STATE.get("attempt12_marker_record")},
            "target_records": TARGET, "stages": STATE["stages"], "checkpoint_binding": STATE.get("binding"),
            "decision_check": STATE.get("decision_check"),
            "float32_scoring": {"module": ref(r2_float32_scoring.__file__), "installs": STATE["float32_installs"],
                                "old": r2_float32_scoring.OLD, "new": r2_float32_scoring.NEW},
            "refuse_second_opening_installs": STATE["refuse_installs"], "driver": ref(__file__),
            "parallel_scoring": {"module": ref(r2_parallel_scoring.__file__), "options": dict(PARALLEL_ADAPTER_OPTIONS),
                                 "hard_cap": r2_parallel_scoring.MAX_WORKERS, "installs": list(STATE["parallel_installs"]),
                                 "scope": "private secondary-consumer copies only; shared bgbench, primary evaluator and "
                                          "m.original.evaluate_new_period untouched; inert before the label"},
            "code": {name: ref(HERE / name) for name in ("r2_exec.py", "r2_checkpoint.py", "r2_parallel_origin.py", "r2_float32_decision.py",
                                                         "r2_stable_persistence.py", "r2_input_cache.py", "r2_fast_authorize.py",
                                                         "r2_fast_json.py", "r2_parallel_scoring.py", "amend_wiring.py", "d60_only.py")},
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
        out = {}
        for k, v in value.items():
            sk = k if isinstance(k, str) else str(k)
            if sk in out:   # str(k1) == str(k2): writing would silently drop one entry — refuse instead of inventing a document
                raise ValueError(f"stringifying dict keys would collide: {sk!r} from {k!r} and another key")
            out[sk] = _stringify_keys(v)
        return out
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


def _parts_intact(directory, name, persisted):
    """The persisted bytes themselves, not just their names: the expected ordered part files (name.pkl.part0000, part0001, ...)
    must exist as regular files, their total length must equal the manifest byte count, and the SHA-256 of their concatenation
    must equal the manifest digest. A truncated, same-size mutated or wrongly named part is not a persisted result."""
    try:
        digest, total = hashlib.sha256(), 0
        for index in range(persisted["parts"]):
            part = Path(directory) / f"{name}.pkl.part{index:04d}"
            if not stat.S_ISREG(os.lstat(part).st_mode):
                return False
            total += os.lstat(part).st_size
            with part.open("rb") as stream:
                for block in iter(lambda: stream.read(1 << 24), b""):
                    digest.update(block)
        return total == persisted["bytes"] and digest.hexdigest() == persisted["sha256_of_concatenated_parts"]
    except OSError:
        return False


def _families_problems(records):
    """Gate the isolation-wrapper entries against the pinned EXPECTED_FAMILY_ENTRIES.

    Exactly the pinned families, each exactly once, honestly scored, each durably persisted with its manifest present on disk
    and matching the reported manifest. A family fails only when its scoring call raised (wrapper status 'failed', kept exactly
    as recorded); unavailable/no_input/censored bookkeeping inside a successfully scored family is science, not a family
    failure, and is never reinterpreted here."""
    entries = STATE["families"]
    names = [e["family"] for e in entries]
    problems = {k: [] for k in ("missing", "duplicate", "unexpected", "failed", "persist_error", "not_persisted")}
    for name in EXPECTED_FAMILY_ENTRIES:
        if names.count(name) == 0:
            problems["missing"].append(name)
        elif names.count(name) > 1:
            problems["duplicate"].append(name)
    problems["unexpected"] = sorted({n for n in names if n not in EXPECTED_FAMILY_ENTRIES})
    for entry in entries:
        name = entry["family"]
        if entry.get("status") != "scored":
            problems["failed"].append(name)
        if "persist_error" in entry:
            problems["persist_error"].append(name)
            continue
        persisted = entry.get("persisted")
        ok = (isinstance(persisted, dict) and type(persisted.get("parts")) is int and persisted["parts"] >= 1
              and type(persisted.get("bytes")) is int and persisted["bytes"] > 0 and persisted.get("name") == name
              and isinstance(persisted.get("sha256_of_concatenated_parts"), str))
        if ok:   # the manifest must exist and match the report, and the part bytes must exist as described (no glob shortcut)
            try:
                directory = Path(records) / "families"
                ok = json.loads((directory / f"{name}.manifest.json").read_bytes()) == persisted
            except Exception:
                ok = False
            if ok:
                ok = _parts_intact(directory, name, persisted)
        if not ok:
            problems["not_persisted"].append(name)
    return problems


def _composition_problems(result):
    """The composed result must carry the keys the pinned runner/components call sites produce, membership keyed by the
    five pinned families, and the covered-secondary-families list they build."""
    problems = {"missing_key": [], "membership_families": [], "covered_secondary_families": []}
    for key in sorted(EXPECTED_SECONDARY_KEYS):
        if key not in result:
            problems["missing_key"].append(key)
    if "membership" in result:
        membership = result["membership"]
        if not isinstance(membership, dict) or set(membership) != set(EXPECTED_MEMBERSHIP_FAMILIES):
            problems["membership_families"].append(sorted(map(str, membership)) if isinstance(membership, dict)
                                                    else type(membership).__name__)
    if result.get("covered_secondary_families") != EXPECTED_COVERED_SECONDARY_FAMILIES:
        problems["covered_secondary_families"].append(result.get("covered_secondary_families"))
    return problems


def _primary_equality_problems(comparison, score_receipts):
    """The recomputation is a consistency check: it must equal attempt 12 canonically, except the D-A39 marker path in
    primary.json and the recomputed-report path in primary-scores.json, and exactly one score sidecar receipt must exist."""
    problems = {}
    if comparison.get("canonical_identical_except_unblinded_marker") is not True:
        problems["primary_identical_except_marker"] = comparison.get("canonical_identical_except_unblinded_marker")
    scores = comparison.get("scores") or {}
    if scores.get("canonical_identical_except_primary_report_path") is not True:
        problems["scores_identical_except_report_path"] = scores.get("canonical_identical_except_primary_report_path")
    if len(score_receipts) != 1:
        problems["score_receipts"] = len(score_receipts)
    return problems


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
    family_problems = _families_problems(records)
    composition_problems = _composition_problems(result)
    comparison = report.get("primary_comparison") or {}
    primary_problems = _primary_equality_problems(comparison, score_receipts)
    blocking = {f"families_{k}": v for k, v in family_problems.items() if v}          # scientific verdict, built BEFORE encoding
    blocking.update({f"composition_{k}": v for k, v in composition_problems.items() if v})
    blocking.update(primary_problems)
    if errors:
        blocking["write_errors"] = list(errors)
    gate = {"expected_families": list(EXPECTED_FAMILY_ENTRIES), "families": family_problems,
            "composition": composition_problems, "primary_equality": primary_problems,
            "blocking": dict(blocking), "errors": list(errors)}
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
                  "completion_gate": gate,
                  "json_value_notes": counts, "outcome_release_authorized": False}
        document = {"header": header, "secondary": secondary}
        try:
            encoded = json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=True, default=_default)
        except TypeError:   # a non-string/mixed-type dict key: write every key as str(key), and say so (collisions refuse)
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
    if errors:   # a result document cannot describe its own write failure: the final verdict goes to the completion record
        blocking["write_errors"] = list(errors)
    failed = [f["family"] for f in STATE["families"] if f.get("status") != "scored"]
    completion = {"kind": "newperiod_secondary_rescore_completion_D-A39_v1", "deviation": "D-A39",
                  "passed": not blocking, "blocking": dict(blocking), "errors": list(errors),
                  "records": str(records), "label_reads": reader.label_reads, "job_id": os.environ.get("SLURM_JOB_ID"),
                  "secondary_result": report.get("secondary_result"), "raw_result": report.get("raw_result"),
                  "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "outcome_release_authorized": False}
    completion_file = Path(records) / "completion.json"
    completion_receipt = None
    try:   # exclusive, once: the FINAL completion gate (including blocking) is durable before the run reports or refuses
        with os.fdopen(os.open(completion_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
            json.dump(completion, stream, sort_keys=True, default=str)
            stream.flush()
            os.fsync(stream.fileno())
        completion_receipt = {"path": str(completion_file), "sha256": sha_file(completion_file), "bytes": completion_file.stat().st_size}
    except Exception as error:
        errors.append("completion.json: " + repr(error)[:300])
        blocking["write_errors"] = list(errors)
    gate["blocking"] = dict(blocking)
    gate["errors"] = list(errors)
    report["completion_gate"] = gate
    report["completion"] = completion_receipt
    say(completion=gate, completion_file=completion_receipt, secondary_result=report.get("secondary_result"),
        raw_result=report.get("raw_result"))
    if blocking:   # durable raw/family artifacts, (if writable) secondary-result.json and completion.json stay on disk; the run refuses
        raise CompletionRefused("D-A39 completion refused: " + json.dumps(blocking, sort_keys=True, default=str)[:4000]
                                + f"; durable records under {records}")
    return {"passed": True, "deviation": "D-A39", "records": str(records),
            "label_reads": reader.label_reads, "families": STATE["families"], "failed_families": failed, "errors": errors,
            "completion_gate": gate, "completion": completion_receipt,
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
    import r2_parallel_scoring
    need(ready["parallel_scoring"]["module"]["sha256"] == sha_file(r2_parallel_scoring.__file__), "parallel scoring adapter changed since the dry run")
    need(ready["parallel_scoring"]["options"] == PARALLEL_ADAPTER_OPTIONS and ready["parallel_scoring"]["hard_cap"] == r2_parallel_scoring.MAX_WORKERS,
         "parallel scoring options differ from the fixed ones recorded by the dry run")
    need(all(ready["code"][n]["sha256"] == sha_file(HERE / n) for n in ready["code"]), "chain code changed since the dry run")
    # the approval binds the preparation bytes: recompute the dry run's stage/fingerprint/artifact binding from its ready record
    items, binding = binding_of(ready.get("stages") or [])
    stored = ready.get("checkpoint_binding")
    need(isinstance(stored, dict) and stored.get("sha256") == binding and stored.get("items") == items,
         "the dry run's checkpoint binding differs from its own stage records")
    STATE["approved_binding"] = {"sha256": binding, "items": items, "ready": dry}
    return approval, {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "checkpoint_binding_sha256": binding}


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
