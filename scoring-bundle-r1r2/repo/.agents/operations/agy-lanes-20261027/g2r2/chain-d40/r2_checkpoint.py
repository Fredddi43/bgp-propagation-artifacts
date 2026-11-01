"""D-A37: persist every label-free preparation result of the R2 evaluation, so a rerun after any later refusal does not recompute them.

The pinned R2 evaluation prepares every family (origin, baseline, counts, five membership families, stable) in one process and keeps the
results only in memory: a refusal anywhere before the label join discards hours of work. `wrap` stores each preparation result with pickle
under CKPT_DIR keyed by a fingerprint of (stage name, every non-callable argument, the source of the in-process patch modules), and returns
the stored object when the fingerprint matches. A different seal, freeze, evidence document, arm set or patch code changes the key.
Stored results are label-free (no label table is opened before the label join); a loaded result skips the stage's reads and their
access-log rows, which are already in the log from the run that produced the checkpoint.
"""
import hashlib
import json
import os
import pickle
import shutil
from pathlib import Path

# Files whose content can change a stage's result: a patch to one stage must not invalidate the saved results of the others.
STAGE_FILES = {
    "origin": ("r2_parallel_origin.py", "r2_input_cache.py", "r2_fast_json.py"),
    "baseline": ("r2_input_cache.py",),
    "members": ("r2_float32_decision.py", "r2_input_cache.py"),
    "stable": ("r2_stable_persistence.py", "r2_input_cache.py"),
    "counts": (),
}
COMMON_FILES = ("r2_checkpoint.py",)
MIN_FREE = 150 << 30


PART_BYTES = 6 << 30   # the runner sets RLIMIT_FSIZE to 16 GiB for this process: every file stays well below it


class _RollingWriter:
    def __init__(self, base):
        self.base, self.index, self.size, self.stream = Path(base), 0, 0, None
        self._open()

    def _open(self):
        if self.stream:
            self.stream.close()
        self.stream = open(f"{self.base}.part{self.index:04d}", "wb")
        self.index += 1
        self.size = 0

    def write(self, data):
        view = memoryview(data)
        while len(view):
            room = PART_BYTES - self.size
            if room <= 0:
                self._open()
                room = PART_BYTES
            chunk = view[:room]
            self.stream.write(chunk)
            self.size += len(chunk)
            view = view[len(chunk):]
        return len(data)

    def close(self):
        if self.stream:
            self.stream.close()
        return self.index


class _RollingReader:
    def __init__(self, base, parts):
        self.paths = [Path(f"{base}.part{i:04d}") for i in range(parts)]
        self.index, self.stream = 0, open(self.paths[0], "rb")

    def read(self, n=-1):
        out = []
        while n != 0:
            data = self.stream.read(n if n and n > 0 else -1)
            if data:
                out.append(data)
                if n and n > 0:
                    n -= len(data)
                    if n == 0:
                        break
                    continue
            if self.index + 1 >= len(self.paths):
                break
            self.stream.close()
            self.index += 1
            self.stream = open(self.paths[self.index], "rb")
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


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=lambda o: "pickle:" + hashlib.sha256(pickle.dumps(o)).hexdigest(),
                                     separators=(",", ":")).encode()).hexdigest()


def code_fingerprint(directory=None, stage=None):
    here = Path(directory or Path(__file__).resolve().parent)
    names = COMMON_FILES + (STAGE_FILES.get(stage, ()) if stage else tuple(sorted({f for v in STAGE_FILES.values() for f in v})))
    return _digest({name: hashlib.sha256((here / name).read_bytes()).hexdigest() for name in names if (here / name).exists()})


def wrap(function, name, ckpt_dir, code_key):
    ckpt_dir = Path(ckpt_dir)

    def wrapped(*args, **kwargs):
        fingerprint = _digest({"stage": name, "code": code_fingerprint(stage=name),
                               "args": [a for a in args if not callable(a)], "kwargs": {k: v for k, v in kwargs.items() if not callable(v)}})
        base = ckpt_dir / f"{name}-{fingerprint[:24]}"
        manifest = Path(f"{base}.manifest.json")
        if manifest.is_file():
            info = json.loads(manifest.read_text())
            if info.get("fingerprint") != fingerprint:
                raise ValueError(f"checkpoint {manifest} does not match its key")
            result = pickle.load(_RollingReader(base, info["parts"]))
            print(json.dumps({"checkpoint": "loaded", "stage": name, "parts": info["parts"]}), flush=True)
            return result
        result = function(*args, **kwargs)
        try:
            ckpt_dir.mkdir(parents=True, exist_ok=True)
            if shutil.disk_usage(ckpt_dir).free > MIN_FREE:
                writer = _RollingWriter(base)
                pickle.dump(result, writer, protocol=5)
                parts = writer.close()
                tmp = Path(f"{base}.manifest.tmp")
                tmp.write_text(json.dumps({"fingerprint": fingerprint, "stage": name, "parts": parts}))
                os.replace(tmp, manifest)
                print(json.dumps({"checkpoint": "saved", "stage": name, "parts": parts}), flush=True)
            else:
                print(json.dumps({"checkpoint": "skipped-low-disk", "stage": name}), flush=True)
        except Exception as error:   # a failed save must never fail the evaluation
            print(json.dumps({"checkpoint": "save-failed", "stage": name, "error": repr(error)[:200]}), flush=True)
        return result

    wrapped._d_a37 = True
    return wrapped
