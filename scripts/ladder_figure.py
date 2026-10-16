"""Paper figure for the ADR-0007 ladder on the slow regime: (a) Jaccard gain over persistence at Δ = 30 s / 60 s per rung with
bootstrap 95 % CIs, (b) two-hour extent sMAPE per rung vs persistence. Reads tgn/<year>_leak200/d{30,60}s/_results/*_summary.json
(sage, gat, tgn, dyrep, hist_avg) and eventset/<year>/cascade_vs_persistence_*leak*200*.json when present.
usage: ladder_figure.py <year> <out_dir>"""
from __future__ import annotations

import csv
import glob
import json
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from bgbench import config

year, out_dir = int(sys.argv[1]), Path(sys.argv[2]); out_dir.mkdir(parents=True, exist_ok=True)
LABEL = {"hist_avg": "2 historical avg", "cascade": "3 cascade (type prior)", "sage": "5 relational SAGE", "gat": "5-ref GAT", "tgn": "6 TGN", "dyrep": "6b DyRep"}


def three(v):
    """(mean, lo, hi) from the bootstrap-diff object whatever its shape."""
    if isinstance(v, dict):
        nums = {k: x for k, x in v.items() if isinstance(x, (int, float))}
        m = nums.get("mean", nums.get("diff", nums.get("point")))
        lo = nums.get("lo", nums.get("ci_lo", nums.get("low", nums.get("p2.5"))))
        hi = nums.get("hi", nums.get("ci_hi", nums.get("high", nums.get("p97.5"))))
        ci = v.get("ci95", v.get("ci"))
        if lo is None and ci:
            lo, hi = ci
        return m, lo, hi
    if isinstance(v, (list, tuple)) and len(v) == 3:
        return tuple(v)
    return v, None, None


def pick(d, *pats):
    for p in pats:
        for k, x in d.items():
            if re.fullmatch(p, k) and isinstance(x, (int, float)):
                return x
    return None


rows = []
for d in (30, 60):
    R = config.DATA_ROOT / "tgn" / f"{year}_leak200" / f"d{d}s" / "_results"
    for m in ("sage", "gat", "tgn", "dyrep"):
        f = R / f"{m}_summary.json"
        if not f.exists():
            continue
        s = json.load(open(f)); ft = s["final_test"]
        mean, lo, hi = three(ft["diff_tuned_minus_persistence"])
        rows.append({"delta_s": d, "rung": m, "j_model": pick(ft, r"jaccard_model_tuned_mean", r"jaccard_model_mean"), "j_persist": pick(ft, r"jaccard_persist_mean"),
                     "diff": mean, "lo": lo, "hi": hi, "smape_model": pick(ft, r"curve_smape_2h_model", r"curve_smape_model"), "smape_persist": pick(ft, r"curve_smape_2h_persist", r"curve_smape_persist")})
    f = R / "hist_avg_summary.json"
    if f.exists():
        h = json.load(open(f)); mean, lo, hi = three(h["diff_hist_minus_persistence"])
        rows.append({"delta_s": d, "rung": "hist_avg", "j_model": h["jaccard_hist_mean"], "j_persist": h["jaccard_persist_mean"], "diff": mean, "lo": lo, "hi": hi,
                     "smape_model": h.get("smape_2h_hist"), "smape_persist": h.get("smape_2h_persist")})
    for f in glob.glob(str(config.DATA_ROOT / "eventset" / str(year) / f"cascade_vs_persistence_d{d}s_*leak*200*.json")):
        if "coaffection" in f:
            continue
        c = json.load(open(f))
        rows.append({"delta_s": d, "rung": "cascade", "j_model": c.get("cascade_jaccard_mean"), "j_persist": c.get("persist_jaccard_mean"),
                     "diff": (c.get("cascade_jaccard_mean") or 0) - (c.get("persist_jaccard_mean") or 0), "lo": None, "hi": None, "smape_model": None, "smape_persist": None})
if not rows:
    sys.exit("no results found")
with open(out_dir / f"ladder_leak200_{year}.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

order = ["hist_avg", "cascade", "sage", "gat", "tgn", "dyrep"]
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2), gridspec_kw={"width_ratios": [1.3, 1]})
for i, d in enumerate((30, 60)):
    sub = {r["rung"]: r for r in rows if r["delta_s"] == d}
    ys = [j + (0.18 if d == 60 else -0.18) for j in range(len(order))]
    for j, m in enumerate(order):
        r = sub.get(m)
        if not r or r["diff"] is None:
            continue
        err = None if r["lo"] is None else [[r["diff"] - r["lo"]], [r["hi"] - r["diff"]]]
        ax1.errorbar(r["diff"], ys[j], xerr=err, fmt="o" if d == 30 else "s", color=f"C{i}", capsize=3, label=f"Δ = {d} s" if j == 0 else None)
ax1.axvline(0, color="k", lw=0.8); ax1.set_yticks(range(len(order))); ax1.set_yticklabels([LABEL[m] for m in order]); ax1.invert_yaxis()
ax1.set_xlabel("Jaccard(model) − Jaccard(persistence) at 2 h, test events, 95 % bootstrap CI"); ax1.legend(loc="lower right"); ax1.grid(axis="x", alpha=0.3)
ax1.set_title(f"(a) membership gain over persistence, leaks ≥ 200 ASes, {year}")
sub30 = {r["rung"]: r for r in rows if r["delta_s"] == 30}
bars = [("persistence", sub30.get("sage", {}).get("smape_persist"))] + [(LABEL[m], sub30[m]["smape_model"]) for m in order if m in sub30 and sub30[m]["smape_model"] is not None]
ax2.barh([b[0] for b in bars], [b[1] for b in bars], color=["0.5"] + ["C0"] * (len(bars) - 1)); ax2.invert_yaxis()
ax2.set_xlabel("sMAPE of the 2-h affected-AS count (Δ = 30 s)"); ax2.set_title("(b) extent error"); ax2.grid(axis="x", alpha=0.3)
fig.tight_layout(); fig.savefig(out_dir / f"ladder_leak200_{year}.png", dpi=160)
print("wrote", out_dir / f"ladder_leak200_{year}.png", len(rows), "rows")
for r in rows:
    print(r)
