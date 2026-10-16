"""Paper figure for the ADR-0007 ladder on the slow regime: (a) Jaccard gain over persistence at Δ = 30 s / 60 s per rung with
bootstrap 95 % CIs, (b) two-hour extent sMAPE per rung vs persistence. Reads tgn/<year>_leak200/d{30,60}s/_results/*_summary.json
(sage, gat, tgn, dyrep, hist_avg) and eventset/<year>/cascade_vs_persistence_*leak*200*.json when present.
usage: ladder_figure.py <year> <out_dir>"""
from __future__ import annotations

import argparse
import csv
import json
import hashlib
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import numpy as np
import polars as pl

from bgbench import config

parser = argparse.ArgumentParser()
parser.add_argument('year', type=int)
parser.add_argument('out_dir', type=Path)
parser.add_argument('--nongraph-root', type=Path)
parser.add_argument('--nongraph-plan', type=Path)
parser.add_argument('--require-complete', action='store_true')
args = parser.parse_args()
year, out_dir = args.year, args.out_dir
out_dir.mkdir(parents=True, exist_ok=True)
if bool(args.nongraph_root) != bool(args.nongraph_plan):
    parser.error('--nongraph-root and --nongraph-plan must be used together')
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
sources = []
for d in (30, 60):
    R = config.DATA_ROOT / "tgn" / f"{year}_leak200" / f"d{d}s" / "_results"
    common_ids = None
    reference = None
    for m in ("sage", "gat", "tgn", "dyrep"):
        f = R / f"{m}_summary.json"
        if not f.exists():
            if args.require_complete:
                raise FileNotFoundError(f)
            continue
        sources.extend([f, R / f"{m}_test_per_event.csv"])
        s = json.load(open(f)); ft = s["final_test"]
        if ft.get("membership_target") != "full_observed_2h":
            raise ValueError(f"Old candidate-only results cannot enter a common-target ladder: {f}")
        reference = pl.read_csv(R / f"{m}_test_per_event.csv").select("event_id", "jaccard_persist")
        ids = set(reference["event_id"])
        if common_ids is not None and ids != common_ids:
            raise ValueError(f"Model evaluation populations differ: {f}")
        common_ids = ids
        mean, lo, hi = three(ft["diff_tuned_minus_persistence"])
        rows.append({"delta_s": d, "rung": m, "j_model": pick(ft, r"jaccard_model_tuned_mean", r"jaccard_model_mean"), "j_persist": pick(ft, r"jaccard_persist_mean"),
                     "diff": mean, "lo": lo, "hi": hi, "smape_model": pick(ft, r"curve_smape_2h_model", r"curve_smape_model"), "smape_persist": pick(ft, r"curve_smape_2h_persist", r"curve_smape_persist")})
    f = R / "hist_avg_summary.json"
    if args.require_complete and not f.exists():
        raise FileNotFoundError(f)
    if f.exists():
        sources.extend([f, R / "hist_avg_test_per_event.csv"])
        h = json.load(open(f))
        if h.get("membership_target") != "full_observed_2h":
            raise ValueError(f"Old candidate-only historical baseline: {f}")
        ids = set(pl.read_csv(R / "hist_avg_test_per_event.csv")["event_id"])
        if common_ids is not None and ids != common_ids:
            raise ValueError(f"Historical baseline population differs: {f}")
        common_ids = ids
        mean, lo, hi = three(h["diff_hist_minus_persistence"])
        rows.append({"delta_s": d, "rung": "hist_avg", "j_model": h["jaccard_hist_mean"], "j_persist": h["jaccard_persist_mean"], "diff": mean, "lo": lo, "hi": hi,
                     "smape_model": h.get("smape_2h_hist"), "smape_persist": h.get("smape_2h_persist")})
    label = "30s" if d == 30 else "1m"
    f = config.DATA_ROOT / "eventset" / str(year) / f"cascade_vs_persistence_d{label}_final_2h_leak_ge200.json"
    if args.nongraph_root:
        plan = json.loads(args.nongraph_plan.read_text())
        selected = [task for task in plan if task['year'] == year and task.get('name') == f.stem]
        if len(selected) != 1:
            raise ValueError(f'Expected one type-prior cascade task for {year}/{d}: {selected}')
        task = selected[0]
        f = args.nongraph_root / str(year) / f"{task['index']:03d}_{task['kind']}" / f.name
    if args.require_complete and not f.exists():
        raise FileNotFoundError(f)
    if f.exists():
        sources.extend([f, f.with_suffix(".parquet")])
        c = pl.read_parquet(f.with_suffix(".parquet"))
        if common_ids is None:
            raise ValueError("Graph event IDs required to construct common cascade comparison")
        c = c.filter(pl.col("event_id").is_in(sorted(common_ids))).sort("event_id")
        if set(c["event_id"]) != common_ids or c["event_id"].n_unique() != c.height:
            raise ValueError(f"Cascade does not cover every graph event exactly once: {f}")
        if reference is not None:
            checked = c.join(reference, on='event_id')
            if not np.allclose(checked['persist_jaccard'], checked['jaccard_persist'], atol=1e-10, rtol=0):
                raise ValueError(f'Cascade and graph persistence targets differ: {f}')
        diff = (c["cascade_jaccard"] - c["persist_jaccard"]).to_numpy()
        rng = np.random.default_rng(0)
        ci = np.quantile([diff[rng.integers(len(diff), size=len(diff))].mean() for _ in range(2000)], [0.025, 0.975])
        rows.append({"delta_s": d, "rung": "cascade", "j_model": c["cascade_jaccard"].mean(), "j_persist": c["persist_jaccard"].mean(),
                     "diff": diff.mean(), "lo": ci[0], "hi": ci[1], "smape_model": c["cascade_size_smape"].mean() if "cascade_size_smape" in c.columns else None,
                     "smape_persist": c["persist_size_smape"].mean() if "persist_size_smape" in c.columns else None})

if not rows:
    sys.exit("no results found")
with open(out_dir / f"ladder_leak200_{year}.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n"); w.writeheader(); w.writerows(rows)

(out_dir / f"ladder_leak200_{year}_sources.json").write_text(json.dumps({
    'year': year, 'membership_target': 'full_observed_2h',
    'cohort_rule': 'identical graph/historical IDs; cascade restricted to and required to cover those IDs',
    'source_sha256': {(str(path.relative_to(config.DATA_ROOT)) if path.is_relative_to(config.DATA_ROOT)
                       else 'nongraph/' + str(path.relative_to(args.nongraph_root))): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
    'generator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}, indent=2))

order = ["hist_avg", "cascade", "sage", "gat", "tgn", "dyrep"]
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.6), gridspec_kw={"width_ratios": [1.3, 1]})
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
ax1.set_xlabel("Mean Jaccard gain at 2 h\n(test events, 95 % bootstrap CI)")
ax1.set_ylim(len(order) + .3, -.5)
ax1.xaxis.set_major_locator(MaxNLocator(nbins=5))
ax1.legend(loc="lower center", ncol=2); ax1.grid(axis="x", alpha=0.3)
ax1.set_title(f"(a) membership gain over persistence, leaks ≥ 200 ASes, {year}")
sub30 = {r["rung"]: r for r in rows if r["delta_s"] == 30}
bars = [("persistence", sub30.get("sage", {}).get("smape_persist"))] + [(LABEL[m], sub30[m]["smape_model"]) for m in order if m in sub30 and sub30[m]["smape_model"] is not None]
ax2.barh([b[0] for b in bars], [b[1] for b in bars], color=["0.5"] + ["C0"] * (len(bars) - 1)); ax2.invert_yaxis()
ax2.set_xlabel("sMAPE of the 2-h affected-AS count (Δ = 30 s)"); ax2.set_title("(b) extent error"); ax2.grid(axis="x", alpha=0.3)
fig.tight_layout(); fig.savefig(out_dir / f"ladder_leak200_{year}.png", dpi=160)
print("wrote", out_dir / f"ladder_leak200_{year}.png", len(rows), "rows")
for r in rows:
    print(r)
