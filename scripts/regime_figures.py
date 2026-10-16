"""Paper figures for the regime split (ADR-0019 finding): fraction of events still growing at Δ and the persistence
floor, by family, by final extent, by duration class, and per vantage point. Reads eventset/<year>[_tag]/ outputs.
usage: regime_figures.py <year> <out_dir>"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import polars as pl

from bgbench import config
from bgbench.eventset import DELTAS_S


def jac(a, b):
    return pl.col(a).list.set_intersection(pl.col(b)).list.len() / pl.col(a).list.set_union(pl.col(b)).list.len().clip(1)


def load(year: int, tag: str) -> pl.DataFrame:
    t = pl.read_parquet(config.DATA_ROOT / "eventset" / (f"{year}_{tag}" if tag else str(year)) / "events.parquet").filter(pl.col("error").is_null())
    if tag == "leak":
        t = t.filter(pl.col("observation_lag_s").is_null() | (pl.col("observation_lag_s") >= -60))
    d = config.DATA_ROOT / "eventset" / (f"{year}_{tag}" if tag else str(year)) / "durations.parquet"
    if d.exists():
        t = t.join(pl.read_parquet(d).select("event_id", "duration_s"), on="event_id", how="left")
    return t


def curves(t: pl.DataFrame, group: pl.Expr | None):
    out = {}
    for dk in DELTAS_S:
        j = jac(f"set_{dk}", "set_final_2h")
        g = t.with_columns(j=j, grown=(j >= 0.999))
        if group is not None:
            g = g.with_columns(grp=group)
            r = g.group_by("grp").agg(n=pl.len(), J=pl.col("j").mean(), growing=1 - pl.col("grown").mean())
            for row in r.iter_rows(named=True):
                out.setdefault(row["grp"], {})[dk] = (row["J"], row["growing"], row["n"])
        else:
            out.setdefault("all", {})[dk] = (float(g["j"].mean()), float(1 - g["grown"].mean()), g.height)
    return out


def main(year: int, out_dir: str) -> None:
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    xs = [DELTAS_S[k] for k in DELTAS_S]
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6))
    for tag, name in (("", "origin change"), ("leak", "route leak"), ("withdrawal", "withdrawal wave")):
        try:
            t = load(year, tag)
        except FileNotFoundError:
            continue
        c = curves(t, None)["all"]
        axes[0].plot(xs, [c[k][1] for k in DELTAS_S], marker="o", label=f"{name} (n={c['d30s'][2]})")
        axes[1].plot(xs, [c[k][0] for k in DELTAS_S], marker="o", label=name)
    for ax, yl in zip(axes, ("fraction still growing at Δ", "persistence Jaccard Δ → 2 h")):
        ax.set_xscale("log"); ax.set_xlabel("Δ (s of observation)"); ax.set_ylabel(yl); ax.grid(alpha=.3); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(out / f"regime_by_family_{year}.png", dpi=160); plt.close(fig)
    # by size and duration, leaks and hijacks
    for tag, name in (("", "hijack"), ("leak", "leak")):
        try:
            t = load(year, tag)
        except FileNotFoundError:
            continue
        size = pl.when(pl.col("asns_final_2h") < 50).then(pl.lit("<50 ASes")).when(pl.col("asns_final_2h") < 200).then(pl.lit("50-199")).otherwise(pl.lit("200+"))
        dur = pl.when(pl.col("duration_s") < 60).then(pl.lit("ephemeral <60 s")).when(pl.col("duration_s") < 600).then(pl.lit("1-10 min")).otherwise(pl.lit("persistent >10 min")) if "duration_s" in t.columns else None
        fig, axes = plt.subplots(1, 2 if dur is not None else 1, figsize=(10, 3.6), squeeze=False)
        for ax, (grp, title) in zip(axes[0], [(size, "by final extent"), (dur, "by duration of activity")][: axes.shape[1]]):
            for g, c in sorted(curves(t, grp).items()):
                ax.plot(xs, [c[k][0] for k in DELTAS_S], marker="o", label=f"{g} (n={c['d30s'][2]})")
            ax.set_xscale("log"); ax.set_xlabel("Δ (s)"); ax.set_ylabel("persistence Jaccard Δ → 2 h"); ax.set_title(f"{name}s {title}"); ax.grid(alpha=.3); ax.legend(fontsize=8)
        fig.tight_layout(); fig.savefig(out / f"floor_by_size_duration_{name}_{year}.png", dpi=160); plt.close(fig)
        # per VP
        pv = config.DATA_ROOT / "eventset" / (f"{year}_{tag}" if tag else str(year)) / "persistence_per_vp_test.csv"
        if pv.exists():
            df = pl.read_csv(pv)
            fig, ax = plt.subplots(figsize=(6, 3.4))
            for col in sorted(df["collector"].unique().to_list()):
                sub = df.filter(pl.col("collector") == col).with_columns(sec=pl.col("delta").replace_strict(DELTAS_S, default=None)).sort("sec")
                ax.plot(sub["sec"], sub["jaccard_mean"], marker=".", label=col)
            ax.set_xscale("log"); ax.set_xlabel("Δ (s)"); ax.set_ylabel("persistence Jaccard Δ → 2 h"); ax.set_title(f"{name}s per vantage point (test)"); ax.grid(alpha=.3); ax.legend(fontsize=6, ncol=2)
            fig.tight_layout(); fig.savefig(out / f"floor_per_vp_{name}_{year}.png", dpi=160); plt.close(fig)
    print("figures in", out)


if __name__ == "__main__":
    main(int(sys.argv[1]), sys.argv[2])
