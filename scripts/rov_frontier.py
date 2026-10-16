"""Does the invalid route stop at ROV-enforcing ASes? For each replayed origin-change event, split the CAIDA one-hop
neighbourhood of the 2-h carrier set into carriers and non-carrying neighbours, look up each AS's RoVista ROV ratio at the
nearest measurement date ≤ t₀ (rpki/rovista/as_rov_series.parquet: asn, date, total, filter, ratio), and compare the share of
enforcing ASes (ratio ≥ 0.5) among carriers vs non-carrying neighbours — per validity state of the new origin. If ROV is the
mechanism, invalid events show far fewer enforcing carriers than valid/unknown events do, and their non-carrying frontier is
enriched in enforcers. Also reports RoVista coverage (fraction of ASes with any measurement).
usage: rov_frontier.py <year> [--max-events N] [--threshold T] [--freeze-date D] [--min-total N] [--suffix S]  → eventset/<year>/rov_frontier<S>.json"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict

import numpy as np
import polars as pl

from bgbench import config
from bgbench.rov_history import ratio_at as historical_ratio_at

ap = argparse.ArgumentParser()
ap.add_argument("year", type=int)
ap.add_argument("--max-events", type=int, default=0)
ap.add_argument("--threshold", type=float, default=0.5, help="RoVista ratio at or above which an AS counts as ROV-enforcing")
ap.add_argument("--freeze-date", default=None, help="YYYY-MM-DD: ignore RoVista measurements after this date (nearest date <= min(t0, freeze) is used); "
                "guards against a change of the RoVista measurement regime between years")
ap.add_argument("--min-total", type=int, default=0, help="drop RoVista measurements with fewer than N probes (column total)")
ap.add_argument("--suffix", default="", help="write eventset/<year>/rov_frontier<suffix>.json instead of overwriting the default")
ap.add_argument("--only-reason", default=None, help="keep only events with this selection reason (events.parquet column reason), e.g. rpki_invalid_sample")
ap.add_argument("--exclude-reason", default=None, help="drop events with this selection reason, e.g. rpki_invalid_sample to reproduce the pre-stratum population")
a = ap.parse_args()
E = config.DATA_ROOT / "eventset" / str(a.year)

rov = pl.read_parquet(config.DATA_ROOT / "rpki" / "rovista" / "as_rov_series.parquet").with_columns(pl.col("date").cast(pl.Utf8)).sort("asn", "date")
if a.freeze_date:
    rov = rov.filter(pl.col("date") <= a.freeze_date)
if a.min_total:
    rov = rov.filter(pl.col("total") >= a.min_total)
series: dict[int, tuple[list[str], list[float]]] = {}
for asn, g in rov.group_by("asn", maintain_order=True):
    series[int(asn[0])] = (g["date"].to_list(), g["ratio"].to_list())


def ratio_at(asn: int, day: str):
    return historical_ratio_at(series, asn, day)


ev = pl.read_parquet(E / "events.parquet").filter(pl.col("error").is_null())
if a.only_reason:
    ev = ev.filter(pl.col("reason") == a.only_reason)
if a.exclude_reason:
    ev = ev.filter(pl.col("reason") != a.exclude_reason)
ev = ev.select("event_id", "split", "set_final_2h", "asns_final_2h")
val = pl.read_parquet(E / "rpki_validity.parquet").select("event_id", "validity")
ev = ev.join(val, on="event_id", how="left", validate="1:1").with_columns(pl.col("event_id").str.slice(0, 8).alias("day8"))
if ev["validity"].null_count():
    raise ValueError("Missing RPKI labels for frontier events")
if a.max_events:
    ev = ev.sample(n=min(a.max_events, ev.height), seed=0)
rel_cache: dict[str, dict[int, set]] = {}


def neighbours(month: str) -> dict[int, set]:
    if month not in rel_cache:
        rel_cache.clear()
        f = config.DATA_ROOT / "graphs" / f"{month}01.rel.parquet"
        nb = defaultdict(set)
        if f.exists():
            for u, v in pl.read_parquet(f, columns=["u", "v"]).iter_rows():
                nb[int(u)].add(int(v)); nb[int(v)].add(int(u))
        rel_cache[month] = nb
    return rel_cache[month]


acc = defaultdict(lambda: {"events": 0, "carriers": 0, "carriers_measured": 0, "carriers_enforcing": 0, "frontier": 0, "frontier_measured": 0, "frontier_enforcing": 0, "carriers_future_only": 0, "frontier_future_only": 0, "odds": []})
event_rows = []
current_day = None
measured_asns, enforcing_asns, future_asns = set(), set(), set()
for r in ev.sort("day8").iter_rows(named=True):
    day = f"{r['day8'][:4]}-{r['day8'][4:6]}-{r['day8'][6:8]}"
    if day != current_day:
        # Each historical lookup depends only on the AS and day, not the event.
        # Set intersections replace millions of repeated Python-level lookups.
        ratios = {asn: ratio_at(asn, day) for asn in series}
        measured_asns = {asn for asn, ratio in ratios.items() if ratio is not None}
        enforcing_asns = {asn for asn, ratio in ratios.items() if ratio is not None and ratio >= a.threshold}
        future_asns = {asn for asn, (dates, _) in series.items() if dates[0] > day}
        current_day = day
    nb = neighbours(r["day8"][:6])
    carriers = set(int(x) for x in (r["set_final_2h"] or []))
    if not carriers:
        continue
    frontier = set().union(*(nb.get(c, set()) for c in carriers)) - carriers
    A = acc[r["validity"]]
    A["events"] += 1
    A["carriers_future_only"] += len(carriers & future_asns)
    A["frontier_future_only"] += len(frontier & future_asns)
    cm_count, fm_count = len(carriers & measured_asns), len(frontier & measured_asns)
    ce, fe = len(carriers & enforcing_asns), len(frontier & enforcing_asns)
    A["carriers"] += len(carriers); A["carriers_measured"] += cm_count; A["carriers_enforcing"] += ce
    A["frontier"] += len(frontier); A["frontier_measured"] += fm_count; A["frontier_enforcing"] += fe
    odds = None
    if cm_count and fm_count:
        pc, pf = (ce + 0.5) / (cm_count + 1), (fe + 0.5) / (fm_count + 1)
        odds = float(np.log((pf / (1 - pf)) / (pc / (1 - pc))))
        A["odds"].append(odds)   # >0: frontier more enforcing than carriers
    event_rows.append({"event_id": r["event_id"], "split": r["split"], "validity": r["validity"],
                       "carriers": len(carriers), "carriers_measured": cm_count, "carriers_enforcing": ce,
                       "frontier": len(frontier), "frontier_measured": fm_count, "frontier_enforcing": fe,
                       "log_odds": odds})

pl.DataFrame(event_rows).write_parquet(E / f"rov_frontier{a.suffix}.parquet")
out = {"year": a.year, "threshold": a.threshold, "freeze_date": a.freeze_date, "min_total": a.min_total, "only_reason": a.only_reason,
       "exclude_reason": a.exclude_reason, "lookup_policy": "latest measurement at or before event date; missing history is unknown", "rovista_ases": len(series), "by_validity": {}}
rng = np.random.default_rng(0)
for v, A in acc.items():
    out["by_validity"][v] = {
        "events": A["events"],
        "future_only_carrier_observations_excluded": A["carriers_future_only"],
        "future_only_frontier_observations_excluded": A["frontier_future_only"],
        "carriers_measured_share": round(A["carriers_measured"] / max(A["carriers"], 1), 3), "frontier_measured_share": round(A["frontier_measured"] / max(A["frontier"], 1), 3),
        "enforcing_share_carriers": round(A["carriers_enforcing"] / A["carriers_measured"], 4) if A["carriers_measured"] else None,
        "enforcing_share_frontier": round(A["frontier_enforcing"] / A["frontier_measured"], 4) if A["frontier_measured"] else None,
        "log_odds_frontier_vs_carriers_mean": round(float(np.mean(A["odds"])), 3) if A["odds"] else None,
        "log_odds_mean_ci95_bootstrap": [round(float(x), 3) for x in np.percentile([np.mean(rng.choice(A["odds"], size=len(A["odds"]))) for _ in range(1000)], (2.5, 97.5))] if len(A["odds"]) > 20 else None,
        "log_odds_per_event_p10_p90": [round(float(np.percentile(A["odds"], q)), 3) for q in (10, 90)] if len(A["odds"]) > 20 else None,
        "events_with_both_measured": len(A["odds"])}
print(json.dumps(out, indent=1))
(E / f"rov_frontier{a.suffix}.json").write_text(json.dumps(out, indent=1))
