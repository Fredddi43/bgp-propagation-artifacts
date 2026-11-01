#!/usr/bin/env python3
"""Create (or list) every retained-outputs parent dir + access-log parent the G2 specs require, ON THE CLUSTER.

Run on the cluster (or via --ssh HOST): reads the generated g2 spec files, collects arms[].output_parents, and
either prints them (--dry) or mkdir -p's them (--mkdir). Idempotent; creates NO files (runners require parents
present, files ABSENT; the absence of the output files is verified separately by the validators).
usage: python3 -B make_output_parents.py (--specs-glob 'DIR/**/g2.spec*.json' | --specs FILE ...) [--dry|--mkdir]
"""
import argparse
import glob
import json
import subprocess
from pathlib import Path


def collect(spec_paths):
    parents = set()
    for sp in spec_paths:
        doc = json.loads(Path(sp).read_bytes())
        for arm in doc.get("arms", []):
            parents.update(arm.get("output_parents", []))
        for key in ("access_log",):
            pass
    return sorted(parents)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--specs", action="append", default=[], help="one spec file (repeatable)")
    p.add_argument("--specs-glob", action="append", default=[], help="glob over spec files (repeatable)")
    p.add_argument("--dry", action="store_true")
    p.add_argument("--mkdir", action="store_true")
    a = p.parse_args(argv)
    paths = list(a.specs)
    for g in a.specs_glob:
        paths.extend(sorted(glob.glob(g, recursive=True)))
    parents = collect(paths)
    if not parents:
        raise SystemExit("no output_parents found in " + str(len(paths)) + " spec files")
    if a.mkdir:
        proc = subprocess.run(["bash", "-c", 'while IFS= read -r d; do mkdir -p "$d"; done'],
                              input="\n".join(parents) + "\n", text=True)
        raise SystemExit(proc.returncode)
    print(f"{len(parents)} output parents from {len(paths)} specs; examples:")
    for d in parents[:4] + parents[-2:]:
        print(" ", d)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
