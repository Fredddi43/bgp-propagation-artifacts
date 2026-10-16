"""ADR-0008 §6 follow-up / plan open question "ephemeral-leak filtering: preprocessing step or learned gate": can the onset
(first 30 s) tell an ephemeral leak (< 1 min) from a persistent one? Features from anomalous.parquet up to Δ: messages, prefixes,
ASes, collectors, sessions; label duration_min ≥ 1. Gradient boosting, train Jan–Aug / test Sep–Dec; AUPRC, F1, and the floor of
the events the gate lets through. usage: ephemeral_gate.py <year> [delta_s]"""
from __future__ import annotations

import datetime as dt
import json
import sys

import numpy as np
import polars as pl

from bgbench import config
from bgbench.replay_day import roots

year = int(sys.argv[1]); delta_s = int(sys.argv[2]) if len(sys.argv) > 2 else 30
E = config.DATA_ROOT / "eventset" / f"{year}_leak"
ev = pl.read_parquet(E / "events.parquet").filter(pl.col("error").is_null()).select("event_id", "split", "t0_obs", "duration_min", "asns_final_2h", "set_d30s", "set_final_2h")
root = roots("leak")[1]
rows = []
for r in ev.iter_rows(named=True):
    f = root / r["event_id"] / "anomalous.parquet"
    if not f.exists():
        continue
    a = pl.read_parquet(f, columns=["prefix", "ts", "collector", "peer_ip", "as_path"])
    if a["ts"].dtype.time_zone:
        a = a.with_columns(pl.col("ts").dt.replace_time_zone(None))
    t0 = dt.datetime.fromisoformat(r["t0_obs"]).replace(tzinfo=None)
    w = a.filter(pl.col("ts") <= t0 + dt.timedelta(seconds=delta_s))
    if w.is_empty():
        continue
    ases = set()
    for p in w["as_path"].to_list():
        ases.update(p.replace("{", "").replace("}", "").split())
    s30 = set(r["set_d30s"] or []); fin = set(r["set_final_2h"] or [])
    rows.append({"event_id": r["event_id"], "split": r["split"], "y": int((r["duration_min"] or 0) >= 1), "msgs": w.height, "prefixes": w["prefix"].n_unique(), "collectors": w["collector"].n_unique(),
                 "sessions": w["peer_ip"].n_unique(), "path_ases": len(ases), "members_delta": len(s30), "span_s": float((w["ts"].max() - w["ts"].min()).total_seconds()),
                 "j30": len(s30 & fin) / len(s30 | fin) if (s30 | fin) else 1.0, "asns_final": r["asns_final_2h"]})
d = pl.DataFrame(rows)
F = ["msgs", "prefixes", "collectors", "sessions", "path_ases", "members_delta", "span_s"]
tr = d.filter(pl.col("split") == "train"); te = d.filter(pl.col("split") == "test")
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, f1_score, roc_auc_score

clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05).fit(tr.select(F).to_numpy(), tr["y"].to_numpy())
p = clf.predict_proba(te.select(F).to_numpy())[:, 1]; y = te["y"].to_numpy()
thr = 0.5
te = te.with_columns(pl.Series("p", p))
kept = te.filter(pl.col("p") >= thr)
out = {"year": year, "delta_s": delta_s, "train": tr.height, "test": te.height, "persistent_share_test": round(float(y.mean()), 4),
       "auprc": round(float(average_precision_score(y, p)), 4), "auroc": round(float(roc_auc_score(y, p)), 4), "f1_at_0.5": round(float(f1_score(y, p >= thr)), 4),
       "recall_persistent_at_0.5": round(float(((p >= thr) & (y == 1)).sum() / max(y.sum(), 1)), 4), "precision_at_0.5": round(float(((p >= thr) & (y == 1)).sum() / max((p >= thr).sum(), 1)), 4),
       "floor_j30_all_test": round(float(te["j30"].mean()), 4), "floor_j30_gated_through": round(float(kept["j30"].mean()), 4) if kept.height else None, "gated_through_share": round(kept.height / te.height, 4),
       "floor_j30_true_persistent": round(float(te.filter(pl.col("y") == 1)["j30"].mean()), 4), "floor_j30_true_ephemeral": round(float(te.filter(pl.col("y") == 0)["j30"].mean()), 4)}
print(json.dumps(out, indent=1)); (E / f"ephemeral_gate_d{delta_s}s.json").write_text(json.dumps(out, indent=1))
