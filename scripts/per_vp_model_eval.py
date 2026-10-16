"""ADR-0008 §2 for the models: score a saved model's per-event probabilities against each collector's own membership
(never pooled). usage: per_vp_model_eval.py <year> <tag> <delta_s> <prefix>  → prints per-collector Jaccard model vs persistence."""
import sys
import numpy as np
import polars as pl
import torch
from bgbench import config
from bgbench.replay_day import roots

year, tag, delta_s, prefix = int(sys.argv[1]), sys.argv[2], int(sys.argv[3]), sys.argv[4]
res_dir = config.tgn_dir(year, delta_s, tag) / "_results"
probs = torch.load(res_dir / f"{prefix}_test_probs.pt", weights_only=False)
thr = torch.load(res_dir / f"{prefix}_model.pt", weights_only=False, map_location='cpu')["threshold"]
from bgbench.tgn_data import replay_tag
root = roots(replay_tag(tag))[1]
import datetime as dt
import json
base = replay_tag(tag)
table = config.DATA_ROOT / "eventset" / (f"{year}_{base}" if base else str(year)) / "events.parquet"
onsets = dict(pl.read_parquet(table).select("event_id", "t0_obs").iter_rows())
rows = []
for eid, (asn, p) in probs.items():
    d = root / eid
    if not (d / "membership.parquet").exists():
        raise FileNotFoundError(d / "membership.parquet")
    t0 = onsets[eid]
    if isinstance(t0, str):
        t0 = dt.datetime.fromisoformat(t0)
    mem = pl.read_parquet(d / "membership.parquet")
    tensor = torch.load(config.tgn_dir(year, delta_s, tag) / f"{eid}.pt", weights_only=False, mmap=True)
    pooled_prediction = set(int(a) for a, q in zip(asn, p) if q >= thr) | set(tensor["seed_asns"].tolist())
    for c, g in mem.group_by("collector"):
        fin = set(int(a) for a in g.filter(pl.col("first_seen") <= pl.lit(t0 + dt.timedelta(hours=2)))["asn"].to_list())
        seed = set(int(a) for a in g.filter(pl.col("first_seen") <= pl.lit(t0 + dt.timedelta(seconds=delta_s)))["asn"].to_list())
        if not fin:
            continue
        pred = seed | pooled_prediction
        rows.append({"event_id": eid, "collector": c[0], "target_asns": json.dumps(sorted(fin)), "seed_asns": json.dumps(sorted(seed)),
                     "predicted_asns": json.dumps(sorted(pred)), "j_model": len(pred & fin) / len(pred | fin), "j_persist": len(seed & fin) / len(seed | fin)})
df = pl.DataFrame(rows)
df.write_csv(res_dir / f"{prefix}_per_vp_per_event.csv")
out = df.group_by("collector").agg(n=pl.len(), j_model=pl.col("j_model").mean(), j_persist=pl.col("j_persist").mean(),
                                   diff=(pl.col("j_model") - pl.col("j_persist")).mean()).sort("collector")
print(out); out.write_csv(res_dir / f"{prefix}_per_vp.csv")
print("spread of model gain across collectors: min", float(out["diff"].min()), "max", float(out["diff"].max()))
