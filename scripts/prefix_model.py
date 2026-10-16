"""Prefix-level membership (ADR-0005 stretch) on the one slice where it is a real target: multi-prefix leaks (≥ 10 leaked prefixes
at 2 h). For each such leak (leaker a, sources b, novel upstreams x) the candidate prefixes are those whose pre-event RIB paths
(latest weekly RIB before t₀, ten collectors) traverse a. Label: the prefix is in the leaked set at 2 h. Features per prefix: seen
leaked by Δ (persistence), prefix length, a is origin, how a learned it (origin-side neighbour is a source b / a customer / peer /
provider of a), number of RIB sessions carrying it via a, share of those sessions where the neighbour is a source. Models: the
persistence floor, the rule "every prefix a learned from a source", and a gradient-boosted classifier trained on Jan–Aug events,
tested on Sep–Dec (prefix-set Jaccard vs the 2-h leaked set, per event). usage: prefix_model.py <year> [delta_s]"""
from __future__ import annotations

import datetime as dt
import json
import sys

import numpy as np
import polars as pl

from bgbench import config
from bgbench.extent import _rib_paths
from bgbench.leakcheck import rel_parquet
from bgbench.replay_day import roots

year = int(sys.argv[1]); delta_s = int(sys.argv[2]) if len(sys.argv) > 2 else 30
E = config.DATA_ROOT / "eventset" / f"{year}_leak"
root = roots("leak")[1]
ev = pl.read_parquet(E / "events.parquet").filter(pl.col("error").is_null() & (pl.col("leaked_prefixes") >= 10)).select("event_id", "split", "t0_obs")
print("multi-prefix leaks:", ev.height, flush=True)
rel_cache: dict[str, dict] = {}


def rel(month: str) -> dict:
    if month not in rel_cache:
        rel_cache.clear()
        d = pl.read_parquet(rel_parquet(month))
        rel_cache[month] = {(int(u), int(v)): k for u, v, k in d.iter_rows()}   # kind: v is u's <kind>
    return rel_cache[month]


PARTS = E / f"prefix_model_parts_d{delta_s}s"; PARTS.mkdir(exist_ok=True)
NEG_CAP = 2_000_000   # negatives sampled for training (all positives kept); test events are scored on their full candidate sets
for r in ev.sort("event_id").iter_rows(named=True):
    if (PARTS / f"{r['event_id']}.parquet").exists():
        continue
    rows = []
    d = root / r["event_id"]
    s = json.loads((d / "summary.json").read_text())
    a = int(s["leaker"]); srcs = {int(b) for b in str(s.get("sources") or "").split("|") if b}
    t0 = dt.datetime.fromisoformat(r["t0_obs"])
    t0u = t0 if t0.tzinfo else t0.replace(tzinfo=dt.UTC)
    anom = pl.read_parquet(d / "anomalous.parquet", columns=["prefix", "ts"])
    if anom["ts"].dtype.time_zone:
        anom = anom.with_columns(pl.col("ts").dt.replace_time_zone(None))
    t0n = t0u.replace(tzinfo=None)
    leaked = set(anom.filter(pl.col("ts") <= t0n + dt.timedelta(hours=2))["prefix"].to_list())
    seen_d = set(anom.filter(pl.col("ts") <= t0n + dt.timedelta(seconds=delta_s))["prefix"].to_list())
    if not leaked:
        continue
    try:
        rib = (_rib_paths(None, t0u).filter(pl.col("as_path").str.contains(rf"(^| ){a}( |$)")).select("prefix", "as_path", "peer_ip").collect(engine="streaming"))
    except FileNotFoundError:
        continue
    if rib.is_empty():
        continue
    R = rel(r["event_id"][:6])
    feats: dict[str, dict] = {}
    for pfx, path, peer in rib.iter_rows():
        hops = [int(h) for h in path.replace("{", "").replace("}", "").split() if h.isdigit()]
        if a not in hops:
            continue
        i = hops.index(a)
        nb = hops[i + 1] if i + 1 < len(hops) else None          # origin-side neighbour: the AS a learned the route from
        f = feats.setdefault(pfx, {"n_sess": 0, "from_src": 0, "from_cust": 0, "from_peer": 0, "from_prov": 0, "is_origin": 0})
        f["n_sess"] += 1
        if nb is None:
            f["is_origin"] += 1
        else:
            if nb in srcs:
                f["from_src"] += 1
            k = R.get((a, nb))
            if k == "customer":
                f["from_cust"] += 1
            elif k == "peer":
                f["from_peer"] += 1
            elif k == "provider":
                f["from_prov"] += 1
    for pfx, f in feats.items():
        n = f["n_sess"]
        rows.append({"event_id": r["event_id"], "split": r["split"], "prefix": pfx, "plen": int(pfx.split("/")[1]), "seen_delta": int(pfx in seen_d), "y": int(pfx in leaked),
                     "log_sess": float(np.log1p(n)), "share_src": f["from_src"] / n, "share_cust": f["from_cust"] / n, "share_peer": f["from_peer"] / n, "share_prov": f["from_prov"] / n, "share_origin": f["is_origin"] / n})
    # leaked prefixes absent from the RIB candidate set (a not on any pre-event path): counted as misses of every method
    for pfx in leaked - set(feats):
        rows.append({"event_id": r["event_id"], "split": r["split"], "prefix": pfx, "plen": int(pfx.split("/")[1]), "seen_delta": int(pfx in seen_d), "y": 1, "log_sess": 0.0,
                     "share_src": 0.0, "share_cust": 0.0, "share_peer": 0.0, "share_prov": 0.0, "share_origin": 0.0})
    pl.DataFrame(rows).write_parquet(PARTS / f"{r['event_id']}.parquet")
    del rows, feats, rib
    print(r["event_id"], "leaked", len(leaked), "seen@Δ", len(seen_d), flush=True)
df = pl.scan_parquet(str(PARTS / "*.parquet"))
F = ["seen_delta", "plen", "log_sess", "share_src", "share_cust", "share_peer", "share_prov", "share_origin"]
tr_pos = df.filter((pl.col("split") == "train") & (pl.col("y") == 1)).collect(engine="streaming")
tr_neg = df.filter((pl.col("split") == "train") & (pl.col("y") == 0)).collect(engine="streaming")
if tr_neg.height > NEG_CAP:
    tr_neg = tr_neg.sample(n=NEG_CAP, seed=0)
tr = pl.concat([tr_pos, tr_neg])
print("train rows", tr.height, "positives", tr_pos.height, flush=True)
from sklearn.ensemble import HistGradientBoostingClassifier

clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, class_weight="balanced").fit(tr.select(F).to_numpy(), tr["y"].to_numpy())
# threshold tuned on the training split (as the graph models do)
tr = tr.with_columns(pl.Series("p", clf.predict_proba(tr.select(F).to_numpy())[:, 1]))
te_ids = df.filter(pl.col("split") == "test").select("event_id").unique().collect()["event_id"].to_list()


def set_jaccard(g: pl.DataFrame, pred_col) -> float:
    pred = set(g.filter(pred_col)["prefix"].to_list()) | set(g.filter(pl.col("seen_delta") == 1)["prefix"].to_list())
    truth = set(g.filter(pl.col("y") == 1)["prefix"].to_list())
    return len(pred & truth) / len(pred | truth) if (pred | truth) else 1.0


best_thr, best = 0.5, -1
for thr in np.arange(0.1, 0.95, 0.05):
    j = np.mean([set_jaccard(g, pl.col("p") >= thr) for _, g in tr.group_by("event_id")])
    if j > best:
        best, best_thr = j, float(thr)
res_rows = []
for eid in te_ids:
    g = df.filter(pl.col("event_id") == eid).collect(engine="streaming")
    g = g.with_columns(pl.Series("p", clf.predict_proba(g.select(F).to_numpy())[:, 1]))
    res_rows.append({"event_id": eid, "n_cand": g.height, "n_leaked": int(g["y"].sum()), "n_seen": int(g["seen_delta"].sum()),
                     "j_persist": set_jaccard(g, pl.col("seen_delta") == 1), "j_rule_src": set_jaccard(g, pl.col("share_src") > 0.5), "j_rule_nonprov": set_jaccard(g, (pl.col("share_src") > 0.5) | (pl.col("share_peer") > 0.5) | (pl.col("share_prov") > 0.5)),
                     "j_model": set_jaccard(g, pl.col("p") >= best_thr)})
R = pl.DataFrame(res_rows)
rng = np.random.default_rng(0)
def ci(x):
    x = np.asarray(x); return [round(float(v), 4) for v in np.percentile([rng.choice(x, len(x)).mean() for _ in range(1000)], (2.5, 97.5))]
out = {"year": year, "delta_s": delta_s, "events_train": tr["event_id"].n_unique(), "events_test": R.height, "threshold": best_thr,
       "candidates_per_event_p50": float(R["n_cand"].median()), "leaked_per_event_p50": float(R["n_leaked"].median()),
       "jaccard_test_mean": {c: round(float(R[c].mean()), 4) for c in ("j_persist", "j_rule_src", "j_rule_nonprov", "j_model")},
       "model_minus_persist_ci95": ci(R["j_model"] - R["j_persist"]), "rule_src_minus_persist_ci95": ci(R["j_rule_src"] - R["j_persist"]),
       "feature_importance_note": "gradient boosting; features " + ",".join(F)}
print(json.dumps(out, indent=1)); (E / f"prefix_model_summary_d{delta_s}s.json").write_text(json.dumps(out, indent=1))
