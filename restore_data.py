"""Verify the release and rejoin large files. Run from any working directory."""
from pathlib import Path
import hashlib
import json
import os

root = Path(__file__).resolve().parent
manifest = json.loads((root / "MANIFEST.json").read_text())
for entry in manifest:
    p = root / entry["path"]
    if not p.is_file() or p.stat().st_size != entry["bytes"]:
        raise SystemExit(f"Missing or wrong-size release file: {entry['path']}")
    if hashlib.sha256(p.read_bytes()).hexdigest() != entry["sha256"]:
        raise SystemExit(f"Checksum mismatch: {entry['path']}")

shards = json.loads((root / "data/shards.json").read_text())
for entry in shards:
    dst = root / entry["path"]
    if dst.exists() and hashlib.sha256(dst.read_bytes()).hexdigest() == entry["sha256"]:
        continue
    tmp = dst.with_name(dst.name + ".restoring")
    digest = hashlib.sha256()
    with tmp.open("wb") as out:
        for name in entry["parts"]:
            with (root / name).open("rb") as part:
                while chunk := part.read(1024 * 1024):
                    out.write(chunk)
                    digest.update(chunk)
    if tmp.stat().st_size != entry["bytes"] or digest.hexdigest() != entry["sha256"]:
        tmp.unlink()
        raise SystemExit(f"Reassembly checksum mismatch: {entry['path']}")
    os.replace(tmp, dst)
(root / "work").mkdir(exist_ok=True)
print(f"Verified {len(manifest)} release files; restored {len(shards)} split files.")
