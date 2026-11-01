"""Extract recorded D-A39 secondary-lane summaries from the nine family pickles (read-only).

Copies recorded values only: cell statuses/roles/event counts, failure-chain refs, and each recorded paired
contrast's summary fields (arm, comparator, cohort, metric, status, events, mean_difference, reason). Per-event
rows, event_differences and cohort id lists are never copied; only their lengths are checked for consistency.
No metric is recomputed.  usage: python -I -B extract_lanes.py <out.json>
"""
import collections, hashlib, json, pickle, sys

D = "<FORECAST_ROOT>/data-custodian/single-R2-v1/arms/000/rescore-secondary-D-A39/families"
FAMILIES = ["counts", "membership-h1", "membership-h3", "membership-timing", "membership-history", "membership-ordinary",
            "stable", "origin", "additional_baselines"]


def load(name):
    man = json.load(open(f"{D}/{name}.manifest.json"))
    h, chunks = hashlib.sha256(), []
    for i in range(man["parts"]):
        with open(f"{D}/{name}.pkl.part{i:04d}", "rb") as s:
            b = s.read()
        h.update(b)
        chunks.append(b)
    raw = b"".join(chunks)
    ok = h.hexdigest() == man["sha256_of_concatenated_parts"] and len(raw) == man["bytes"]
    if not ok:
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
    out["keys"] = sorted(cell.keys())
    return out


def contrast_summary(c):
    out = {k: plain(c[k]) for k in ("arm_id", "comparator", "training_seed", "cohort", "status", "metric", "events",
                                    "mean_difference", "reason") if k in c}
    if "event_differences" in c:
        out["event_differences_len"] = len(c["event_differences"])
        out["event_differences_len_matches_events"] = len(c["event_differences"]) == c.get("events")
    out["keys"] = sorted(c.keys())
    return out


def section(obj):
    out = {k: plain(obj[k]) for k in ("kind", "family", "declares_primary_finding", "formal_tests", "intervals_computed",
                                      "selection_performed", "fits", "target_scope", "label_horizon", "targets_s",
                                      "broader_training_reused_at_30_60_seconds", "persistence_note", "incident_count",
                                      "actor_day_collapsed_count", "limited_independent_support", "interpretation",
                                      "model_input_distribution") if k in obj}
    out["top_keys"] = sorted(obj.keys())
    cells = obj.get("cells") or {}
    out["cells"] = [cell_summary(n, c) for n, c in cells.items()]
    out["cell_status_counts"] = dict(collections.Counter(c.get("status") for c in cells.values()))
    if obj.get("contrasts") is not None:
        out["contrasts"] = [contrast_summary(c) for c in obj["contrasts"]]
        out["contrast_status_counts"] = dict(collections.Counter(c.get("status") for c in obj["contrasts"]))
    if obj.get("planned_seed_population") is not None:
        out["planned_seed_population"] = [{k: plain(v) for k, v in p.items()} for p in obj["planned_seed_population"]]
    if isinstance(obj.get("cohort_ids"), dict):
        out["cohort_sizes"] = {d: len(v) for d, v in obj["cohort_ids"].items()}
    if isinstance(obj.get("h3_cohorts"), dict):
        out["h3_cohort_sizes"] = {d: {k: len(v) for k, v in cs.items()} for d, cs in obj["h3_cohorts"].items()}
    return out


result = {"source_dir": D, "families": {}}
for name in FAMILIES:
    obj, receipt = load(name)
    entry = {"receipt": receipt}
    if isinstance(obj, dict) and obj.get("status") == "failed":
        tb = obj.get("traceback", "")
        frames = [ln.strip() for ln in tb.splitlines() if ln.strip().startswith("File ")]
        entry.update(status="failed", kind=obj.get("kind"), error=obj.get("error"), traceback_frames=frames,
                     top_keys=sorted(obj.keys()))
    elif name == "origin":
        entry.update(status="scored", kind=obj.get("kind"), valid_family_branch=obj.get("valid_family_branch"),
                     fits=obj.get("fits"), declares_primary_finding=obj.get("declares_primary_finding"),
                     source_sampling_comparability=obj.get("source_sampling_comparability"), top_keys=sorted(obj.keys()),
                     strata={s: section(v) for s, v in obj["families"].items()})
    else:
        entry.update(status="scored", **section(obj))
    result["families"][name] = entry
    del obj
    print(name, "ok", flush=True)

with open(sys.argv[1], "w") as f:
    json.dump(result, f, indent=1, sort_keys=True, default=str)
print("written", sys.argv[1])
