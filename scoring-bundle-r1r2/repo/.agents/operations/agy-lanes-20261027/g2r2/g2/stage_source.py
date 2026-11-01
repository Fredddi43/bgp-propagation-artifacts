#!/usr/bin/env python3
"""Stage a hash-pinned source root for the family runners. Every pin is checked; nothing unpinned is trusted.

Root reverted the reviewer amendment on the six pinned files (b9bc5467), so the WORKING TREE carries the pinned bytes and is
the default source. `--rev REV` stages from a git revision instead (use 6bebfc7c^ if the amendment is ever re-applied).
Staged: src/bgbench/**/*.py, every path in the family's pins.json / scientific-pins.json, and the runner's own
`SCIENCE = {path: sha256}` table (history/stable pin scripts/forecast_campaign.py etc. there, outside pins.json).
Writes the closure document {source_root, files} for plan['scientific_source_closure'].
`--final-root` is where the tree will live on the cluster (closure paths and source_root use it); copy with
`tar -C DEST -c . | ssh <BATCH_HOST> 'tar -C FINAL_ROOT -x'`.
"""
import argparse
import ast
import hashlib
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
_top = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--show-toplevel"], capture_output=True, text=True).stdout.strip()
assert Path(_top).resolve() == REPO, f"REPO heuristic wrong: {REPO} vs git toplevel {_top}"


def git_blob(rev, path):
    if rev is None:
        return (REPO / path).read_bytes()
    return subprocess.run(["git", "-C", str(REPO), "show", f"{rev}:{path}"], check=True, capture_output=True).stdout


def science_pins(family_dir):
    """The runner's literal SCIENCE table, if it has one."""
    runner = Path(family_dir) / "runner.py"
    if not runner.exists():
        return {}
    for node in ast.parse(runner.read_bytes()).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "SCIENCE" for t in node.targets):
            return ast.literal_eval(node.value)
    return {}


def stage(family_dirs, dest, final_root, rev=None, extra=()):
    dest, final_root = Path(dest), Path(final_root)
    if rev is None:
        paths = {str(p.relative_to(REPO)) for p in (REPO / "src/bgbench").rglob("*.py")}
    else:
        names = subprocess.run(["git", "-C", str(REPO), "ls-tree", "-r", "--name-only", rev, "src/bgbench"], check=True,
                               capture_output=True, text=True).stdout.split()
        paths = {n for n in names if n.endswith(".py")}
    paths.update(extra)
    expected = {}
    for fam in family_dirs:
        for rel, digest in science_pins(fam).items():
            paths.add(rel); expected[rel] = digest
    for fam in family_dirs:
        fam = Path(fam)
        for name in ("pins.json", "scientific-pins.json"):
            if (fam / name).exists():
                doc = json.loads((fam / name).read_bytes())
                for key, item in doc.items():
                    if isinstance(item, dict) and "path" in item:
                        paths.add(item["path"]); expected[item["path"]] = item["sha256"]
                    elif isinstance(item, str) and len(item) == 64:
                        paths.add(key); expected[key] = item
    files = []
    for rel in sorted(paths):
        data = git_blob(rev, rel)
        digest = hashlib.sha256(data).hexdigest()
        if rel in expected and expected[rel] != digest:
            raise SystemExit(f"{rel} at {rev} is {digest[:12]}, pinned {expected[rel][:12]}")
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        if rel.startswith("src/bgbench/"):
            files.append({"path": str(final_root / rel), "sha256": digest})
    if not any(f["path"].endswith("src/bgbench/forecast_custody.py") for f in files) or len(files) < 60:
        raise SystemExit(f"closure has {len(files)} bgbench files: wrong source tree/revision")
    closure = {"source_root": str(final_root), "files": files}
    (dest / "scientific-closure.json").write_text(json.dumps(closure, indent=2, sort_keys=True) + "\n")
    return closure


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--family-dir", action="append", required=True)
    p.add_argument("--dest", required=True)
    p.add_argument("--final-root", required=True)
    p.add_argument("--rev", default=None, help="git revision; default = working tree")
    p.add_argument("--extra", action="append", default=[], help="additional repo-relative pinned source")
    a = p.parse_args()
    c = stage(a.family_dir, a.dest, a.final_root, a.rev, a.extra)
    print(json.dumps({"files": len(c["files"]), "source_root": c["source_root"]}))
