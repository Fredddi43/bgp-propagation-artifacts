"""Growth-curve figures for the slice events (matplotlib, headless)."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import polars as pl

from . import config
from .extent import TARGETS_S


def growth_figure(name: str, title: str, out: Path | None = None) -> Path:
    d = config.EVENT_DIR / name / "_extent"
    pfx = pl.read_csv(d / "leak_prefix_growth_curve.csv")
    asn = pl.read_csv(d / "leak_growth_curve_pooled.csv")
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8))
    for ax, df, ylab in (
        (axes[0], pfx, "leaked prefixes (cumulative)"),
        (axes[1], asn, "ASes on leaked paths (cumulative)"),
    ):
        df = df.filter(pl.col("rel_s") >= 0)
        ax.step(df["rel_s"] / 60, df["N"], where="post", lw=1.6)
        for lbl, secs in TARGETS_S.items():
            ax.axvline(secs / 60, color="grey", lw=0.6, ls="--")
            ax.text(
                secs / 60,
                ax.get_ylim()[1] * 0.02,
                lbl,
                rotation=90,
                fontsize=7,
                color="grey",
                va="bottom",
            )
        ax.set_xscale("symlog", linthresh=1)
        ax.set_xlabel("minutes after t₀ (symlog)")
        ax.set_ylabel(ylab)
        ax.grid(alpha=0.3)
    fig.suptitle(title)
    fig.tight_layout()
    out = out or (d / f"{name}_growth.png")
    fig.savefig(out, dpi=150)
    return out
