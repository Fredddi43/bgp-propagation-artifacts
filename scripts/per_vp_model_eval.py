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
thr = torch.load(res_dir / f"{prefix}_model.pt", weights_only=False)["threshold"]
from bgbench.tgn_data import replay_tag
root = roots(replay_tag(tag))[1]
import datetime as dt, json
rows = []
for eid, (asn, p) in probs.items():
    d = root / eid
    if not (d / "membership.parquet").exists():
        continue
    t0 = dt.datetime.fromisoformat(json.loads((d / "summary.json").read_text())["first_observation"])
    mem = pl.read_parquet(d / "membership.parquet")
    pred_new = set(int(a) for a, q in zip(asn, p) if q >= thr)
    for c, g in mem.group_by("collector"):
        fin = set(int(a) for a in g.filter(pl.col("first_seen") <= pl.lit(t0 + dt.timedelta(hours=2)))["asn"].to_list())
        seed = set(int(a) for a in g.filter(pl.col("first_seen") <= pl.lit(t0 + dt.timedelta(seconds=delta_s)))["asn"].to_list())
        if not fin:
            continue
        pred = seed | (pred_new & set(int(a) for a in asn))
        rows.append({"event_id": eid, "collector": c[0], "j_model": len(pred & fin) / len(pred | fin), "j_persist": len(seed & fin) / len(seed | fin)})
df = pl.DataFrame(rows)
out = df.group_by("collector").agg(n=pl.len(), j_model=pl.col("j_model").mean().round(3), j_persist=pl.col("j_persist").mean().round(3),
                                   diff=(pl.col("j_model") - pl.col("j_persist")).mean().round(3)).sort("collector")
print(out); out.write_csv(res_dir / f"{prefix}_per_vp.csv")
print("spread of model gain across collectors: min", float(out["diff"].min()), "max", float(out["diff"].max()))
