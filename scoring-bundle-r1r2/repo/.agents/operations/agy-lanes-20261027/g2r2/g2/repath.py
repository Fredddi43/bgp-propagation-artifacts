#!/usr/bin/env python3
"""Rewrite a path PREFIX inside generated plan/spec/template JSON files (paths only, never shas).

Used when a generator is run with a local copy of the publication namespace but the artifacts will execute from
the cluster path (or a rehearsal shadow): the bytes at the new path are identical (scp-verified), only the
embedded strings change. Refuses to touch files whose *contents hash into another document* (specs are read,
not hash-pinned; templates/arms ARE hash-pinned BY the spec at execution time — g2_exec re-hashes the template
file bytes, which this does not change; the freeze/admission/closure refs keep their real shas).
usage: repath.py --dir DIR --from PREFIX --to PREFIX [--glob '*.json']
"""
import argparse
import json
from pathlib import Path


def walk_edit(node, src, dst):
    n = 0
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, str):
                if k == "path" and v.startswith(src):
                    node[k] = dst + v[len(src):]
                    n += 1
            else:
                n += walk_edit(v, src, dst)
    elif isinstance(node, list):
        for v in node:
            n += walk_edit(v, src, dst)
    return n


def fix_refs(node, root, local_root=None):
    """Any {path,sha256} ref pointing INTO the repathed dir must carry the post-edit bytes' sha.

    When the specs embed CLUSTER paths for files generated locally (q10: {STAGE}/<family>/templates/...),
    pass --map CLUSTERPREFIX=LOCALDIR so the local files are hashed for those refs."""
    n = 0
    if isinstance(node, dict):
        p, s = node.get("path"), node.get("sha256")
        if isinstance(p, str) and isinstance(s, str) and len(s) == 64 and p.startswith(root):
            lp = Path(local_root.rstrip("/") + "/" + p[len(root):]) if local_root else Path(p)
            if lp.is_file():
                import hashlib
                d = hashlib.sha256(lp.read_bytes()).hexdigest()
                if d != s:
                    node["sha256"] = d
                    n += 1
        for v in node.values():
            n += fix_refs(v, root, local_root)
    elif isinstance(node, list):
        for v in node:
            n += fix_refs(v, root, local_root)
    return n


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dir", type=Path, required=True)
    p.add_argument("--frm", required=True)
    p.add_argument("--to", required=True)
    p.add_argument("--map", dest="mapref", default=None,
                   help="CLUSTERPREFIX=LOCALDIR: hash LOCALDIR files for refs whose path starts with CLUSTERPREFIX")
    p.add_argument("--glob", default="*.json")
    a = p.parse_args()
    total_files = total_edits = 0
    for f in sorted(a.dir.rglob(a.glob)):
        doc = json.loads(f.read_bytes())
        n = walk_edit(doc, a.frm.rstrip("/"), a.to.rstrip("/"))
        if n:
            f.write_text(json.dumps(doc, indent=1) + "\n")
            total_files += 1
            total_edits += n
    roots = [(str(a.dir) + "/", None)]
    if a.mapref:
        c, l = a.mapref.split("=", 1)
        roots.append((c.rstrip("/") + "/", l.rstrip("/")))
    for _ in range(3):  # specs pin template/plan shas: recompute refs into the dir until stable
        changed = 0
        for f in sorted(a.dir.rglob(a.glob)):
            doc = json.loads(f.read_bytes())
            for root, local in roots:
                changed += fix_refs(doc, root, local)
            if changed:
                f.write_text(json.dumps(doc, indent=1) + "\n")
        if not changed:
            break
    print(f"repath: {total_edits} path fields in {total_files} files: {a.frm} -> {a.to} (inner refs re-hashed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
