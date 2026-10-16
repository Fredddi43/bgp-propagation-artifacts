"""Label-free counterpart of the Radar-labelled replay stratum (2026-09-15). For 2023–2025 the replay set holds every Radar hijack
seen by ≥ 10 peers, and 96–99 % of those have an RPKI-invalid new origin; years without Radar (2022) only get the 3×3×2 stratified
sample. This script builds the same kind of stratum without labels: candidate origin changes at ≥ 10 peers and ≥ 3 collectors whose
new origin is RPKI-invalid against that day's ROAs and is not a CAIDA neighbour (provider/customer/peer) of any previous origin
(Radar suppresses visible provider–customer pairs, Demystifying 2026). A seeded random sample of N such events is appended to
replay_selection.parquet with reason "rpki_invalid_sample"; the same rule applied to 2024 gives the like-for-like control.
usage: select_validity_stratum.py <year> [n=3000]"""
from __future__ import annotations

import datetime as dt
import json
import sys

import polars as pl

from bgbench import config
from bgbench.leakcheck import rel_parquet
from bgbench.rpki_validate import roas_for, validity

year = int(sys.argv[1]); N = int(sys.argv[2]) if len(sys.argv) > 2 else 3000
INV = config.DATA_ROOT / "inventory" / str(year)
ev = pl.read_parquet(INV / "events_ranked.parquet").filter((pl.col("max_peers") >= 10) & (pl.col("max_collectors") >= 3))
ev = ev.with_columns(day=pl.col("first_ts").dt.strftime("%Y-%m-%d")).sort("first_ts")
print("candidates at >=10 peers, >=3 collectors:", ev.height, flush=True)
states = []; reasons = []
for day, g in ev.group_by("day", maintain_order=True):
    tab = roas_for(day[0])
    for p, o in g.select("prefix", "new_origin").iter_rows():
        if tab is None:
            states.append("no_roa_data"); reasons.append("")
        else:
            s, _, r = validity(p, int(o), tab); states.append(s); reasons.append(r)
ev = ev.with_columns(pl.Series("validity", states), pl.Series("invalid_reason", reasons))
counts = ev.group_by("validity").len().to_dicts()
inv = ev.filter(pl.col("validity") == "invalid")
# familiar pairs: new origin adjacent to a previous origin in that month's CAIDA graph
nb_cache: dict[str, set] = {}
def neighbours(month: str) -> set:
    if month not in nb_cache:
        nb_cache.clear(); d = pl.read_parquet(rel_parquet(month), columns=["u", "v"])
        nb_cache[month] = set(zip(d["u"].to_list(), d["v"].to_list()))
    return nb_cache[month]
fam = []
for m, o, prev in inv.select(pl.col("first_ts").dt.strftime("%Y%m"), "new_origin", "prev_origins").iter_rows():
    nbs = neighbours(m); prevs = [int(x) for x in str(prev or "").split(",") if x.strip().isdigit()]
    fam.append(any((int(o), q) in nbs or (q, int(o)) in nbs for q in prevs))
inv = inv.with_columns(pl.Series("familiar", fam))
pool = inv.filter(~pl.col("familiar"))
sample = pool.sample(n=min(N, pool.height), seed=20260915)
sample = sample.with_columns(
    vis_bucket=pl.when(pl.col("max_collectors") <= 4).then(pl.lit("2-4")).when(pl.col("max_collectors") <= 7).then(pl.lit("5-7")).otherwise(pl.lit("8-10")),
    dur_bucket=pl.when(pl.col("duration_min") <= 5).then(pl.lit("5")).when(pl.col("duration_min") <= 15).then(pl.lit("10-15")).otherwise(pl.lit(">15")),
    split=pl.when(pl.col("first_ts").dt.month() <= config.SPLIT_MONTH).then(pl.lit("train")).otherwise(pl.lit("test")),
    event_id=pl.concat_str([pl.col("first_ts").dt.strftime("%Y%m%dT%H%M%S"), pl.lit("_"), pl.col("prefix").str.replace_all("[/:]", "-"), pl.lit("_"), pl.col("new_origin").cast(pl.String)]),
    reason=pl.lit("rpki_invalid_sample")).drop("day", "validity", "invalid_reason", "familiar")
sel = pl.read_parquet(INV / "replay_selection.parquet")
before = sel.height
merged = pl.concat([sel, sample.select(sel.columns)], how="diagonal_relaxed").unique(["prefix", "new_origin", "first_ts"], keep="first").sort("first_ts")
merged.write_parquet(INV / "replay_selection.parquet")
added = merged.height - before
# the replay-by-day workflow marks finished collector-days; days that gained events must be redone
parts = config.DATA_ROOT / "events_replay_parts" / "_done"
new_days = set(merged.filter(pl.col("reason") == "rpki_invalid_sample")["first_ts"].dt.strftime("%Y-%m-%d").to_list())
removed = 0
for c in parts.iterdir() if parts.exists() else []:
    for d in new_days:
        f = c / f"{d}.json"
        if f.exists():
            f.unlink(); removed += 1
summ = {"year": year, "candidates_ge10peers_ge3coll": ev.height, "validity_counts": counts, "invalid": inv.height, "invalid_familiar_pair": int(inv["familiar"].sum()),
        "invalid_unfamiliar_pool": pool.height, "sampled": sample.height, "added_to_selection": added, "selection_total": merged.height, "done_markers_removed": removed,
        "invalid_reason_in_pool": pool.group_by("invalid_reason").len().to_dicts()}
print(json.dumps(summ, indent=1)); (INV / "validity_stratum_summary.json").write_text(json.dumps(summ, indent=1))
ev.select("prefix", "new_origin", "first_ts", "max_peers", "max_collectors", "validity", "invalid_reason").write_parquet(INV / "candidates_ge10_validity.parquet")
