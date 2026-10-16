"""ADR-0007 rung 2: historical-average propagation for similar onset signatures.

Onset signature per event (from the tensors): log1p(all observed seeds), number of visible candidate ASes by Δ, log1p(candidate path-hop appearances by Δ),
log1p(universe size). For a test event, the k nearest training events (standardised Euclidean) predict
extent as their mean final member count, floored at the observed seed count. Membership is seeds ∪ the top-(pred −
seeds) non-seed candidates ranked by participation over the full training library: how often the AS was affected
relative to how often it was a candidate. Membership ranking does not use only the nearest neighbours.
"""
from __future__ import annotations

import json

import numpy as np
import polars as pl
import torch

from . import config
from .graph_metrics import membership_metrics, legacy_window_crosses_midnight
from .gnn_train import _jaccard, bootstrap_diff, load_splits, prospective_training_events, event_onsets


def signature(d: dict) -> np.ndarray:
    x = d["x"].numpy()
    return np.array([np.log1p(len(d["seed_asns"])), float((x[:, 6] > 0).sum()), np.log1p(float(np.expm1(x[:, 7]).sum())), np.log1p(len(x))], dtype=np.float64)


def run(year="2024", delta_s: int = 30, tag: str = "", k: int = 20, online_completed: bool = False) -> dict:
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
    all_training = tr
    tr, split_protocol = prospective_training_events(tr, te, year, tag)
    if not tr:
        return {"error": "No training labels completed before first test onset"}
    S = np.stack([signature(d) for d in tr]); mu, sd = S.mean(0), S.std(0) + 1e-9; Sz = (S - mu) / sd
    finals = np.array([len(d["target_asns"]) for d in tr], dtype=np.float64)
    # historical participation: affected / candidate counts per ASN over the training events
    aff, cand = {}, {}
    def add_participation(d):
        asn = d["asn"].numpy(); y = d["y"].numpy().astype(bool)
        for a in asn: cand[int(a)] = cand.get(int(a), 0) + 1
        for a in asn[y]: aff[int(a)] = aff.get(int(a), 0) + 1
    if online_completed:
        from datetime import timedelta
        onsets = event_onsets(all_training + te, tag)
        library = sorted({d['event_id']: d for d in all_training + te}.values(), key=lambda d: (onsets[d['event_id']], d['event_id']))
        library_signatures = np.stack([signature(d) for d in library])
        library_finals = np.array([len(d['target_asns']) for d in library], dtype=np.float64)
        te = sorted(te, key=lambda d: (onsets[d['event_id']], d['event_id']))
        available = 0
    else:
        for d in tr:
            add_participation(d)
    rows = []
    for d in te:
        if online_completed:
            while available < len(library) and onsets[library[available]['event_id']] + timedelta(hours=2) <= onsets[d['event_id']]:
                add_participation(library[available]); available += 1
            S = library_signatures[:available]
            if available:
                mu, sd = S.mean(0), S.std(0) + 1e-9; Sz = (S - mu) / sd
            finals = library_finals[:available]
        z = (signature(d) - mu) / sd
        nn_idx = np.argsort(((Sz - z) ** 2).sum(1))[:k] if len(finals) else []
        pred_final = max(float(finals[nn_idx].mean()), float(len(d["seed_asns"]))) if len(nn_idx) else float(len(d["seed_asns"]))
        seed = d["persistence_pred"].numpy().astype(bool); y = d["y"].numpy().astype(bool); asn = d["asn"].numpy()
        score = np.array([aff.get(int(a), 0) / (cand.get(int(a), 0) + 5.0) for a in asn])   # shrunk participation rate
        score[seed] = -1
        n_add = int(max(0, round(pred_final - len(d["seed_asns"]))))
        pred = seed.copy()
        if n_add:
            pred[np.argsort(-score)[:n_add]] = True
        truth = d["curve"].numpy() if "curve" in d else np.array([float(y.sum())])
        sm = lambda a, b: float(np.mean(2 * np.abs(a - b) / np.maximum(np.abs(a) + np.abs(b), 1e-9)))
        metrics = membership_metrics(d, pred)
        rows.append({"event_id": d["event_id"], "legacy_window_crosses_midnight": legacy_window_crosses_midnight(d["event_id"]), "predicted_asns_hist": json.dumps(sorted(set(d["seed_asns"].tolist()) | set(asn[pred].tolist()))),
                     "jaccard_hist": metrics["jaccard"], "jaccard_persist": metrics["jaccard_persist"],
                     "candidate_jaccard_hist": metrics["candidate_jaccard"], "candidate_jaccard_persist": metrics["candidate_jaccard_persist"],
                     "candidate_target_coverage": metrics["candidate_target_coverage"],
                     "smape_2h_hist": sm(np.array([pred_final]), truth[-1:]), "smape_2h_persist": sm(np.array([float(len(d["seed_asns"]))]), truth[-1:]),
                     "pred_final": pred_final, "true_final": float(truth[-1]), "n_seed": len(d["seed_asns"]),
                     "library_events": len(finals)})
    df = pl.DataFrame(rows)
    res = {"model": "hist_avg", "membership_target": "full_observed_2h", "tag": tag, "delta_s": delta_s, "k": k, "train_events": len(tr), "test_events": len(te),
           "split_protocol": split_protocol, "library_protocol": "online_completed_train_and_test" if online_completed else "fixed_training_library",
           "onset_signature": ["log1p_all_observed_seeds", "visible_candidate_asns", "log1p_candidate_path_hop_appearances", "log1p_candidate_count"],
           "membership_ranking": "global_library_participation", "magnitude_prediction": "knn_mean_full_target_size_floored_at_observed_seeds",
           "jaccard_hist_mean": round(float(df["jaccard_hist"].mean()), 4), "jaccard_persist_mean": round(float(df["jaccard_persist"].mean()), 4),
           "diff_hist_minus_persistence": bootstrap_diff(df, "jaccard_hist", "jaccard_persist"),
           "smape_2h_hist": round(float(df["smape_2h_hist"].mean()), 4), "smape_2h_persist": round(float(df["smape_2h_persist"].mean()), 4)}
    clean_rows = df.filter(~df["legacy_window_crosses_midnight"])
    res["same_day_replay_sensitivity"] = {"events": clean_rows.height, "excluded": df.height - clean_rows.height,
        "jaccard_hist_mean": clean_rows["jaccard_hist"].mean(), "jaccard_persist_mean": clean_rows["jaccard_persist"].mean(),
        "diff_hist_minus_persistence": bootstrap_diff(clean_rows, "jaccard_hist", "jaccard_persist")}
    out_dir = config.tgn_dir(last, delta_s, tag) / "_results"; out_dir.mkdir(exist_ok=True)
    suf = "" if ys.isdigit() else "_" + ys.replace(",", "+").replace(">", "_to_")
    res["years"] = ys
    prefix = 'hist_avg_online_completed' if online_completed else 'hist_avg'
    df.write_csv(out_dir / f"{prefix}{suf}_test_per_event.csv"); (out_dir / f"{prefix}{suf}_summary.json").write_text(json.dumps(res, indent=1, default=str))
    return res
