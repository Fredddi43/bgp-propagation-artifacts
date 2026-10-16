"""ADR-0018 step 4 / ADR-0007 rung 5: static GNN on the per-event 2-hop graphs (the "generic graph model" baseline),
before the temporal model. GraphSAGE over the typed CAIDA edges (relationship type as a learned embedding added to
messages), node features from tgn_data, BCE with positive weighting; train on Jan–Aug events, test on Sep–Dec;
scored per event (AUPRC, Jaccard at 0.5) against persistence (predict the seeds) on the same universe.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from . import config


def load_events(dir_: Path, split: str) -> list[dict]:
    return load_splits(dir_)[split]


def load_splits(dir_: Path) -> dict[str, list[dict]]:
    """One pass over the .pt files (network filesystem) → {"train": [...], "test": [...]}."""
    out: dict[str, list[dict]] = {"train": [], "test": []}
    for f in sorted(dir_.glob("*.pt")):
        d = torch.load(f, weights_only=False)
        if d.get("split") in out:
            d["edge_index"] = d["edge_index"].long()      # tensors built before 2026-09-05 carry scipy's int32 indices
            out[d["split"]].append(d)
    return out


QUANTILES = (0.1, 0.5, 0.9)
N_HORIZONS = 4            # extent.TARGETS_S: 5 min, 15 min, 60 min, 2 h


class TypedSAGE(nn.Module):
    """Relational GraphSAGE: one SAGEConv per CAIDA edge class (c2p, p2c, p2p) per layer, summed — the relationship type
    is now used (RESEARCH-PLAN "edge features: relationship type"). Two heads off the shared embedding (ADR-0005):
    membership logits per node, and a curve head — quantiles of log1p(members) at the four target horizons from the
    pooled seed embedding + [log1p(n_seed), log1p(n_nodes)] — trained with the pinball loss (the uncertainty cone)."""

    def __init__(self, in_dim: int, hid: int = 64, n_types: int = 3, layers: int = 2, dropout: float = 0.2,
                 curve_head: str = "quantile", separate_encoders: bool = False):
        super().__init__()
        from torch_geometric.nn import SAGEConv
        self.n_types = n_types; self.curve_head = curve_head; self.separate = separate_encoders
        mk = lambda: nn.ModuleList([nn.ModuleList([SAGEConv(in_dim if i == 0 else hid, hid) for _ in range(n_types)]) for i in range(layers)])  # noqa: E731
        self.convs = mk()
        self.convs_curve = mk() if separate_encoders else None          # plan's open question: shared vs separate encoders
        self.out = nn.Linear(hid + in_dim, 1)
        n_out = N_HORIZONS * len(QUANTILES) if curve_head == "quantile" else 3    # logistic head: (K, r, t_mid)
        self.curve = nn.Sequential(nn.Linear(2 * hid + 2, hid), nn.ReLU(), nn.Linear(hid, n_out))
        self.dropout = dropout

    def _encode(self, convs, x, edge_index, edge_type):
        h = x
        for layer in convs:
            agg = None
            for t, conv in enumerate(layer):
                m = edge_type == t
                if m.any():
                    out = conv(h, edge_index[:, m])
                    agg = out if agg is None else agg + out
            if agg is None:                              # no edges at all in this universe
                agg = layer[0](h, edge_index)
            h = F.dropout(F.relu(agg), self.dropout, self.training)
        return h

    def forward(self, x, edge_index, edge_type, seed_mask):
        h = self._encode(self.convs, x, edge_index, edge_type)
        logits = self.out(torch.cat([h, x], dim=1)).squeeze(-1)
        seed = seed_mask.bool()
        hc = self._encode(self.convs_curve, x, edge_index, edge_type) if self.separate else h
        pooled = torch.cat([hc[seed].mean(0) if seed.any() else hc.mean(0), hc.mean(0),
                            torch.log1p(seed.sum().float()).view(1), torch.log1p(torch.tensor(float(hc.shape[0]), device=hc.device)).view(1)])
        raw = self.curve(pooled)
        n0 = torch.log1p(seed.sum().float())
        if self.curve_head == "logistic":
            # parametric growth curve (plan's alternative head): log-count = n0 + K·σ(r·(t − t_mid)) at the four horizons; emitted as
            # a point curve replicated over the quantile slots so downstream code is unchanged (no interval)
            K = F.softplus(raw[0]); r = F.softplus(raw[1]) + 1e-3; tm = raw[2] * 60.0
            ts = torch.tensor([300.0, 900.0, 3600.0, 7200.0], device=raw.device)
            pt = n0 + K * torch.sigmoid(r * (torch.log1p(ts) - torch.log1p(F.softplus(tm))))
            return logits, pt.unsqueeze(1).repeat(1, len(QUANTILES))
        q = raw.view(N_HORIZONS, len(QUANTILES))
        # monotone in the quantile index and never below log1p(n_seed): members can only be added
        q = torch.cumsum(F.softplus(q), dim=1) + n0
        return logits, q


def n_edge_types(events: list[dict]) -> int:
    """3 for the plain CAIDA classes, 6 when tensors carry the valley-free legality split (tag option legal=1)."""
    m = max((int(d["edge_type"].max()) for d in events if d["edge_type"].numel()), default=2)
    return 6 if m >= 3 else 3


def rank_loss(logit: torch.Tensor, first_s: torch.Tensor, n_pairs: int = 256, margin: float = 0.5) -> torch.Tensor:
    """Plan's optional ranking loss on affection order: among nodes that do join by 2 h, the earlier joiner should score higher.
    Pairwise margin ranking on sampled (earlier, later) pairs of non-seed positives; zero when fewer than two such nodes."""
    pos = torch.nonzero(first_s > 0, as_tuple=False).squeeze(-1)
    if pos.numel() < 2:
        return logit.sum() * 0.0
    i = pos[torch.randint(0, pos.numel(), (n_pairs,), device=logit.device)]; j = pos[torch.randint(0, pos.numel(), (n_pairs,), device=logit.device)]
    keep = first_s[i] != first_s[j]
    if keep.sum() == 0:
        return logit.sum() * 0.0
    i, j = i[keep], j[keep]
    sign = torch.where(first_s[i] < first_s[j], 1.0, -1.0)     # +1: i joined earlier → logit_i should exceed logit_j
    return F.margin_ranking_loss(logit[i], logit[j], sign, margin=margin)


def pinball(q: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    """q: (H, Q) predicted quantiles of log1p(count); target: (H,) log1p(count)."""
    diff = target.unsqueeze(1) - q
    taus = torch.tensor(QUANTILES, device=q.device).view(1, -1)
    return torch.maximum(taus * diff, (taus - 1) * diff).mean()


def focal_bce(logit: torch.Tensor, y: torch.Tensor, pos_weight: torch.Tensor, gamma: float) -> torch.Tensor:
    bce = F.binary_cross_entropy_with_logits(logit, y, pos_weight=pos_weight, reduction="none")
    p = torch.sigmoid(logit); pt = torch.where(y > 0.5, p, 1 - p)
    return ((1 - pt) ** gamma * bce).mean()


def _auprc(y: np.ndarray, p: np.ndarray) -> float:
    from sklearn.metrics import average_precision_score
    return float(average_precision_score(y, p)) if y.sum() > 0 and y.sum() < len(y) else float("nan")


def _jaccard(y: np.ndarray, pred: np.ndarray) -> float:
    inter = np.logical_and(y, pred).sum(); union = np.logical_or(y, pred).sum()
    return float(inter / union) if union else float("nan")


def sage_forward(model, d: dict, device):
    return model(d["x"].to(device), d["edge_index"].to(device), d["edge_type"].to(device), d["persistence_pred"].to(device))


THRESHOLDS = [round(0.05 * k, 2) for k in range(2, 20)]     # 0.10 … 0.95


def predict(model, events: list[dict], device, forward=sage_forward) -> list[tuple[dict, np.ndarray]]:
    """Per-event membership probabilities; model.eval() inside no_grad (TGNMemory.train(False) flushes its store)."""
    out = []
    with torch.no_grad():
        model.eval()
        for d in events:
            logit, q = forward(model, d, device)
            out.append((d, torch.sigmoid(logit).cpu().numpy(), q.cpu().numpy()))
    return out


def best_threshold(preds: list[tuple[dict, np.ndarray]]) -> float:
    """Decision threshold that maximises mean Jaccard on the given (training) events — the model's operating point."""
    best, best_j = 0.5, -1.0
    for t in THRESHOLDS:
        js = []
        for d, p, _q in preds:
            y = d["y"].numpy().astype(bool); seed = d["persistence_pred"].numpy().astype(bool)
            js.append(_jaccard(y, seed | (p >= t)))
        j = float(np.nanmean(js)) if js else float("nan")
        if j > best_j:
            best, best_j = t, j
    return best


def evaluate(model, events: list[dict], device, forward=sage_forward, threshold: float = 0.5) -> dict:
    """Per-event scoring shared by every model. Seeds are known members; the model forecasts the *new* ones, so AUPRC is
    over non-seed nodes and the set metrics use seeds ∪ {p ≥ threshold}. Reported at 0.5 and at `threshold`."""
    rows = []
    for d, p, q in predict(model, events, device, forward):
        y = d["y"].numpy(); yb = y.astype(bool); seed = d["persistence_pred"].numpy().astype(bool); mask = ~seed
        pred5 = seed | (p >= 0.5); predt = seed | (p >= threshold)
        row = {"event_id": d["event_id"], "n": len(y), "pos": int(y.sum()), "new_pos": int(y[mask].sum()),
               "auprc_new": _auprc(y[mask], p[mask]) if mask.sum() else float("nan"),
               "jaccard_model": _jaccard(yb, pred5), "jaccard_model_tuned": _jaccard(yb, predt),
               "jaccard_persist": _jaccard(yb, seed),
               "recall_model": float(np.logical_and(yb, pred5).sum() / max(y.sum(), 1)),
               "recall_model_tuned": float(np.logical_and(yb, predt).sum() / max(y.sum(), 1)),
               "size_ratio_tuned": float(predt.sum() / max(y.sum(), 1))}
        if "curve" in d:
            truth = d["curve"].numpy(); n_seed = float(d.get("n_seed_all", d["n_seed"]))
            med = np.expm1(q[:, 1]); lo = np.expm1(q[:, 0]); hi = np.expm1(q[:, 2])
            sm = lambda a, b: float(np.mean(2 * np.abs(a - b) / np.maximum(np.abs(a) + np.abs(b), 1e-9)))
            row.update({"curve_smape_model": sm(med, truth), "curve_smape_persist": sm(np.full_like(truth, n_seed), truth),
                        "curve_cover80": float(np.mean((truth >= lo) & (truth <= hi))),
                        "curve_smape_2h_model": sm(med[-1:], truth[-1:]), "curve_smape_2h_persist": sm(np.full(1, n_seed), truth[-1:])})
        rows.append(row)
    import polars as pl
    df = pl.DataFrame(rows)
    return {"events": df.height, "threshold": threshold, "auprc_new_mean": round(float(df["auprc_new"].drop_nans().mean()), 4),
            "jaccard_model_mean": round(float(df["jaccard_model"].mean()), 4),
            "jaccard_model_tuned_mean": round(float(df["jaccard_model_tuned"].mean()), 4),
            "jaccard_persist_mean": round(float(df["jaccard_persist"].mean()), 4),
            "model_beats_persistence_frac": round(float((df["jaccard_model"] > df["jaccard_persist"]).mean()), 4),
            "tuned_beats_persistence_frac": round(float((df["jaccard_model_tuned"] > df["jaccard_persist"]).mean()), 4),
            "recall_model_mean": round(float(df["recall_model"].mean()), 4), "recall_model_tuned_mean": round(float(df["recall_model_tuned"].mean()), 4),
            "size_ratio_tuned_p50": round(float(df["size_ratio_tuned"].median()), 4),
            **({"curve_smape_model": round(float(df["curve_smape_model"].mean()), 4), "curve_smape_persist": round(float(df["curve_smape_persist"].mean()), 4),
                "curve_cover80": round(float(df["curve_cover80"].mean()), 4),
                "curve_smape_2h_model": round(float(df["curve_smape_2h_model"].mean()), 4), "curve_smape_2h_persist": round(float(df["curve_smape_2h_persist"].mean()), 4)}
               if "curve_smape_model" in df.columns else {}),
            "_rows": df}


def bootstrap_diff(rows, col_a: str, col_b: str, n: int = 2000, seed: int = 0) -> dict:
    """Bootstrap over events of mean(col_a − col_b): point estimate and 95 % interval (ADR-0019: every model-vs-persistence
    comparison carries one)."""
    d = (rows[col_a] - rows[col_b]).to_numpy()
    d = d[~np.isnan(d)]
    if d.size == 0:
        return {"mean": float("nan"), "ci95": [float("nan"), float("nan")], "n": 0}
    rng = np.random.default_rng(seed)
    means = np.array([d[rng.integers(0, d.size, d.size)].mean() for _ in range(n)])
    return {"mean": round(float(d.mean()), 4), "ci95": [round(float(np.percentile(means, 2.5)), 4), round(float(np.percentile(means, 97.5)), 4)], "n": int(d.size)}


def fit(year, delta_s: int, model_factory, prefix: str, epochs: int, forward=sage_forward, prepare=None,
        post_step=None, lr: float = 1e-3, pos_weight_cap: float = 20.0, seed: int = 0, extra: dict | None = None, tag: str = "",
        focal_gamma: float = 0.0, curve_weight: float = 1.0, rank_weight: float = 0.0) -> dict:
    """The one training loop every rung shares (so the rung-5 / rung-6 comparison stays like-for-like):
    train-statistic feature normalisation, Adam(lr, wd 1e-5), BCE with capped positive weight on the *non-seed* nodes,
    per-epoch test evaluation, results as <prefix>_test_per_event.csv + <prefix>_summary.json.
    model_factory(in_dim, events) → nn.Module; prepare(event) runs once per event after normalisation;
    post_step(model) runs after each optimiser step (e.g. detaching TGN memory)."""
    import time

    torch.manual_seed(seed); np.random.seed(seed)
    # years: "2024" (one year, ADR-0017 within-year split) | "2023,2024,2025" (pooled within-year splits) |
    # "2023,2024>2025" (train on the first years, test on the last — cross-year generalisation, ADR-0008 §1 strict)
    ys = str(year)
    if ">" in ys:
        tr_years, te_years = [int(y) for y in ys.split(">")[0].split(",")], [int(y) for y in ys.split(">")[1].split(",")]
        tr = [d for y in tr_years for sp in load_splits(config.tgn_dir(y, delta_s, tag)).values() for d in sp]
        te = [d for y in te_years for sp in load_splits(config.tgn_dir(y, delta_s, tag)).values() for d in sp]
        dir_ = config.tgn_dir(te_years[-1], delta_s, tag)
    else:
        years = [int(y) for y in ys.split(",")]
        tr, te = [], []
        for y in years:
            sp = load_splits(config.tgn_dir(y, delta_s, tag)); tr += sp["train"]; te += sp["test"]
        dir_ = config.tgn_dir(years[-1], delta_s, tag)
    if not tr or not te:
        return {"error": f"train={len(tr)} test={len(te)} events"}
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    zero = [int(i) for i in os.environ.get("BGBENCH_ZERO_FEATURES", "").split(",") if i.strip()]   # ablation: blank feature columns
    if zero:
        for d in tr + te:
            d["x"][:, zero] = 0.0
        prefix = f"{prefix}{os.environ.get('BGBENCH_PREFIX_SUFFIX', '_z' + '-'.join(map(str, zero)))}"
    elif os.environ.get("BGBENCH_PREFIX_SUFFIX"):
        prefix = prefix + os.environ["BGBENCH_PREFIX_SUFFIX"]
    X = torch.cat([d["x"] for d in tr]); mu, sd = X.mean(0), X.std(0) + 1e-6; del X
    for d in tr + te:
        d["x"] = (d["x"] - mu) / sd
        if prepare is not None:
            prepare(d)
    model = model_factory(tr[0]["x"].shape[1], tr + te).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-5)
    hist = []; t_start = time.time(); ev = None
    for ep in range(epochs):
        model.train(); tot = 0.0
        for i in np.random.permutation(len(tr)):
            d = tr[i]; y = d["y"].to(device)
            mask = ~d["persistence_pred"].bool().to(device)           # learn on the non-seed nodes only
            if mask.sum() == 0:
                continue
            logit, q = forward(model, d, device)
            pos = y[mask].sum(); neg = mask.sum() - pos
            pw = torch.clamp(neg / torch.clamp(pos, min=1.0), max=pos_weight_cap)
            loss = (focal_bce(logit[mask], y[mask], pw, focal_gamma) if focal_gamma > 0
                    else F.binary_cross_entropy_with_logits(logit[mask], y[mask], pos_weight=pw))
            if "curve" in d and curve_weight > 0:
                loss = loss + curve_weight * pinball(q, torch.log1p(d["curve"].to(device)))
            if rank_weight > 0 and "first_s" in d:
                fs = d["first_s"].to(device); fs = torch.where(mask, fs, torch.full_like(fs, -1.0))   # rank only non-seed joiners
                loss = loss + rank_weight * rank_loss(logit, fs)
            opt.zero_grad(); loss.backward(); opt.step(); tot += float(loss)
            if post_step is not None:
                post_step(model)
        ev = evaluate(model, te, device, forward)
        if post_step is not None:
            post_step(model)              # e.g. detach TGN memory after the eval-mode flush
        hist.append({"epoch": ep + 1, "loss": round(tot / max(len(tr), 1), 4), "test_auprc_new": ev["auprc_new_mean"],
                     "test_jaccard_model": ev["jaccard_model_mean"], "elapsed_s": round(time.time() - t_start)})
    thr = best_threshold(predict(model, tr, device, forward))            # operating point chosen on the training events
    final = evaluate(model, te, device, forward, threshold=thr)
    rows = final.pop("_rows")
    probs = {d["event_id"]: (d["asn"].numpy(), p) for d, p, _q in predict(model, te, device, forward)}   # for per-VP scoring (ADR-0008 §2)
    final["diff_tuned_minus_persistence"] = bootstrap_diff(rows, "jaccard_model_tuned", "jaccard_persist")
    final["diff_at05_minus_persistence"] = bootstrap_diff(rows, "jaccard_model", "jaccard_persist")
    out_dir = dir_ / "_results"; out_dir.mkdir(exist_ok=True)
    prefix = prefix if str(year).isdigit() else f"{prefix}_{str(year).replace(',', '+').replace('>', '_to_')}"
    rows.write_csv(out_dir / f"{prefix}_test_per_event.csv")
    torch.save({"state_dict": model.state_dict(), "mu": mu, "sd": sd, "threshold": thr, "prefix": prefix, "tag": tag, "delta_s": delta_s, "n_types": n_edge_types(tr)},
               out_dir / f"{prefix}_model.pt")                      # for the robustness evaluations (ADR-0008 §4–5)
    torch.save(probs, out_dir / f"{prefix}_test_probs.pt")
    if "curve_smape_model" in rows.columns:
        final["diff_curve_smape_model_minus_persist"] = bootstrap_diff(rows, "curve_smape_model", "curve_smape_persist")
    res = {"model": prefix, "tag": tag, "years": str(year), "delta_s": delta_s, "train_events": len(tr), "test_events": len(te), "epochs": epochs, "lr": lr, "threshold_tuned_on_train": thr,
           "focal_gamma": focal_gamma, "curve_weight": curve_weight, "rank_weight": rank_weight,
           "pos_weight_cap": pos_weight_cap, "device": str(device), **(extra or {}), "final_test": final, "history": hist}
    (out_dir / f"{prefix}_summary.json").write_text(json.dumps(res, indent=1, default=str))
    return res


def train(year="2024", delta_s: int = 30, epochs: int = 20, hid: int = 64, lr: float = 1e-3, pos_weight_cap: float = 20.0, seed: int = 0, tag: str = "",
          focal_gamma: float = 0.0, curve_weight: float = 1.0, rank_weight: float = 0.0, curve_head: str = "quantile", separate_encoders: bool = False) -> dict:
    return fit(year, delta_s, lambda in_dim, evs: TypedSAGE(in_dim, hid, n_types=n_edge_types(evs), curve_head=curve_head, separate_encoders=separate_encoders), "sage", epochs, lr=lr, pos_weight_cap=pos_weight_cap, rank_weight=rank_weight,
               seed=seed, extra={"hid": hid}, tag=tag, focal_gamma=focal_gamma, curve_weight=curve_weight)
