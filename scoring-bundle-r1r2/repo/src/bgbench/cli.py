"""bgbench CLI. `bgbench ingest-day` is the unit of work for Snakemake / sbatch (collector × day)."""

from __future__ import annotations

import json
import os
import shutil
import time
import datetime as dt
from datetime import UTC
from pathlib import Path

import typer

from . import config
from .aggregate import minute_signals
from .broker import day_window, search
from .fetch import fetch_all
from .parse import parse_day
from .prefix_events import merge_side_tables, minute_counts, new_edges, new_triples, origin_changes

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command()
def ingest_day(
    collector: str,
    date: str,
    workers: int = typer.Option(32, help="parallel download streams"),
    procs: int = typer.Option(8, help="parser processes"),
    keep_raw: bool = typer.Option(False, help="do not delete raw MRT after parsing"),
    keep_parquet: bool = typer.Option(
        True, help="keep the hourly Parquet parts (False = aggregates-only pass, ADR-0011)"
    ),
    force: bool = typer.Option(False, help="re-run even if the manifest exists"),
):
    """Download one collector-day of updates into RAM, parse to hourly Parquet, write per-minute
    aggregates and a manifest (broker completeness check). Idempotent: skips if manifest exists."""
    manifest = config.MANIFEST_DIR / collector / f"{date}.json"
    if manifest.exists() and not force:
        typer.echo(f"[skip] {collector} {date}: manifest exists")
        return
    t0 = time.time()
    start, end = day_window(date)
    items = search(collector, start, end, "updates")
    expected = config.expected_update_files(collector)
    step = 1 if collector.startswith("pch.") else (5 if collector.startswith("rrc") else 15)
    have = {it.ts_start.strftime("%H%M") for it in items}
    grid = {f"{h:02d}{m:02d}" for h in range(24) for m in range(0, 60, step)}
    missing_slots = sorted(grid - have)
    typer.echo(
        f"[broker] {collector} {date}: {len(items)} files (expected {expected}); missing slots: {len(missing_slots)}"
    )

    keep_dir = config.PARQUET_DIR / collector / date
    if not keep_parquet and any(keep_dir.glob("part-*.parquet")):
        # guard: an aggregates-only run must never destroy Parquet that a previous *kept* run produced —
        # i.e. a manifest exists and says parquet_kept. Leftover parts from a cancelled attempt are not that.
        prev_kept = False
        if manifest.exists():
            try:
                prev_kept = bool(json.loads(manifest.read_text()).get("parquet_kept"))
            except Exception:  # noqa: BLE001
                prev_kept = False
        if prev_kept:
            typer.echo(f"[guard] {collector} {date}: Parquet exists from a kept run — keeping it")
            keep_parquet = True
        else:
            typer.echo(
                f"[guard] {collector} {date}: leftover Parquet from an unfinished attempt — will be replaced"
            )
            shutil.rmtree(keep_dir, ignore_errors=True)
    shm = config.shm_dir() / collector / date
    shm.mkdir(parents=True, exist_ok=True)
    # aggregates-only pass: the hourly Parquet is transient, so it lives in RAM too (ADR-0011). Writing it to the NFS
    # share and reading it back for the side tables made a 120-job pass ~3× slower per collector-day than an isolated run.
    out_dir = keep_dir if keep_parquet else shm / "pq"
    try:
        res = fetch_all(items, shm, workers=workers)
        ok = [r for r in res if r.path]
        failed = [r for r in res if not r.path]
        got = sum(r.size for r in ok)
        t1 = time.time()
        transient = [r for r in failed if r.error != "404"]
        if transient:
            # a missing file at the source (404) is recorded; anything else (timeouts, throttling, size mismatch)
            # is a transient failure and must fail the job so the workflow retries it instead of writing a manifest
            # with a silent gap (2024 pass: 872 collector-days had such gaps and needed a repair run)
            raise RuntimeError(f"{len(transient)} transient download failures, e.g. {transient[0].item.filename}: {transient[0].error}")
        typer.echo(
            f"[fetch] {len(ok)}/{len(res)} files, {got / 1e6:.1f} MB in {t1 - t0:.1f}s "
            f"({got / 1e6 / max(t1 - t0, 1e-9):.1f} MB/s); failed={len(failed)}"
        )

        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "_INCOMPLETE").touch()
        # in-worker extraction (#27): side tables per hour in RAM, merged below; BGBENCH_SIDE_TABLES=0 restores
        # the three streaming scans over the finished Parquet
        side_dir = shm / "side" if os.environ.get("BGBENCH_SIDE_TABLES", "1") != "0" else None
        # identifier v5 (prefix-level valley violations): default on since 2026-09-06 (validated on rrc03 2024-06-27,
        # +35 s per collector-day with the distinct-triple join); BGBENCH_VIOLATIONS=0 disables
        rel_path = None
        if side_dir is not None and os.environ.get("BGBENCH_VIOLATIONS", "1") == "1":
            from .leakcheck import rel_parquet
            rel_path = rel_parquet(date[:7].replace("-", ""))
        stats = parse_day(
            [r.path for r in ok], collector, out_dir, procs=procs, delete_raw=not keep_raw, side_dir=side_dir, rel_path=rel_path
        )
        (out_dir / "_INCOMPLETE").unlink(missing_ok=True)
        t2 = time.time()
        typer.echo(f"[parse] {stats['elems']:,} elems → {stats['parts']} parts in {t2 - t1:.1f}s "
                   f"(engine {stats.get('engine')}, workers {stats.get('rust_workers', procs)}+{stats.get('side_workers', '-')}, "
                   f"est {stats.get('per_hour_mb_est', '-')} MB/hour)")
        if stats["elems"] == 0:
            # archive gap (e.g. route-views.linx 2023-10-20..23: broker lists 0 files): record the day as empty and stop —
            # no aggregates / per-prefix tables to write, and downstream loaders skip missing files
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(json.dumps({"collector": collector, "date": date, "files_expected": expected, "files_listed": len(items),
                                            "files_ok": len(ok), "missing_slots": missing_slots, "elems": 0, "parts": 0, "empty": True,
                                            "engine": stats.get("engine"), "parquet_kept": False, "seconds": round(time.time() - t0, 1)}, indent=1))
            typer.echo(f"[done] {collector} {date}: no data in the archive → empty manifest")
            return

        vio = None
        if side_dir is not None and stats["elems"]:
            agg, oc, ne, nt = merge_side_tables(side_dir, collector)
            if rel_path is not None:
                from .prefix_events import merge_violations
                vio = merge_violations(side_dir, collector)
            shutil.rmtree(side_dir, ignore_errors=True)
        else:
            agg = minute_signals(out_dir)
            # per-prefix state signals (identifier v2): origin changes + first-seen AS edges, kept as compact tables
            oc = origin_changes(out_dir)
            ne = new_edges(out_dir)
            nt = new_triples(out_dir)   # identifier v4 (ADR-0018)
        pe_dir = config.DATA_ROOT / "prefix_events" / collector
        pe_dir.mkdir(parents=True, exist_ok=True)
        oc.write_parquet(pe_dir / f"{date}.origin_changes.parquet", compression="zstd")
        ne.write_parquet(pe_dir / f"{date}.new_edges.parquet", compression="zstd")
        nt.write_parquet(pe_dir / f"{date}.new_triples.parquet", compression="zstd")
        if vio is not None:
            vio.write_parquet(pe_dir / f"{date}.violations.parquet", compression="zstd")
        import polars as pl

        agg = (
            agg.with_columns(pl.col("collector").cast(pl.String))
            .join(
                minute_counts(oc, ne).with_columns(pl.col("collector").cast(pl.String)),
                on=["collector", "minute"],
                how="left",
            )
            .fill_null(0)
        )
        agg_path = config.AGG_DIR / collector / f"{date}.parquet"
        agg_path.parent.mkdir(parents=True, exist_ok=True)
        agg.write_parquet(agg_path, compression="zstd")
        t3 = time.time()
        typer.echo(
            f"[prefix-events] {oc.height:,} origin changes, {ne.height:,} first-seen edges in {t3 - t2:.1f}s"
        )
        parquet_bytes = sum(f.stat().st_size for f in out_dir.glob("part-*.parquet"))
        if not keep_parquet:
            shutil.rmtree(out_dir, ignore_errors=True)

        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            json.dumps(
                {
                    "collector": collector,
                    "date": date,
                    "broker_files": len(items),
                    "expected_files": expected,
                    "missing_slots": missing_slots,
                    "fetched": len(ok),
                    "failed": [{"file": r.item.filename, "error": r.error} for r in failed],
                    "bytes_raw": got,
                    "elems": stats["elems"],
                    "parts": stats["parts"],
                    "bytes_parquet": parquet_bytes,
                    "parquet_kept": keep_parquet,
                    "engine": stats.get("engine"),
                    "side_tables": side_dir is not None,
                    "violations": None if vio is None else vio.height,
                    "origin_changes": oc.height,
                    "new_edges_day": ne.height,
                    "per_hour": stats["per_hour"],
                    "seconds": {
                        "fetch": round(t1 - t0, 1),
                        "parse": round(t2 - t1, 1),
                        "total": round(time.time() - t0, 1),
                    },
                },
                indent=1,
            )
        )
        typer.echo(f"[done] {collector} {date} in {time.time() - t0:.0f}s → {manifest}")
    finally:
        config.release_shm(shm)


@app.command()
def beacons(
    start: str,
    end: str,
    collectors: str = typer.Option(
        "", help="comma-separated; default = every collector with parquet"
    ),
):
    """Week-1 slice: beacon propagation delays per VP from parsed UPDATE parquet (ADR-0016)."""
    from .beacon_analysis import run

    cols = [c for c in collectors.split(",") if c] or sorted(
        p.name for p in config.PARQUET_DIR.iterdir() if p.is_dir()
    )
    res = run(cols, start, end)
    typer.echo(json.dumps(res))


@app.command()
def beacon_visibility(start: str, end: str, collectors: str = typer.Option("")):
    """Beacon/anchor/RPKI-triple visibility per prefix over the window (ROV meter + collector-artefact control)."""
    from .beacon_analysis import visibility

    cols = [c for c in collectors.split(",") if c] or sorted(
        p.name for p in config.PARQUET_DIR.iterdir() if p.is_dir()
    )
    df = visibility(cols, start, end)
    out = config.BEACON_DIR / f"{start}_{end}" / "visibility.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.write_csv(out)
    typer.echo(df.write_csv())


@app.command()
def beacon_followups(
    week_dir: str = typer.Option("2024-06-10_2024-06-16"),
    rib_at: str = typer.Option("2024-06-12T12:00:00"),
    peer_stats_day: str = typer.Option("2024-06-15"),
):
    """#24: RIB-based anchor/RPKI visibility (ROV meter) + full-feed split of beacon delays."""
    from datetime import datetime

    import polars as pl

    from .beacon_analysis import full_feed_join, per_vp_summary_by_feed, rib_visibility, rov_meter

    out_dir = config.BEACON_DIR / week_dir
    vis = rib_visibility(datetime.fromisoformat(rib_at).replace(tzinfo=UTC))
    vis.write_csv(out_dir / "visibility_rib.csv")
    rov = rov_meter(vis)
    cyc = pl.read_parquet(out_dir / "cycles.parquet")
    cyc = full_feed_join(
        cyc, config.DATA_ROOT / "vp_selection" / peer_stats_day / "peer_stats.parquet"
    )
    byfeed = per_vp_summary_by_feed(cyc)
    byfeed.write_csv(out_dir / "per_feed_summary.csv")
    typer.echo(
        json.dumps(
            {
                "rib_visibility_rows": vis.height,
                "rov_meter": rov,
                "full_feed_sessions": int(
                    cyc.filter(pl.col("full_feed"))
                    .select(pl.struct("collector", "peer_ip").n_unique())
                    .item()
                ),
                "partial_sessions": int(
                    cyc.filter(~pl.col("full_feed"))
                    .select(pl.struct("collector", "peer_ip").n_unique())
                    .item()
                ),
                "by_feed": byfeed.to_dicts(),
            },
            indent=1,
            default=str,
        )
    )
    typer.echo(
        vis.filter(
            pl.col("kind").is_in(["anchor", "rpki_valid", "rpki_invalid", "longprefix"])
        ).write_csv()
    )


@app.command()
def ingest_window(
    collector: str,
    start: str,
    end: str,
    workers: int = typer.Option(32),
    procs: int = typer.Option(8),
    name: str = typer.Option(..., help="event name, e.g. cloudflare-2024-06-27"),
):
    """Event slice: ingest updates for one collector over an arbitrary UTC window
    (ISO timestamps, e.g. 2024-06-27T17:50:00 2024-06-27T21:55:00) into EVENT_DIR/<name>/<collector>/."""
    from datetime import datetime

    s = datetime.fromisoformat(start).replace(tzinfo=UTC)
    e = datetime.fromisoformat(end).replace(tzinfo=UTC)
    out_dir = config.EVENT_DIR / name / collector
    if (out_dir / "_manifest.json").exists():
        typer.echo(f"[skip] {name}/{collector}: manifest exists")
        return
    t0 = time.time()
    items = search(collector, s, e, "updates")
    shm = config.shm_dir() / name / collector
    shm.mkdir(parents=True, exist_ok=True)
    try:
        res = fetch_all(items, shm, workers=workers)
        ok = [r for r in res if r.path]
        stats = parse_day([r.path for r in ok], collector, out_dir, procs=procs)
        (out_dir / "_manifest.json").write_text(
            json.dumps(
                {
                    "name": name,
                    "collector": collector,
                    "start": start,
                    "end": end,
                    "broker_files": len(items),
                    "fetched": len(ok),
                    "failed": [
                        {"file": r.item.filename, "error": r.error} for r in res if not r.path
                    ],
                    "elems": stats["elems"],
                    "parts": stats["parts"],
                    "seconds": round(time.time() - t0, 1),
                },
                indent=1,
            )
        )
        typer.echo(
            f"[done] {name}/{collector}: {stats['elems']:,} elems from {len(ok)}/{len(items)} files in {time.time() - t0:.0f}s"
        )
    finally:
        config.release_shm(shm)


@app.command()
def extent(
    name: str,
    t0: str,
    prefixes: str,
    actors: str,
    collectors: str = typer.Option("", help="comma-separated; default = all ingested"),
):
    """Week-2 slice: announcement-wave membership + growth curve for an ingested event window (ADR-0012)."""
    from .extent import run

    res = run(
        name,
        t0,
        prefixes.split(","),
        [int(a) for a in actors.split(",")],
        [c for c in collectors.split(",") if c] or None,
    )
    typer.echo(json.dumps(res, indent=1, default=str))


@app.command()
def ingest_rib(
    collector: str,
    at: str = typer.Option(..., help="ISO UTC instant; the latest RIB at or before it is taken"),
):
    """Parse one RIB dump per collector (pre-event path state for ADR-0012 path-loss membership)."""
    from datetime import datetime

    from .ribs import ingest_rib as _ingest

    res = _ingest(collector, datetime.fromisoformat(at).replace(tzinfo=UTC))
    typer.echo(json.dumps(res, default=str))


@app.command()
def leak_extent(
    name: str,
    t0: str,
    leaker: int,
    collectors: str = typer.Option("", help="comma-separated; default = all ingested"),
):
    """Leak blast radius: discover every prefix that newly transits the leaker after t0 (vs the pre-event
    RIB), then membership + prefix-count growth curves (ADR-0012)."""
    from .extent import run_leak

    res = run_leak(name, t0, leaker, [c for c in collectors.split(",") if c] or None)
    typer.echo(json.dumps(res, indent=1, default=str))


@app.command()
def plot_growth(name: str, title: str = typer.Option("")):
    """Render the leak growth curves (prefixes, ASes) for an event to PNG under its _extent dir."""
    from .plots import growth_figure

    typer.echo(str(growth_figure(name, title or name)))


@app.command()
def identify(
    start: str,
    end: str,
    collectors: str = typer.Option(""),
    z: float = typer.Option(8.0),
    min_vps: int = typer.Option(3),
    window: int = typer.Option(1440),
    consecutive: int = typer.Option(2),
    raw: bool = typer.Option(False, help="z on raw counts instead of log1p"),
    labels_dir: str = typer.Option("", help="labels/<start>_<end> dir to compute overlap against"),
    signals: str = typer.Option("", help="comma-separated subset of n_ann,n_wd,n_prefixes,n_origins,n_paths (default all)"),
):
    """Event identifier v1 (ADR-0013) over the per-minute aggregates: robust z + min-VP agreement."""
    import polars as pl

    from .identifier import SIGNALS, IdentifierParams, overlap_with_labels, run

    cols = [c for c in collectors.split(",") if c] or sorted(
        p.name for p in config.AGG_DIR.iterdir() if p.is_dir()
    )
    res = run(
        cols,
        start,
        end,
        IdentifierParams(
            window_min=window,
            z_thresh=z,
            min_vps=min_vps,
            min_consecutive=consecutive,
            log_transform=not raw,
            signals=tuple(c for c in signals.split(",") if c) or tuple(SIGNALS),
        ),
    )
    if labels_dir:
        cand = pl.read_csv(Path(res["out"]) / "candidates.csv", try_parse_dates=True)
        ld = Path(labels_dir)
        ov = {}
        if (ld / "grip.parquet").exists():
            g = pl.read_parquet(ld / "grip.parquet")
            if g.height:
                ov["grip_all"] = overlap_with_labels(cand, g, "view_ts")
                hi = g.filter(pl.col("suspicion").cast(pl.Float64, strict=False) >= 80)
                ov["grip_susp80"] = overlap_with_labels(cand, hi, "view_ts")
        for kind, col, size in (
            ("hijacks", "min_hijack_ts", "peer_ip_count"),
            ("leaks", "min_ts", "peer_count"),
        ):
            f = ld / f"cloudflare_{kind}.parquet"
            if f.exists():
                d = pl.read_parquet(f)
                if d.height and col in d.columns:
                    d = d.with_columns(pl.col(col).str.to_datetime(time_zone="UTC", strict=False))
                    ov[f"cloudflare_{kind}"] = overlap_with_labels(cand, d, col)
                    if size in d.columns and cand.height:
                        import datetime as _dt

                        from .identifier import overlap_by_size

                        span = (
                            _dt.datetime.fromisoformat(start).replace(tzinfo=_dt.UTC),
                            _dt.datetime.fromisoformat(end).replace(tzinfo=_dt.UTC)
                            + _dt.timedelta(days=1),
                        )
                        ov[f"cloudflare_{kind}_by_size"] = overlap_by_size(
                            cand, d, col, size, span=span
                        ).to_dicts()
        res["label_overlap"] = ov
    typer.echo(json.dumps(res, indent=1, default=str))


@app.command()
def route_change(
    name: str,
    t0: str,
    prefixes: str = typer.Option(
        "", help="comma-separated; default = the event's discovered leaked prefixes"
    ),
    collectors: str = typer.Option(""),
):
    """ADR-0012 secondary metric + withdrawal wave: VP-peer route changes and path-loss membership vs the pre-event RIB."""
    from .extent import run_route_change

    pfx = [p for p in prefixes.split(",") if p]
    if not pfx:
        import polars as pl

        pfx = (
            pl.read_parquet(config.EVENT_DIR / name / "_extent" / "leaked_prefix_vp.parquet")[
                "prefix"
            ]
            .unique()
            .to_list()
        )
    res = run_route_change(name, t0, pfx, [c for c in collectors.split(",") if c] or None)
    typer.echo(json.dumps(res, indent=1, default=str))


@app.command()
def labels(
    start: str,
    end: str,
    min_susp: int = typer.Option(60, help="GRIP suspicion floor (server-side)"),
):
    """Fetch GRIP (epoch ts, day-chunked) + Cloudflare Radar hijack/leak events for [start, end) into DATA_ROOT/labels/."""
    from .labels import fetch_all_labels

    typer.echo(json.dumps(fetch_all_labels(start, end, min_susp=min_susp), indent=1, default=str))


@app.command()
def vp_select(day: str, k: int = typer.Option(10)):
    """ADR-0014: score collectors from BGPKit peer-stats and pick k by greedy marginal full-feed-ASN coverage."""
    from .vp_select import run

    typer.echo(json.dumps(run(day, k), indent=1, default=str))


@app.command()
def diffusion(
    name: str,
    t0: str,
    month: str = typer.Option(..., help="CAIDA as-rel month YYYYMM"),
    delta: int = typer.Option(300),
    rollouts: int = typer.Option(200),
    p_c2p: float = typer.Option(0.9),
    p_p2c: float = typer.Option(0.5),
    p_p2p: float = typer.Option(0.3),
    candidates: str = typer.Option("rib", help="rib | all"),
):
    """ADR-0007 rung 3: independent-cascade baseline seeded with the ASes seen by t0+delta; scored vs the 2 h set."""
    from .diffusion import ICParams, baseline_for_event

    res = baseline_for_event(
        name,
        t0,
        delta,
        month,
        ICParams(p_c2p=p_c2p, p_p2c=p_p2c, p_p2p=p_p2p, rollouts=rollouts),
        candidates=candidates,
    )
    typer.echo(json.dumps(res, indent=1, default=str))


@app.command()
def diffusion_calibrate(
    name: str,
    t0: str,
    month: str = typer.Option(...),
    delta: int = typer.Option(300),
    rollouts: int = typer.Option(30),
    candidates: str = typer.Option("rib", help="rib | all"),
):
    """Grid-search cascade edge probabilities on one event (Jaccard/AUPRC vs the 2 h set over the RIB candidate set)."""
    import polars as pl

    from .diffusion import calibrate

    df = calibrate(name, t0, delta, month, rollouts=rollouts, candidates=candidates)
    out = config.EVENT_DIR / name / "_extent" / f"cascade_calibration_delta{delta}.csv"
    out = (
        config.EVENT_DIR
        / name
        / "_extent"
        / f"cascade_calibration_delta{delta}_{candidates.replace(':', '')}.csv"
    )
    df.write_csv(out)
    pl.Config.set_tbl_rows(60)
    pl.Config.set_tbl_width_chars(220)
    typer.echo(
        str(
            df.select(
                "p_c2p",
                "p_p2c",
                "p_p2p",
                "expected_size",
                "candidates",
                "positives",
                "tp",
                "fp",
                "fn",
                "precision",
                "recall",
                "jaccard",
                "auprc",
            ).head(12)
        )
    )
    typer.echo(str(out))


@app.command()
def prefix_events_from_parquet(collector: str, date: str):
    """Backfill the per-prefix event tables (+ aggregate columns) for a collector-day whose hourly Parquet is kept."""
    out_dir = config.PARQUET_DIR / collector / date
    if not list(out_dir.glob("part-*.parquet")):
        typer.echo(f"[skip] no parquet for {collector} {date}")
        return
    import polars as pl

    pe_dir = config.DATA_ROOT / "prefix_events" / collector
    pe_dir.mkdir(parents=True, exist_ok=True)
    agg_path = config.AGG_DIR / collector / f"{date}.parquet"
    agg = pl.read_parquet(agg_path)
    if not (pe_dir / f"{date}.new_triples.parquet").exists():      # identifier v4 table for kept-Parquet days (beacon week)
        new_triples(out_dir).write_parquet(pe_dir / f"{date}.new_triples.parquet", compression="zstd")
        typer.echo(f"[triples] {collector} {date}: new_triples written")
    if not (pe_dir / f"{date}.violations.parquet").exists():       # identifier v5 table
        from .leakcheck import rel_parquet
        from .prefix_events import violations_from_parquet
        violations_from_parquet(out_dir, collector, rel_parquet(date[:7].replace("-", ""))).write_parquet(
            pe_dir / f"{date}.violations.parquet", compression="zstd")
        typer.echo(f"[violations] {collector} {date}: violations written")
    if (pe_dir / f"{date}.origin_changes.parquet").exists() and "n_new_edges" in agg.columns:
        typer.echo(f"[skip] {collector} {date}: prefix events + aggregate columns exist")
        return
    if (pe_dir / f"{date}.origin_changes.parquet").exists():
        oc = pl.read_parquet(pe_dir / f"{date}.origin_changes.parquet")
        ne = pl.read_parquet(pe_dir / f"{date}.new_edges.parquet")
    else:
        oc = origin_changes(out_dir)
        ne = new_edges(out_dir)
        oc.write_parquet(pe_dir / f"{date}.origin_changes.parquet", compression="zstd")
        ne.write_parquet(pe_dir / f"{date}.new_edges.parquet", compression="zstd")
    agg = agg.drop(
        [
            c
            for c in (
                "n_origin_change_pfx",
                "n_origin_change_peers",
                "n_new_origins",
                "n_new_edges",
            )
            if c in agg.columns
        ]
    )
    agg = (
        agg.with_columns(pl.col("collector").cast(pl.String))
        .join(
            minute_counts(oc, ne).with_columns(pl.col("collector").cast(pl.String)),
            on=["collector", "minute"],
            how="left",
        )
        .fill_null(0)
    )
    agg.write_parquet(agg_path, compression="zstd")
    typer.echo(
        f"[done] {collector} {date}: {oc.height:,} origin changes, {ne.height:,} first-seen edges"
    )


@app.command()
def identify2(
    start: str,
    end: str,
    collectors: str = typer.Option(""),
    min_collectors: int = typer.Option(2),
    bin_min: int = typer.Option(5),
    labels_dir: str = typer.Option(""),
):
    """Identifier v2: per-prefix origin-change and new-edge candidates with cross-collector agreement, evaluated per labelled event."""
    from .identifier2 import run

    cols = [c for c in collectors.split(",") if c] or sorted(
        p.name for p in (config.DATA_ROOT / "prefix_events").iterdir() if p.is_dir()
    )
    res = run(cols, start, end, Path(labels_dir) if labels_dir else None, min_collectors, bin_min)
    typer.echo(json.dumps(res, indent=1, default=str))


@app.command()
def identify2_events(
    start: str,
    end: str,
    collectors: str = typer.Option(""),
    min_collectors: int = typer.Option(2),
    bin_min: int = typer.Option(5),
    flapper_bins: int = typer.Option(20),
    labels_dir: str = typer.Option(""),
):
    """Identifier v2 event level: dedupe origin-change candidates into events, whitelist persistent flappers, evaluate."""
    from .identifier2 import run_events

    cols = [c for c in collectors.split(",") if c] or sorted(
        p.name for p in (config.DATA_ROOT / "prefix_events").iterdir() if p.is_dir()
    )
    res = run_events(
        cols,
        start,
        end,
        Path(labels_dir) if labels_dir else None,
        min_collectors,
        bin_min,
        flapper_bins,
    )
    typer.echo(json.dumps(res, indent=1, default=str))


@app.command()
def curve_baseline(name: str, no_chronos: bool = typer.Option(False)):
    """ADR-0007 rung 4: zero-shot Chronos-2 + naive baselines on the event's prefix growth curve (1-min bins)."""
    from .curve_baseline import run

    typer.echo(json.dumps(run(name, use_chronos=not no_chronos), indent=1))


@app.command()
def leakcheck(
    start: str,
    end: str,
    month: str = typer.Option(..., help="CAIDA as-rel month YYYYMM"),
    collectors: str = typer.Option(""),
    min_collectors: int = typer.Option(2),
    labels_dir: str = typer.Option(""),
):
    """Identifier v3 leak signal: classify first-seen edges (valley-free vs CAIDA) and evaluate vs Cloudflare leaks."""
    import polars as pl

    from .identifier2 import load_prefix_events, new_edge_candidates
    from .leakcheck import classify_new_edges, eval_leaks_v3

    cols = [c for c in collectors.split(",") if c] or sorted(
        p.name for p in (config.DATA_ROOT / "prefix_events").iterdir() if p.is_dir()
    )
    _, NE = load_prefix_events(cols, start, end)
    if "example_path" not in NE.columns:
        typer.echo("new_edges tables lack example_path (pre-2026-09-04 schema); backfill first")
        raise typer.Exit(1)
    cand = new_edge_candidates(NE, min_collectors, 5)
    # attach an example path per (a,b) from NE
    ex = NE.sort("first_ts").group_by("a", "b").agg(example_path=pl.col("example_path").first())
    cand = cand.join(ex, on=["a", "b"], how="left")
    cl = classify_new_edges(cand, month)
    out_dir = config.DATA_ROOT / "identifier2" / f"{start}_{end}" / f"leakcheck_m{min_collectors}"
    out_dir.mkdir(parents=True, exist_ok=True)
    cl.write_parquet(out_dir / "new_edges_classified.parquet")
    res = {
        "new_edge_candidates": cl.height,
        "edge_known": int(cl["edge_known"].sum()),
        "leak_like": int(cl["leak_like"].sum()),
        "by_kind": cl.group_by("learned_from", "exported_to")
        .len()
        .sort("len", descending=True)
        .head(12)
        .to_dicts(),
    }
    from .labels import load_cf_leaks
    leaks = load_cf_leaks(Path(labels_dir)) if labels_dir else None
    if leaks is None and labels_dir:
        res["leak_labels"] = "none in window (Cloudflare Radar leak events start in 2024)"
    if leaks is not None:
        res["leaks_all_edges"] = eval_leaks_v3(cl, leaks, require_leak_like=False)
        res["leaks_leaklike_or_unknown"] = eval_leaks_v3(cl, leaks, require_leak_like=True)
    typer.echo(json.dumps(res, indent=1, default=str))


@app.command()
def leakcheck4(
    start: str,
    end: str,
    month: str = typer.Option(..., help="CAIDA as-rel month YYYYMM"),
    collectors: str = typer.Option(""),
    min_collectors: int = typer.Option(2),
    labels_dir: str = typer.Option(""),
    null_shift_days: int = typer.Option(7, help="null model: candidates shifted by ±N days (0 = off)"),
):
    """Identifier v4 leak signal (ADR-0018): valley-free classification of first-seen path triples (x, a, b) and
    evaluation against Cloudflare leaks, with a shifted-time null model."""
    import polars as pl

    from .leakcheck import classify_triples, eval_leaks_v4, load_new_triples, triple_candidates

    cols = [c for c in collectors.split(",") if c] or sorted(
        p.name for p in (config.DATA_ROOT / "prefix_events").iterdir() if p.is_dir()
    )
    NT = load_new_triples(cols, start, end)
    if NT.is_empty():
        typer.echo("no new_triples tables in the window (re-pass with identifier v4 pending)")
        raise typer.Exit(1)
    days_loaded = NT.select(pl.col("first_ts").dt.date().n_unique()).item()
    cand = triple_candidates(NT, min_collectors, 5)
    cl = classify_triples(cand, month)
    out_dir = config.DATA_ROOT / "identifier2" / f"{start}_{end}" / f"leakcheck4_m{min_collectors}"
    out_dir.mkdir(parents=True, exist_ok=True)
    cl.write_parquet(out_dir / "new_triples_classified.parquet")
    res = {
        "collectors": len(cols), "days_with_triples": days_loaded, "triples_loaded": NT.height,
        "triple_candidates": cl.height,
        "both_known": int((cl["in_known"] & cl["out_known"]).sum()),
        "leak_like": int(cl["leak_like"].sum()),
        "by_kind": cl.group_by("learned_from", "exported_to").len().sort("len", descending=True).head(12).to_dicts(),
    }
    from .labels import load_cf_leaks
    leaks = load_cf_leaks(Path(labels_dir)) if labels_dir else None
    if leaks is None and labels_dir:
        res["leak_labels"] = "none in window (Cloudflare Radar leak events start in 2024)"
    if leaks is not None:
        leaks = leaks.filter((pl.col("min_ts") >= pl.lit(start).str.to_datetime(time_zone="UTC"))
                             & (pl.col("min_ts") < (pl.lit(end).str.to_datetime(time_zone="UTC") + pl.duration(days=1))))
        for mode in ("all", "leak_like", "leak_like_or_unknown"):
            res[f"leaks_{mode}"] = eval_leaks_v4(cl, leaks, mode=mode)
            if null_shift_days:
                sh = cl.with_columns(pl.col("first_ts") + pl.duration(days=null_shift_days))
                res[f"leaks_{mode}_null_shift"] = eval_leaks_v4(sh, leaks, mode=mode)
    (out_dir / "summary.json").write_text(json.dumps(res, indent=1, default=str))
    typer.echo(json.dumps(res, indent=1, default=str))


@app.command()
def leak_events(start: str, end: str, labels_dir: str = typer.Option(""), min_collectors: int = typer.Option(2), min_msgs: int = typer.Option(3),
                mode: str = typer.Option("leak_like", help="leak_like | leak_like_or_unknown")):
    """Sprint 3: leak events (leaker AS × merged 5-min bins) from the classified triples; matched to Cloudflare leaks by leaker ASN."""
    from .leak_events import run
    ld = Path(labels_dir) if labels_dir else config.DATA_ROOT / "labels" / f"{start[:4]}-01-01_{int(start[:4]) + 1}-01-01"
    typer.echo(json.dumps(run(start, end, ld, min_collectors, min_msgs, mode), indent=1, default=str))


@app.command()
def leakcheck5(
    start: str,
    end: str,
    collectors: str = typer.Option(""),
    min_collectors: int = typer.Option(2),
    min_prefixes: int = typer.Option(1),
    warmup_days: int = typer.Option(7, help="days at the start of the window that only seed the (triple, prefix) state"),
    labels_dir: str = typer.Option(""),
    null_shift_days: int = typer.Option(7),
):
    """Identifier v5 leak inventory: leaker events from newly violating (triple, prefix) pairs; evaluation vs Cloudflare leaks."""
    import polars as pl

    from .leakcheck import eval_leaks_v5, load_violations, violation_events

    cols = [c for c in collectors.split(",") if c] or sorted(p.name for p in (config.DATA_ROOT / "prefix_events").iterdir() if p.is_dir())
    V = load_violations(cols, start, end)
    if V.is_empty():
        typer.echo("no violations tables in the window (v5 re-pass pending)"); raise typer.Exit(1)
    ev = violation_events(V, min_collectors, min_prefixes, 5, warmup_days)
    out_dir = config.DATA_ROOT / "identifier2" / f"{start}_{end}" / f"leakcheck5_m{min_collectors}_p{min_prefixes}"
    out_dir.mkdir(parents=True, exist_ok=True)
    ev.write_parquet(out_dir / "violation_events.parquet")
    res = {"collectors": len(cols), "days_with_violations": V.select(pl.col("first_ts").dt.date().n_unique()).item(), "violation_rows": V.height,
           "events": ev.height, "events_per_day": round(ev.height / max(1, (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days + 1 - warmup_days), 1),
           "n_prefixes_p50_p90": [float(ev["n_prefixes"].quantile(q)) for q in (0.5, 0.9)] if ev.height else None,
           "events_ge_10_prefixes": int((ev["n_prefixes"] >= 10).sum()) if ev.height else 0}
    from .labels import load_cf_leaks
    lk = load_cf_leaks(Path(labels_dir)) if labels_dir else None
    if lk is None and labels_dir:
        res["leak_labels"] = "none in window (Cloudflare Radar leak events start in 2024)"
    if lk is not None:
        s0 = pl.lit(start).str.to_datetime(time_zone="UTC") + pl.duration(days=warmup_days); e0 = pl.lit(end).str.to_datetime(time_zone="UTC") + pl.duration(days=1)
        lk = lk.filter((pl.col("min_ts") >= s0) & (pl.col("min_ts") < e0))
        res["leaks"] = eval_leaks_v5(ev, lk)
        res["leaks_ge_10_prefixes"] = eval_leaks_v5(ev.filter(pl.col("n_prefixes") >= 10), lk) if ev.height else None
        if null_shift_days:
            res["leaks_null_shift"] = eval_leaks_v5(ev.with_columns(pl.col("t0") + pl.duration(days=null_shift_days)), lk)
    (out_dir / "summary.json").write_text(json.dumps(res, indent=1, default=str))
    typer.echo(json.dumps(res, indent=1, default=str))


@app.command()
def identify2_eval(start: str, end: str, labels_dir: str, min_collectors: int = typer.Option(2), flapper_bins: int = typer.Option(50)):
    """Re-score saved identifier v2 events against labels restricted to the window (fast; no recomputation)."""
    from .identifier2 import evaluate_saved_events
    typer.echo(json.dumps(evaluate_saved_events(start, end, Path(labels_dir), min_collectors, 5, flapper_bins), indent=1, default=str))


@app.command()
def rank_events(year: int = typer.Option(2024), labels_dir: str = typer.Option("")):
    """Sprint-2 step 3: rank the year's identifier-v2 events (visibility, duration, flip-back, label match)."""
    from .ranking import run
    ld = Path(labels_dir) if labels_dir else config.DATA_ROOT / "labels" / f"{year}-01-01_{year + 1}-01-01"
    typer.echo(json.dumps(run(year, ld), indent=1, default=str))


@app.command()
def select_replay(year: int = typer.Option(2024), per_cell: int = typer.Option(110), label_peers: int = typer.Option(10)):
    """ADR-0017: stratified replay selection (3×3×2 cells) + all events matching a Cloudflare hijack at ≥ label_peers peers."""
    from .select_replay import run
    typer.echo(json.dumps(run(year, per_cell, label_peers), indent=1, default=str))


@app.command()
def replay(event_id: str, prefix: str, new_origin: int, t0: str, workers: int = typer.Option(16), procs: int = typer.Option(4)):
    """Replay one selected event: window ingest on the pass collectors → announcement-wave labels + curves (ADR-0012/0017)."""
    from datetime import datetime, timezone
    from .replay import replay_event
    res = replay_event(event_id, prefix, new_origin, datetime.fromisoformat(t0).replace(tzinfo=timezone.utc), workers=workers, procs=procs)
    typer.echo(json.dumps({k: res.get(k) for k in ("event_id", "observation_lag_s", "anomalous_msgs", "sessions_switched_to_new_origin", "sessions_carrying_prefix", "error")}, default=str))


@app.command()
def replay_manifest(year: int = typer.Option(2024)):
    """Write workflow/config/replay-<year>.tsv (event_id, prefix, new_origin, t0) from the replay selection."""
    import polars as pl
    sel = pl.read_parquet(config.DATA_ROOT / "inventory" / str(year) / "replay_selection.parquet")
    out = config.DATA_ROOT / "inventory" / str(year) / "replay_manifest.tsv"
    sel.select("event_id", "prefix", pl.col("new_origin").cast(pl.Int64), pl.col("first_ts").dt.strftime("%Y-%m-%dT%H:%M:%S").alias("t0"), "split", "reason").write_csv(out, separator="\t")
    typer.echo(f"{sel.height} events → {out}")


@app.command()
def eventset_vp(year: int = typer.Option(2024), tag: str = typer.Option("")):
    """ADR-0008 §2/§6: persistence floor per collector (not pooled) and by event duration (ephemeral vs persistent)."""
    from .eventset import per_vp_and_duration
    typer.echo(json.dumps(per_vp_and_duration(year, tag), indent=1, default=str))


@app.command()
def eventset(year: int = typer.Option(2024), tag: str = typer.Option("", help="replay set: '' (origin-change) or 'leak'")):
    """Assemble replayed events into eventset/<year>[_<tag>]/events.parquet and score the persistence baseline per split."""
    from .eventset import run
    typer.echo(json.dumps(run(year, tag), indent=1, default=str))


@app.command()
def baselines_eventset(year: int = typer.Option(2024), sample: int = typer.Option(300), delta: str = typer.Option("d5m"),
                       coaffection: bool = typer.Option(False, help="#21: per-edge probabilities fitted on train-split co-affection"),
                       alpha: float = typer.Option(5.0, help="shrinkage weight towards the type prior"),
                       tag: str = typer.Option("", help="replay set ('' origin-change, 'leak')"), min_asns: int = typer.Option(0, help="restrict to events with ≥ this many ASes at 2 h"),
                       rec: float = typer.Option(1.0, help="SIR variant: per-step recovery probability (1.0 = independent cascade)"),
                       valley_free: bool = typer.Option(False, "--valley-free", help="Gao–Rexford export constraint on cascade edges (type prior only)")):
    """Cascade vs persistence on a sample of growing test-split events (seeds at Δ, target at 2 h)."""
    from .baselines_eventset import run
    typer.echo(json.dumps(run(year, sample, delta, coaffection=coaffection, alpha=alpha, set_tag=tag, min_asns=min_asns, rec=rec, valley_free=valley_free), indent=1, default=str))


@app.command()
def curve_eventset(year: int = typer.Option(2024), sample: int = typer.Option(200), no_chronos: bool = typer.Option(False),
                   tag: str = typer.Option(""), min_asns: int = typer.Option(0), curve: str = typer.Option("asn", help="asn (affected-AS count) or vp (VP sessions)")):
    """Magnitude-curve baselines (persistence / linear / logistic / Chronos-2) on sampled growing test events."""
    from .curve_eventset import run
    typer.echo(json.dumps(run(year, sample, use_chronos=not no_chronos, set_tag=tag, min_asns=min_asns, curve=curve), indent=1))


@app.command()
def extract_day(collector: str, date: str, workers: int = typer.Option(32), procs: int = typer.Option(8),
                manifest: str = typer.Option("", help="replay manifest TSV (default: the ADR-0017 origin-change set)"),
                tag: str = typer.Option("", help="replay set tag → events_replay_parts_<tag> (e.g. leak)")):
    """Replay by collector-day: parse the day once, write per-event window parts (prefix for origin events, leaked adjacency for leak events)."""
    from .replay_day import extract_day as _x
    typer.echo(json.dumps(_x(collector, date, Path(manifest) if manifest else None, workers=workers, procs=procs, tag=tag), default=str))


@app.command()
def merge_events(force: bool = typer.Option(False), manifest: str = typer.Option(""), tag: str = typer.Option("")):
    """Merge per-collector parts into per-event labels/curves/summary for every event in the replay manifest."""
    from .replay_day import merge_all
    typer.echo(json.dumps(merge_all(Path(manifest) if manifest else None, force=force, tag=tag)))


@app.command()
def select_withdrawal_replay(year: int = typer.Option(2024), run_tag: str = typer.Option("z8_m3_c2_log_n_wd")):
    """Sprint 3: withdrawal-wave replay set = all identifier-v1 n_wd candidates; writes the withdrawal replay manifest."""
    from .select_withdrawal_replay import run
    typer.echo(json.dumps(run(year, run_tag), indent=1, default=str))


@app.command()
def select_leak_replay(year: int = typer.Option(2024), top_k: int = typer.Option(400), label_collectors: int = typer.Option(3), min_collectors: int = typer.Option(3)):
    """Sprint 3: slow-regime replay set = labelled leak events at ≥ label_collectors + top_k by collectors × log msgs; writes the leak replay manifest."""
    from .select_leak_replay import run
    typer.echo(json.dumps(run(year, top_k, label_collectors, min_collectors), indent=1, default=str))


@app.command()
def tgn_build(year: int = typer.Option(2024), delta: int = typer.Option(30), max_events: int = typer.Option(0), max_nodes: int = typer.Option(3000), tag: str = typer.Option("")):
    """ADR-0018: build per-event graph tensors (2-hop universe, features, labels at 2 h, message stream) for the growing subset."""
    from .tgn_data import build_split
    typer.echo(json.dumps(build_split(year, delta, max_events or None, max_nodes, tag), indent=1, default=str))


@app.command()
def robustness(year: int = typer.Option(2024), delta: int = typer.Option(30), tag: str = typer.Option(""), prefix: str = typer.Option("sage")):
    """ADR-0008 §5: message dropout / fake-seed injection / hidden visibility on the saved model vs persistence."""
    from .robustness import run
    typer.echo(json.dumps(run(year, delta, tag, prefix), indent=1, default=str))


@app.command()
def cross_eval(model_year: int = typer.Option(2024), model_tag: str = typer.Option("leak200"), eval_year: int = typer.Option(2024),
               eval_tag: str = typer.Option("withdrawal"), delta: int = typer.Option(30), prefix: str = typer.Option("sage")):
    """ADR-0008 §4: a saved model of one family evaluated on another family's events (e.g. large-leak model on withdrawal waves)."""
    from .robustness import cross_eval as _ce
    typer.echo(json.dumps(_ce(model_year, model_tag, eval_year, eval_tag, delta, prefix), indent=1, default=str))


@app.command()
def dyrep_train(year: str = typer.Option("2024"), delta: int = typer.Option(30), epochs: int = typer.Option(20), hid: int = typer.Option(64), mem: int = typer.Option(64), tag: str = typer.Option("")):
    """Rung 6 alternative: DyRep-style embedding updates over the Δ message stream + rung-5 readout (TGN vs DyRep)."""
    from .dyrep_train import train
    typer.echo(json.dumps(train(year, delta, epochs, hid, mem, tag=tag), indent=1, default=str))


@app.command()
def gat_train(year: str = typer.Option("2024"), delta: int = typer.Option(30), epochs: int = typer.Option(20), hid: int = typer.Option(64), tag: str = typer.Option("")):
    """Rung 5 reference: GAT (the architecture family of published BGP-GNN detectors) on the same tensors and heads."""
    from .gat_train import train
    typer.echo(json.dumps(train(year, delta, epochs, hid, tag=tag), indent=1, default=str))


@app.command()
def hist_avg(year: str = typer.Option("2024"), delta: int = typer.Option(30), tag: str = typer.Option(""), k: int = typer.Option(20)):
    """ADR-0007 rung 2: historical-average propagation (k nearest onset signatures in the training events)."""
    from .hist_avg import run
    typer.echo(json.dumps(run(year, delta, tag, k), indent=1, default=str))


@app.command()
def gnn_train(year: str = typer.Option("2024", help="year, 'y1,y2,y3' (pooled within-year splits) or 'y1,y2>y3' (cross-year)"), delta: int = typer.Option(30), epochs: int = typer.Option(20), hid: int = typer.Option(64), tag: str = typer.Option(""),
              focal_gamma: float = typer.Option(0.0), curve_weight: float = typer.Option(1.0),
              rank_weight: float = typer.Option(0.0, help="pairwise ranking loss on affection order"), curve_head: str = typer.Option("quantile", help="quantile | logistic"),
              separate_encoders: bool = typer.Option(False, help="second graph encoder for the curve head")):
    """ADR-0007 rung 5 / ADR-0018: static GraphSAGE on per-event 2-hop graphs vs persistence (train Jan–Aug, test Sep–Dec)."""
    from .gnn_train import train
    typer.echo(json.dumps(train(year, delta, epochs, hid, tag=tag, focal_gamma=focal_gamma, curve_weight=curve_weight, rank_weight=rank_weight, curve_head=curve_head, separate_encoders=separate_encoders), indent=1, default=str))


@app.command()
def tgn_train(year: str = typer.Option("2024", help="year, 'y1,y2,y3' or 'y1,y2>y3'"), delta: int = typer.Option(30), epochs: int = typer.Option(20), hid: int = typer.Option(64), mem: int = typer.Option(64), tag: str = typer.Option(""),
              focal_gamma: float = typer.Option(0.0), curve_weight: float = typer.Option(1.0)):
    """ADR-0007 rung 6: TGN memory over the Δ message stream + GraphSAGE on the 2-hop universe vs persistence (same tensors/split as gnn-train)."""
    from .tgn_train import train
    typer.echo(json.dumps(train(year, delta, epochs, hid, mem, tag=tag, focal_gamma=focal_gamma, curve_weight=curve_weight), indent=1, default=str))


@app.command()
def broker_list(collector: str, date: str, data_type: str = "updates"):
    """Print the broker's file list for a collector-day (debug / completeness check)."""
    start, end = day_window(date)
    for it in search(collector, start, end, data_type):
        typer.echo(f"{it.ts_start:%Y-%m-%d %H:%M} {it.exact_size or it.rough_size:>12} {it.url}")


if __name__ == "__main__":
    app()
