"""Time course by RPKI validity of the new origin: for each year and class, the mean Jaccard(set at Δ, set at 2 h) and the share of
events still growing at Δ, for Δ ∈ {30 s, 1, 5, 15, 60 min}; plus the recovery set as its own curve. Writes
<out_dir>/validity_timecourse.{csv,png}. usage: validity_timecourse.py <out_dir> [years...]"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import polars as pl

from bgbench import config

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
years = [int(y) for y in sys.argv[2:]] or [2023, 2024, 2025]
GRID = [("set_d30s", 30), ("set_d1m", 60), ("set_d5m", 300), ("set_d15m", 900), ("set_T60m", 3600)]
rows = []
for y in years:
    E = config.DATA_ROOT / "eventset"
    ev = pl.read_parquet(E / str(y) / "events.parquet").filter(pl.col("error").is_null()).select("event_id", "split", *[c for c, _ in GRID], "set_final_2h")
    val = pl.read_parquet(E / str(y) / "rpki_validity.parquet").select("event_id", "validity", "prev_validity")
    ev = ev.join(val, on="event_id").with_columns(pl.when((pl.col("validity") == "valid") & (pl.col("prev_validity") == "invalid")).then(pl.lit("valid ← invalid (recovery)")).otherwise(pl.col("validity")).alias("cls"))
    sets = {"origin": ev}
    rf = E / f"{y}_recovery" / "events.parquet"
    if rf.exists():
        sets["recovery set"] = pl.read_parquet(rf).filter(pl.col("error").is_null()).select("event_id", "split", *[c for c, _ in GRID], "set_final_2h").with_columns(pl.lit("recovery replay set").alias("cls"))
    for name, t in sets.items():
        for (cls,), g in t.filter(pl.col("split") == "test").group_by("cls"):
            fin = [set(x or []) for x in g["set_final_2h"].to_list()]
            for col, s in GRID:
                cur = [set(x or []) for x in g[col].to_list()]
                j = [len(a & b) / len(a | b) if (a | b) else 1.0 for a, b in zip(cur, fin)]
                grow = [len(b) > len(a) for a, b in zip(cur, fin)]
                rows.append({"year": y, "cls": cls, "delta_s": s, "n": g.height, "jaccard_mean": round(sum(j) / len(j), 4), "still_growing": round(sum(grow) / len(grow), 4)})
t = pl.DataFrame(rows).sort("year", "cls", "delta_s"); t.write_csv(out / "validity_timecourse.csv")
fig, axes = plt.subplots(1, 2, figsize=(11, 4))
COL = {"invalid": "C3", "unknown": "0.4", "valid": "C2", "valid ← invalid (recovery)": "C0", "recovery replay set": "C1"}
LS = {2023: ":", 2024: "-", 2025: "--"}
for (y, cls), g in t.group_by("year", "cls", maintain_order=True):
    if cls not in COL:
        continue
    axes[0].plot(g["delta_s"].to_list(), g["jaccard_mean"].to_list(), ls=LS[y], color=COL[cls], marker="o", ms=3, label=f"{cls} {y}" if y == 2024 or cls.startswith("recovery") else None)
    axes[1].plot(g["delta_s"].to_list(), g["still_growing"].to_list(), ls=LS[y], color=COL[cls], marker="o", ms=3)
for ax in axes:
    ax.set_xscale("log"); ax.set_xlabel("Δ after first observation (s)"); ax.grid(alpha=0.3)
axes[0].set_ylabel("mean Jaccard(set at Δ, set at 2 h), test"); axes[0].set_title("(a) how much of the final set is known at Δ"); axes[0].legend(fontsize=7, title="colour = class (line style: 2023 ⋯ 2024 — 2025 – –)", title_fontsize=7)
axes[1].set_ylabel("share of events still growing after Δ"); axes[1].set_title("(b) how many are still spreading")
fig.tight_layout(); fig.savefig(out / "validity_timecourse.png", dpi=160); print("wrote", out / "validity_timecourse.png")
with pl.Config(tbl_rows=60): print(t.filter(pl.col("year") == 2024))
