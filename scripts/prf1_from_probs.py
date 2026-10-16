"""Precision / recall / F1 (ADR-0008 §3) of a saved model at its tuned threshold, on the non-seed candidate nodes and on the full
predicted set (seeds ∪ predicted), from the persisted test probabilities. usage: prf1_from_probs.py <year> <tag> <delta_s> <prefix>"""
from __future__ import annotations

import json
import sys

import numpy as np
import torch

from bgbench import config

year, tag, delta_s, prefix = int(sys.argv[1]), sys.argv[2], int(sys.argv[3]), sys.argv[4]
R = config.tgn_dir(year, delta_s, tag) / "_results"
probs = torch.load(R / f"{prefix}_test_probs.pt", weights_only=False)
thr = torch.load(R / f"{prefix}_model.pt", weights_only=False)["threshold"]
D = config.tgn_dir(year, delta_s, tag)
rows = []
for eid, (asn, p) in probs.items():
    f = D / f"{eid}.pt"
    if not f.exists():
        continue
    d = torch.load(f, weights_only=False)
    y = d["y"].numpy().astype(bool); seed = d["persistence_pred"].numpy().astype(bool); mask = ~seed
    pred_new = (np.asarray(p) >= thr) & mask
    tp = int((pred_new & y).sum()); fp = int((pred_new & ~y).sum()); fn = int((~pred_new & y & mask).sum())
    prec = tp / (tp + fp) if tp + fp else float("nan"); rec = tp / (tp + fn) if tp + fn else float("nan")
    f1 = 2 * prec * rec / (prec + rec) if (tp + fp) and (tp + fn) and (prec + rec) else float("nan")
    full = seed | pred_new
    tpf = int((full & y).sum()); fpf = int((full & ~y).sum()); fnf = int((~full & y).sum())
    rows.append({"tp": tp, "fp": fp, "fn": fn, "prec": prec, "rec": rec, "f1": f1, "prec_full": tpf / max(tpf + fpf, 1), "rec_full": tpf / max(tpf + fnf, 1), "new_pos": int((y & mask).sum()), "pred_new": int(pred_new.sum())})
import polars as pl
t = pl.DataFrame(rows)
out = {"year": year, "tag": tag, "delta_s": delta_s, "model": prefix, "threshold": thr, "events": t.height,
       "new_members_only": {"precision_mean": round(float(t["prec"].drop_nans().mean()), 4), "recall_mean": round(float(t["rec"].drop_nans().mean()), 4), "f1_mean": round(float(t["f1"].drop_nans().mean()), 4),
                            "micro_precision": round(float(t["tp"].sum() / max(t["tp"].sum() + t["fp"].sum(), 1)), 4), "micro_recall": round(float(t["tp"].sum() / max(t["tp"].sum() + t["fn"].sum(), 1)), 4),
                            "predicted_new_per_event_p50": float(t["pred_new"].median()), "true_new_per_event_p50": float(t["new_pos"].median())},
       "full_set_seeds_plus_predicted": {"precision_mean": round(float(t["prec_full"].mean()), 4), "recall_mean": round(float(t["rec_full"].mean()), 4)}}
print(json.dumps(out, indent=1)); (R / f"{prefix}_prf1.json").write_text(json.dumps(out, indent=1))
