"""Rung 4, fine-tuned (RESEARCH-PLAN: "zero-shot first, then lightweight fine-tuning (LoRA/PEFT)"): Chronos-2 fine-tuned with
LoRA on the training-split magnitude curves of the year's large leaks, evaluated on the test split like curve_eventset / tsfm_curves
(sMAPE at 15 / 60 / 120 min from a Δ-minute context, vs the zero-shot model and persistence). Curves are the affected-AS count at
minute resolution (curve_asn.csv of each replayed event). Runs on a GPU. usage: tsfm_finetune.py <year> <set_tag> <min_asns> <out_json>"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import polars as pl
import torch

from bgbench import config
from bgbench.replay_day import roots

year, tag, min_asns, out_json = int(sys.argv[1]), sys.argv[2], int(sys.argv[3]), Path(sys.argv[4])
E = config.DATA_ROOT / "eventset" / (f"{year}_{tag}" if tag else str(year))
root = roots("leak" if tag.startswith("leak") else tag)[1]
tbl = pl.read_parquet(E / "events.parquet").filter(pl.col("error").is_null())
if tag.startswith("leak"):
    tbl = tbl.filter(pl.col("observation_lag_s").is_null() | (pl.col("observation_lag_s") >= -60))
if min_asns:
    tbl = tbl.filter(pl.col("asns_final_2h") >= min_asns)


def load_series(eid: str):
    f = root / eid / "curve_asn.csv"
    if not f.exists():
        return None
    c = pl.read_csv(f).sort("rel_s")
    if c.height == 0:
        return None
    t = np.arange(0, 7201); N = np.zeros_like(t, dtype=float)
    idx = np.searchsorted(c["rel_s"].to_numpy(), t, side="right") - 1
    N[idx >= 0] = c["N"].to_numpy()[idx[idx >= 0]]
    return N[::60]                     # 121 points, minute resolution


train = [s for s in (load_series(e) for e in tbl.filter(pl.col("split") == "train")["event_id"].to_list()) if s is not None and s[-1] > s[0]]
test = [s for s in (load_series(e) for e in tbl.filter(pl.col("split") == "test")["event_id"].to_list()) if s is not None and s[-1] > s[0]]
print(f"train series {len(train)} test series {len(test)}", flush=True)
from chronos import BaseChronosPipeline

device = "cuda" if torch.cuda.is_available() else "cpu"
zs = BaseChronosPipeline.from_pretrained("amazon/chronos-2", device_map=device, torch_dtype=torch.float32)
H = 120
# fine-tune: each training curve as one series (log1p-scaled counts, the scale the curve heads use); LoRA, few hundred steps
inputs = [torch.tensor(np.log1p(s), dtype=torch.float32) for s in train]
# series are 121 points long: fine-tune on 30-point contexts predicting the next 60 minutes (min_past keeps every series eligible)
ft = zs.fit(inputs, prediction_length=60, finetune_mode="lora", learning_rate=1e-4, num_steps=int(sys.argv[5]) if len(sys.argv) > 5 else 600, batch_size=32,
            context_length=60, min_past=30, output_dir=str(out_json.parent / "chronos2_lora_ckpt"))


def smape(a, b):
    return 0.0 if a == b == 0 else 2 * abs(a - b) / (abs(a) + abs(b))


def forecast(pipe, ctx_log: np.ndarray, steps: int) -> np.ndarray:
    # Chronos-2 takes a list of 1-D series (or a 3-D tensor); a 2-D (1, T) tensor is rejected
    q, mean = pipe.predict_quantiles([torch.tensor(ctx_log, dtype=torch.float32)], prediction_length=steps, quantile_levels=[0.5])
    q0 = q[0] if isinstance(q, (list, tuple)) else q[0]
    arr = np.asarray(q0.detach().cpu() if hasattr(q0, "detach") else q0, dtype=float)
    return np.expm1(arr.reshape(-1, arr.shape[-1])[:, 0] if arr.ndim >= 2 else arr)


res = {"year": year, "tag": tag, "min_asns": min_asns, "train_series": len(train), "test_series": len(test), "finetune": "chronos-2 LoRA, log1p counts", "by_delta": {}}
for delta in (1, 5, 15):
    rows = {"persistence": {}, "chronos2_zeroshot": {}, "chronos2_lora": {}}
    for hm in (15, 60, 120):
        if hm <= delta:
            continue
        acc = {k: [] for k in rows}
        for s in test:
            ctx = np.log1p(s[: delta + 1]); steps = hm - delta
            truth = float(s[hm]); last = float(s[delta])
            fz = forecast(zs, ctx, steps); fl = forecast(ft, ctx, steps)
            acc["persistence"].append(smape(last, truth))
            acc["chronos2_zeroshot"].append(smape(max(float(fz[-1]), last), truth))
            acc["chronos2_lora"].append(smape(max(float(fl[-1]), last), truth))
        for k in rows:
            rows[k][f"T{hm}m"] = round(float(np.mean(acc[k])), 4)
    res["by_delta"][f"d{delta}m"] = rows
    print(delta, rows, flush=True)
out_json.parent.mkdir(parents=True, exist_ok=True)
out_json.write_text(json.dumps(res, indent=1))
print(json.dumps(res, indent=1))
