#!/usr/bin/env python3
"""Read-only: does the H1 successor's fit module accept the real v2-G049 package, and do the 20 bound H1 arms point at it?
Runs the successor's reviewed_fit functions (closure, requirements, check_approval, cells) ON <BATCH_HOST> over package
metadata, plus per-arm path/hash comparisons. No prediction/label/protected payload is read; checkpoints are only hashed.
"""
import base64
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(HERE.parents[1] / "g1"))
FIT = HERE.parent / "h1-successor/reviewed_fit.py"

REMOTE = r'''
import base64, json, sys, types, hashlib
from pathlib import Path
src = base64.b64decode(%(fit)r)
fit = types.ModuleType("fit"); fit.__file__ = "/nonexistent/reviewed_fit.py"; exec(compile(src, "reviewed_fit.py", "exec"), fit.__dict__)
arms = json.loads(base64.b64decode(%(arms)r))
out = []
def check(name, fn):
    try:
        r = fn(); out.append(("OK", name, "" if r in (None, True) else str(r)[:120]))
    except BaseException as e:
        out.append(("FAIL", name, repr(e)[:300]))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
a0 = arms[0]
pubref = a0["calibration_publication"]
check("publication sha", lambda: sha(pubref["path"]) == pubref["sha256"] or 1/0)
pub = json.loads(Path(pubref["path"]).read_bytes())
cp = fit.read(pub["plan"])
pkgref = cp["package"]; package = fit.read(pkgref); root = Path(pkgref["path"]).parent
check("root==STAGE", lambda: root == fit.STAGE or 1/0)
check("package stage/output", lambda: (package["stage"] == str(fit.STAGE) and package["output"] == str(fit.OUTPUT)) or 1/0)
check("fit.cells(package selection)==package cells", lambda: fit.cells(package["selection"]) == package["cells"] or 1/0)
check("fit.closure", lambda: fit.closure(package, root))
refs = {}
def req():
    refs.update(fit.requirements(package)); return len(refs)
check("fit.requirements", req)
check("fit.check_approval", lambda: fit.check_approval(package, pkgref, fit.read(cp["fit_approval"]), fit.read(cp["fit_operation"]), cp["fit_operation"]))
check("pub slice_rule == fit.SLICE_RULE", lambda: pub["slice_rule"]["sha256"] == fit.SLICE_RULE or 1/0)
check("arms slice_rule == fit.SLICE_RULE", lambda: all(a["slice_decisions"]["slice_rules"]["sha256"] == fit.SLICE_RULE for a in arms) or 1/0)
records = {r["run"]["run_id"]: r for r in pub["records"]}
rules = {e["run_id"]: e for e in pub["decision_rules"]}
bad = []
for a in arms:
    cid = a["arm_id"]
    # arm_id of H1 arms is the cell id (e.g. none-d30-s0)
    cell = next((c for c in package["cells"] if c["cell_id"] == cid), None)
    rec = records.get(cid)
    if cell is None or rec is None:
        bad.append((cid, "no cell/record")); continue
    fitout = Path(package["output"]) / cid
    ok = (rec["checkpoint"] == {"path": a["model_path"], "sha256": a["model_sha256"]}
          and a["model_path"] == str(fitout / "fit/checkpoint.pt")
          and rec["completion"]["path"] == str(fitout / "complete.json")
          and rec["fit_receipt"]["path"] == str(fitout / "fit/fit_receipt.json")
          and rec["predictions"]["path"] == str(fitout / "fit/validation_predictions.json")
          and not (fitout / "failed.json").exists()
          and a["decision_rules"] == {k: rules[cid][k] for k in ("path", "sha256")}
          and sha(a["model_path"]) == a["model_sha256"] and sha(rec["completion"]["path"]) == rec["completion"]["sha256"]
          and sha(rec["fit_receipt"]["path"]) == rec["fit_receipt"]["sha256"] and sha(a["decision_rules"]["path"]) == a["decision_rules"]["sha256"])
    if not ok: bad.append((cid, "path/hash mismatch"))
out.append(("OK" if not bad else "FAIL", "20 arms vs v2 records/paths/hashes", str(bad[:5])))
for o in out: print(*o)
'''


def main():
    import incremental_draft as inc
    groups, _ = inc.load_current_state()
    arms = [a for a in groups["h1"] if a.get("status") == "committed_for_prediction"]
    code = REMOTE % {"fit": base64.b64encode(FIT.read_bytes()).decode(), "arms": base64.b64encode(json.dumps(arms).encode()).decode()}
    done = subprocess.run(["ssh", "<BATCH_HOST>", "python3 -"], input=code, capture_output=True, text=True)
    print(done.stdout + done.stderr[-800:])
    return 1 if "FAIL" in done.stdout or done.returncode else 0


if __name__ == "__main__":
    sys.exit(main())
