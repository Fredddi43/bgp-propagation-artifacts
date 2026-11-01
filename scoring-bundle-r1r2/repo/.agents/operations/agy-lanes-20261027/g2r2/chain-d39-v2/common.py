"""Shared helpers for the G3/R2 chain scripts. No label is opened by anything in this module."""
import hashlib
import json
import sys
from pathlib import Path

def _find_repo(start):
    for p in [start, *start.parents]:
        if (p / "src" / "bgbench" / "forecast_custodian_eval.py").is_file():
            return p
    raise SystemExit("REFUSED: repo root with src/bgbench not found above " + str(start))


REPO = _find_repo(Path(__file__).resolve().parent)
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

BASE = Path("<FORECAST_ROOT>/data-custodian")
GO_FILE = Path(__file__).resolve().parents[1] / "ROOT-GO-R2.txt"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(ok, why):
    if not ok:
        raise SystemExit("REFUSED: " + why)


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    return sha(path)
