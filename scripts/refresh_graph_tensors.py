"""Repair a copied tensor directory from retained replay inputs; never edit the source tree.

Use one process per year/tag/delta. It refreshes complete truth/seed metadata, ROV
features, temporal endpoints and history counts, and reconciles large-leak eligibility.
Writes an impact manifest. Existing model results must be rerun after this operation.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import numpy as np
import polars as pl
import torch

from bgbench import config
from bgbench.extent import TARGETS_S
from bgbench.graph_metrics import message_stream, completed_event_histories
from bgbench.replay_day import roots
from bgbench.tgn_data import build_event, parse_tag, replay_tag, rov_ratio


def refresh(year, tag, delta):
    base, options = parse_tag(tag)
    vp = options.get("vp")
    shift = float(options.get("t0", 0))
    directory = config.tgn_dir(year, delta, tag)
    table_tag = replay_tag(tag)
    table = pl.read_parquet(config.DATA_ROOT / "eventset" / (f"{year}_{table_tag}" if table_tag else str(year)) / "events.parquet")
    table = table.filter(pl.col("error").is_null()).unique("event_id")
    if table_tag == "leak":
        table = table.filter(pl.col("observation_lag_s").is_null() | (pl.col("observation_lag_s") >= -60))
    if base == "leak200":
        table = table.filter(pl.col("set_final_2h").list.len() >= 200)
    if base in ("rpkivalid", "rpkiinvalid"):
        validity = pl.read_parquet(config.DATA_ROOT / "eventset" / str(year) / "rpki_validity.parquet")
        table = table.join(validity.filter(pl.col("validity") == base[4:]).select("event_id"), on="event_id", how="semi")
    metadata = {row["event_id"]: row for row in table.iter_rows(named=True)}
    histories = completed_event_histories({eid: row["t0_obs"] for eid, row in metadata.items()},
                                         {eid: row["set_final_2h"] for eid, row in metadata.items()})
    files = sorted(directory.glob("*.pt"))
    impact = {"year": year, "tag": tag, "delta_s": delta, "events": [], "removed_ids": [], "added_ids": []}
    for f in files:
        event_id = f.stem
        if event_id not in metadata:
            f.unlink()
            impact["removed_ids"].append(event_id)
            continue
        event = torch.load(f, weights_only=False)
        replay = roots(table_tag)[1] / event_id
        summary = json.loads((replay / "summary.json").read_text())
        onset = dt.datetime.fromisoformat(metadata[event_id]["t0_obs"])
        trigger = onset + dt.timedelta(seconds=shift)
        mem = pl.read_parquet(replay / "membership.parquet")
        anom = pl.read_parquet(replay / "anomalous.parquet")
        if vp:
            mem = mem.filter(pl.col("collector") == vp)
            anom = anom.filter(pl.col("collector") == vp)
        first = mem.group_by("asn").agg(first=pl.col("first_seen").min())
        seeds = first.filter(pl.col("first") <= pl.lit(trigger + dt.timedelta(seconds=delta)))["asn"].to_list()
        target = first.filter(pl.col("first") <= pl.lit(onset + dt.timedelta(hours=2)))["asn"].to_list()
        asns = event["asn"].numpy()
        if set(seeds) != set(asns[event["persistence_pred"].numpy().astype(bool)]) | (set(seeds) - set(asns)):
            raise ValueError(f"Candidate seeds changed: rebuild {f}")
        old_y = event["y"].numpy().copy()
        event["target_asns"] = torch.tensor(sorted(target), dtype=torch.int64)
        event["seed_asns"] = torch.tensor(sorted(seeds), dtype=torch.int64)
        event["n_seed_all"] = len(seeds)
        event["y"] = torch.from_numpy(np.isin(asns, target).astype(np.float32))
        event["n_pos"] = int(event["y"].sum())
        event["curve"] = torch.tensor([first.filter(pl.col("first") <= pl.lit(onset + dt.timedelta(seconds=h))).height for h in TARGETS_S.values()], dtype=torch.float32)
        old_x = event["x"].clone()
        event["x"][:, 10] = torch.tensor([np.log1p(histories[event_id].get(int(a), 0)) for a in asns])
        day = onset.date().isoformat()
        ratios = [rov_ratio(int(a), day) for a in asns]
        if event["x"].shape[1] > 12:
            event["x"][:, 11] = torch.tensor([v if v is not None else 0 for v in ratios])
            event["x"][:, 12] = torch.tensor([float(v is not None) for v in ratios])
        by_delta = anom.filter(pl.col("ts") <= pl.lit(trigger + dt.timedelta(seconds=delta)))
        paths = [[int(a) if a.isdigit() else None for a in p.replace("{", "").replace("}", "").split()] if p else [] for p in by_delta["as_path"]]
        messages = message_stream(by_delta["ts"].to_list(), paths, asns, trigger)
        old_messages = event["msgs"].numpy()
        changed_messages = old_messages.shape != messages.shape or not np.array_equal(old_messages, messages)
        event["msgs"] = torch.from_numpy(messages)
        event["measurement_version"] = 2
        record = {"event_id": event_id, "split": event["split"], "old_messages": len(old_messages), "new_messages": len(messages),
                  "messages_changed": changed_messages, "labels_changed": bool(np.any(old_y != event["y"].numpy())),
                  "feature_rows_changed": int((old_x != event["x"]).any(dim=1).sum()),
                  "rov_rows_changed": int((old_x[:, 11:13] != event["x"][:, 11:13]).any(dim=1).sum()) if old_x.shape[1] > 12 else 0,
                  "full_target": len(target), "candidate_target": event["n_pos"]}
        impact["events"].append(record)
        torch.save(event, f)
    # Other regimes can be deliberately sampled; only the full large-leak cohort is reconciled here.
    if base == "leak200":
        graphs = {}
        for event_id in sorted(set(metadata) - {p.stem for p in directory.glob("*.pt")}):
            built = build_event(event_id, delta, year, int(options.get("k", 3000)), graphs, tag, histories.get(event_id), vp=vp, t0_shift_s=shift, legality=options.get("legal") == "1")
            if built is None:
                continue
            built = {k: torch.from_numpy(v) if isinstance(v, np.ndarray) else v for k, v in built.items()}
            built["split"] = metadata[event_id]["split"]
            torch.save(built, directory / f"{event_id}.pt")
            impact["added_ids"].append(event_id)
    (directory / "correction-impact.json").write_text(json.dumps(impact, indent=2))
    print(json.dumps({k: len(v) if isinstance(v, list) else v for k, v in impact.items()}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("year", type=int)
    parser.add_argument("tag")
    parser.add_argument("delta", type=int)
    args = parser.parse_args()
    refresh(args.year, args.tag, args.delta)
