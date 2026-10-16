"""Precision / recall / F1 (ADR-0008 §3) of a saved model at its tuned threshold, against all observed non-seed members and on the full
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
thr = torch.load(R / f"{prefix}_model.pt", weights_only=False, map_location='cpu')["threshold"]
D = config.tgn_dir(year, delta_s, tag)
rows = []
for eid, (asn, p) in probs.items():
    f = D / f"{eid}.pt"
    if not f.exists():
        raise FileNotFoundError(f)
    d = torch.load(f, weights_only=False)
    y = d["y"].numpy().astype(bool); seed = d["persistence_pred"].numpy().astype(bool); mask = ~seed
    pred_new = (np.asarray(p) >= thr) & mask
    truth = set(d["target_asns"].tolist()); seeds = set(d["seed_asns"].tolist())
    predicted_new = set(np.asarray(asn)[pred_new].tolist()) - seeds
    true_new = truth - seeds
    tp = len(predicted_new & true_new); fp = len(predicted_new - true_new); fn = len(true_new - predicted_new)
    prec = tp / (tp + fp) if tp + fp else float("nan"); rec = tp / (tp + fn) if tp + fn else float("nan")
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else float("nan")
    full = seeds | predicted_new
    tpf = len(full & truth); fpf = len(full - truth); fnf = len(truth - full)
    rows.append({"event_id": eid, "target_asns": json.dumps(sorted(truth)), "seed_asns": json.dumps(sorted(seeds)),
                 "predicted_asns": json.dumps(sorted(full)), "tp": tp, "fp": fp, "fn": fn, "prec": prec, "rec": rec, "f1": f1, "prec_full": tpf / max(tpf + fpf, 1), "rec_full": tpf / max(tpf + fnf, 1), "new_pos": len(true_new), "pred_new": len(predicted_new)})

import polars as pl
t = pl.DataFrame(rows)
t.write_csv(R / f"{prefix}_prf1_per_event.csv")
out = {"year": year, "tag": tag, "delta_s": delta_s, "model": prefix, "threshold": thr, "membership_target": "full_observed_2h", "events": t.height,
       "new_members_only": {"undefined_event_policy": "omit undefined ratios from macro means; retain all events in micro totals",
                            "precision_defined_events": t["prec"].drop_nans().len(), "recall_defined_events": t["rec"].drop_nans().len(),
                            "f1_defined_events": t["f1"].drop_nans().len(), "zero_prediction_events": int((t["pred_new"] == 0).sum()),
                            "precision_mean": round(float(t["prec"].drop_nans().mean()), 4), "recall_mean": round(float(t["rec"].drop_nans().mean()), 4), "f1_mean": round(float(t["f1"].drop_nans().mean()), 4),
                            "micro_precision": round(float(t["tp"].sum() / max(t["tp"].sum() + t["fp"].sum(), 1)), 4), "micro_recall": round(float(t["tp"].sum() / max(t["tp"].sum() + t["fn"].sum(), 1)), 4),
                            "predicted_new_per_event_p50": float(t["pred_new"].median()), "true_new_per_event_p50": float(t["new_pos"].median())},
       "full_set_seeds_plus_predicted": {"precision_mean": round(float(t["prec_full"].mean()), 4), "recall_mean": round(float(t["rec_full"].mean()), 4)}}
print(json.dumps(out, indent=1)); (R / f"{prefix}_prf1.json").write_text(json.dumps(out, indent=1))
