"""ADR-0007 rung 3: epidemic / independent-cascade baseline for BGP propagation over the CAIDA AS graph.

Graph: CAIDA AS Relationships serial-1 (`YYYYMM01.as-rel.txt.bz2`, lines `a|b|rel` with rel -1 = a is
provider of b, 0 = peers). Model: independent cascade — at each step every newly-affected AS infects each
neighbour independently with probability p(edge). Edge probability parameterised by relationship and
direction (customer→provider, provider→customer, peer↔peer) so that valley-free-ish preferences can be
encoded and later *estimated from historical co-affection* (ADR-0007). Monte-Carlo rollout from a seed
set gives the expected affected set and a hop-indexed growth curve.

Implemented on scipy.sparse: 77k nodes / 0.5M edges, ~1000 rollouts in minutes (audit: 3.7 min).
"""

from __future__ import annotations

import bz2
import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import httpx
import numpy as np
import polars as pl
import scipy.sparse as sp

from . import config

CAIDA_SERIAL1 = (
    "https://publicdata.caida.org/datasets/as-relationships/serial-1/{ym}01.as-rel.txt.bz2"
)


@dataclass
class ASGraph:
    asns: np.ndarray  # index -> ASN
    index: dict[int, int]  # ASN -> index
    # directed adjacency by edge class, CSR, shape (n, n), entry 1 where an edge of that class goes i -> j
    c2p: sp.csr_matrix  # customer -> provider
    p2c: sp.csr_matrix  # provider -> customer
    p2p: sp.csr_matrix  # peer -> peer (symmetric)
    month: str


def caida_path(month: str) -> Path:
    d = config.DATA_ROOT / "graphs"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{month}01.as-rel.txt.bz2"


def load_asgraph(month: str) -> ASGraph:
    """month = 'YYYYMM'. Downloads the CAIDA file once (AUA: cite CAIDA AS Relationships) and caches it."""
    p = caida_path(month)
    if not p.exists():
        r = httpx.get(CAIDA_SERIAL1.format(ym=month), timeout=120, follow_redirects=True)
        r.raise_for_status()
        p.write_bytes(r.content)
    a, b, rel = [], [], []
    with bz2.open(p, "rt") as f:
        for line in f:
            if line.startswith("#"):
                continue
            x, y, r_ = line.strip().split("|")[:3]
            a.append(int(x))
            b.append(int(y))
            rel.append(int(r_))
    a, b, rel = np.array(a), np.array(b), np.array(rel)
    asns = np.unique(np.concatenate([a, b]))
    index = {int(v): i for i, v in enumerate(asns)}
    ia = np.array([index[int(v)] for v in a])
    ib = np.array([index[int(v)] for v in b])
    n = len(asns)
    prov = rel == -1  # a provider of b  →  p2c: a->b ; c2p: b->a
    peer = rel == 0
    ones = lambda k: np.ones(k, dtype=np.float32)
    p2c = sp.csr_matrix((ones(prov.sum()), (ia[prov], ib[prov])), shape=(n, n))
    c2p = sp.csr_matrix((ones(prov.sum()), (ib[prov], ia[prov])), shape=(n, n))
    p2p = sp.csr_matrix((ones(peer.sum()), (ia[peer], ib[peer])), shape=(n, n))
    p2p = p2p + p2p.T
    return ASGraph(asns, index, c2p, p2c, p2p, month)


@dataclass
class ICParams:
    p_c2p: float = 0.9  # a customer's new route is almost always exported to its providers
    p_p2c: float = 0.5  # a provider re-exports to customers
    p_p2p: float = 0.3  # peers accept/export selectively
    max_steps: int = 12
    rollouts: int = 200
    seed: int = 0
    rec: float = 1.0          # recovery probability per step: 1.0 = independent cascade (one attempt), < 1 = SIR-like re-attempts
    valley_free: bool = False # Gao–Rexford export constraint: a node that learned the route from a provider or peer re-exports
                              # only to customers; one that learned it from a customer exports to everyone. Seeds are unconstrained
                              # (for a leak, the seed's own export *is* the violation).



def transition_matrix(g: ASGraph, p: ICParams) -> sp.csr_matrix:
    """Infection probability matrix P[i, j] = probability that affected i infects j in one step."""
    P = (p.p_c2p * g.c2p + p.p_p2c * g.p2c + p.p_p2p * g.p2p).tocsr()
    P.data = np.minimum(P.data, 1.0)
    return P


def _stay(PT: sp.csr_matrix, idx: np.ndarray) -> np.ndarray:
    """probability that each j stays uninfected given attempts from frontier nodes idx: prod_i (1 - P[i, j])."""
    sub = PT[:, idx]
    log_stay = sub.copy()
    log_stay.data = np.log1p(-log_stay.data)
    return np.exp(np.asarray(log_stay.sum(axis=1)).ravel())


def independent_cascade(
    P: sp.csr_matrix, seed_idx: np.ndarray, p: ICParams, rng: np.random.Generator,
    vf: tuple[sp.csr_matrix, sp.csr_matrix, sp.csr_matrix] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """One rollout. Returns (infection_step per node, -1 if never; list of cumulative counts per step).
    vf: optional (P_c2p, P_other, P_down) for the valley-free variant — attempts from an 'up' node (learned from a customer, or a
    seed) use P_c2p ∪ P_other = P; attempts from a 'down' node use P_down (provider→customer edges only); a node infected through
    a c2p edge becomes 'up', otherwise 'down'."""
    n = P.shape[0]
    step = np.full(n, -1, dtype=np.int16)
    step[seed_idx] = 0
    frontier = np.zeros(n, dtype=bool)
    frontier[seed_idx] = True
    active = frontier.copy()
    up = frontier.copy()
    curve = [int(active.sum())]
    PT = P.T.tocsr()  # PT[j, i] = P[i, j]; to get attempts on j from frontier i's
    if vf is not None:
        PT_c2p, PT_other, PT_down = (m.T.tocsr() for m in vf)
    for t in range(1, p.max_steps + 1):
        idx = np.flatnonzero(frontier)
        if idx.size == 0:
            break
        if vf is None:
            newly = (rng.random(n) > _stay(PT, idx)) & ~active
        else:
            iu = np.flatnonzero(frontier & up); idn = np.flatnonzero(frontier & ~up)
            via_c2p = rng.random(n) > _stay(PT_c2p, iu) if iu.size else np.zeros(n, dtype=bool)
            stay_other = _stay(PT_other, iu) if iu.size else np.ones(n)
            stay_down = _stay(PT_down, idn) if idn.size else np.ones(n)
            via_other = rng.random(n) > stay_other * stay_down
            newly = (via_c2p | via_other) & ~active
            up[newly & via_c2p] = True
        step[newly] = t
        active |= newly
        keep = frontier & (rng.random(n) >= p.rec) if p.rec < 1.0 else np.zeros(n, dtype=bool)   # SIR: still infectious next step
        frontier = newly | keep
        curve.append(int(active.sum()))
    return step, np.array(curve)


def simulate(g: ASGraph, seeds: list[int], p: ICParams, P: sp.csr_matrix | None = None) -> dict:
    """Monte-Carlo expected affected set: per-ASN infection probability, expected size per step.
    P: optional precomputed transition matrix (e.g. fit_coaffection); default = relationship-type probabilities."""
    rng = np.random.default_rng(p.seed)
    vf = None
    if p.valley_free and P is None:
        vf = ((p.p_c2p * g.c2p).tocsr(), (p.p_p2c * g.p2c + p.p_p2p * g.p2p).tocsr(), (p.p_p2c * g.p2c).tocsr())
        for m in vf:
            m.data = np.minimum(m.data, 1.0)
    P = transition_matrix(g, p) if P is None else P
    seed_idx = np.array([g.index[s] for s in seeds if s in g.index], dtype=np.int64)
    if seed_idx.size == 0:
        raise ValueError("no seed ASN present in the graph")
    prob = np.zeros(P.shape[0])
    first = np.zeros(P.shape[0])
    curves = []
    for _ in range(p.rollouts):
        step, curve = independent_cascade(P, seed_idx, p, rng, vf=vf)
        hit = step >= 0
        prob[hit] += 1
        first[hit] += step[hit]
        curves.append(curve)
    prob /= p.rollouts
    mean_step = np.where(prob > 0, first / np.maximum(prob * p.rollouts, 1), np.nan)
    L = max(len(c) for c in curves)
    padded = np.array([np.pad(c, (0, L - len(c)), mode="edge") for c in curves])
    return {
        "asn": g.asns,
        "p_affected": prob,
        "mean_step": mean_step,
        "expected_curve": padded.mean(axis=0),
        "curve_p10": np.percentile(padded, 10, axis=0),
        "curve_p90": np.percentile(padded, 90, axis=0),
        "seeds_in_graph": int(seed_idx.size),
    }


def evaluate_membership(
    pred_prob: np.ndarray,
    asns: np.ndarray,
    observed: set[int],
    candidates: set[int] | None = None,
    threshold: float = 0.5,
) -> dict:
    """Precision/recall/F1/Jaccard + AUPRC of the cascade's per-AS probability against the observed set,
    over the candidate set (default: all ASes with p > 0 ∪ observed)."""
    df = pl.DataFrame({"asn": asns.astype(np.int64), "p": pred_prob})
    df = df.with_columns(y=pl.col("asn").is_in(list(observed)))
    if candidates is not None:
        df = df.filter(pl.col("asn").is_in(list(candidates)))
    else:
        df = df.filter((pl.col("p") > 0) | pl.col("y"))
    pred = df["p"] >= threshold
    tp = int((pred & df["y"]).sum())
    fp = int((pred & ~df["y"]).sum())
    fn = int((~pred & df["y"]).sum())
    prec = tp / max(tp + fp, 1)
    rec = tp / max(tp + fn, 1)
    # AUPRC by sorting
    d = df.sort("p", descending=True)
    y = d["y"].to_numpy().astype(int)
    n_pos = y.sum()
    if n_pos == 0:
        auprc = float("nan")
    else:
        cum_tp = np.cumsum(y)
        k = np.arange(1, len(y) + 1)
        precision_at = cum_tp / k
        auprc = float((precision_at * y).sum() / n_pos)
    return {
        "candidates": df.height,
        "positives": int(df["y"].sum()),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": round(prec, 4),
        "recall": round(rec, 4),
        "f1": round(2 * prec * rec / max(prec + rec, 1e-9), 4),
        "jaccard": round(tp / max(tp + fp + fn, 1), 4),
        "auprc": round(auprc, 4),
    }


def baseline_for_event(
    name: str, t0: str, delta_s: int, month: str, p: ICParams | None = None, candidates: str = "rib"
) -> dict:
    """Seed = ASes observed on leaked paths by t₀+Δ (from leak_membership.parquet); target = ASes observed by 2 h.
    Reports persistence (seed set) vs cascade (p ≥ 0.5) vs observed final, plus AUPRC of the cascade probabilities."""
    p = p or ICParams()
    t0d = dt.datetime.fromisoformat(t0).replace(tzinfo=dt.UTC)
    mem = pl.read_parquet(config.EVENT_DIR / name / "_extent" / "leak_membership.parquet")
    seeds = set(
        mem.filter(pl.col("first_seen") <= pl.lit(t0d + dt.timedelta(seconds=delta_s)))[
            "asn"
        ].to_list()
    )
    final = set(
        mem.filter(pl.col("first_seen") <= pl.lit(t0d + dt.timedelta(seconds=7200)))[
            "asn"
        ].to_list()
    )
    g = load_asgraph(month)
    sim = simulate(g, sorted(seeds), p)
    cand = candidate_set(candidates, name, g, seeds, final, t0d)
    ev = evaluate_membership(sim["p_affected"], sim["asn"], final, cand)
    ev["candidate_set"] = candidates
    # persistence scored on the same candidate set, so the two are comparable
    cand_pos = final if cand is None else (final & cand)
    # persistence baseline: predict final == seeds
    tp = len(seeds & cand_pos)
    fp = len(seeds - cand_pos)
    fn = len(cand_pos - seeds)
    persistence = {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": round(tp / max(tp + fp, 1), 4),
        "recall": round(tp / max(tp + fn, 1), 4),
        "jaccard": round(tp / max(tp + fp + fn, 1), 4),
    }
    out_dir = config.EVENT_DIR / name / "_extent"
    pl.DataFrame(
        {
            "asn": sim["asn"].astype(np.int64),
            "p_affected": sim["p_affected"],
            "mean_step": sim["mean_step"],
        }
    ).filter(pl.col("p_affected") > 0).write_parquet(out_dir / f"cascade_delta{delta_s}.parquet")
    return {
        "event": name,
        "delta_s": delta_s,
        "graph_month": month,
        "graph_nodes": len(g.asns),
        "seeds": len(seeds),
        "seeds_in_graph": sim["seeds_in_graph"],
        "observed_final": len(final),
        "cascade_expected_size": [round(float(x), 1) for x in sim["expected_curve"]],
        "cascade_membership_p50": ev,
        "persistence": persistence,
        "params": p.__dict__,
    }


# ---- candidate set + calibration -------------------------------------------------------------------
def rib_candidate_asns(
    name: str, t0: dt.datetime | None = None, prefixes: list[str] | None = None
) -> set[int]:
    """ASes on ANY pre-event RIB path (all collectors, all peers) to the event's prefixes — the VP-visible
    universe the cascade is scored on (ADR-0005 pruned candidate set, v0). Uses the RIB parquet itself, not
    the route-change table (which only holds the routes that changed and would make the set ≈ positives)."""
    from .extent import _rib_paths

    if prefixes is None:
        f = config.EVENT_DIR / name / "_extent" / "leaked_prefix_vp.parquet"
        prefixes = pl.read_parquet(f)["prefix"].unique().to_list()
    rib = (
        _rib_paths(None, t0)
        .filter(pl.col("prefix").is_in(prefixes))
        .select("as_path")
        .collect(engine="streaming")
    )
    hops = (
        rib.with_columns(
            h=pl.col("as_path")
            .str.replace_all(r"[{}]", "")
            .str.split(" ")
            .list.eval(pl.element().cast(pl.Int64, strict=False))
        )
        .select(pl.col("h").explode())
        .drop_nulls()
        .unique()
    )
    return set(hops["h"].to_list())


def khop_candidates(g: ASGraph, seeds: set[int], k: int = 2) -> set[int]:
    """ADR-0005: the k-hop neighbourhood of the seed set on the (undirected) AS graph."""
    A = g.c2p + g.p2c + g.p2p
    A.data[:] = 1.0
    A = A.tocsr()
    idx = np.array([g.index[s] for s in seeds if s in g.index], dtype=np.int64)
    reached = np.zeros(A.shape[0], dtype=bool)
    reached[idx] = True
    frontier = reached.copy()
    for _ in range(k):
        nxt = np.asarray(A[np.flatnonzero(frontier)].sum(axis=0)).ravel() > 0
        frontier = nxt & ~reached
        reached |= nxt
    return {int(a) for a in g.asns[reached]}


def candidate_set(
    kind: str, name: str, g: ASGraph, seeds: set[int], final: set[int], t0: dt.datetime
) -> set[int] | None:
    if kind == "all":
        return None
    if kind == "rib":
        return rib_candidate_asns(name, t0) | seeds | final
    if kind.startswith("khop"):
        k = int(kind.split(":")[1]) if ":" in kind else 2
        return khop_candidates(g, seeds, k) | seeds | final
    raise ValueError(kind)


def calibrate(
    name: str,
    t0: str,
    delta_s: int,
    month: str,
    grid: dict | None = None,
    rollouts: int = 30,
    candidates: str = "rib",
) -> pl.DataFrame:
    """Grid over edge probabilities; each row = params + membership metrics vs the 2 h observed set."""
    grid = grid or {
        "p_c2p": [0.02, 0.05, 0.1, 0.3],
        "p_p2c": [0.0005, 0.001, 0.002, 0.005, 0.01, 0.02],
        "p_p2p": [0.0002, 0.0005, 0.001, 0.002, 0.005],
    }
    t0d = dt.datetime.fromisoformat(t0).replace(tzinfo=dt.UTC)
    mem = pl.read_parquet(config.EVENT_DIR / name / "_extent" / "leak_membership.parquet")
    seeds = set(
        mem.filter(pl.col("first_seen") <= pl.lit(t0d + dt.timedelta(seconds=delta_s)))[
            "asn"
        ].to_list()
    )
    final = set(
        mem.filter(pl.col("first_seen") <= pl.lit(t0d + dt.timedelta(seconds=7200)))[
            "asn"
        ].to_list()
    )
    g = load_asgraph(month)
    cand = candidate_set(candidates, name, g, seeds, final, t0d)
    rows = []
    for a in grid["p_c2p"]:
        for b in grid["p_p2c"]:
            for c in grid["p_p2p"]:
                p = ICParams(p_c2p=a, p_p2c=b, p_p2p=c, rollouts=rollouts)
                sim = simulate(g, sorted(seeds), p)
                ev = evaluate_membership(sim["p_affected"], sim["asn"], final, cand)
                exp_final = float(sim["expected_curve"][-1])
                # size error of the expected cascade size against the observed 2 h membership (magnitude target, ADR-0012)
                size_smape = 2 * abs(exp_final - len(final)) / max(exp_final + len(final), 1e-9)
                rows.append(
                    {
                        "p_c2p": a,
                        "p_p2c": b,
                        "p_p2p": c,
                        "expected_size": round(exp_final, 1),
                        "size_smape": round(size_smape, 3),
                        "observed_final": len(final),
                        "seeds": len(seeds),
                        "candidate_set": candidates,
                        **ev,
                    }
                )
    return pl.DataFrame(rows).sort("jaccard", descending=True)


def fit_coaffection(
    g: ASGraph,
    seeds_list: list[set[int]],
    finals_list: list[set[int]],
    prior: ICParams,
    alpha: float = 5.0,
) -> tuple[sp.csr_matrix, dict]:
    """Issue #21: per-edge infection probabilities from historical co-affection on training events.

    For every graph edge i→j (i's route exported to j), a *trial* is a training event where i was affected by Δ and
    j was not yet; a *success* is such a trial where j was affected by the target horizon. The estimate is shrunk
    towards the relationship-type prior (the calibrated global ICParams):  p_ij = (s_ij + α·p_type) / (n_ij + α),
    so edges never exercised in training keep the type prior. Returns (P, fit stats)."""
    n = len(g.asns)
    A = transition_matrix(g, prior).tocoo()
    I, J, ptype = A.row, A.col, A.data
    ev_rows, s_cols, g_cols = [], [], []
    for e, (S, F) in enumerate(zip(seeds_list, finals_list)):
        si = [g.index[a] for a in S if a in g.index]
        gi = [g.index[a] for a in (F - S) if a in g.index]
        ev_rows.append((si, gi))
    E = len(ev_rows)
    Sm = sp.csr_matrix(
        (np.ones(sum(len(s) for s, _ in ev_rows)), (np.repeat(np.arange(E), [len(s) for s, _ in ev_rows]),
                                                       np.concatenate([s for s, _ in ev_rows] or [np.array([], int)]))),
        shape=(E, n),
    ).tocsc()
    Gm = sp.csr_matrix(
        (np.ones(sum(len(q) for _, q in ev_rows)), (np.repeat(np.arange(E), [len(q) for _, q in ev_rows]),
                                                       np.concatenate([q for _, q in ev_rows] or [np.array([], int)]))),
        shape=(E, n),
    ).tocsc()
    seed_count = np.asarray(Sm.sum(axis=0)).ravel()
    # trials n_ij = #events with i∈S and j∉S ; successes s_ij = #events with i∈S and j∈F\S — both on the edge support
    trials = np.zeros(len(I))
    succ = np.zeros(len(I))
    chunk = 200_000
    for k in range(0, len(I), chunk):
        ii, jj = I[k : k + chunk], J[k : k + chunk]
        both_seed = np.asarray(Sm[:, ii].multiply(Sm[:, jj]).sum(axis=0)).ravel()
        trials[k : k + chunk] = seed_count[ii] - both_seed
        succ[k : k + chunk] = np.asarray(Sm[:, ii].multiply(Gm[:, jj]).sum(axis=0)).ravel()
    p = (succ + alpha * ptype) / (trials + alpha)
    P = sp.csr_matrix((np.minimum(p, 1.0), (I, J)), shape=(n, n))
    stats = {
        "events": E, "edges": int(len(I)), "edges_with_trials": int((trials > 0).sum()),
        "edges_with_success": int((succ > 0).sum()), "trials_total": int(trials.sum()), "successes_total": int(succ.sum()),
        "alpha": alpha, "p_mean_exercised": float(p[trials > 0].mean()) if (trials > 0).any() else None,
    }
    return P, stats


CAIDA_CONE = "https://publicdata.caida.org/datasets/as-relationships/serial-1/{ym}01.ppdc-ases.txt.bz2"


def load_cone(month: str) -> dict[int, int]:
    """Customer-cone size per ASN from CAIDA's ppdc-ases file of the month (downloaded once, cached next to as-rel)."""
    p = config.DATA_ROOT / "graphs" / f"{month}01.ppdc-ases.txt.bz2"
    if not p.exists():
        r = httpx.get(CAIDA_CONE.format(ym=month), timeout=180, follow_redirects=True)
        r.raise_for_status()
        p.write_bytes(r.content)
    cone: dict[int, int] = {}
    with bz2.open(p, "rt") as f:
        for line in f:
            if line.startswith("#"):
                continue
            parts = line.split()
            if parts:
                cone[int(parts[0])] = len(parts)          # the AS itself plus its customer cone
    return cone
