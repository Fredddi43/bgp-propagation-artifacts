"""Figure: hijack vs its recovery, paired. (a) CDF of time to 90 % of the 2-h extent for hijacks and their recoveries; (b) persistence
Jaccard 30 s → 2 h, hijack vs recovery, per pair (2-D histogram); (c) recovery reach / hijack reach. Reads
eventset/<year>_recovery/pairs.parquet. usage: recovery_figure.py <out_dir> [years...]"""
from __future__ import annotations

from pathlib import Path
import hashlib
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import polars as pl

from bgbench import config

import argparse
_ap = argparse.ArgumentParser(); _ap.add_argument("out"); _ap.add_argument("years", nargs="*", type=int)
_ap.add_argument("--recovery-tag", default="recovery", help="eventset suffix containing the paired measurements")
_ap.add_argument("--pairs", default="", help="per-year pairs file suffix, e.g. 2024=_labelled")
_a = _ap.parse_args()
out = Path(_a.out); out.mkdir(parents=True, exist_ok=True)
years = _a.years or [2024, 2025]
PSUF = dict(kv.split("=") for kv in _a.pairs.split(",") if kv)
fig, axes = plt.subplots(1, 3, figsize=(13, 4.2))

from matplotlib.colors import LogNorm
loaded = []
sources = {}
for i, y in enumerate(years):
    f = config.DATA_ROOT / "eventset" / f"{y}_{_a.recovery_tag}" / f"pairs{PSUF.get(str(y), '')}.parquet"
    if not f.is_file():
        raise FileNotFoundError(f)
    loaded.append((y, pl.read_parquet(f)))
    sources[str(f.relative_to(config.DATA_ROOT))] = hashlib.sha256(f.read_bytes()).hexdigest()
if not loaded:
    raise SystemExit("No pair tables found")
figure_data = {"years": years, "recovery_tag": _a.recovery_tag, "pairs_suffixes": PSUF,
               "source_sha256": sources, "weighting": "one row per retained event link",
               "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "timing_cdf": {}, "reach_ratio_cdf": {}}


def timing_cdf(ax, values, **style):
    values = np.asarray(values, dtype=float)
    values = np.sort(values[np.isfinite(values)])
    if values.size:
        ax.step(values, np.arange(1, values.size + 1) / values.size, where="post", **style)
    return values.tolist()


# (a) how fast: pooled CDF of t90 for hijack and recovery (thick), single years thin
ax = axes[0]
for col, lab, color in (("h_t90_s", "outward transition", "C3"), ("r_t90_s", "return transition", "C0")):
    figure_data["timing_cdf"][col] = {}
    for y, p in loaded:
        figure_data["timing_cdf"][col][str(y)] = timing_cdf(ax, p[col].to_numpy(), color=color, lw=0.8, alpha=0.35)
    allv = np.concatenate([p[col].to_numpy() for _, p in loaded])
    timing_cdf(ax, allv, color=color, lw=2.4, label=f"{lab} (n={np.isfinite(allv).sum():,})")
ax.set_xscale("symlog", linthresh=1); ax.set_xlim(0, 8000); ax.set_ylim(0, 1.02); ax.set_xlabel("time to 90 % of the 2-h extent (s)"); ax.set_ylabel("share of links with defined timing")
ax.set_title(f"(a) how fast, {loaded[0][0]}–{loaded[-1][0]} pooled (thin: single years)"); ax.grid(alpha=0.3); ax.legend(fontsize=8, loc="lower right")
# (b) per pair: 2-D histogram on a log colour scale, pooled over the years
ax = axes[1]
hx = np.concatenate([p["h_j30"].to_numpy() for _, p in loaded]); ry = np.concatenate([p["r_j30"].to_numpy() for _, p in loaded])
h = ax.hist2d(hx, ry, bins=20, range=[[0, 1], [0, 1]], cmap="Greys", norm=LogNorm(vmin=1))
figure_data["paired_jaccard_histogram"] = {"counts": h[0].tolist(), "x_edges": h[1].tolist(),
                                         "y_edges": h[2].tolist(), "medians": [float(np.median(hx)), float(np.median(ry))]}
fig.colorbar(h[3], ax=ax, label="pairs (log scale)", fraction=0.046, pad=0.03)
ax.plot([0, 1], [0, 1], "r--", lw=0.9); ax.axvline(np.median(hx), color="C3", lw=0.9, ls=":"); ax.axhline(np.median(ry), color="C0", lw=0.9, ls=":")
ax.set_xlabel("outward transition: Jaccard 30 s → 2 h"); ax.set_ylabel("paired return transition: Jaccard 30 s → 2 h")
ax.set_title(f"(b) per pair, all {len(hx):,} pairs (dotted: medians)")
# (c) Zero return reach is an explicit atom at zero; zero hijack reach has undefined ratio.
ax = axes[2]
for i, (y, p) in enumerate(loaded):
    valid = p.filter(pl.col("h_reach") > 0)
    ratio = np.sort((valid["r_reach"] / valid["h_reach"]).to_numpy())
    figure_data["reach_ratio_cdf"][str(y)] = {"sorted_values": ratio.tolist(),
                                             "undefined_zero_outward": p.height - valid.height}
    if len(ratio):
        ax.step(ratio, np.arange(1, len(ratio) + 1) / len(ratio), where="post", color=f"C{i}", lw=1.6,
                label=f"{y}: p50 {np.median(ratio):.1f}×; zero R {(ratio == 0).sum()}, zero H {p.height-valid.height}")
ax.axvline(1, color="k", lw=0.8)
ax.set_xscale("symlog", linthresh=0.1); ax.set_xlim(left=0); ax.set_ylim(0, 1.02)
ax.set_xlabel("return extent / outward extent, ASes at 2 h")
ax.set_ylabel("share of pairs with nonzero outward reach")
ax.set_title("(c) return footprint vs outward footprint")
ax.legend(fontsize=7, loc="lower right"); ax.grid(alpha=0.3)
fig.tight_layout(); fig.savefig(out / "recovery_pairs.png", dpi=160); print("wrote", out / "recovery_pairs.png")
(out / "recovery_pairs_data.json").write_text(json.dumps(figure_data, indent=2) + "\n")
