"""Rung 4, fine-tuned (RESEARCH-PLAN: "zero-shot first, then lightweight fine-tuning (LoRA/PEFT)"): Chronos-2 fine-tuned with
LoRA on the training-split magnitude curves of the year's large leaks, evaluated on the test split like curve_eventset / tsfm_curves
(sMAPE at 15 / 60 / 120 min from a Δ-minute context, vs the zero-shot model and persistence). Curves are the affected-AS count at
minute resolution (curve_asn.csv of each replayed event). Runs on a GPU. usage: tsfm_finetune.py <year> <set_tag> <min_asns> <out_json>"""
from __future__ import annotations

import json
import hashlib
from importlib.metadata import version, PackageNotFoundError
import sys
from pathlib import Path

import numpy as np
import polars as pl
import torch

from bgbench import config
from bgbench.curve_eventset import event_series
from bgbench.replay_day import roots

torch.manual_seed(0)
np.random.seed(0)

year, tag, min_asns, out_json = int(sys.argv[1]), sys.argv[2], int(sys.argv[3]), Path(sys.argv[4])
E = config.DATA_ROOT / "eventset" / (f"{year}_{tag}" if tag else str(year))
root = roots("leak" if tag.startswith("leak") else tag)[1]
tbl = pl.read_parquet(E / "events.parquet").filter(pl.col("error").is_null())
if tag.startswith("leak"):
    tbl = tbl.filter(pl.col("observation_lag_s").is_null() | (pl.col("observation_lag_s") >= -60))
if min_asns:
    tbl = tbl.filter(pl.col("asns_final_2h") >= min_asns)


onsets = dict(tbl.select("event_id", "t0_obs").iter_rows())


def load_series(eid: str):
    return event_series(root / eid, onsets[eid], "asn")


series = {}
eligibility = []
for row in tbl.iter_rows(named=True):
    eid = row["event_id"]
    values = load_series(eid)
    if values is None:
        raise RuntimeError(f"Usable event has no source membership: {eid}")
    series[eid] = values
    membership = root/eid/"membership.parquet"
    digest = hashlib.sha256()
    with membership.open("rb") as stream:
        for block in iter(lambda: stream.read(8*1024*1024), b""):
            digest.update(block)
    eligibility.append({"event_id": eid, "split": row["split"], "t0_obs": row["t0_obs"],
                        "observed_zero_count": int(values[0]), "final_count": int(values[-1]),
                        "eligible_growth": bool(values[-1] > values[0]), "membership_sha256": digest.hexdigest()})
out_json.parent.mkdir(parents=True, exist_ok=True)
pl.DataFrame(eligibility).write_parquet(out_json.parent/"curve_eligibility.parquet")
train_pairs = [(e, series[e]) for e in tbl.filter(pl.col("split") == "train")["event_id"].to_list()]
test_pairs = [(e, series[e]) for e in tbl.filter(pl.col("split") == "test")["event_id"].to_list()]
train_pairs = [(e, s) for e, s in train_pairs if s is not None and s[-1] > s[0]]
test_pairs = [(e, s) for e, s in test_pairs if s is not None and s[-1] > s[0]]
from bgbench.graph_metrics import embargo_training_events
kept, embargo = embargo_training_events([{"event_id": e} for e, _ in train_pairs], [{"event_id": e} for e, _ in test_pairs], onsets)
kept_ids = {row["event_id"] for row in kept}
train_pairs = [(e, s) for e, s in train_pairs if e in kept_ids]
train = [s for _, s in train_pairs]
test = [s for _, s in test_pairs]
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


package_versions = {}
for package in ("chronos-forecasting", "peft", "transformers", "torch", "numpy"):
    try:
        package_versions[package] = version(package)
    except PackageNotFoundError:
        package_versions[package] = None
base_revision = getattr(zs.model.config, "_commit_hash", None)
if base_revision is None:
    from huggingface_hub import try_to_load_from_cache
    cached_config = try_to_load_from_cache("amazon/chronos-2", "config.json")
    if isinstance(cached_config, str) and "/snapshots/" in cached_config:
        base_revision = cached_config.split("/snapshots/", 1)[1].split("/", 1)[0]
final_checkpoint = out_json.parent / "chronos2_lora_final"
ft.save_pretrained(final_checkpoint)
(final_checkpoint / "reproduction.json").write_text(json.dumps({"package_versions": package_versions, "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu", "base_model": "amazon/chronos-2", "base_revision": base_revision, "finetune_mode": "lora", "steps": int(sys.argv[5]) if len(sys.argv)>5 else 600, "seed": 0, "input_scale": "log1p_counts", "train_event_ids": [e for e,_ in train_pairs], "training_embargo": embargo},indent=1))


def smape(a, b):
    return 0.0 if a == b == 0 else 2 * abs(a - b) / (abs(a) + abs(b))


def forecast(pipe, ctx_log: np.ndarray, steps: int) -> np.ndarray:
    # Chronos-2 takes a list of 1-D series (or a 3-D tensor); a 2-D (1, T) tensor is rejected
    q, mean = pipe.predict_quantiles([torch.tensor(ctx_log, dtype=torch.float32)], prediction_length=steps, quantile_levels=[0.5])
    q0 = q[0] if isinstance(q, (list, tuple)) else q[0]
    arr = np.asarray(q0.detach().cpu() if hasattr(q0, "detach") else q0, dtype=float)
    result = np.expm1(arr.reshape(-1, arr.shape[-1])[:, 0] if arr.ndim >= 2 else arr)
    if len(result) < steps or not np.isfinite(result).all():
        raise ValueError("Chronos forecast is incomplete or non-finite")
    return result


res = {"measurement_definition": "exact_minute_counts_from_membership_at_t0_obs_v1", "year": year, "tag": tag, "min_asns": min_asns, "train_series": len(train), "test_series": len(test), "finetune": "chronos-2 LoRA, log1p counts", "by_delta": {}}
res["final_checkpoint"] = "chronos2_lora_final"
res["eligibility_table"] = "curve_eligibility.parquet"
res["training_embargo"] = embargo
res["train_event_ids"] = [e for e, _ in train_pairs]
res["test_event_ids"] = [e for e, _ in test_pairs]
scored = []
for delta in (1, 5, 15):
    rows = {"persistence": {}, "chronos2_zeroshot": {}, "chronos2_lora": {}}
    for hm in (15, 60, 120):
        if hm <= delta:
            continue
        acc = {k: [] for k in rows}
        for eid, s in test_pairs:
            ctx = np.log1p(s[: delta + 1]); steps = hm - delta
            truth = float(s[hm]); last = float(s[delta])
            fz = forecast(zs, ctx, steps); fl = forecast(ft, ctx, steps)
            acc["persistence"].append(smape(last, truth))
            acc["chronos2_zeroshot"].append(smape(max(float(fz[-1]), last), truth))
            acc["chronos2_lora"].append(smape(max(float(fl[-1]), last), truth))
            for name, prediction in (("persistence", last), ("chronos2_zeroshot", max(float(fz[-1]), last)), ("chronos2_lora", max(float(fl[-1]), last))):
                scored.append({"event_id": eid, "model": name, "delta_min": delta, "horizon_min": hm, "truth": truth, "observed_delta_count": last, "prediction": prediction, "smape": smape(prediction, truth)})
        for k in rows:
            rows[k][f"T{hm}m"] = round(float(np.mean(acc[k])), 4)
    res["by_delta"][f"d{delta}m"] = rows
    print(delta, rows, flush=True)
out_json.parent.mkdir(parents=True, exist_ok=True)
pl.DataFrame(scored).write_parquet(out_json.with_suffix(".predictions.parquet"))
out_json.write_text(json.dumps(res, indent=1))
print(json.dumps(res, indent=1))
