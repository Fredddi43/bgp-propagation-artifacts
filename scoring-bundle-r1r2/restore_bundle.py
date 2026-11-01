#!/usr/bin/env python3
"""Verify the published scoring bundle and restore its large files (Python 3.8+, standard library only).

usage: python3 restore_bundle.py           verify every published file, then join, decompress and check the large files
       python3 restore_bundle.py --check   verify everything, including every decompressed stream, and write nothing

Files larger than 7,000,000 bytes are published xz-compressed, split into numbered parts where still larger
(shards.json). Each restored file is checked against MANIFEST.json before it is written at its MANIFEST.json path.
"""
import hashlib
import json
import lzma
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
check_only = "--check" in sys.argv[1:]


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


published = json.loads((root / "PUBLISHED.json").read_text())
for entry in published:
    p = root / entry["path"]
    if not p.is_file() or p.stat().st_size != entry["bytes"]:
        raise SystemExit("Missing or wrong-size published file: " + entry["path"])
    if file_sha256(p) != entry["sha256"]:
        raise SystemExit("Checksum mismatch: " + entry["path"])

manifest = {e["path"]: e for e in json.loads((root / "MANIFEST.json").read_text())["items"]}
shards = json.loads((root / "shards.json").read_text())
sharded = {s["path"] for s in shards}
direct = {e["path"]: e for e in published}
for path, item in manifest.items():   # every bundle file is either published as is or restored from a shard
    if path not in sharded and (path not in direct or direct[path]["sha256"] != item["sha256"]):
        raise SystemExit("Bundle file neither published nor sharded: " + path)

restored = 0
for s in shards:
    item = manifest[s["path"]]
    if item["sha256"] != s["sha256"] or item["bytes"] != s["bytes"]:
        raise SystemExit("shards.json and MANIFEST.json disagree: " + s["path"])
    dst = root / s["path"]
    if not check_only and dst.is_file() and dst.stat().st_size == s["bytes"] and file_sha256(dst) == s["sha256"]:
        continue
    decomp, raw_digest, packed_digest, total = lzma.LZMADecompressor(), hashlib.sha256(), hashlib.sha256(), 0
    tmp = dst.with_name(dst.name + ".restoring")
    out = None
    if not check_only:
        dst.parent.mkdir(parents=True, exist_ok=True)
        out = tmp.open("wb")
    try:
        for name in s["parts"]:
            with (root / name).open("rb") as part:
                for chunk in iter(lambda: part.read(1 << 20), b""):
                    packed_digest.update(chunk)
                    data = decomp.decompress(chunk)
                    raw_digest.update(data)
                    total += len(data)
                    if out is not None:
                        out.write(data)
    finally:
        if out is not None:
            out.close()
    ok = (decomp.eof and packed_digest.hexdigest() == s["compressed_sha256"] and total == s["bytes"]
          and raw_digest.hexdigest() == s["sha256"])
    if not ok:
        if tmp.exists():
            tmp.unlink()
        raise SystemExit("Restored file does not match MANIFEST.json: " + s["path"])
    if not check_only:
        os.replace(tmp, dst)
    restored += 1
print(("Checked" if check_only else "Verified") + f" {len(published)} published files; "
      + ("checked" if check_only else "restored") + f" {restored} of {len(shards)} compressed files.")
