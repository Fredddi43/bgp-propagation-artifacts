"""ADR-0018 step 4: build per-event graph tensors for the growing origin-change subset.

Per event: seeds = ASes on anomalous paths by Δ; candidate universe = 2-hop neighbourhood of the seeds on the CAIDA
graph of the event month (capped to the closest `max_nodes` by hop then degree); labels = membership at 2 h
(binary per node); node features: [is_seed, log1p(degree), n_providers, n_customers, n_peers, hop_from_seeds,
n_collectors_seen_by_delta (0..10), log1p(msgs_by_delta), log1p(customer-cone size), log1p(valley-position msgs),
log1p(prior-event participation)]; edges: CAIDA adjacencies within the universe with a
3-way relationship type; message stream (for TGN): (ts_rel, src=origin-side AS, dst=collector-side AS) for every
anomalous announcement hop by Δ — the route flows from src to dst. Saved as one .pt per event under tgn/<year>/<delta>/.
"""
from __future__ import annotations

import datetime as dt
import json
from numbers import Integral
from pathlib import Path

import numpy as np
import polars as pl
import scipy.sparse as sp

from . import config
from .diffusion import load_asgraph, load_cone
from .forecast_protocol import INPUT_CUTOFF_RULE, INPUT_CUTOFF_RULE_ID


def _hops_from(g, seed_idx: np.ndarray, k: int, max_nodes: int) -> tuple[np.ndarray, np.ndarray]:
    A = (g.c2p + g.p2c + g.p2p).tocsr(); A.data[:] = 1.0
    n = A.shape[0]
    hop = np.full(n, -1, dtype=np.int16); hop[seed_idx] = 0
    frontier = seed_idx
    for h in range(1, k + 1):
        nxt = np.unique(A[frontier].indices)
        nxt = nxt[hop[nxt] < 0]
        hop[nxt] = h
        frontier = nxt
    nodes = np.flatnonzero(hop >= 0)
    if nodes.size > max_nodes:
        deg = np.asarray(A[nodes].sum(axis=1)).ravel()
        order = np.lexsort((-deg, hop[nodes]))            # by hop, then high degree first
        nodes = nodes[np.sort(order[:max_nodes])]
    return nodes, hop


def _safe_cone(month: str) -> dict[int, int]:
    try:
        return load_cone(month)
    except Exception as e:  # noqa: BLE001 — a missing cone file must not stop the build; the feature is then constant
        print(f"[cone] {month}: {e}; using 1 for all ASes")
        return {}


def _rel_lookup(month: str) -> dict[tuple[int, int], str]:
    """(u, v) → kind of v for u ('provider' | 'customer' | 'peer') from the month's CAIDA table (cached Parquet)."""
    from .leakcheck import rel_parquet

    rel = pl.read_parquet(rel_parquet(month))
    return {(int(u), int(v)): k for u, v, k in zip(rel["u"].to_list(), rel["v"].to_list(), rel["kind"].to_list())}


def observed_membership(replay: Path, collector: str | tuple[str, ...] | None = None,
                        available_by: dt.datetime | None = None) -> pl.DataFrame:
    """Canonical affected membership, including first-actor path truncation.

    Raw origin paths can repeat the actor and contain suffix ASes that have not
    propagated its route. Exploding all hops would incorrectly make them seeds.

    ``available_by`` (an issue time) keeps only per-collector rows available by
    then under the declared input rule (forecast_protocol.available_at) BEFORE
    pooling; pooling first would hide which collector supplied the minimum. The
    pooled ``first`` stays the raw first_seen of the admitted rows.
    """
    table = pl.read_parquet(replay / 'membership.parquet')
    if collector is not None:
        panel = (collector,) if isinstance(collector, str) else tuple(collector)
        if not panel:
            raise ValueError("An explicit collector panel must not be empty")
        table = table.filter(pl.col('collector').is_in(panel))
    if available_by is not None:
        from .forecast_protocol import admit_available
        table = admit_available(table, available_by, ts_column='first_seen')
    return table.group_by('asn').agg(first=pl.col('first_seen').min())


def build_event(event_id: str, delta_s: int, year: int, max_nodes: int = 3000, graphs: dict | None = None, tag: str = "",
                participation: dict[int, int] | None = None, vp: str | None = None, t0_shift_s: float = 0.0, legality: bool = False,
                retain_no_growth: bool = False, retain_unmapped_seeds: bool = False,
                topology_lag_months: int = 0, rov_lag_days: int = 0,
                input_collectors: tuple[str, ...] | None = None,
                reference_collectors: tuple[str, ...] | None = None,
                early_filter_inputs: bool = False,
                candidate_history_snapshot=None, candidate_history_k: int = 0) -> dict | None:
    from .replay_day import roots

    if not isinstance(candidate_history_k, Integral) or isinstance(candidate_history_k, bool) or candidate_history_k < 0:
        raise ValueError('Candidate history K must be a nonnegative integer')

    d = roots(replay_tag(tag))[1] / event_id
    s = json.loads((d / "summary.json").read_text())
    if s.get("error") or not s.get("first_observation"):
        return None
    t0_true = dt.datetime.fromisoformat(s["first_observation"])
    # ADR-0006 trigger-error test: the forecaster is triggered at t0_true + shift (late trigger > 0, early < 0); its inputs and
    # seeds are what was observed up to the shifted trigger + Δ, while the target stays the true 2-h extent
    t0 = t0_true + dt.timedelta(seconds=t0_shift_s)
    if input_collectors is not None and reference_collectors is None:
        raise ValueError("Input-panel experiments require an explicit fixed reference panel")
    if input_collectors is not None and vp is not None:
        raise ValueError("Specify an input panel or legacy vp, not both")
    input_panel = tuple(sorted(set(input_collectors))) if input_collectors is not None else (vp,) if vp else None
    reference_panel = tuple(sorted(set(reference_collectors))) if reference_collectors is not None else (vp,) if vp else None
    if input_panel == () or reference_panel == ():
        raise ValueError("Collector panels must not be empty")
    issue_time = t0 + dt.timedelta(seconds=delta_s)
    if early_filter_inputs:
        # Superset prefilter only; the declared availability rule is applied to by_delta below.
        source = pl.scan_parquet(d / "anomalous.parquet").filter(pl.col("ts") <= pl.lit(issue_time))
        if input_panel is not None:
            source = source.filter(pl.col("collector").is_in(input_panel))
        anom = source.select("ts", "collector", "as_path", "prefix").collect()
    else:
        anom = pl.read_parquet(d / "anomalous.parquet")
    anom = anom.with_columns(hops=pl.col("as_path").str.replace_all(r"[{}]", "").str.split(" ").list.eval(pl.element().cast(pl.Int64, strict=False)))
    if input_panel is not None:
        anom = anom.filter(pl.col("collector").is_in(input_panel))
        if anom.is_empty():
            return None
    # Inputs: only records available by issue time (whole-second sources at ts + 1 s, WHOLE-SECOND-CUTOFF.md rule A).
    from .forecast_protocol import admit_available
    by_delta = admit_available(anom.filter(pl.col("ts") <= pl.lit(issue_time)), issue_time)
    from .extent import TARGETS_S

    # Every event family uses replay's canonical affected-set definition. In
    # origin paths too, ASes beyond the first actor occurrence are not members.
    # Seeds are inputs (availability rule, per collector before pooling); targets/curve/first_s are labels (raw first_seen).
    mem = observed_membership(d, input_panel, available_by=issue_time)
    target_mem = observed_membership(d, reference_panel)
    seeds = set(int(a) for a in mem["asn"].to_list())
    target = set(int(a) for a in target_mem.filter(pl.col("first") <= pl.lit(t0_true + dt.timedelta(hours=2)))["asn"].to_list())
    # curve labels: pooled members at each target horizon (the magnitude curve the curve head / TSFMs forecast)
    curve = np.array([target_mem.filter(pl.col("first") <= pl.lit(t0_true + dt.timedelta(seconds=ts))).height for ts in TARGETS_S.values()], dtype=np.float32)
    if not seeds or (target <= seeds and not retain_no_growth):
        return None                                       # nothing to forecast (fully grown at Δ)
    # Prospective metadata is anchored to the observed onset, not the catalogue
    # identifier: an event identified on Feb1 can have started on Jan31.
    # Keep the unlagged legacy mode's historical identifier-month convention.
    anchor_year, anchor_month = ((t0_true.year, t0_true.month) if topology_lag_months
                                 else (int(event_id[:4]), int(event_id[4:6])))
    month_index = anchor_year * 12 + anchor_month - 1 - topology_lag_months
    month = f"{month_index // 12:04d}{month_index % 12 + 1:02d}"
    graphs = graphs if graphs is not None else {}
    if month not in graphs:
        graphs[month] = load_asgraph(month)
    g = graphs[month]
    if retain_unmapped_seeds:
        # Unknown seed ASNs remain predictable through persistence, represented
        # as isolated nodes. They are never dropped because CAIDA omits them.
        missing = sorted(seeds - set(g.index))
        if missing:
            from .diffusion import ASGraph
            asns = np.concatenate([g.asns, np.asarray(missing, dtype=np.int64)])
            pad = sp.csr_matrix((len(missing), len(missing)))
            g = ASGraph(asns, {int(a): i for i, a in enumerate(asns)},
                        *(sp.block_diag((m, pad), format="csr") for m in (g.c2p, g.p2c, g.p2p)), month)
    seed_idx = np.array([g.index[a] for a in seeds if a in g.index], dtype=np.int64)
    if seed_idx.size == 0:
        return None
    nodes, hop = _hops_from(g, seed_idx, 2, max(max_nodes, len(seed_idx)))
    new_truth = target - seeds
    known_asns = set(map(int, graphs[month].asns))
    uncapped_asns = set(map(int, g.asns[hop >= 0]))
    candidate_asns = set(map(int, g.asns[nodes]))
    original_candidate_asns = g.asns[nodes].astype(np.int64).copy()
    expansion = None
    if candidate_history_k:
        from .forecast_candidates import expand_graph_candidates
        g, nodes, hop, expansion = expand_graph_candidates(
            g, nodes, hop, candidate_history_snapshot, candidate_history_k,
            issue_time=issue_time, event_id=event_id, participation=participation)
    label_diagnostics = {
        "new_target_count": len(new_truth), "new_target_in_candidates": len(new_truth & candidate_asns),
        "new_target_in_uncapped_two_hop": len(new_truth & uncapped_asns),
        "new_target_omitted_by_cap": len((new_truth & uncapped_asns) - candidate_asns),
        "new_target_outside_two_hop": len(new_truth - uncapped_asns),
        "new_target_unknown_topology": len(new_truth - known_asns),
        "uncapped_candidate_count": len(uncapped_asns),
    }
    reference_seeds = set(map(int, (mem if input_panel == reference_panel
                                    else observed_membership(d, reference_panel, available_by=issue_time))["asn"]))
    label_diagnostics.update(reference_seed_asns=sorted(reference_seeds),
                             reference_new_target_count=len(target - reference_seeds),
                             input_new_target_count=len(target - seeds))
    expansion_fields = {}
    if expansion is not None:
        added = set(expansion['added_asns'])
        expanded = candidate_asns | added
        expansion_fields = {'candidate_expansion': expansion,
                            'original_candidate_asns': original_candidate_asns,
                            'original_uncapped_asns': np.array(sorted(uncapped_asns), dtype=np.int64),
                            'expanded_label_diagnostics': {
                                'new_target_in_candidates': len(new_truth & expanded),
                                'recovered_from_cap': len(new_truth & added & uncapped_asns),
                                'recovered_outside_two_hop': len((new_truth & added) - uncapped_asns),
                                'recovered_unknown_topology': len((new_truth & added) - known_asns),
                                'remaining_outside_candidates': len(new_truth - expanded)}}
    # node features
    deg = np.asarray((g.c2p + g.p2c + g.p2p)[nodes].sum(axis=1)).ravel()
    n_prov = np.asarray(g.c2p[nodes].sum(axis=1)).ravel(); n_cust = np.asarray(g.p2c[nodes].sum(axis=1)).ravel(); n_peer = np.asarray(g.p2p[nodes].sum(axis=1)).ravel()
    asn_of = g.asns[nodes].astype(np.int64)
    seen = (by_delta.select("collector", "hops").explode("hops").rename({"hops": "asn"}).drop_nulls()
                    .group_by("asn").agg(ncol=pl.col("collector").n_unique(), nmsg=pl.len()))
    seen_map = {int(r["asn"]): (r["ncol"], r["nmsg"]) for r in seen.to_dicts()}
    ncol = np.array([seen_map.get(int(a), (0, 0))[0] for a in asn_of], dtype=np.float32)
    nmsg = np.array([seen_map.get(int(a), (0, 0))[1] for a in asn_of], dtype=np.float32)
    # dynamic per-node features of the plan: distinct AS paths and distinct prefixes touching the node in the Δ window
    dyn = (by_delta.select("as_path", "prefix", "hops").explode("hops").rename({"hops": "asn"}).drop_nulls("asn")
                   .group_by("asn").agg(npath=pl.col("as_path").n_unique(), npfx=pl.col("prefix").n_unique()))
    dyn_map = {int(r["asn"]): (r["npath"], r["npfx"]) for r in dyn.to_dicts()}
    npath = np.array([np.log1p(dyn_map.get(int(a), (0, 0))[0]) for a in asn_of], dtype=np.float32)
    npfx = np.array([np.log1p(dyn_map.get(int(a), (0, 0))[1]) for a in asn_of], dtype=np.float32)
    is_seed = np.isin(asn_of, list(seeds)).astype(np.float32)
    if ("cone", month) not in graphs:
        graphs[("cone", month)] = _safe_cone(month)
    cones = graphs[("cone", month)]
    cone = np.array([np.log1p(cones.get(int(a), 1)) for a in asn_of], dtype=np.float32)      # customer-cone size (tier proxy)
    # valley position: how many Δ-window anomalous paths have this AS exporting a route learned from a provider/peer to
    # another provider/peer (the edge-legality signal of the plan, aggregated per node)
    if ("rel", month) not in graphs:
        graphs[("rel", month)] = _rel_lookup(month)
    rel = graphs[("rel", month)]
    valley: dict[int, int] = {}
    for hops in by_delta["hops"].to_list():
        if not hops:
            continue
        for i in range(1, len(hops) - 1):
            xh, a, b = hops[i - 1], hops[i], hops[i + 1]
            if a is None or xh is None or b is None:
                continue
            lf, ex = rel.get((a, b)), rel.get((a, xh))
            if lf in ("provider", "peer") and ex in ("provider", "peer"):
                valley[a] = valley.get(a, 0) + 1
    n_valley = np.array([np.log1p(valley.get(int(a), 0)) for a in asn_of], dtype=np.float32)
    # historical participation: events strictly before this one in which the AS was a member (built in build_split)
    hist = np.array([np.log1p((participation or {}).get(int(a), 0)) for a in asn_of], dtype=np.float32)
    # RPKI/ROV (2026-09-12): per-AS RoVista ROV ratio at the event date (+ measured flag) and the event's new-origin validity
    # (origin-change family; zeros elsewhere) — feature indices 11–15, so ablations can zero them (BGBENCH_ZERO_FEATURES)
    day = (t0_true.date() - dt.timedelta(days=rov_lag_days)).isoformat()
    rr = [rov_ratio(int(a), day) for a in asn_of]
    rov = np.array([r if r is not None else 0.0 for r in rr], dtype=np.float32); rov_m = np.array([r is not None for r in rr], dtype=np.float32)
    if replay_tag(tag) == "" and ("validity", year) not in graphs:
        graphs[("validity", year)] = _validity_map(year)
    vmap = graphs.get(("validity", year), {}) if replay_tag(tag) == "" else {}
    v = vmap.get(event_id, "")
    v_inv, v_unk, v_val = (np.full(len(nodes), float(v == k), dtype=np.float32) for k in ("invalid", "unknown", "valid"))
    # country (plan node feature): the AS's country ROV score (RoVista, 0–1; 0 if unknown) and whether it shares the seeds' majority country
    cc_map, cc_score = _country()
    ccs = [cc_map.get(int(a), "") for a in asn_of]
    from collections import Counter as _C
    seed_cc = _C(c for c, sflag in zip(ccs, is_seed) if sflag and c).most_common(1)
    seed_cc = seed_cc[0][0] if seed_cc else ""
    # The downloaded country score is an undated contemporary snapshot, not a historical feature.
    # Keep its coordinate reserved at zero; only the country-identity feature is available.
    cc_rov = np.zeros(len(ccs), dtype=np.float32)
    cc_same = np.array([float(bool(c) and c == seed_cc) for c in ccs], dtype=np.float32)
    x = np.stack([is_seed, np.log1p(deg), n_prov, n_cust, n_peer, hop[nodes].astype(np.float32), ncol, np.log1p(nmsg), cone, n_valley, hist,
                  rov, rov_m, v_inv, v_unk, v_val, npath, npfx, cc_rov, cc_same], axis=1).astype(np.float32)
    # first membership time per node (seconds after t₀; −1 = never in 2 h) — for the ranking loss on affection order
    first_map = {int(a): (f - t0_true).total_seconds() for a, f in zip(target_mem["asn"].to_list(), target_mem["first"].to_list()) if f is not None and f <= t0_true + dt.timedelta(hours=2)}
    first_s = np.array([first_map.get(int(a), -1.0) for a in asn_of], dtype=np.float32)
    y = np.isin(asn_of, list(target)).astype(np.float32)
    # edges within the universe, typed
    ei, et = [], []
    for M, t in ((g.c2p, 0), (g.p2c, 1), (g.p2p, 2)):
        sub = M[nodes][:, nodes].tocoo()
        ei.append(np.stack([sub.row, sub.col])); et.append(np.full(sub.row.size, t, dtype=np.int64))
    edge_index = np.concatenate(ei, axis=1).astype(np.int64); edge_type = np.concatenate(et)   # scipy coo gives int32; torch scatter wants int64
    if legality:
        # RESEARCH-PLAN edge feature "valley-free legality": can the route legally travel u→v (row→col)? Legal if v is u's customer
        # (types: 0 = c2p means row's provider is col → exporting to a provider; 1 = p2c → exporting to a customer; 2 = p2p → to a peer),
        # or if u is known to have learned the route from a customer (seen in a Δ-window path with a customer as its origin-side hop).
        # Encoded as 3 extra edge classes (3–5 = illegal variants), so the relational readout sees legality per edge.
        from .graph_metrics import learned_from_customers
        learned_from_customer = learned_from_customers(by_delta["hops"].to_list(), rel)
        src_asn = asn_of[edge_index[0]]
        legal = (edge_type == 1) | np.isin(src_asn, list(learned_from_customer))
        edge_type = np.where(legal, edge_type, edge_type + 3)
    # message stream up to Δ: consecutive hops, origin-side → collector-side direction (route flows toward the collector)
    from .graph_metrics import message_stream
    msgs = message_stream(by_delta["ts"].to_list(), by_delta["hops"].to_list(), asn_of, t0)
    return {"event_id": event_id, "x": x, "y": y, "edge_index": edge_index, "edge_type": edge_type, "msgs": msgs,
            "asn": asn_of, "n_seed": int(is_seed.sum()), "n_pos": int(y.sum()), "n_nodes": int(len(nodes)),
            "persistence_pred": is_seed, "curve": curve, "n_seed_all": float(len(seeds)), "first_s": first_s,
            "target_asns": np.array(sorted(target), dtype=np.int64),
            "seed_asns": np.array(sorted(seeds), dtype=np.int64), "observation_cutoff_s": delta_s + t0_shift_s, "measurement_version": measurement_version(tag),
            "topology_month": month, "rov_lookup_day": day,
            "label_diagnostics": label_diagnostics,
            "input_collectors": input_panel or "pooled", "reference_collectors": reference_panel or "pooled",
            "source_availability_assumption": "calendar_lag_not_publication_proof" if topology_lag_months or rov_lag_days else "legacy_event_period",
            "input_cutoff_rule": INPUT_CUTOFF_RULE,
            **expansion_fields}


def parse_tag(tag: str) -> tuple[str, dict]:
    """'leak200@vp=rrc00,k=1500' → ('leak200', {'vp': 'rrc00', 'k': '1500'}). Options: vp = single-collector conditioning
    (seeds, targets, onset messages from that collector only — ADR-0008 §2), k = max_nodes of the pruned universe."""
    base, _, opt = tag.partition("@")
    return base, dict(kv.split("=", 1) for kv in opt.split(",") if "=" in kv)


def feature_width(tag):
    """Recorded experiment schemas; appended exploratory columns are opt-in."""
    base, options = parse_tag(tag)
    return 20 if options.get('v') == '3' else 16 if base in ('rpkivalid', 'rpkiinvalid') else 18 if options and 't0' not in options else 11


def replay_tag(tag: str) -> str:
    """Model-set tag → replay set: leak* → 'leak'; rpkivalid / rpkiinvalid (validity slices) → '' (origin-change set); else itself."""
    base = parse_tag(tag)[0]
    return "leak" if base.startswith("leak") else "" if base in ("rpkivalid", "rpkiinvalid") else base


def measurement_version(tag: str) -> int:
    """Reject origin caches built before canonical first-actor membership."""
    return 3 if replay_tag(tag) == "" else 2


_ROV: dict | None = None


def _rov_series() -> dict:
    """RoVista per-AS ROV ratio series {asn: (dates, ratios)}; empty if the fetch is absent."""
    global _ROV
    if _ROV is None:
        f = config.DATA_ROOT / "rpki" / "rovista" / "as_rov_series.parquet"
        _ROV = {}
        if f.exists():
            d = pl.read_parquet(f).with_columns(pl.col("date").cast(pl.Utf8)).sort("asn", "date")
            for a, g in d.group_by("asn", maintain_order=True):
                _ROV[int(a[0])] = (g["date"].to_list(), g["ratio"].to_list())
    return _ROV


def rov_ratio(asn: int, day: str) -> float | None:
    import bisect
    s = _rov_series().get(asn)
    if not s:
        return None
    i = bisect.bisect_right(s[0], day) - 1
    return s[1][i] if i >= 0 else None


_CC: dict | None = None


def _country() -> tuple[dict[int, str], dict[str, float]]:
    """ASN → country (NRO delegated stats, scripts/fetch_delegated.py) and country → RoVista ROV score (0–100)."""
    global _CC
    if _CC is None:
        f = config.DATA_ROOT / "graphs" / "asn_country.parquet"; g = config.DATA_ROOT / "rpki" / "rovista" / "country_scores.json"
        cc = dict(zip(*[pl.read_parquet(f)[c].to_list() for c in ("asn", "cc")])) if f.exists() else {}
        sc = json.loads(g.read_text()) if g.exists() else {}
        _CC = ({int(k): str(v).lower() for k, v in cc.items()}, {str(k).lower(): float(v) for k, v in sc.items()})
    return _CC


def _validity_map(year: int) -> dict[str, str]:
    f = config.DATA_ROOT / "eventset" / str(year) / "rpki_validity.parquet"
    return dict(zip(*[pl.read_parquet(f)[c].to_list() for c in ("event_id", "validity")])) if f.exists() else {}


def build_split(year: int = 2024, delta_s: int = 30, max_events: int | None = None, max_nodes: int = 3000, tag: str = "",
                *, history_mode: str = "legacy", history_years=None, cohort_mode: str = "legacy",
                manifest_path: Path | None = None, output_dir: Path | None = None,
                history_frozen_at=None, topology_lag_months: int = 0, rov_lag_days: int = 0,
                execution_shard: tuple[int, int] | None = None,
                input_collectors: tuple[str, ...] | None = None,
                reference_collectors: tuple[str, ...] | None = None,
                early_filter_inputs: bool = False, candidate_history_k: int = 0,
                tensor_writer=None, history_root: Path | None = None, history_intervention: dict | None = None) -> dict:
    # ``history_root`` (shared completed history only): a separate data root whose eventsets and replay memberships
    # feed the completed-history library. The current event's inputs, targets and own issue-time signature always
    # come from config.DATA_ROOT. A history root that resolves to the data root is the same as none, so
    # construction is then byte-identical to the single-root builder.
    # ``history_intervention`` (history sensitivities only; None = unchanged primary construction): the explicit
    # identity of a delay or withholding variant (forecast_history_variants.intervention_identity). It is recorded
    # in the contract and source receipt; a withholding identity also removes its donors from every snapshot,
    # before participation and candidate expansion read it.
    import torch
    if not isinstance(candidate_history_k, Integral) or isinstance(candidate_history_k, bool) or candidate_history_k < 0:
        raise ValueError('Candidate history K must be a nonnegative integer')
    if candidate_history_k and history_mode != 'shared_completed':
        raise ValueError('Candidate expansion requires shared completed history')
    if history_mode not in ("legacy", "shared_completed") or cohort_mode not in ("legacy", "broad"):
        raise ValueError("Unknown history/cohort mode")
    if (history_mode != "legacy" or cohort_mode != "legacy" or manifest_path is not None) and output_dir is None:
        raise ValueError("New forecasting protocols require an explicit fresh output_dir")
    if history_mode == "shared_completed" and not history_years:
        raise ValueError("Shared history requires explicit history_years")
    if history_intervention is not None and history_mode != "shared_completed":
        raise ValueError("A history intervention requires shared completed history")
    if history_root is not None:
        if history_mode != "shared_completed":
            raise ValueError("A separate history root requires shared completed history")
        history_root = Path(history_root).resolve()
        if history_root == Path(config.DATA_ROOT).resolve():
            history_root = None
    if topology_lag_months < 0 or rov_lag_days < 0:
        raise ValueError("Availability lags must be nonnegative")
    if (topology_lag_months or rov_lag_days) and output_dir is None:
        raise ValueError("Lagged sources require an explicit fresh output_dir")
    if input_collectors is not None and reference_collectors is None:
        raise ValueError("Input-panel experiments require an explicit fixed reference panel")
    if (input_collectors is not None or reference_collectors is not None or early_filter_inputs) and output_dir is None:
        raise ValueError("Collector-panel/optimized builds require an explicit fresh output_dir")
    base, opts = parse_tag(tag)
    vp = opts.get("vp"); max_nodes = int(opts.get("k", max_nodes)); t0_shift = float(opts.get("t0", 0)); legality = opts.get("legal", "0") == "1"
    if input_collectors is not None and vp is not None:
        raise ValueError("Specify an input panel or legacy vp, not both")
    base_tag = replay_tag(tag)
    tbl = pl.read_parquet(config.DATA_ROOT / "eventset" / (f"{year}_{base_tag}" if base_tag else str(year)) / "events.parquet").filter(pl.col("error").is_null())
    if base_tag == "leak" and cohort_mode == "legacy":
        tbl = tbl.filter(pl.col("observation_lag_s").is_null() | (pl.col("observation_lag_s") >= -60))   # clean onsets only
    if base == "leak200" and cohort_mode == "legacy":                   # the slow regime: large leaks (≥ 200 ASes at 2 h; all still growing at 30 s)
        tbl = tbl.filter(pl.col("set_final_2h").list.len() >= 200)
    if base == "rpkiinvalid":               # RPKI-invalid new origins (the ROV-bounded regime; 2026-09-09-rpki-validity.md)
        val = pl.read_parquet(config.DATA_ROOT / "eventset" / str(year) / "rpki_validity.parquet").filter(pl.col("validity") == "invalid")
        tbl = tbl.join(val.select("event_id"), on="event_id", how="semi")
    if base == "rpkivalid":                  # the slow regime of the origin-change family: ROA-valid new origins (2026-09-09-rpki-validity.md)
        val = pl.read_parquet(config.DATA_ROOT / "eventset" / str(year) / "rpki_validity.parquet").filter(pl.col("validity") == "valid")
        tbl = tbl.join(val.select("event_id"), on="event_id", how="semi")
    if base == "withdrawal":
        base_tag = "withdrawal"
    manifest_digest = None
    manifest_metadata = {}
    if manifest_path is not None:
        import hashlib
        manifest_path = Path(manifest_path)
        manifest_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        if manifest_path.suffix == ".parquet":
            manifest = pl.read_parquet(manifest_path)
        elif manifest_path.suffix == ".json":
            payload = json.loads(manifest_path.read_text())
            manifest_metadata = payload if isinstance(payload, dict) else {}
            if manifest_metadata.get("locked_test"):
                raise ValueError("Protected outcomes require a custodian build, not the retrospective builder")
            if manifest_metadata.get("delta_s", delta_s) != delta_s:
                raise ValueError("Manifest observation horizon differs from build")
            manifest = pl.DataFrame(payload["events"] if isinstance(payload, dict) else payload)
        else:
            manifest = pl.read_csv(manifest_path, separator="\t" if manifest_path.suffix == ".tsv" else ",")
        if "year" in manifest.columns:
            manifest = manifest.filter(pl.col("year") == year)
        else:
            manifest = manifest.filter(pl.col("event_id").str.starts_with(str(year)))
        if manifest["event_id"].n_unique() != manifest.height:
            raise ValueError("Manifest event IDs must be unique")
        missing = set(manifest["event_id"].to_list()) - set(tbl["event_id"].to_list())
        if missing:
            raise ValueError(f"Manifest events absent from eligible source table: {sorted(missing)[:10]}")
        if max_events:
            raise ValueError("A fixed manifest cannot be randomly subsampled")
        tbl = tbl.drop("split").join(manifest.select("event_id", "split"), on="event_id", how="inner")
    out_dir = Path(output_dir) if output_dir is not None else config.tgn_dir(year, delta_s, tag)
    out_dir.mkdir(parents=True, exist_ok=True)
    graphs: dict = {}
    kept, skipped, rows = 0, 0, []
    split_of = dict(zip(tbl["event_id"].to_list(), tbl["split"].to_list()))
    lag_of = dict(zip(tbl["event_id"].to_list(), tbl["observation_lag_s"].to_list())) if "observation_lag_s" in tbl.columns else {}
    if max_events:
        # per-split random sample (a head-of-list cap took only January events → no test split)
        rng = np.random.default_rng(0)
        ids = []
        for sp in ("train", "test"):
            pool = tbl.filter(pl.col("split") == sp)["event_id"].to_list()
            take = min(max_events // 2 if sp == "train" else max_events - max_events // 2, len(pool))
            ids += [pool[i] for i in sorted(rng.choice(len(pool), size=take, replace=False))]
    else:
        ids = tbl.sort("event_id")["event_id"].to_list()
    if execution_shard is not None:
        shard, count = execution_shard
        if count <= 0 or not 0 <= shard < count or output_dir is None:
            raise ValueError("Execution shard requires 0 <= index < count and a private output directory")
        ids = ids[shard::count]
    # A historical footprint is known only after its full target horizon has elapsed.
    t0_of = dict(zip(tbl["event_id"].to_list(), tbl["t0_obs"].to_list()))
    finals = dict(zip(tbl["event_id"].to_list(), tbl["set_final_2h"].to_list()))
    from .graph_metrics import completed_event_histories
    part_at = completed_event_histories(t0_of, finals, query_offset_seconds=t0_shift) if history_mode == "legacy" else {}
    library = None
    if history_mode == "shared_completed":
        from .forecast_history import CompletedEventLibrary, HISTORY_VERSION, utc
        panel_options = ({"signature_collectors": input_collectors, "target_collectors": reference_collectors}
                         if reference_collectors is not None else {"collectors": (vp,) if vp else None})
        library = CompletedEventLibrary.from_eventsets(history_root or config.DATA_ROOT, history_years, base_tag,
                                                       **panel_options,
                                                       availability_delay_s=manifest_metadata.get("availability_delay_s", 0))
        # With a separate history root, the event's own issue-time signature is a current-event input and is
        # read from the data root, never from the history root's (original) record of the same event.
        signature_library = library if history_root is None else CompletedEventLibrary.from_eventsets(
            config.DATA_ROOT, [year], base_tag, **panel_options,
            availability_delay_s=manifest_metadata.get("availability_delay_s", 0))
        receipt = {"source_digest": library.digest, "sources": library.sources}
        if history_intervention is not None:
            from .forecast_history_variants import WITHHOLD_KIND, builder_intervention
            history_intervention = builder_intervention(
                history_intervention, availability_delay_s=manifest_metadata.get("availability_delay_s", 0))
            if history_intervention["kind"] == WITHHOLD_KIND:
                absent = [e for e in history_intervention["withheld_event_ids"] if e not in library.by_id]
                if absent:
                    raise ValueError(f"Withheld donors are not in the history library: {absent}")
            receipt["history_intervention"] = history_intervention
        receipt_path = out_dir / "history_sources.json"
        if receipt_path.exists():
            if json.loads(receipt_path.read_text()) != receipt:
                raise ValueError("Stale history source receipt; use a fresh output directory")
        else:
            with receipt_path.open("x") as handle:
                json.dump(receipt, handle, indent=2)
    history_version = HISTORY_VERSION if library is not None else 2
    contract = {"history_mode": history_mode, "history_version": history_version,
                "history_source_digest": library.digest if library is not None else None,
                "history_frozen_at": str(history_frozen_at) if history_frozen_at is not None else None,
                "cohort_mode": cohort_mode, "manifest_sha256": manifest_digest,
                "delta_s": delta_s, "tag": tag, "max_nodes": max_nodes,
                "topology_lag_months": topology_lag_months, "rov_lag_days": rov_lag_days,
                "input_collectors": sorted(set(input_collectors)) if input_collectors is not None else None,
                "reference_collectors": sorted(set(reference_collectors)) if reference_collectors is not None else None,
                "history_target_scope": "fixed_reference_collectors" if reference_collectors is not None else "legacy_input_collectors",
                "early_filter_inputs": early_filter_inputs,
                # Stale raw-cutoff tensors in a resumed directory fail the contract check below.
                "input_cutoff_rule": INPUT_CUTOFF_RULE_ID}
    if history_root is not None:
        contract["history_root"] = str(history_root)
        # The data-root library that supplies each event's own issue-time signature.
        contract["signature_source_digest"] = signature_library.digest
    if history_intervention is not None:
        contract["history_intervention"] = history_intervention
    if candidate_history_k:
        contract['candidate_expansion'] = {
            'policy': 'original_union_top_completed_participation', 'top_k': int(candidate_history_k),
            'tie_rule': 'descending completed-event participation, then ascending ASN',
            'outside_two_hop_sentinel': -1, 'history_source_digest': library.digest}
    ledger = []
    for eid in ids:
        f = out_dir / f"{eid}.pt"
        if f.exists():
            cached = torch.load(f, weights_only=False, mmap=False)
            if topology_lag_months:
                onset = t0_of[eid]
                onset = dt.datetime.fromisoformat(onset) if isinstance(onset, str) else onset
                month_index = onset.year * 12 + onset.month - 1 - topology_lag_months
                expected_month = f"{month_index // 12:04d}{month_index % 12 + 1:02d}"
                if cached.get('topology_month') != expected_month:
                    raise ValueError(f'Stale topology clock in {f}; rebuild in a fresh output directory')
            if cached.get("measurement_version") != measurement_version(tag) or cached.get('history_version') != history_version or cached['x'].shape[1] != feature_width(tag):
                raise ValueError(f"Stale graph tensor {f}; rebuild in a fresh output directory")
            if history_mode != 'legacy' or cohort_mode != 'legacy' or manifest_path is not None or topology_lag_months or rov_lag_days or input_collectors is not None or reference_collectors is not None or early_filter_inputs:
                if cached.get('forecast_contract') != contract or cached.get('split') != split_of[eid]:
                    raise ValueError(f'Stale forecasting contract in {f}')
            ledger.append({'event_id': eid, 'status': 'built', 'split': split_of[eid]})
            rows.append({'event_id': eid, 'split': cached['split'], 'n_nodes': cached['n_nodes'],
                         'n_seed': cached['n_seed'], 'n_pos': cached['n_pos'], 'n_msgs': int(cached['msgs'].shape[0])})
            kept += 1; continue
        snapshot = library.snapshot(utc(t0_of[eid]) + dt.timedelta(seconds=delta_s + t0_shift),
                                    exclude_event_id=eid, frozen_at=history_frozen_at) if library is not None else None
        if history_intervention is not None and history_intervention["kind"] == "withhold_unavailable_source_donors":
            from .forecast_history_sensitivity import withhold_snapshot
            if eid in history_intervention["withheld_event_ids"]:
                raise ValueError(f"A query cannot be a withheld donor: {eid}")
            snapshot = withhold_snapshot(snapshot, history_intervention["withheld_event_ids"],
                                         policy_sha256=history_intervention["policy_sha256"])
        participation = snapshot.participation if snapshot is not None else part_at.get(eid)
        b = build_event(eid, delta_s, year, max_nodes, graphs, tag, participation, vp=vp,
                        t0_shift_s=t0_shift, legality=legality,
                        retain_no_growth=cohort_mode == "broad", retain_unmapped_seeds=cohort_mode == "broad",
                        topology_lag_months=topology_lag_months, rov_lag_days=rov_lag_days,
                        input_collectors=input_collectors, reference_collectors=reference_collectors,
                        early_filter_inputs=early_filter_inputs,
                        candidate_history_snapshot=snapshot, candidate_history_k=candidate_history_k)
        if b is None:
            ledger.append({"event_id": eid, "status": "unbuildable", "split": split_of[eid],
                           "reason": "missing_valid_onset_or_input_seeds" if cohort_mode == "broad" else "legacy_no_growth_or_nograph"})
            skipped += 1; continue
        b['feature_dim'] = feature_width(tag)
        b['x'] = b['x'][:, :b['feature_dim']].copy()
        b['history_version'] = history_version
        b['forecast_contract'] = contract
        b['source_observation_lag_s'] = lag_of.get(eid)
        b['legacy_onset_clean'] = lag_of.get(eid) is None or lag_of[eid] >= -60
        for key in ("feature_contract", "library_protocol"):
            if key in manifest_metadata:
                b[key] = manifest_metadata[key]
        if snapshot is not None:
            b['history_provenance'] = snapshot.provenance if history_root is None else {
                **snapshot.provenance, "history_root": str(history_root), "signature_source_digest": signature_library.digest}
            b['history_signature'] = signature_library.by_id[eid].signature(delta_s + t0_shift).copy()
        ledger.append({"event_id": eid, "status": "built", "split": split_of[eid],
                       "source_observation_lag_s": lag_of.get(eid), "legacy_onset_clean": b['legacy_onset_clean']})
        # Storage adapters receive the exact same payload; scientific construction is unchanged.
        (tensor_writer or torch.save)({k: (torch.from_numpy(v) if isinstance(v, np.ndarray) else v) for k, v in b.items()} | {"split": split_of[eid]}, f)
        rows.append({"event_id": eid, "split": split_of[eid], "n_nodes": b["n_nodes"], "n_seed": b["n_seed"], "n_pos": b["n_pos"], "n_msgs": int(b["msgs"].shape[0])})
        kept += 1
    if history_mode != "legacy" or cohort_mode != "legacy" or manifest_path is not None or topology_lag_months or rov_lag_days or input_collectors is not None or reference_collectors is not None or early_filter_inputs:
        (out_dir / "forecast_contract.json").write_text(json.dumps(contract, indent=2))
        (out_dir / "cohort_ledger.json").write_text(json.dumps(ledger, indent=2))
    if rows:
        pl.DataFrame(rows).write_csv(out_dir / "index.csv")
    return {"delta_s": delta_s, "built": kept, "skipped_fully_grown_or_nograph": skipped, "out": str(out_dir),
            "by_split": pl.DataFrame(rows).group_by("split").len().to_dicts() if rows else []}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Build isolated, manifest-driven forecasting tensors")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--delta-s", type=int, required=True)
    parser.add_argument("--tag", default="leak")
    parser.add_argument("--history-years", type=int, nargs="+", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-nodes", type=int, default=3000)
    parser.add_argument("--topology-lag-months", type=int, default=1)
    parser.add_argument("--rov-lag-days", type=int, default=1)
    parser.add_argument("--history-frozen-at")
    args = parser.parse_args()
    print(json.dumps(build_split(args.year, args.delta_s, max_nodes=args.max_nodes, tag=args.tag,
                                 history_mode="shared_completed", history_years=args.history_years,
                                 cohort_mode="broad", manifest_path=args.manifest, output_dir=args.output_dir,
                                 history_frozen_at=args.history_frozen_at, topology_lag_months=args.topology_lag_months,
                                 rov_lag_days=args.rov_lag_days), indent=2))
