"""Sprint-2 step 5/6: assemble the replayed events into one table and score the persistence baseline.

Per event (from events_replay/<id>/summary.json + membership.parquet + curve_vp.csv): extents at the ADR-0012
targets, membership sets at Δ ∈ {30 s, 1, 5, 15 min} (from membership first_seen) and at the targets, split
(train/test) and selection reason from the replay selection. Persistence baseline: predict membership at T =
membership at Δ; report Jaccard / recall and the size ratio, per Δ × T, on the test split (Sep–Dec).
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import polars as pl

from . import config
from .extent import TARGETS_S

DELTAS_S = {"d30s": 30, "d1m": 60, "d5m": 300, "d15m": 900}


def build_table(year: int = 2024, tag: str = "", replay_root: Path | None = None,
                event_ids: set[str] | None = None) -> pl.DataFrame:
    """tag "" = the ADR-0017 origin-change set (events_replay); "leak" = the sprint-3 slow-regime set (events_replay_leak)."""
    from .replay_day import roots

    if tag.startswith("leak"):
        sel = pl.read_parquet(config.DATA_ROOT / "inventory" / str(year) / "leak_replay_selection.parquet").select(
            "event_id", "split", "reason", "labelled", pl.col("n_collectors").alias("max_collectors"), "n_msgs", "duration_min", "a")
    elif tag == "withdrawal":
        sel = pl.read_parquet(config.DATA_ROOT / "inventory" / str(year) / "withdrawal_replay_selection.parquet").select(
            "event_id", "split", "reason", "labelled", pl.col("peak_vps").alias("max_collectors"), "duration_min")
    else:   # "" = the ADR-0017 origin-change set; "recovery" = the B→A counterparts of invalid-displacing-valid hijacks (same columns)
        sel = pl.read_parquet(config.DATA_ROOT / "inventory" / str(year) / ("recovery_replay_selection.parquet" if tag == "recovery" else "replay_selection.parquet")).select(
            "event_id", "split", "reason", "vis_bucket", "dur_bucket", "flip_back", "labelled", "max_collectors", "max_peers", "duration_min")
    # A return can be linked to hijacks on both sides of the temporal cutoff.
    # Its payload has one split, determined by its own event time; link analyses
    # retain the hijack split from the selection link table separately.
    if tag == "recovery":
        definitions = pl.read_parquet(config.DATA_ROOT / "inventory" / str(year) / "recovery_replay_selection.parquet")
        cutoff = 5 if year == 2026 else config.SPLIT_MONTH
        splits = definitions.select("event_id", pl.when(pl.col("first_ts").dt.month() <= cutoff)
                                    .then(pl.lit("train")).otherwise(pl.lit("test")).alias("split")).unique()
        sel = sel.drop("split").unique().join(splits, on="event_id", validate="1:1")
    else:
        sel = sel.unique(maintain_order=True)
    if sel["event_id"].n_unique() != sel.height:
        raise ValueError("conflicting selection metadata for one event_id")
    if event_ids is not None:
        missing = event_ids - set(sel["event_id"])
        if missing:
            raise ValueError(f"Replay scope includes unselected event IDs: {sorted(missing)}")
        sel = sel.filter(pl.col("event_id").is_in(sorted(event_ids)))
    rows = []
    _, root = roots(tag)
    root = replay_root or root
    for event_id in sel["event_id"]:
        d = root / event_id
        f = d / "summary.json"
        if not f.exists():
            continue
        s = json.loads(f.read_text())
        if s.get("error"):
            rows.append({"event_id": d.name, "error": s["error"],
                         **{k: v for k, v in s.items() if k.startswith("recovery_") or k.startswith("measurement_")}})
            continue
        mem_f = d / "membership.parquet"
        mem = pl.read_parquet(mem_f) if mem_f.exists() else None
        t0_ident = dt.datetime.fromisoformat(s["t0"])
        # ADR-0018: t₀ = first observation at any collector; the identifier's 2-collector instant is the trigger lag
        t0 = dt.datetime.fromisoformat(s["first_observation"]) if s.get("first_observation") else t0_ident
        # t90: seconds after t0 (first observation, ADR-0018) at which the cumulative set of distinct ASes reaches 90 % of its
        # 2-h size. Until 2026-09-19 this came from curve_asn.csv, which is relative to the identifier's t0 (negative values for
        # late identifiers) and counts collector×AS rows, so recoveries read 59 s where the horizon sets show an hour.
        t90 = None
        if mem is not None and mem.height:
            firsts = mem.group_by("asn").agg(first=pl.col("first_seen").min()).sort("first")["first"].to_list()
            end = t0 + dt.timedelta(seconds=TARGETS_S["final_2h"])
            firsts = [f for f in firsts if f <= end]
            if firsts:
                need = int(np.ceil(0.9 * len(firsts)))
                t90 = max(0.0, (firsts[need - 1] - t0).total_seconds())
        row = {"event_id": d.name, "error": None, "observation_lag_s": s.get("observation_lag_s"), "anomalous_msgs": s["anomalous_msgs"], "t90_s": t90,
               "t0_obs": t0.isoformat(), "trigger_lag_s": (t0_ident - t0).total_seconds(),
               "sessions_carrying": s["sessions_carrying_prefix"], "sessions_switched": s["sessions_switched_to_new_origin"],
               "collectors_seeing": len(s["collectors_seeing"]), "leaked_prefixes": s.get("leaked_prefixes"), "wave_prefixes": s.get("wave_prefixes")}
        row.update({k: v for k, v in s.items() if k.startswith("recovery_") or k.startswith("measurement_")})
        first = (mem.group_by("asn").agg(first=pl.col("first_seen").min())
                 if mem is not None and mem.height else None)
        for key, seconds in {**DELTAS_S, **TARGETS_S}.items():
            members = (sorted(first.filter(pl.col("first") <= pl.lit(t0 + dt.timedelta(seconds=seconds)))["asn"].to_list())
                       if first is not None else [])
            row[f"set_{key}"] = members
            row[f"asns_{key}"] = len(members)
        # Historical summaries used the identifier origin for VP counts too.
        # Reconstruct from timestamps; never copy those incompatible counts.
        vp_file = d / "vp_first.parquet"
        if vp_file.exists():
            vp = pl.read_parquet(vp_file)
        elif (d / "vp_changes.parquet").exists():
            vp = (pl.read_parquet(d / "vp_changes.parquet")
                  .group_by("collector", "peer_ip").agg(first=pl.col("change_ts").min()))
        elif (d / "anomalous.parquet").exists():
            vp = (pl.read_parquet(d / "anomalous.parquet", columns=["collector", "peer_ip", "ts"])
                  .group_by("collector", "peer_ip").agg(first=pl.col("ts").min()))
        else:
            raise FileNotFoundError(f"cannot rebuild VP horizon counts for {d.name}")
        for key, seconds in TARGETS_S.items():
            row[f"vp_{key}"] = (vp.filter(pl.col("first") <= pl.lit(t0 + dt.timedelta(seconds=seconds))).height
                                 if vp.height else 0)
        rows.append(row)
    if not rows:
        return sel.head(0).with_columns(error=pl.lit(None, pl.String))
    df = pl.DataFrame(rows, strict=False, infer_schema_length=None)
    for key in {**DELTAS_S, **TARGETS_S}:
        name = f"set_{key}"
        if name in df.columns:
            df = df.with_columns(pl.col(name).cast(pl.List(pl.UInt32)))
    return sel.join(df, on="event_id", how="inner", validate="1:1")


def persistence_scores(table: pl.DataFrame, split: str = "test") -> pl.DataFrame:
    t = table.filter((pl.col("split") == split) & pl.col("error").is_null())
    out = []
    for dk in DELTAS_S:
        for tk in TARGETS_S:
            if TARGETS_S[tk] <= DELTAS_S[dk]:
                continue
            a = t.select(pl.col(f"set_{dk}").alias("pred"), pl.col(f"set_{tk}").alias("truth")).drop_nulls()
            if a.is_empty():
                continue
            j = a.with_columns(
                inter=pl.col("pred").list.set_intersection(pl.col("truth")).list.len(),
                union=pl.col("pred").list.set_union(pl.col("truth")).list.len(),
                np=pl.col("pred").list.len(), nt=pl.col("truth").list.len(),
            ).with_columns(jaccard=pl.col("inter") / pl.col("union").clip(1), recall=pl.col("inter") / pl.col("nt").clip(1),
                           size_ratio=pl.col("np") / pl.col("nt").clip(1))
            out.append({"delta": dk, "target": tk, "events": j.height,
                        "jaccard_mean": round(float(j["jaccard"].mean()), 4), "jaccard_p50": round(float(j["jaccard"].median()), 4),
                        "recall_mean": round(float(j["recall"].mean()), 4), "size_ratio_p50": round(float(j["size_ratio"].median()), 4),
                        "frac_events_fully_grown_at_delta": round(float((j["jaccard"] >= 0.999).mean()), 4)})
    return pl.DataFrame(out)


def run(year: int = 2024, tag: str = "", replay_root: Path | None = None, output_dir: Path | None = None, table_override: pl.DataFrame | None = None) -> dict:
    tbl = table_override if table_override is not None else build_table(year, tag, replay_root)
    out_dir = output_dir or config.DATA_ROOT / "eventset" / (f"{year}_{tag}" if tag else str(year))
    out_dir.mkdir(parents=True, exist_ok=True)
    temporary = out_dir / "events.parquet.tmp"
    tbl.write_parquet(temporary, compression="zstd")
    temporary.replace(out_dir / "events.parquet")
    res = {"events": tbl.height, "errors": int(tbl["error"].is_not_null().sum()),
           "train": int((tbl["split"] == "train").sum()), "test": int((tbl["split"] == "test").sum())}
    ok = tbl.filter(pl.col("error").is_null())
    if ok.height:
        res["observation_lag_s_p10_p50_p90"] = [float(ok["observation_lag_s"].quantile(q)) for q in (0.1, 0.5, 0.9)]
        res["asns_final_p50_p90"] = [float(ok["asns_final_2h"].quantile(q)) for q in (0.5, 0.9)]
        res["vp_final_p50_p90"] = [float(ok["vp_final_2h"].quantile(q)) for q in (0.5, 0.9)]
        switch_fraction = (ok["sessions_switched"] / ok["sessions_carrying"].cast(pl.Float64).clip(1)).median()
        res["switch_fraction_p50"] = float(switch_fraction) if switch_fraction is not None else None
        if "t90_s" in ok.columns and ok["t90_s"].drop_nulls().len():
            t90 = ok["t90_s"].drop_nulls()
            res["time_to_90pct_extent_s_p10_p50_p90"] = [float(t90.quantile(q)) for q in (0.1, 0.5, 0.9)]   # ADR-0002 "how fast": seconds after t₀ to reach 90 % of the 2-h extent
            res["frac_events_t90_over_5min"] = round(float((t90 > 300).mean()), 4)
        if tag.startswith("leak"):
            res["leaked_prefixes_p50_p90"] = [float(ok["leaked_prefixes"].quantile(q)) for q in (0.5, 0.9)]
            res["anomalous_msgs_p50_p90"] = [float(ok["anomalous_msgs"].quantile(q)) for q in (0.5, 0.9)]
        for split in ("test", "train"):
            ps = persistence_scores(tbl, split)
            ps.write_csv(out_dir / f"persistence_{split}.csv")
            res[f"persistence_{split}"] = ps.to_dicts()
        # clean subset: events whose first observation is not (much) before the identifier's t₀ — a first observation
        # an hour earlier means the adjacency pre-existed (e.g. month-boundary novelty resets) and t₀ is not an onset
        clean = tbl.filter(pl.col("observation_lag_s").is_null() | (pl.col("observation_lag_s") >= -60))
        res["clean_events"] = int(clean.filter(pl.col("error").is_null()).height)
        for split in ("test", "train"):
            res[f"persistence_{split}_clean"] = persistence_scores(clean, split).to_dicts()
    (out_dir / "summary.json").write_text(json.dumps(res, indent=1, default=str))
    return res


def per_vp_and_duration(year: int = 2024, tag: str = "") -> dict:
    """ADR-0004 / ADR-0008 §2 and §6: (a) the persistence floor per collector (never pooled) and (b) the floor and share
    of ephemeral events (anomalous activity lasting < 60 s) vs persistent ones. Reads the replayed membership tables."""
    from .replay_day import roots

    _, root = roots(tag)
    tbl = pl.read_parquet(config.DATA_ROOT / "eventset" / (f"{year}_{tag}" if tag else str(year)) / "events.parquet").filter(pl.col("error").is_null())
    if tag.startswith("leak"):
        tbl = tbl.filter(pl.col("observation_lag_s").is_null() | (pl.col("observation_lag_s") >= -60))
    rows, durs = [], []
    for r in tbl.select("event_id", "split", "t0_obs").iter_rows(named=True):
        d = root / r["event_id"]
        t0 = dt.datetime.fromisoformat(r["t0_obs"])
        mf, af = d / "membership.parquet", d / "anomalous.parquet"
        if not mf.exists() or not af.exists():
            raise FileNotFoundError(f"Usable event {r['event_id']} lacks membership or announcement timestamps")
        mem = pl.read_parquet(mf, columns=["collector", "asn", "first_seen"])
        a = pl.read_parquet(af, columns=["ts"]).filter(pl.col("ts") <= pl.lit(t0 + dt.timedelta(hours=2)))
        durs.append({"event_id": r["event_id"], "split": r["split"], "duration_s": (a["ts"].max() - a["ts"].min()).total_seconds() if a.height else 0.0})
        # First-arrival sets are nested, so J(early, final) = |early| / |final|.
        # Aggregate every horizon together and retain distinct ASNs per collector.
        mem = mem.filter(pl.col("first_seen") <= pl.lit(t0 + dt.timedelta(hours=2)))
        counts = mem.group_by("collector").agg(final=pl.col("asn").n_unique(), **{
            key: pl.col("asn").filter(pl.col("first_seen") <= pl.lit(t0 + dt.timedelta(seconds=seconds))).n_unique()
            for key, seconds in DELTAS_S.items()})
        for c in counts.iter_rows(named=True):
            for key in DELTAS_S:
                rows.append({"event_id": r["event_id"], "split": r["split"], "collector": c["collector"],
                             "delta": key, "jaccard": c[key] / c["final"]})
    pv = pl.DataFrame(rows, schema={"event_id": pl.String, "split": pl.String, "collector": pl.String, "delta": pl.String, "jaccard": pl.Float64})
    per_vp = (pv.filter(pl.col("split") == "test").group_by("collector", "delta").agg(n=pl.len(), jaccard_mean=pl.col("jaccard").mean().round(3))
                .sort("delta", "collector"))
    spread = per_vp.group_by("delta").agg(min=pl.col("jaccard_mean").min(), max=pl.col("jaccard_mean").max(), std=pl.col("jaccard_mean").std().round(3)).sort("delta")
    du = pl.DataFrame(durs, schema={"event_id": pl.String, "split": pl.String, "duration_s": pl.Float64}).with_columns(bucket=pl.when(pl.col("duration_s") < 60).then(pl.lit("ephemeral <60 s")).when(pl.col("duration_s") < 600).then(pl.lit("1-10 min")).otherwise(pl.lit("persistent >10 min")))
    pooled = tbl.select("event_id", "split", *[f"set_{k}" for k in DELTAS_S], "set_final_2h").join(du.select("event_id", "bucket", "duration_s"), on="event_id")
    def jac(a, b):
        return pl.col(a).list.set_intersection(pl.col(b)).list.len() / pl.col(a).list.set_union(pl.col(b)).list.len().clip(1)
    by_dur = (pooled.filter(pl.col("split") == "test").with_columns(**{f"j_{k}": jac(f"set_{k}", "set_final_2h") for k in DELTAS_S})
                    .group_by("bucket").agg(n=pl.len(), **{f"J_{k}": pl.col(f"j_{k}").mean().round(3) for k in DELTAS_S}).sort("bucket"))
    out_dir = config.DATA_ROOT / "eventset" / (f"{year}_{tag}" if tag else str(year))
    per_vp.write_csv(out_dir / "persistence_per_vp_test.csv"); du.write_parquet(out_dir / "durations.parquet"); by_dur.write_csv(out_dir / "persistence_by_duration_test.csv")
    res = {"tag": tag, "events": tbl.height, "per_vp_test": per_vp.to_dicts(), "per_vp_spread": spread.to_dicts(),
           "duration_share_all": du.group_by("bucket").agg(n=pl.len(), frac=(pl.len() / du.height)).sort("bucket").to_dicts(), "persistence_by_duration_test": by_dur.to_dicts()}
    (out_dir / "per_vp_duration.json").write_text(json.dumps(res, indent=1, default=str))
    return res
