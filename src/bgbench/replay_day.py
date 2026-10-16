"""Replay by collector-day (replaces per-event replay, which re-parsed each window: 18k events × 10 collectors).

extract_day(collector, date): parse the whole day once (as in the pass), then for every selected event whose
window [t₀−1 h, t₀+3 h] intersects the day, write the announcements of the event prefix inside the window
(any origin, so the VP switch metric is computable) to events_replay_parts/<event_id>/<collector>__<date>.parquet.
merge_event(event_id): concatenate the parts → membership / curves / extents / summary (same outputs as replay.py).
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import polars as pl

from . import config
from .broker import day_window, search
from .extent import TARGETS_S, growth_curve, membership
from .fetch import fetch_all
from .parse import parse_day

BEFORE_H, AFTER_H = 1, 3


MAX_PARTS_MB_DEFAULT = float(os.environ.get("BGBENCH_MAX_PARTS_MB", "3000"))   # merge refuses events whose compressed parts exceed this


def roots(tag: str = "") -> tuple[Path, Path]:
    """(parts root, merged root) for a replay set; tag "" = the ADR-0017 origin-change set, "leak" = the slow-regime set."""
    suf = f"_{tag}" if tag else ""
    return config.DATA_ROOT / f"events_replay_parts{suf}", config.DATA_ROOT / f"events_replay{suf}"


def load_manifest(path: Path | None = None) -> pl.DataFrame:
    path = path or (config.DATA_ROOT / "inventory" / "2024" / "replay_manifest.tsv")
    m = pl.read_csv(path, separator="\t", schema_overrides={"new_origin": pl.Int64, "a": pl.Int64, "sources": pl.String, "upstreams": pl.String, "burst_end": pl.String})
    if "kind" not in m.columns:
        m = m.with_columns(kind=pl.lit("origin"))
    if "burst_end" in m.columns:
        m = m.with_columns(burst_end=pl.col("burst_end").str.to_datetime("%Y-%m-%dT%H:%M:%S", time_zone="UTC"))
    return m.with_columns(t0=pl.col("t0").str.to_datetime("%Y-%m-%dT%H:%M:%S", time_zone="UTC"),
                          w_start=pl.col("t0").str.to_datetime("%Y-%m-%dT%H:%M:%S", time_zone="UTC") - pl.duration(hours=BEFORE_H),
                          w_end=pl.col("t0").str.to_datetime("%Y-%m-%dT%H:%M:%S", time_zone="UTC") + pl.duration(hours=AFTER_H))


def events_for_day(man: pl.DataFrame, date: str) -> pl.DataFrame:
    d0, d1 = day_window(date)
    return man.filter((pl.col("w_start") < pl.lit(d1)) & (pl.col("w_end") > pl.lit(d0)))


def _leak_regex(a: int, sources: str) -> str:
    """Path string reads collector-side → origin-side, so a route learned by `a` from b appears as "… a b …"."""
    bs = "|".join(str(int(b)) for b in sources.split("|") if b)
    return rf"(^| ){a} ({bs})( |$)"


# communities are dropped from the retained replay tables by default; BGB_KEEP_COMMUNITIES=1 keeps them (communities check, 2026-09-15)
ROW_COLS = ["ts", "collector", "peer_ip", "peer_asn", "prefix", "as_path", "origin_asn"] + (["communities"] if os.environ.get("BGB_KEEP_COMMUNITIES") else [])


def extract_day(collector: str, date: str, manifest: Path | None = None, workers: int = 32, procs: int = 8, tag: str = "", force: bool = False) -> dict:
    man = load_manifest(manifest)
    evs = events_for_day(man, date)
    parts_root, _ = roots(tag)
    done_marker = parts_root / "_done" / collector / f"{date}.json"
    if done_marker.exists() and not force:
        return json.loads(done_marker.read_text())
    if evs.is_empty():
        done_marker.parent.mkdir(parents=True, exist_ok=True)
        done_marker.write_text(json.dumps({"collector": collector, "date": date, "events": 0}))
        return {"collector": collector, "date": date, "events": 0}
    start, end = day_window(date)
    shm = config.shm_dir() / "xday" / collector / date
    try:
        items = search(collector, start, end, "updates")
        res = fetch_all(items, shm, workers=workers)
        ok = [r.path for r in res if r.path]
        transient = [r for r in res if not r.path and r.error != "404"]
        if transient:
            raise RuntimeError(f"{len(transient)} transient download failures ({transient[0].error})")
        pq_dir = shm / "pq"
        parse_day(ok, collector, pq_dir, procs=procs, delete_raw=True)
        parts = sorted(pq_dir.glob("part-*.parquet"))
        if not parts:
            # collector-day with no usable archive (all 404 / empty files): record it as a zero-event day so the DAG completes
            s = {"collector": collector, "date": date, "events": 0, "note": f"no parquet parts ({len(items)} items, {len(ok)} fetched)"}
            done_marker.parent.mkdir(parents=True, exist_ok=True); done_marker.write_text(json.dumps(s))
            return s
        base = (pl.scan_parquet([str(p) for p in parts])
                  .filter((pl.col("elem_type") == "A") & pl.col("as_path").is_not_null())
                  .select("ts", pl.col("collector").cast(pl.String), *[c for c in ROW_COLS if c not in ("ts", "collector")]))
        orig = evs.filter(pl.col("kind") == "origin"); leak = evs.filter(pl.col("kind") == "leak"); wd = evs.filter(pl.col("kind") == "withdrawal")
        subw = None
        if wd.height:
            # withdrawal waves: rows of *both* types for the prefixes withdrawn by ≥ 3 peers inside the burst window; the
            # prefix set is discovered per collector-day from the W rows of the burst itself
            allw = (pl.scan_parquet([str(p) for p in parts]).select("ts", "elem_type", pl.col("collector").cast(pl.String), *[c for c in ROW_COLS if c not in ("ts", "collector")])
                      .filter((pl.col("ts") >= pl.lit(wd["w_start"].min())) & (pl.col("ts") <= pl.lit(wd["w_end"].max()))).collect(engine="streaming"))
            subw = allw
        sub = base.filter(pl.col("prefix").is_in(orig["prefix"].unique().to_list())).collect(engine="streaming") if orig.height else None
        subl = None
        if leak.height:
            any_re = "|".join(_leak_regex(int(e["a"]), e["sources"]) for e in leak.iter_rows(named=True))
            subl = base.filter(pl.col("as_path").str.contains(any_re)).collect(engine="streaming")
        n_written = 0
        for e in evs.iter_rows(named=True):
            if e["kind"] == "withdrawal":
                burst_end = (e.get("burst_end") or e["t0"]) + dt.timedelta(minutes=5)
                wrows = subw.filter((pl.col("elem_type") == "W") & (pl.col("ts") >= pl.lit(e["t0"])) & (pl.col("ts") <= pl.lit(burst_end)))
                pfx = (wrows.group_by("prefix").agg(n=pl.col("peer_ip").n_unique()).filter(pl.col("n") >= 3))["prefix"]
                rows = subw.filter(pl.col("prefix").is_in(pfx.implode()) & (pl.col("ts") >= pl.lit(e["w_start"])) & (pl.col("ts") <= pl.lit(e["w_end"])))
            elif e["kind"] == "leak":
                rows = subl.filter(pl.col("as_path").str.contains(_leak_regex(int(e["a"]), e["sources"]))
                                   & (pl.col("ts") >= pl.lit(e["w_start"])) & (pl.col("ts") <= pl.lit(e["w_end"])))
            else:
                rows = sub.filter((pl.col("prefix") == e["prefix"]) & (pl.col("ts") >= pl.lit(e["w_start"])) & (pl.col("ts") <= pl.lit(e["w_end"])))
            out = parts_root / e["event_id"]
            out.mkdir(parents=True, exist_ok=True)
            rows.write_parquet(out / f"{collector}__{date}.parquet", compression="zstd")
            n_written += 1
        summary = {"collector": collector, "date": date, "events": n_written, "files": f"{len(ok)}/{len(items)}",
                   "rows_prefix_window": sub.height if sub is not None else 0, "rows_leak_paths": subl.height if subl is not None else 0}
        done_marker.parent.mkdir(parents=True, exist_ok=True)
        done_marker.write_text(json.dumps(summary))
        return summary
    finally:
        config.release_shm(shm)


def merge_event(event_id: str, prefix: str, new_origin: int, t0: dt.datetime, expected_collectors: int = 10, tag: str = "",
                leak: tuple[int, str] | None = None, max_parts_mb: float | None = None,
                recovery_prev_origin: int | None = None,
                parts_root_override: Path | None = None, merged_root_override: Path | None = None) -> dict:
    """leak=(a, sources): anomalous rows are every part row (they all carry the leaked adjacency), the actor is the
    leaker a, membership = ASes collector-side of a (the ones that accepted and propagated the leaked routes)."""
    if max_parts_mb is None:
        max_parts_mb = MAX_PARTS_MB_DEFAULT
    parts_root, merged_root = roots(tag)
    parts_root = parts_root_override or parts_root
    merged_root = merged_root_override or merged_root
    parts_dir = parts_root / event_id
    out_dir = merged_root / event_id
    files = sorted(parts_dir.glob("*.parquet")) if parts_dir.exists() else []
    out_dir.mkdir(parents=True, exist_ok=True)
    if not files:
        s = {"event_id": event_id, "error": "no parts", "collectors_with_parts": 0}
        (out_dir / "summary.json").write_text(json.dumps(s)); return s
    parts_mb = sum(f.stat().st_size for f in files) / 1e6
    if parts_mb > max_parts_mb:
        # a leak whose adjacency sits on a tier-1 carries tens of millions of rows per collector; the driver OOM'd at 32 GB
        s = {"event_id": event_id, "error": f"parts too large ({parts_mb:.0f} MB compressed > {max_parts_mb} MB)", "collectors_with_parts": len(files), "parts_mb": round(parts_mb)}
        (out_dir / "summary.json").write_text(json.dumps(s)); return s
    cols = ROW_COLS
    allp = pl.concat([pl.read_parquet(f, columns=cols) for f in files], how="diagonal_relaxed").unique()
    recovery_meta = {}
    transitions = None
    actor = int(leak[0]) if leak else new_origin
    if leak:
        # the parts hold every path carrying the (a, b) adjacency; the *leak* is the subset exported to a new upstream x,
        # i.e. paths reading "… x a b …" for the event's novel upstreams. Paths via a's old upstreams are the baseline
        # (they are what inflated t₀ backwards to the window start in the first merge). No upstreams → all (a, b) paths.
        a, sources, upstreams = int(leak[0]), leak[1], (leak[2] if len(leak) > 2 else "")
        xs = "|".join(str(int(x)) for x in str(upstreams or "").split("|") if x)
        bs = "|".join(str(int(b)) for b in str(sources).split("|") if b)
        pat = rf"(^| )({xs}) {a} ({bs})( |$)" if xs else rf"(^| ){a} ({bs})( |$)"
        anom = allp.filter(pl.col("as_path").str.contains(pat))
    elif tag == "recovery":
        if recovery_prev_origin is None:
            raise ValueError("recovery merge needs prev_origin from the recovery selection")
        from .recovery import return_wave
        anom, transitions, recovery_meta = return_wave(allp, new_origin, recovery_prev_origin, t0)
    else:
        anom = allp.filter(pl.col("origin_asn") == new_origin)
    anom = anom.with_columns(hops=pl.col("as_path").str.replace_all(r"[{}]", "").str.split(" ").list.eval(pl.element().cast(pl.UInt32, strict=False)))
    first_obs = anom["ts"].min() if anom.height else None
    onset = first_obs or t0
    mem = membership(anom, onset, [actor]) if anom.height else pl.DataFrame(schema={"collector": pl.String, "asn": pl.UInt32, "first_seen": pl.Datetime("us", "UTC"), "via_prefix": pl.String, "n_msgs": pl.UInt32, "delay_s": pl.Float64})
    curve_asn = growth_curve(mem, onset) if mem.height else pl.DataFrame()
    vp_first = (anom.group_by("collector", "peer_ip").agg(first=pl.col("ts").min())
                    .with_columns(rel_s=((pl.col("first") - pl.lit(onset)).dt.total_microseconds() / 1e6).floor().cast(pl.Int64)).sort("rel_s")) if anom.height else pl.DataFrame()
    curve_vp = vp_first.group_by("rel_s").agg(n=pl.len()).sort("rel_s").with_columns(N=pl.col("n").cum_sum()) if vp_first.height else pl.DataFrame()
    def at(secs: int) -> dict:
        lim = onset + dt.timedelta(seconds=secs)
        m = mem.filter(pl.col("first_seen") <= pl.lit(lim)) if mem.height else mem
        return {"asns_pooled": m["asn"].n_unique() if m.height else 0,
                "vp_sessions": vp_first.filter(pl.col("first") <= pl.lit(lim)).height if vp_first.height else 0,
                "per_collector_asns": m.group_by("collector").agg(pl.col("asn").n_unique().alias("n")).sort("collector").to_dicts() if m.height else []}
    summary = {
        "event_id": event_id, "kind": "leak" if leak else ("recovery" if tag == "recovery" else "origin"), "prefix": prefix, "new_origin": int(new_origin) if new_origin is not None else None,
        "leaker": int(leak[0]) if leak else None, "sources": leak[1] if leak else None, "upstreams": (leak[2] if leak and len(leak) > 2 else None), "t0": t0.isoformat(),
        "rows_with_adjacency": allp.height if leak else None,
        "leaked_prefixes": anom["prefix"].n_unique() if (leak and anom.height) else None,
        "collectors_with_parts": len({f.stem.split("__")[0] for f in files}), "expected_collectors": expected_collectors,
        "first_observation": first_obs.isoformat() if first_obs else None,
        "observation_lag_s": (first_obs - t0).total_seconds() if first_obs else None,
        "anomalous_msgs": anom.height, "collectors_seeing": sorted(anom["collector"].unique().to_list()) if anom.height else [],
        "sessions_carrying_prefix": allp.select("collector", "peer_ip").unique().height,
        "sessions_switched_to_new_origin": anom.select("collector", "peer_ip").unique().height if anom.height else 0,
        "extent": {k: at(v) for k, v in TARGETS_S.items()},
        "persistence_extent_asns": mem.filter(pl.col("first_seen") <= pl.lit(first_obs))["asn"].n_unique() if (mem.height and first_obs) else 0,
    }
    summary.update(recovery_meta)
    summary["measurement_onset"] = first_obs.isoformat() if first_obs else None
    window_end = t0 + dt.timedelta(hours=AFTER_H)
    summary["measurement_planned_window_end"] = window_end.isoformat()
    summary["measurement_followup_within_planned_window"] = bool(first_obs and first_obs + dt.timedelta(hours=2) <= window_end)
    if first_obs and not summary["measurement_followup_within_planned_window"]:
        summary["error"] = "insufficient follow-up after first observed announcement"
    if not anom.height:
        summary["error"] = ("no observed post-identifier hijack-to-legitimate announcement transition"
                            if tag == "recovery" else "no observed anomalous announcements")
    if transitions is not None:
        transitions.write_parquet(out_dir / "recovery_transitions.parquet", compression="zstd")
    vp_first.write_parquet(out_dir / "vp_first.parquet", compression="zstd")
    anom.drop("hops").write_parquet(out_dir / "anomalous.parquet", compression="zstd")
    mem.write_parquet(out_dir / "membership.parquet", compression="zstd")
    if curve_asn.height:
        curve_asn.write_csv(out_dir / "curve_asn.csv")
    if curve_vp.height:
        curve_vp.write_csv(out_dir / "curve_vp.csv")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    return summary


def _withdrawal_baselines(at: dt.datetime) -> tuple[list[Path], dict]:
    """Require the declared ten collectors' latest pre-event RIB within one week."""
    from .replay import PASS_COLLECTORS

    paths, selected, missing, stale = [], [], [], []
    for collector in PASS_COLLECTORS:
        candidates = []
        for file in (config.RIB_DIR / collector).glob("*.parquet"):
            timestamp = dt.datetime.strptime(file.stem, "%Y-%m-%dT%H%M").replace(tzinfo=dt.UTC)
            if timestamp <= at:
                candidates.append((timestamp, file))
        if not candidates:
            missing.append(collector)
            continue
        timestamp, file = max(candidates)
        age = (at - timestamp).total_seconds()
        selected.append({"collector": collector, "path": str(file), "timestamp": timestamp.isoformat(), "age_seconds": age})
        if age > 7 * 86400:
            stale.append(collector)
        paths.append(file)
    return paths, {"required_collectors": list(PASS_COLLECTORS), "maximum_age_seconds": 7 * 86400,
                   "selected": selected, "missing_collectors": missing, "stale_collectors": stale}


def merge_withdrawal(event_id: str, t0: dt.datetime, burst_end: dt.datetime | None, tag: str = "withdrawal",
                     parts_root_override: Path | None = None, merged_root_override: Path | None = None) -> dict:
    """Withdrawal wave: prefixes withdrawn by ≥ 3 peers in the burst; membership = ASes dropped from a VP's pre-event RIB
    path for those prefixes (path-loss membership, ADR-0012), first time per (collector, asn)."""
    parts_root, merged_root = roots(tag)
    parts_root = parts_root_override or parts_root
    merged_root = merged_root_override or merged_root
    parts_dir = parts_root / event_id; out_dir = merged_root / event_id; out_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(parts_dir.glob("*.parquet")) if parts_dir.exists() else []
    if not files:
        s = {"event_id": event_id, "kind": "withdrawal", "error": "no parts", "collectors_with_parts": 0}
        (out_dir / "summary.json").write_text(json.dumps(s)); return s
    rib_files, baseline = _withdrawal_baselines(t0)
    if baseline["missing_collectors"] or baseline["stale_collectors"]:
        error = "missing_required_weekly_rib" if baseline["missing_collectors"] else "stale_required_weekly_rib"
        summary = {"event_id": event_id, "kind": "withdrawal", "t0": t0.isoformat(),
                   "error": error, "collectors_with_parts": len(files), "withdrawal_baseline": baseline}
        (out_dir / "summary.json").write_text(json.dumps(summary, indent=1))
        return summary
    allp = pl.concat([pl.read_parquet(f) for f in files], how="diagonal_relaxed")
    burst_end = (burst_end or t0) + dt.timedelta(minutes=5)
    wrows = allp.filter((pl.col("elem_type") == "W") & (pl.col("ts") >= pl.lit(t0)) & (pl.col("ts") <= pl.lit(burst_end)))
    prefixes = wrows.group_by("prefix").agg(n=pl.col("peer_ip").n_unique()).filter(pl.col("n") >= 3)["prefix"].to_list()
    rib = (pl.concat([pl.scan_parquet(file).select("collector", "peer_ip", "prefix", "as_path") for file in rib_files])
           .filter(pl.col("prefix").is_in(prefixes)).rename({"as_path": "rib_path"}).collect(engine="streaming"))
    rib = rib.with_columns(pl.col("collector").cast(pl.String))
    upd = allp.filter(pl.col("prefix").is_in(prefixes) & (pl.col("ts") >= pl.lit(t0)))
    j = upd.join(rib, on=["collector", "peer_ip", "prefix"], how="inner")
    changed = j.filter((pl.col("elem_type") == "W") | (pl.col("as_path") != pl.col("rib_path")))
    first = changed.sort("ts").group_by("collector", "peer_ip", "prefix").agg(change_ts=pl.col("ts").first(), kind=pl.col("elem_type").first(),
                                                                              old_path=pl.col("rib_path").first(), new_path=pl.col("as_path").first())
    mem = (first.with_columns(old=pl.col("old_path").str.replace_all(r"[{}]", "").str.split(" ").list.eval(pl.element().cast(pl.UInt32, strict=False)),
                              new=pl.col("new_path").fill_null("").str.replace_all(r"[{}]", "").str.split(" ").list.eval(pl.element().cast(pl.UInt32, strict=False)))
                .with_columns(lost=pl.col("old").list.set_difference(pl.col("new"))).explode("lost").drop_nulls("lost")
                .group_by("collector", "lost").agg(first_seen=pl.col("change_ts").min(), via_prefix=pl.col("prefix").first(), n_msgs=pl.len().cast(pl.UInt32))
                .rename({"lost": "asn"}).with_columns(delay_s=(pl.col("first_seen") - pl.lit(t0)).dt.total_microseconds() / 1e6).sort("collector", "first_seen"))
    first_obs = wrows["ts"].min() if wrows.height else None
    onset = first_obs or t0
    vp_first = first.group_by("collector", "peer_ip").agg(first=pl.col("change_ts").min()) if first.height else pl.DataFrame(schema={"collector": pl.String, "peer_ip": pl.String, "first": pl.Datetime("us", "UTC")})
    def at(secs: int) -> dict:
        lim = onset + dt.timedelta(seconds=secs)
        m = mem.filter(pl.col("first_seen") <= pl.lit(lim)) if mem.height else mem
        return {"asns_pooled": m["asn"].n_unique() if m.height else 0, "vp_sessions": vp_first.filter(pl.col("first") <= pl.lit(lim)).height if vp_first.height else 0,
                "per_collector_asns": m.group_by("collector").agg(pl.col("asn").n_unique().alias("n")).sort("collector").to_dicts() if m.height else []}
    summary = {"event_id": event_id, "kind": "withdrawal", "prefix": None, "new_origin": None, "t0": t0.isoformat(), "burst_end": burst_end.isoformat(),
               "collectors_with_parts": len(files), "expected_collectors": 10, "first_observation": first_obs.isoformat() if first_obs else None,
               "observation_lag_s": (first_obs - t0).total_seconds() if first_obs else None, "anomalous_msgs": wrows.height,
               "collectors_seeing": sorted(wrows["collector"].unique().to_list()) if wrows.height else [], "wave_prefixes": len(prefixes),
               "rib_vp_prefix_rows": rib.height, "vp_prefix_changed": first.height, "withdrawal_baseline": baseline,
               "sessions_carrying_prefix": rib.select("collector", "peer_ip").unique().height, "sessions_switched_to_new_origin": vp_first.height,
               "extent": {k: at(v) for k, v in TARGETS_S.items()},
               "persistence_extent_asns": mem.filter(pl.col("first_seen") <= pl.lit(first_obs))["asn"].n_unique() if (mem.height and first_obs) else 0}
    wrows.write_parquet(out_dir / "anomalous.parquet", compression="zstd"); mem.write_parquet(out_dir / "membership.parquet", compression="zstd")
    first.write_parquet(out_dir / "vp_changes.parquet", compression="zstd")
    vp_first.write_parquet(out_dir / "vp_first.parquet", compression="zstd")
    if mem.height:
        growth_curve(mem, onset).write_csv(out_dir / "curve_asn.csv")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    return summary


def merge_all(manifest: Path | None = None, force: bool = False, tag: str = "") -> dict:
    man = load_manifest(manifest)
    _, merged_root = roots(tag)
    if tag == "recovery" and "prev_origin" not in man.columns:
        if manifest is None:
            raise ValueError("recovery requires an explicit manifest")
        selection = pl.read_parquet(manifest.parent / "recovery_replay_selection.parquet")
        origins = selection.select("event_id", "prev_origin").unique()
        if origins["event_id"].n_unique() != origins.height:
            raise ValueError("conflicting previous origins for a recovery event")
        man = man.join(origins, on="event_id", how="left", validate="m:1")
    n = err = skipped = 0
    for e in man.unique("event_id", maintain_order=True).iter_rows(named=True):
        out = merged_root / e["event_id"] / "summary.json"
        if out.exists() and not force:
            # A "no parts" stub is what a merge writes when it ran before the replay produced any part for the event (a driver
            # that continued past a failed replay did this for 2,592 events on 2026-09-15). It is not a result; re-merge it.
            try:
                stub = json.loads(out.read_text()).get("error") == "no parts"
            except Exception:
                stub = True
            if not stub:
                skipped += 1; continue
        if e["kind"] == "withdrawal":
            s = merge_withdrawal(e["event_id"], e["t0"], e.get("burst_end"), tag=tag)
        elif e["kind"] == "leak":
            s = merge_event(e["event_id"], None, None, e["t0"], tag=tag, leak=(int(e["a"]), e["sources"], e.get("upstreams") or ""))
        else:
            s = merge_event(e["event_id"], e["prefix"], int(e["new_origin"]), e["t0"], tag=tag,
                            recovery_prev_origin=int(e["prev_origin"]) if tag == "recovery" else None)
        n += 1; err += 1 if s.get("error") else 0
    return {"merged": n, "errors": err, "skipped_existing": skipped}
