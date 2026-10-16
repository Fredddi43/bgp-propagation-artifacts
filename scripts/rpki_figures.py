"""Paper figures for the RPKI headline. (a) persistence floor (Jaccard 30 s → 2 h, test) by validity of the new origin per year,
with the displaced-origin split; (b) ROV frontier: enforcing share among carriers vs frontier and the per-event log-odds by validity.
Reads eventset/<year>/rpki_validity_summary.json and rov_frontier.json. usage: rpki_figures.py <out_dir> [years...]"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from bgbench import config

import argparse
import polars as pl
_ap = argparse.ArgumentParser()
_ap.add_argument("out"); _ap.add_argument("years", nargs="*", type=int)
_ap.add_argument("--exclude-reason", default=None, help="drop events with this selection reason from panel (a), e.g. rpki_invalid_sample")
_ap.add_argument("--frontier", default="", help="per-year rov_frontier file suffix, e.g. 2024=_labelled,2026=_frozen2505")
_a = _ap.parse_args()
out = Path(_a.out); out.mkdir(parents=True, exist_ok=True)
years = _a.years or [2024, 2025]
FSUF = dict(kv.split("=") for kv in _a.frontier.split(",") if kv)


def floors_by_class(y: int):
    """Event- and incident-weighted J(30 s, 2 h) on the test split by validity, from events.parquet (population filter applied)."""
    E = config.DATA_ROOT / "eventset" / str(y)
    ev = pl.read_parquet(E / "events.parquet").filter(pl.col("error").is_null() & (pl.col("split") == "test"))
    if _a.exclude_reason:
        ev = ev.filter(pl.col("reason") != _a.exclude_reason)
    ev = ev.join(pl.read_parquet(E / "rpki_validity.parquet").select("event_id", "validity"), on="event_id")
    man = pl.read_csv(config.DATA_ROOT / "inventory" / str(y) / "replay_manifest.tsv", separator="\t").select("event_id", pl.col("new_origin").cast(pl.Int64), "t0")
    ev = ev.join(man, on="event_id").with_columns(
        (pl.col("set_d30s").list.set_intersection(pl.col("set_final_2h")).list.len() / pl.col("set_d30s").list.set_union(pl.col("set_final_2h")).list.len().clip(1)).alias("J"),
        (pl.col("new_origin").cast(pl.Utf8) + "@" + pl.col("t0").str.slice(0, 13)).alias("incident"))
    e = {r["validity"]: r["J"] for r in ev.group_by("validity").agg(pl.col("J").mean()).iter_rows(named=True)}
    inc = ev.group_by("validity", "incident").agg(pl.col("J").mean()).group_by("validity").agg(pl.col("J").mean())
    i = {r["validity"]: r["J"] for r in inc.iter_rows(named=True)}
    return e, i
ORDER = ["invalid", "unknown", "valid"]
LAB = {"invalid": "RPKI-invalid", "unknown": "no covering\nROA", "valid": "ROA-valid"}
COL = {"invalid": "C3", "unknown": "0.5", "valid": "C2"}

fig, axes = plt.subplots(1, 3, figsize=(13, 4))
# (a) floors by validity per year, event- and incident-weighted
ax = axes[0]; w = 0.38
for i, y in enumerate(years):
    e_, i_ = floors_by_class(y)
    ev = [e_.get(v, 0.0) for v in ORDER]
    inc = [i_.get(v, 0.0) for v in ORDER]
    xs = [k * (len(years) + 1) + i for k in range(len(ORDER))]
    ax.bar([x - w / 2 for x in xs], ev, w, color=[COL[v] for v in ORDER], alpha=1.0 if i == 0 else 0.6, label=f"{y} events" )
    ax.bar([x + w / 2 for x in xs], inc, w, color=[COL[v] for v in ORDER], alpha=1.0 if i == 0 else 0.6, hatch="//", label=f"{y} incidents")
    for x, v in zip(xs, ORDER):
        ax.text(x, -0.06, str(y)[2:], ha="center", va="top", fontsize=8, transform=ax.get_xaxis_transform())
ax.set_xticks([k * (len(years) + 1) + (len(years) - 1) / 2 for k in range(len(ORDER))]); ax.set_xticklabels([LAB[v] for v in ORDER])
ax.set_ylabel("persistence Jaccard, 30 s → 2 h (test)"); ax.set_ylim(0, 0.9); ax.set_title("(a) floor by validity of the new origin"); ax.grid(axis="y", alpha=0.3)
ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color="0.7"), plt.Rectangle((0, 0), 1, 1, color="0.7", hatch="//")], labels=["event-weighted", "incident-weighted"], loc="upper right", fontsize=8)
# (a') displaced-origin split for the first year
ax = axes[1]
d = json.load(open(config.DATA_ROOT / "eventset" / str(years[0]) / "rpki_validity_summary.json"))["by_validity_x_prev"]
keys = [("invalid|prev=valid", "invalid ← valid\n(textbook hijack)"), ("invalid|prev=invalid", "invalid ← invalid"), ("unknown|prev=unknown", "unknown ← unknown"),
        ("valid|prev=valid", "valid ← valid\n(authorised move)"), ("valid|prev=invalid", "valid ← invalid\n(recovery)")]
vals = [(lab, d[k]["persist_j30_test_mean"], d[k]["n"]) for k, lab in keys if k in d]
ax.barh([v[0] for v in vals], [v[1] for v in vals], color=["C3", "C3", "0.5", "C2", "C2"][: len(vals)])
for j, (lab, val, n) in enumerate(vals):
    ax.text(val + 0.01, j, f"n={n:,}", va="center", fontsize=8)
ax.invert_yaxis(); ax.set_xlim(0, 0.95); ax.set_xlabel(f"persistence Jaccard, 30 s → 2 h ({years[0]} test)"); ax.set_title("(b) new origin ← displaced origin"); ax.grid(axis="x", alpha=0.3)
# (c) ROV frontier
ax = axes[2]
for i, y in enumerate(years):
    f = config.DATA_ROOT / "eventset" / str(y) / f"rov_frontier{FSUF.get(str(y), '')}.json"
    if not f.exists():
        continue
    r = json.load(open(f))["by_validity"]
    xs = [k * (len(years) + 1) + i for k in range(len(ORDER))]
    m = [r[v]["log_odds_frontier_vs_carriers_mean"] for v in ORDER]
    lo = [m[k] - r[v]["log_odds_mean_ci95_bootstrap"][0] for k, v in enumerate(ORDER)]; hi = [r[v]["log_odds_mean_ci95_bootstrap"][1] - m[k] for k, v in enumerate(ORDER)]
    ax.bar(xs, m, 0.8, color=[COL[v] for v in ORDER], alpha=1.0 if i == 0 else 0.6, yerr=[lo, hi], capsize=3)
    for x, v in zip(xs, ORDER):
        ax.text(x, 0.02 if m[ORDER.index(v)] < 0 else -0.08, str(y)[2:], ha="center", va="bottom" if m[ORDER.index(v)] < 0 else "top", fontsize=8)
ax.axhline(0, color="k", lw=0.8); ax.set_xticks([k * (len(years) + 1) + (len(years) - 1) / 2 for k in range(len(ORDER))]); ax.set_xticklabels([LAB[v] for v in ORDER])
ax.set_ylabel("log-odds: ROV-enforcing in frontier vs among carriers"); ax.set_title("(c) where the route stops (RoVista)"); ax.grid(axis="y", alpha=0.3)
fig.tight_layout(); fig.savefig(out / "rpki_headline.png", dpi=160); print("wrote", out / "rpki_headline.png")
