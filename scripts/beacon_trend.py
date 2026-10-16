"""Three-year beacon reach trend at the ten pass collectors: monthly median of (invalid beacon sessions / valid twin sessions),
from the retained-RIB results (rpki/beacon_reach.parquet, 2024) and the scan-and-discard results (rpki/beacon_reach_scan/*.parquet,
2023/2025). Writes <out_dir>/beacon_trend.csv and beacon_trend.png. usage: beacon_trend.py <out_dir>"""
from __future__ import annotations

import glob
import hashlib
import json
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
input_hashes = {}
f = config.DATA_ROOT / "rpki" / "beacon_reach.parquet"
if f.exists():
    input_hashes[str(f.relative_to(config.DATA_ROOT))] = hashlib.sha256(f.read_bytes()).hexdigest()
    d = pl.read_parquet(f).with_columns(pl.col("rib_ts").str.slice(0, 10).alias("day")).filter(pl.col("collector").is_in(TEN))
    frames.append(d.select("collector", "day", "beacon", "peers_carrying", "peers_total"))
for g in glob.glob(str(config.DATA_ROOT / "rpki" / "beacon_reach_scan" / "*.parquet")):
    input_hashes[str(Path(g).relative_to(config.DATA_ROOT))] = hashlib.sha256(Path(g).read_bytes()).hexdigest()
    d = pl.read_parquet(g).filter(pl.col("error").is_null()).rename({"monday": "day"})
    frames.append(d.select("collector", "day", "beacon", "peers_carrying", "peers_total"))
d = pl.concat(frames, how="diagonal_relaxed").unique(["collector", "day", "beacon"])
sampling = {"rule": "ten declared collectors, Monday snapshots only",
            "collector_days_before_schedule_filter": d.select("collector", "day").unique().height,
            "off_schedule_collector_days": d.filter(pl.col("day").str.to_date().dt.weekday() != 1).select("collector", "day").unique().height}
d = d.filter(pl.col("collector").is_in(TEN) & (pl.col("day").str.to_date().dt.weekday() == 1))
sampling["collector_days"] = d.select("collector", "day").unique().height
w = d.pivot(on="beacon", index=["collector", "day"], values="peers_carrying").with_columns(pl.col("day").str.slice(0, 7).alias("month"))
pairs = {"RIPE v4 invalid": ("ripe_v4_invalid", "ripe_v4_valid"), "RIPE v6 invalid": ("ripe_v6_invalid", "ripe_v6_valid"), "Snijders v4 invalid": ("snijders_v4_invalid", "ripe_v4_valid"),
         "Cloudflare v4 invalid_length": ("cloudflare_v4_invalid_length", "ripe_v4_valid"), "RIPE v4 unknown": ("ripe_v4_unknown", "ripe_v4_valid")}
rows = []
for lab, (a, b) in pairs.items():
    if a not in w.columns or b not in w.columns:
        continue
    r = w.with_columns(pl.when((pl.col(b) > 0) & pl.col(a).is_not_null())
                      .then(pl.col(a) / pl.col(b)).otherwise(None).alias("r"))
    r = r.group_by("month").agg(ratio=pl.col("r").median(), n=pl.col("r").count(),
                                excluded=pl.col("r").null_count()).sort("month")
    for m, v, n, excluded in r.iter_rows():
        rows.append({"beacon": lab, "month": m, "ratio_to_valid_p50": v,
                     "collector_snapshots": n, "excluded_snapshots": excluded})
t = pl.DataFrame(rows); t.write_csv(out / "beacon_trend.csv")
(out / "beacon_trend_data.json").write_text(json.dumps({
    "definition": "monthly median of collector-day session-count ratios; require observed numerator and positive valid-twin denominator",
    "inputs_sha256": input_hashes, "sampling": sampling, "monthly": rows}, indent=2) + "\n")
fig, ax = plt.subplots(figsize=(6.4, 3.4))
for lab in pairs:
    s = t.filter(pl.col("beacon") == lab)
    if s.height:
        ax.plot(s["month"].to_list(), s["ratio_to_valid_p50"].to_list(), marker="o", ms=3, label=lab)
ax.set_ylim(0, 1.15); ax.set_ylabel("reach relative to the valid twin\n(sessions, monthly p50)", fontsize=9); ax.grid(alpha=0.3)
ax.legend(fontsize=8, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.28), frameon=False); ax.tick_params(labelsize=8); ax.set_ylim(0, 1.08)
months = sorted(t["month"].unique().to_list()); ax.set_xticks([m for m in months if m.endswith(("-01", "-07"))]); ax.tick_params(axis="x", rotation=45)
fig.tight_layout(); fig.savefig(out / "beacon_trend.png", dpi=160)
yr = t.with_columns(pl.col("month").str.slice(0, 4).alias("y")).group_by("beacon", "y").agg(pl.col("ratio_to_valid_p50").median()).sort("beacon", "y")
print(yr)
years = sorted(yr["y"].unique().to_list())
labels = {"RIPE v4 invalid": "RIPE v4 invalid (ASN)", "RIPE v6 invalid": "RIPE v6 invalid (ASN)",
          "Snijders v4 invalid": "Snijders v4 invalid (ASN)",
          "Cloudflare v4 invalid_length": "Cloudflare v4 invalid (maxLength)",
          "RIPE v4 unknown": "RIPE v4 unknown (no ROA)"}
table = [r"\begin{tabular}{l" + "r"*len(years) + "}", r"\toprule",
         "beacon & " + " & ".join(years) + r" \\", r"\midrule"]
for beacon, label in labels.items():
    values = {r["y"]: r["ratio_to_valid_p50"] for r in yr.filter(pl.col("beacon") == beacon).iter_rows(named=True)}
    cells = [f"{values[y]:.2f}" if values.get(y) is not None else "--" for y in years]
    if beacon == "Snijders v4 invalid":
        cells = [value + (r"\textsuperscript{a}" if y >= "2025" else "")
                 for y, value in zip(years, cells)]
    table.append(label + " & " + " & ".join(cells) + r" \\")
table += [r"\bottomrule", r"\multicolumn{" + str(len(years)+1) + r"}{p{0.95\columnwidth}}{\footnotesize \textsuperscript{a} Zero median reach Nov. 2025--Jun. 2026; observed again Jul. 2026.} \\", r"\end{tabular}"]
(out / "beacon_trend.tex").write_text("% Generated by scripts/beacon_trend.py\n" + "\n".join(table) + "\n")
