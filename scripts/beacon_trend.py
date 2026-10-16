"""Three-year beacon reach trend at the ten pass collectors: monthly median of (invalid beacon sessions / valid twin sessions),
from the retained-RIB results (rpki/beacon_reach.parquet, 2024) and the scan-and-discard results (rpki/beacon_reach_scan/*.parquet,
2023/2025). Writes <out_dir>/beacon_trend.csv and beacon_trend.png. usage: beacon_trend.py <out_dir>"""
from __future__ import annotations

import glob
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import polars as pl

from bgbench import config

TEN = ["rrc25", "rrc00", "rrc12", "rrc01", "route-views3", "rrc03", "route-views2", "rrc20", "rrc15", "route-views.linx"]
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
frames = []
f = config.DATA_ROOT / "rpki" / "beacon_reach.parquet"
if f.exists():
    d = pl.read_parquet(f).with_columns(pl.col("rib_ts").str.slice(0, 10).alias("day")).filter(pl.col("collector").is_in(TEN))
    frames.append(d.select("collector", "day", "beacon", "peers_carrying", "peers_total"))
for g in glob.glob(str(config.DATA_ROOT / "rpki" / "beacon_reach_scan" / "*.parquet")):
    d = pl.read_parquet(g).filter(pl.col("error").is_null()).rename({"monday": "day"})
    frames.append(d.select("collector", "day", "beacon", "peers_carrying", "peers_total"))
d = pl.concat(frames, how="diagonal_relaxed").unique(["collector", "day", "beacon"])
w = d.pivot(on="beacon", index=["collector", "day"], values="peers_carrying").with_columns(pl.col("day").str.slice(0, 7).alias("month"))
pairs = {"RIPE v4 invalid": ("ripe_v4_invalid", "ripe_v4_valid"), "RIPE v6 invalid": ("ripe_v6_invalid", "ripe_v6_valid"), "Snijders v4 invalid": ("snijders_v4_invalid", "ripe_v4_valid"),
         "Cloudflare v4 invalid_length": ("cloudflare_v4_invalid_length", "ripe_v4_valid"), "RIPE v4 unknown": ("ripe_v4_unknown", "ripe_v4_valid")}
rows = []
for lab, (a, b) in pairs.items():
    if a not in w.columns or b not in w.columns:
        continue
    r = w.with_columns((pl.col(a) / pl.col(b).clip(1)).alias("r")).group_by("month").agg(ratio=pl.col("r").median(), n=pl.len()).sort("month")
    for m, v, n in r.iter_rows():
        rows.append({"beacon": lab, "month": m, "ratio_to_valid_p50": round(v, 3), "collector_snapshots": n})
t = pl.DataFrame(rows); t.write_csv(out / "beacon_trend.csv")
fig, ax = plt.subplots(figsize=(6.4, 3.4))
for lab in pairs:
    s = t.filter(pl.col("beacon") == lab)
    if s.height:
        ax.plot(s["month"].to_list(), s["ratio_to_valid_p50"].to_list(), marker="o", ms=3, label=lab)
ax.set_ylim(0, 1.15); ax.set_ylabel("reach relative to the valid twin\n(sessions, monthly p50)", fontsize=9); ax.grid(alpha=0.3)
ax.legend(fontsize=8, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.28), frameon=False); ax.tick_params(labelsize=8); ax.set_ylim(0, 1.08)
months = sorted(t["month"].unique().to_list()); ax.set_xticks([m for m in months if m.endswith(("-01", "-07"))]); ax.tick_params(axis="x", rotation=45)
fig.tight_layout(); fig.savefig(out / "beacon_trend.png", dpi=160)
yr = t.with_columns(pl.col("month").str.slice(0, 4).alias("y")).group_by("beacon", "y").agg(pl.col("ratio_to_valid_p50").median().round(3)).sort("beacon", "y")
print(yr)
