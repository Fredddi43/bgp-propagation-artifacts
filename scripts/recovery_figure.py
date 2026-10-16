"""Figure: hijack vs its recovery, paired. (a) CDF of time to 90 % of the 2-h extent for hijacks and their recoveries; (b) persistence
Jaccard 30 s → 2 h, hijack vs recovery, per pair (2-D histogram); (c) recovery reach / hijack reach. Reads
eventset/<year>_recovery/pairs.parquet. usage: recovery_figure.py <out_dir> [years...]"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import polars as pl

from bgbench import config

import argparse
_ap = argparse.ArgumentParser(); _ap.add_argument("out"); _ap.add_argument("years", nargs="*", type=int)
_ap.add_argument("--pairs", default="", help="per-year pairs file suffix, e.g. 2024=_labelled")
_a = _ap.parse_args()
out = Path(_a.out); out.mkdir(parents=True, exist_ok=True)
years = _a.years or [2024, 2025]
PSUF = dict(kv.split("=") for kv in _a.pairs.split(",") if kv)
fig, axes = plt.subplots(1, 3, figsize=(13, 4.2))
grid = [30, 60, 300, 900, 3600, 7200]
from matplotlib.colors import LogNorm
from matplotlib.lines import Line2D
loaded = []
for i, y in enumerate(years):
    f = config.DATA_ROOT / "eventset" / f"{y}_recovery" / f"pairs{PSUF.get(str(y), '')}.parquet"
    if f.exists():
        loaded.append((y, pl.read_parquet(f)))
# (a) how fast: pooled CDF of t90 for hijack and recovery (thick), single years thin
ax = axes[0]
for col, lab, color in (("h_t90_s", "hijack (invalid route out)", "C3"), ("r_t90_s", "recovery (legitimate route back)", "C0")):
    for y, p in loaded:
        v = p[col].to_numpy(); ax.step([0] + grid, [0] + [(v <= g).mean() for g in grid], where="post", color=color, lw=0.8, alpha=0.35)
    allv = np.concatenate([p[col].to_numpy() for _, p in loaded])
    ax.step([0] + grid, [0] + [(allv <= g).mean() for g in grid], where="post", color=color, lw=2.4, label=lab)
ax.set_xscale("log"); ax.set_xlim(20, 8000); ax.set_ylim(0, 1.02); ax.set_xlabel("time to 90 % of the 2-h extent (s)"); ax.set_ylabel("share of pairs")
ax.set_title(f"(a) how fast, {loaded[0][0]}–{loaded[-1][0]} pooled (thin: single years)"); ax.grid(alpha=0.3); ax.legend(fontsize=8, loc="lower right")
# (b) per pair: 2-D histogram on a log colour scale, pooled over the years
ax = axes[1]
hx = np.concatenate([p["h_j30"].to_numpy() for _, p in loaded]); ry = np.concatenate([p["r_j30"].to_numpy() for _, p in loaded])
h = ax.hist2d(hx, ry, bins=20, range=[[0, 1], [0, 1]], cmap="Greys", norm=LogNorm(vmin=1))
fig.colorbar(h[3], ax=ax, label="pairs (log scale)", fraction=0.046, pad=0.03)
ax.plot([0, 1], [0, 1], "r--", lw=0.9); ax.axvline(np.median(hx), color="C3", lw=0.9, ls=":"); ax.axhline(np.median(ry), color="C0", lw=0.9, ls=":")
ax.set_xlabel("hijack: persistence Jaccard 30 s → 2 h"); ax.set_ylabel("its recovery: persistence Jaccard 30 s → 2 h")
ax.set_title(f"(b) per pair, all {len(hx):,} pairs (dotted: medians)")
# (c) footprint ratio: one CDF per year of log10(recovery reach / hijack reach)
ax = axes[2]
for i, (y, p) in enumerate(loaded):
    ratio = np.log10((p["r_reach"] / p["h_reach"].clip(1)).to_numpy()); ratio = np.sort(ratio)
    ax.step(ratio, np.arange(1, len(ratio) + 1) / len(ratio), where="post", color=f"C{i}", lw=1.6, label=f"{y} (p50 {10 ** np.median(ratio):.1f}×)")
ax.axvline(0, color="k", lw=0.8); ax.set_xlim(-1.5, 2); ax.set_ylim(0, 1.02); ax.set_xlabel("log10(recovery reach / hijack reach), ASes at 2 h"); ax.set_ylabel("share of pairs")
ax.set_title("(c) recovery footprint vs hijack footprint"); ax.legend(fontsize=8, loc="lower right"); ax.grid(alpha=0.3)
fig.tight_layout(); fig.savefig(out / "recovery_pairs.png", dpi=160); print("wrote", out / "recovery_pairs.png")
