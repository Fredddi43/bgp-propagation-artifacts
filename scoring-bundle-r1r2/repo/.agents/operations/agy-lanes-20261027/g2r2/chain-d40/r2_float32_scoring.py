"""D-A39: float32 comparison in score_membership's committed-decision check, for the membership consumer only (no pinned file is edited).

R2 attempt 12 (job 52700052) opened the labels, wrote primary.json, then failed in
components/composition/components/membership/consumer.py score_cell -> bgbench/forecast_retrospective_scoring.py score_membership:
`selected = np.asarray(row["probabilities"]) >= row["threshold"]` promotes the float32 model outputs to float64, and the decision set it
derives must equal the committed `predicted_asns` ("Committed decision differs from probabilities/threshold"). The same edge as D-A36
(arm gru-d30-s2, one event, p = float32(0.94) = 0.9399999976158142 at threshold 0.94): the producer compared in float32, float64 says
p < threshold. D-A36 fixed only the consumer's own check_cell; score_membership repeats the comparison and also uses the resulting mask
for membership_metrics (Jaccard etc.), so the float32 mask is the one that reproduces the committed decision.

`patch(consumer)` re-compiles score_membership from its own sha-verified source with that single comparison done in float32 and
nothing else changed, into a PRIVATE copy of the scoring module, and points only the membership consumer's `scoring` global at it.
The shared bgbench module, the primary evaluator, and the stable/origin/baseline consumers (their own reviewed_membership copies) are
untouched. Same AST approach and shape check as r2_float32_decision.py (D-A36).

float32 never removes a float64 selection: for float32 p and any threshold t, p >= t implies p >= float32(t) (rounding is monotone), so
the float32 mask differs from the float64 one only by candidates with float32(t) <= p < t.

`decisions(cell)` / `check_prepared(...)` count, for prepared cells, how many available rows reproduce the committed decision under each
comparison (label-free). `main()` is the standalone offline check that reads the sealed predictions directly (sha-checked against the seal).
"""
import ast
import hashlib
import json
import types
from pathlib import Path

SCORING_SHA = "740bf610afc2d2cdaae40e8726ab6bd8ab9b38d5e6db262a4f0b7f7a14bc4c3d"   # bgbench/forecast_retrospective_scoring.py (pinned)
OLD = 'selected = np.asarray(row["probabilities"]) >= row["threshold"]'
NEW = 'selected = np.asarray(row["probabilities"], dtype=np.float32) >= np.float32(row["threshold"])'
MARK = "_d_a39_float32"


def patched_scoring(scoring):
    """A private copy of the scoring module whose score_membership compares in float32 (one line changed)."""
    raw = Path(scoring.__file__).read_bytes()
    if hashlib.sha256(raw).hexdigest() != SCORING_SHA:
        raise ValueError("forecast_retrospective_scoring.py differs from its pinned hash")
    source = raw.decode()
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "score_membership")
    segment = ast.get_source_segment(source, node)
    if segment.count(OLD) != 1:
        raise ValueError("score_membership shape changed")
    function = ast.parse(segment.replace(OLD, NEW)).body[0]
    private = types.ModuleType(scoring.__name__ + "_d_a39_float32")
    private.__dict__.update(scoring.__dict__)
    exec(compile(ast.Module(body=[function], type_ignores=[]), scoring.__file__, "exec"), private.__dict__)
    private.__dict__[MARK] = True
    return private


def patch(consumer):
    """Point the membership consumer's `scoring` at the float32 copy. Idempotent; returns the private module."""
    if not getattr(consumer.scoring, MARK, False):
        consumer.scoring = patched_scoring(consumer.scoring)
    return consumer.scoring


def row_decisions(row):
    """(committed == float64 decision, committed == float32 decision, detail) for one non-baseline prediction row."""
    import numpy as np
    probabilities = np.asarray(row["probabilities"], dtype=float)
    candidates = np.asarray(row["candidate_asns"])
    seeds = set(row["seed_asns"])
    committed = set(row["predicted_asns"])
    d64 = seeds | set(candidates[probabilities >= row["threshold"]].tolist())
    d32 = seeds | set(candidates[np.asarray(row["probabilities"], dtype=np.float32) >= np.float32(row["threshold"])].tolist())
    detail = None
    if d64 != committed or d32 != committed:
        extra = sorted((d64 ^ committed) | (d32 ^ committed))
        index = {int(a): i for i, a in enumerate(candidates.tolist())}
        detail = {"event_id": row.get("event_id"), "threshold": row["threshold"], "asns": extra,
                  "p": [float(probabilities[index[a]]) if a in index else None for a in extra],
                  "float64_matches": d64 == committed, "float32_matches": d32 == committed}
    return d64 == committed, d32 == committed, detail


def decisions(name, cell):
    """Label-free decision check of one prepared cell: only committed non-baseline cells, only rows whose input is available (the rows
    the consumer's check_cell checks; score_membership sees a subset of them)."""
    if not isinstance(cell, dict) or cell.get("status") != "committed" or cell.get("baseline"):
        return None
    available = {r["event_id"] for r in cell["rows"] if r.get("input_status", "available") == "available"}
    out = {"arm_id": cell.get("arm_id", name), "rows_checked": 0, "float64_mismatch_rows": 0, "float32_mismatch_rows": 0, "mismatches": []}
    for row in cell["predictions"]:
        if row["event_id"] not in available or "probabilities" not in row:
            continue
        ok64, ok32, detail = row_decisions(row)
        out["rows_checked"] += 1
        out["float64_mismatch_rows"] += not ok64
        out["float32_mismatch_rows"] += not ok32
        if detail is not None and len(out["mismatches"]) < 20:
            out["mismatches"].append(detail)
    return out


def summarize(per_arm):
    arms = [a for a in per_arm if a is not None]
    return {"arms_checked": len(arms), "rows_checked": sum(a["rows_checked"] for a in arms),
            "float64_mismatch_rows": sum(a["float64_mismatch_rows"] for a in arms),
            "float32_mismatch_rows": sum(a["float32_mismatch_rows"] for a in arms),
            "arms_with_mismatch": [a for a in arms if a["float64_mismatch_rows"] or a["float32_mismatch_rows"]]}


def check_prepared(members=(), origin=(), stable=()):
    """Decision check over prepared stage results (lists of the objects the stages returned). Membership families: cells and comparators
    (deduplicated by arm id); origin and stable: cells. Only the membership consumer is float32-patched, so the run needs
    members.float32_mismatch_rows == 0 and origin/stable float64_mismatch_rows == 0."""
    seen, member_arms = set(), []
    for prepared in members:
        for group in ("cells", "comparators"):
            for name, cell in prepared[group].items():
                arm = cell.get("arm_id", name) if isinstance(cell, dict) else name
                if arm in seen:
                    continue
                seen.add(arm)
                member_arms.append(decisions(name, cell))
    result = {"members": summarize(member_arms)}
    result["origin"] = summarize([decisions(n, c) for p in origin for n, c in p["cells"].items()])
    result["stable"] = summarize([decisions(n, c) for p in stable for n, c in p["cells"].items()])
    return result


# ---------------------------------------------------------------------------------------------------------------------------------
# Standalone offline check (label-free): sealed predictions + manifests of every committed non-baseline arm, read directly and
# sha-checked against the seal / freeze. Not part of the R2 run; reads no label, writes only --out.

def _load(path, sha):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != sha:
        raise ValueError(f"{path} differs from its sealed hash")
    try:
        import orjson
        return orjson.loads(raw)
    except ImportError:
        return json.loads(raw)


def _arm_task(task):
    arm, predictions_sha = task
    manifest = _load(arm["manifest_path"], arm["manifest_sha256"])
    predictions = _load(arm["predictions_path"], predictions_sha)
    cell = {"status": "committed", "baseline": False, "arm_id": arm["arm_id"], "rows": manifest["events"], "predictions": predictions}
    out = decisions(arm["arm_id"], cell)
    out["role"] = arm["role"]
    return out


def main(argv=None):
    import argparse
    import multiprocessing
    p = argparse.ArgumentParser(description="D-A39 offline float32/float64 committed-decision check over sealed predictions (label-free)")
    p.add_argument("--freeze", required=True)
    p.add_argument("--freeze-sha256", required=True)
    p.add_argument("--seal", required=True)
    p.add_argument("--seal-sha256", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--workers", type=int, default=16)
    p.add_argument("--include-origin", action="store_true", help="also the 40 origin arms (~378 GB of predictions)")
    a = p.parse_args(argv)
    freeze = _load(a.freeze, a.freeze_sha256)
    seal = _load(a.seal, a.seal_sha256)
    if seal["spec_path"] != a.freeze or seal["spec_sha256"] != a.freeze_sha256:
        raise ValueError("seal does not bind this freeze")
    sealed = {s["arm_id"]: s for s in seal["arms"]}
    tasks = []
    for arm in freeze["arms"]:
        role = arm.get("role", {})
        if arm.get("status") != "committed_for_prediction" or role.get("family") == "baseline":
            continue
        if role.get("variant") in ("origin_change_valid", "origin_change_invalid") and not a.include_origin:
            continue
        tasks.append((arm, sealed[arm["arm_id"]]["predictions_sha256"]))
    tasks.sort(key=lambda t: -Path(t[0]["predictions_path"]).stat().st_size)
    with multiprocessing.get_context("fork").Pool(a.workers) as pool:
        per_arm = [r for r in pool.imap_unordered(_arm_task, tasks)]
    per_arm.sort(key=lambda r: r["arm_id"])
    summary = summarize(per_arm)
    summary.update(kind="D-A39_offline_float32_decision_check_v1", labels_read=False, freeze={"path": a.freeze, "sha256": a.freeze_sha256},
                   seal={"path": a.seal, "sha256": a.seal_sha256}, include_origin=a.include_origin, old=OLD, new=NEW,
                   arms_by_family={}, per_arm=[{k: r[k] for k in ("arm_id", "rows_checked", "float64_mismatch_rows", "float32_mismatch_rows")}
                                              for r in per_arm])
    for r in per_arm:
        key = "{}/{}".format(r["role"].get("family") or ("h3-" + str(r["role"].get("stage"))), r["role"].get("variant"))
        summary["arms_by_family"][key] = summary["arms_by_family"].get(key, 0) + 1
    with a.out.open("x") as stream:
        json.dump(summary, stream, indent=1, sort_keys=True)
        stream.write("\n")
    print(json.dumps({k: summary[k] for k in ("arms_checked", "rows_checked", "float64_mismatch_rows", "float32_mismatch_rows")}
                     | {"arms_with_mismatch": [(m["arm_id"], m["float64_mismatch_rows"], m["float32_mismatch_rows"])
                                               for m in summary["arms_with_mismatch"]]}))


if __name__ == "__main__":
    main()
