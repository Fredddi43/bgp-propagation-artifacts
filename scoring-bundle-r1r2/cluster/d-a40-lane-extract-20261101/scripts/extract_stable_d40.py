"""Extract the recorded D-A40 stable-lane summary from the rescore-stable-D-A40 records (read-only).

Same rule as extract_lanes.py: copies recorded values only (cell statuses, roles, event counts, the D-A40 not-scorable
record of each cell); per-event rows are never copied, only their lengths are checked. No metric is recomputed.
Also copies completion.json, the third-label-read marker and the primary consistency check.
usage: python -I -B extract_stable_d40.py <out.json>
"""
import collections, hashlib, json, pickle, sys

R = ("<FORECAST_ROOT>/data-custodian/single-R2-v1/arms/000/"
     "rescore-stable-D-A40")
D = f"{R}/families"
FIELD = "not_scorable_empty_target_and_forecast"


def load(name):
    man = json.load(open(f"{D}/{name}.manifest.json"))
    h, chunks = hashlib.sha256(), []
    for i in range(man["parts"]):
        with open(f"{D}/{name}.pkl.part{i:04d}", "rb") as s:
            b = s.read()
        h.update(b)
        chunks.append(b)
    raw = b"".join(chunks)
    if h.hexdigest() != man["sha256_of_concatenated_parts"] or len(raw) != man["bytes"]:
        raise SystemExit(f"{name}: bytes differ from manifest")
    return pickle.loads(raw), {"manifest": man, "verified_sha256": h.hexdigest(), "bytes": len(raw)}


def plain(v):
    try:
        import numpy as np
        if isinstance(v, np.generic):
            return v.item()
    except ImportError:
        pass
    if isinstance(v, tuple):
        return [plain(x) for x in v]
    return v


def cell_summary(name, cell):
    out = {"arm_id": name, "status": cell.get("status"), "role": {k: plain(v) for k, v in cell.get("role", {}).items()}}
    for k in ("reference_events", "scorable_events", "censored_events", "input_status_counts", "reason"):
        if k in cell:
            out[k] = plain(cell[k]) if not isinstance(cell[k], dict) else {kk: plain(vv) for kk, vv in cell[k].items()}
    if "failure_chain" in cell:
        out["failure_chain"] = [{"path": r.get("path"), "sha256": r.get("sha256")} for r in cell["failure_chain"]]
    if "rows" in cell:
        out["rows_len"] = len(cell["rows"])
        out["rows_len_matches_scorable"] = len(cell["rows"]) == cell.get("scorable_events")
        ids = [r["event_id"] for r in cell["rows"]]
        out["rows_unique"] = len(ids) == len(set(ids))
    if "input_available_rows" in cell:
        out["input_available_rows_len"] = len(cell["input_available_rows"])
    ns = cell.get(FIELD)
    if ns is not None:
        excluded = list(ns.get("event_ids") or [])
        out["not_scorable"] = {"rule": ns.get("rule"), "count": plain(ns.get("count")), "event_ids_len": len(excluded),
                               "event_ids_sha256": hashlib.sha256(json.dumps(sorted(excluded)).encode()).hexdigest(),
                               "input_status_counts": {k: plain(v) for k, v in (ns.get("input_status_counts") or {}).items()}}
        if "rows" in cell:
            out["not_scorable"]["none_scored"] = not (set(excluded) & {r["event_id"] for r in cell["rows"]})
        if all(k in cell for k in ("reference_events", "scorable_events", "censored_events")):
            out["not_scorable"]["population_identity"] = (cell["reference_events"] == cell["scorable_events"]
                                                          + cell["censored_events"] + len(excluded))
    out["keys"] = sorted(cell.keys())
    return out


obj, receipt = load("stable")
result = {"records": R, "receipt": receipt}
if isinstance(obj, dict) and obj.get("status") == "failed":
    tb = obj.get("traceback", "")
    result.update(status="failed", error=obj.get("error"),
                  traceback_frames=[ln.strip() for ln in tb.splitlines() if ln.strip().startswith("File ")])
else:
    cells = obj.get("cells") or {}
    result.update(status="scored",
                  **{k: plain(obj[k]) for k in ("kind", "target_scope", "declares_primary_finding", "formal_tests",
                                                "intervals_computed", "fits", "model_input_distribution") if k in obj},
                  top_keys=sorted(obj.keys()),
                  cells=[cell_summary(n, c) for n, c in cells.items()],
                  cell_status_counts=dict(collections.Counter(c.get("status") for c in cells.values())),
                  input_available_cohort_sizes={d: len(v) for d, v in (obj.get("input_available_cohort") or {}).items()})
    # exclusion is per horizon: the same event set in every committed cell of a horizon (paired arms)
    by_h = collections.defaultdict(set)
    for c in cells.values():
        ns = c.get(FIELD)
        if ns is not None:
            by_h[str(c["role"]["horizon_seconds"])].add(hashlib.sha256(json.dumps(sorted(ns.get("event_ids") or [])).encode()).hexdigest())
    result["exclusion_set_identical_per_horizon"] = {h: len(v) == 1 for h, v in by_h.items()}
del obj

for name in ("completion.json", "third-label-read-D-A40.json", "primary-scores.json", "intent.json", "done.json"):
    try:
        with open(f"{R}/{name}", "rb") as f:
            b = f.read()
        doc = json.loads(b)
        result.setdefault("files", {})[name] = {"sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b),
                                                 "content": doc if len(b) < 200_000 else {"top_keys": sorted(doc)}}
    except FileNotFoundError:
        result.setdefault("files", {})[name] = None

with open(sys.argv[1], "w") as f:
    json.dump(result, f, indent=1, sort_keys=True, default=str)
print("written", sys.argv[1], result.get("status"), result.get("cell_status_counts"))
