"""Does an RPKI-invalid new origin become ROA-valid later? For every replayed origin-change event whose new origin was invalid
against the ROAs of its day, re-validate the same (prefix, origin) against the ROAs 7 and 30 days after t0, grouped by
selection reason. A high share of later-valid origins in a stratum means stale-ROA re-originations (prefix moved before the
ROA followed) are mixed into that stratum's "invalid" class (docs/results/2026-09-15-extension-2022-2026.md, hypothesis).
usage: later_validity.py <year> [--days 7 30]  → prints a markdown table, writes eventset/<year>/later_validity.json"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from collections import defaultdict

import polars as pl

from bgbench import config
from bgbench.rpki_validate import roas_for, validity

ap = argparse.ArgumentParser()
ap.add_argument("year", type=int)
ap.add_argument("--days", type=int, nargs="+", default=[7, 30])
a = ap.parse_args()
E = config.DATA_ROOT / "eventset" / str(a.year)

ev = pl.read_parquet(E / "events.parquet").filter(pl.col("error").is_null()).select("event_id", "reason")
val = pl.read_parquet(E / "rpki_validity.parquet").select("event_id", "validity")
man = pl.read_csv(config.DATA_ROOT / "inventory" / str(a.year) / "replay_manifest.tsv", separator="\t").select(
    "event_id", "prefix", pl.col("new_origin").cast(pl.Int64), pl.col("t0").str.to_datetime(strict=False))
ev = ev.join(val, on="event_id").join(man, on="event_id").filter(pl.col("validity") == "invalid")
ev = ev.with_columns(pl.when(pl.col("reason") == "rpki_invalid_sample").then(pl.lit("label-free stratum"))
                     .when(pl.col("reason") == "stratified").then(pl.lit("stratified")).otherwise(pl.lit("catalogue")).alias("pop"))

states: dict[int, dict[str, str]] = {h: {} for h in a.days}
for h in a.days:
    rows = ev.with_columns((pl.col("t0") + pl.duration(days=h)).dt.strftime("%Y-%m-%d").alias("day")).sort("day")
    for day, g in rows.group_by("day", maintain_order=True):
        tab = roas_for(day[0])
        for eid, p, o in g.select("event_id", "prefix", "new_origin").iter_rows():
            states[h][eid] = "no_roa_data" if tab is None else validity(p, int(o), tab)[0]

out = {"year": a.year, "days": a.days, "by_population": {}}
print(f"year {a.year}: {ev.height} RPKI-invalid origin-change events\n")
print("| population | n | " + " | ".join(f"valid at +{h} d | unknown at +{h} d" for h in a.days) + " | valid at any horizon |")
print("|---|---|" + "---|---|" * len(a.days) + "---|")
for pop, g in sorted(ev.group_by("pop"), key=lambda x: x[0][0]):
    ids = g["event_id"].to_list(); n = len(ids)
    rec = {"n": n}
    cells = []
    for h in a.days:
        st = [states[h][i] for i in ids]
        rec[f"valid_{h}d"] = round(sum(s == "valid" for s in st) / n, 3)
        rec[f"unknown_{h}d"] = round(sum(s == "unknown" for s in st) / n, 3)
        rec[f"no_data_{h}d"] = round(sum(s == "no_roa_data" for s in st) / n, 3)
        cells += [f"{rec[f'valid_{h}d']:.1%}", f"{rec[f'unknown_{h}d']:.1%}"]
    rec["valid_any"] = round(sum(any(states[h][i] == "valid" for h in a.days) for i in ids) / n, 3)
    out["by_population"][pop[0]] = rec
    print(f"| {pop[0]} | {n:,} | " + " | ".join(cells) + f" | {rec['valid_any']:.1%} |")
(E / "later_validity.json").write_text(json.dumps(out, indent=1))
ids = ev["event_id"].to_list()
pl.DataFrame({"event_id": ids, **{f"state_{h}d": [states[h][i] for i in ids] for h in a.days},
              "later_valid": [any(states[h][i] == "valid" for h in a.days) for i in ids]}).write_parquet(E / "later_validity.parquet")
