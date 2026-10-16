"""ADR-0007 rung 2: historical-average propagation for similar onset signatures.

Onset signature per event (from the tensors): log1p(seeds), collectors that saw the event by Δ, log1p(messages by Δ),
log1p(universe size). For a test event, the k nearest training events (standardised Euclidean) give (i) the predicted
extent = mean of their final member counts (curve baseline), and (ii) a membership prediction: seeds ∪ the top-(pred −
seeds) non-seed candidates ranked by how often the same AS was affected in training events relative to how often it was a
candidate (historical participation, the "historical event participation" feature of the plan).
"""
from __future__ import annotations

import json

import numpy as np
import polars as pl
import torch

from . import config
from .gnn_train import _jaccard, bootstrap_diff, load_splits


def signature(d: dict) -> np.ndarray:
    x = d["x"].numpy()
    return np.array([np.log1p(d["n_seed"]), float((x[:, 6] > 0).sum()), np.log1p(float(np.expm1(x[:, 7]).sum())), np.log1p(len(x))], dtype=np.float64)


def run(year="2024", delta_s: int = 30, tag: str = "", k: int = 20) -> dict:
    ys = str(year)
    if ">" in ys:
        a, b = ys.split(">")
        tr = [d for y in a.split(",") for sp in load_splits(config.tgn_dir(int(y), delta_s, tag)).values() for d in sp]
        te = [d for y in b.split(",") for sp in load_splits(config.tgn_dir(int(y), delta_s, tag)).values() for d in sp]
        last = int(b.split(",")[-1])
    else:
        tr, te = [], []
        for y in ys.split(","):
            sp = load_splits(config.tgn_dir(int(y), delta_s, tag)); tr += sp["train"]; te += sp["test"]
        last = int(ys.split(",")[-1])
    if not tr or not te:
        return {"error": f"train={len(tr)} test={len(te)}"}
    S = np.stack([signature(d) for d in tr]); mu, sd = S.mean(0), S.std(0) + 1e-9; Sz = (S - mu) / sd
    finals = np.array([d["n_pos"] for d in tr], dtype=np.float64)
    # historical participation: affected / candidate counts per ASN over the training events
    aff, cand = {}, {}
    for d in tr:
        asn = d["asn"].numpy(); y = d["y"].numpy().astype(bool)
        for a in asn: cand[int(a)] = cand.get(int(a), 0) + 1
        for a in asn[y]: aff[int(a)] = aff.get(int(a), 0) + 1
    rows = []
    for d in te:
        z = (signature(d) - mu) / sd
        nn_idx = np.argsort(((Sz - z) ** 2).sum(1))[:k]
        pred_final = float(finals[nn_idx].mean())
        seed = d["persistence_pred"].numpy().astype(bool); y = d["y"].numpy().astype(bool); asn = d["asn"].numpy()
        score = np.array([aff.get(int(a), 0) / (cand.get(int(a), 0) + 5.0) for a in asn])   # shrunk participation rate
        score[seed] = -1
        n_add = int(max(0, round(pred_final - seed.sum())))
        pred = seed.copy()
        if n_add:
            pred[np.argsort(-score)[:n_add]] = True
        truth = d["curve"].numpy() if "curve" in d else np.array([float(y.sum())])
        sm = lambda a, b: float(np.mean(2 * np.abs(a - b) / np.maximum(np.abs(a) + np.abs(b), 1e-9)))
        rows.append({"event_id": d["event_id"], "jaccard_hist": _jaccard(y, pred), "jaccard_persist": _jaccard(y, seed),
                     "smape_2h_hist": sm(np.array([pred_final]), truth[-1:]), "smape_2h_persist": sm(np.array([float(seed.sum())]), truth[-1:]),
                     "pred_final": pred_final, "true_final": float(truth[-1]), "n_seed": int(seed.sum())})
    df = pl.DataFrame(rows)
    res = {"model": "hist_avg", "tag": tag, "delta_s": delta_s, "k": k, "train_events": len(tr), "test_events": len(te),
           "jaccard_hist_mean": round(float(df["jaccard_hist"].mean()), 4), "jaccard_persist_mean": round(float(df["jaccard_persist"].mean()), 4),
           "diff_hist_minus_persistence": bootstrap_diff(df, "jaccard_hist", "jaccard_persist"),
           "smape_2h_hist": round(float(df["smape_2h_hist"].mean()), 4), "smape_2h_persist": round(float(df["smape_2h_persist"].mean()), 4)}
    out_dir = config.tgn_dir(last, delta_s, tag) / "_results"; out_dir.mkdir(exist_ok=True)
    suf = "" if ys.isdigit() else "_" + ys.replace(",", "+").replace(">", "_to_")
    res["years"] = ys
    df.write_csv(out_dir / f"hist_avg{suf}_test_per_event.csv"); (out_dir / f"hist_avg{suf}_summary.json").write_text(json.dumps(res, indent=1, default=str))
    return res
