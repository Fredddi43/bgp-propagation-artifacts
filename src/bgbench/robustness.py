"""ADR-0008 §5 (data poisoning of onset announcements) and §4-adjacent (partial signal loss) on the saved rung-5/6 models.

Perturbations of a test event's Δ-window input, applied to the tensors:
- drop: a fraction of the messages is removed and the per-node message/collector counts rescaled (signal loss at onset);
- inject: k fake early "affected" nodes are added as seeds (an adversary relaying crafted announcements that make
  uninvolved ASes look hit); the persistence baseline suffers the same injection;
- hide: the true seeds' visibility features are zeroed except is_seed (onset seen but not how widely).
Reported: Jaccard (tuned threshold) and AUPRC per perturbation level vs the clean run and vs persistence.
"""
from __future__ import annotations

import json

import numpy as np
import polars as pl
import torch

from . import config
from .gnn_train import TypedSAGE, _auprc, _jaccard, load_splits, sage_forward


def _perturb(d: dict, kind: str, level: float, rng: np.random.Generator) -> dict:
    e = {k: (v.clone() if torch.is_tensor(v) else v) for k, v in d.items()}
    if kind == "drop" and e["msgs"].shape[0]:
        keep = rng.random(e["msgs"].shape[0]) >= level
        e["msgs"] = e["msgs"][torch.from_numpy(keep)]
        e["x"][:, 6] = e["x"][:, 6] * (1 - level); e["x"][:, 7] = torch.log1p(torch.expm1(e["x"][:, 7]) * (1 - level))
    elif kind == "inject":
        seed = e["persistence_pred"].bool()
        cand = torch.nonzero(~seed & (e["x"][:, 5] == 1)).flatten()          # 1-hop neighbours of the seeds
        k = int(round(level * max(1, int(seed.sum()))))
        if cand.numel() and k:
            pick = cand[torch.from_numpy(rng.choice(cand.numel(), size=min(k, cand.numel()), replace=False))]
            e["persistence_pred"][pick] = 1.0; e["x"][pick, 0] = 1.0; e["x"][pick, 6] = 1.0; e["x"][pick, 7] = np.log1p(1.0)
    elif kind == "hide":
        seed = e["persistence_pred"].bool()
        e["x"][seed, 6] = 0.0; e["x"][seed, 7] = 0.0
    return e


def run(year: int = 2024, delta_s: int = 30, tag: str = "", prefix: str = "sage", seed: int = 0) -> dict:
    dir_ = config.tgn_dir(year, delta_s, tag)
    ck = torch.load(dir_ / "_results" / f"{prefix}_model.pt", weights_only=False)
    te = load_splits(dir_)["test"]
    if not te:
        return {"error": "no test events"}
    mu, sd, thr = ck["mu"], ck["sd"], ck["threshold"]
    in_dim = te[0]["x"].shape[1]
    if prefix != "sage":
        return {"error": "robustness runs on the saved relational SAGE (TGN state needs the event stream re-prepared)"}
    model = TypedSAGE(in_dim, 64); model.load_state_dict(ck["state_dict"]); model.eval()
    rng = np.random.default_rng(seed)
    levels = {"clean": [0.0], "drop": [0.3, 0.6, 0.9], "inject": [0.25, 0.5, 1.0], "hide": [1.0]}
    rows = []
    with torch.no_grad():
        for kind, lv in levels.items():
            for level in lv:
                for d in te:
                    e = _perturb(d, kind, level, rng) if kind != "clean" else d
                    e = dict(e); e["x"] = (e["x"] - mu) / sd
                    logit, _ = sage_forward(model, e, "cpu")
                    p = torch.sigmoid(logit).numpy(); y = d["y"].numpy().astype(bool)
                    sd_ = e["persistence_pred"].numpy().astype(bool); mask = ~sd_
                    rows.append({"kind": kind, "level": level, "event_id": d["event_id"],
                                 "jaccard_model": _jaccard(y, sd_ | (p >= thr)), "jaccard_persist": _jaccard(y, sd_),
                                 "auprc_new": _auprc(y[mask], p[mask]) if mask.sum() and y[mask].sum() else float("nan")})
    df = pl.DataFrame(rows)
    summ = (df.group_by("kind", "level").agg(n=pl.len(), jaccard_model=pl.col("jaccard_model").mean().round(4), jaccard_persist=pl.col("jaccard_persist").mean().round(4),
                                             auprc_new=pl.col("auprc_new").drop_nans().mean().round(4)).sort("kind", "level"))
    out = dir_ / "_results"; df.write_csv(out / f"{prefix}_robustness_per_event.csv"); summ.write_csv(out / f"{prefix}_robustness.csv")
    res = {"model": prefix, "tag": tag, "delta_s": delta_s, "threshold": thr, "table": summ.to_dicts()}
    (out / f"{prefix}_robustness.json").write_text(json.dumps(res, indent=1, default=str))
    return res


def cross_eval(model_year: int, model_tag: str, eval_year: int, eval_tag: str, delta_s: int = 30, prefix: str = "sage") -> dict:
    """ADR-0008 §4 (signal loss / blind spot): evaluate a saved membership model trained on one family (e.g. large leaks)
    on another family's test events (e.g. withdrawal waves, where the input stream is withdrawals and the seeds are the
    ASes that already lost a path). Reports Jaccard at the saved threshold and at 0.5 against persistence, plus AUPRC."""
    ck = torch.load(config.tgn_dir(model_year, delta_s, model_tag) / "_results" / f"{prefix}_model.pt", weights_only=False)
    splits = load_splits(config.tgn_dir(eval_year, delta_s, eval_tag)); te = splits["test"] or splits["train"]
    if not te:
        return {"error": "no events"}
    mu, sd, thr = ck["mu"], ck["sd"], ck["threshold"]
    in_dim = int(mu.shape[0])                       # tensors built later may carry more feature columns; score on the model's own
    model = TypedSAGE(in_dim, 64, n_types=int(ck.get("n_types", 3))); model.load_state_dict(ck["state_dict"]); model.eval()
    rows = []
    with torch.no_grad():
        for d in te:
            e = dict(d); e["x"] = (e["x"][:, :in_dim] - mu) / sd
            logit, q = sage_forward(model, e, "cpu"); p = torch.sigmoid(logit).numpy()
            y = d["y"].numpy().astype(bool); seed = d["persistence_pred"].numpy().astype(bool); mask = ~seed
            rows.append({"event_id": d["event_id"], "n": len(y), "pos": int(y.sum()), "seeds": int(seed.sum()),
                         "jaccard_thr": _jaccard(y, seed | (p >= thr)), "jaccard_05": _jaccard(y, seed | (p >= 0.5)), "jaccard_persist": _jaccard(y, seed),
                         "auprc_new": _auprc(y[mask], p[mask]) if mask.sum() and y[mask].sum() else float("nan"),
                         "curve_pred_2h": float(np.expm1(q[-1, 1].item())), "curve_true_2h": float(d["curve"][-1].item()) if "curve" in d else float(y.sum())})
    df = pl.DataFrame(rows)
    res = {"model": f"{prefix}:{model_tag}:{model_year}", "eval": f"{eval_tag}:{eval_year}", "delta_s": delta_s, "threshold": thr, "events": df.height,
           "jaccard_thr": round(float(df["jaccard_thr"].mean()), 4), "jaccard_05": round(float(df["jaccard_05"].mean()), 4), "jaccard_persist": round(float(df["jaccard_persist"].mean()), 4),
           "auprc_new": round(float(df["auprc_new"].drop_nans().mean()), 4) if df["auprc_new"].drop_nans().len() else None,
           "curve_smape_2h": round(float((2 * (df["curve_pred_2h"] - df["curve_true_2h"]).abs() / (df["curve_pred_2h"].abs() + df["curve_true_2h"].abs()).clip(1e-9)).mean()), 4)}
    out = config.tgn_dir(eval_year, delta_s, eval_tag) / "_results"; out.mkdir(exist_ok=True)
    df.write_csv(out / f"cross_{prefix}_{model_tag}{model_year}_per_event.csv"); (out / f"cross_{prefix}_{model_tag}{model_year}.json").write_text(json.dumps(res, indent=1, default=str))
    return res
