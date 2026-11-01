"""Event identifier v1 (ADR-0013): per-VP robust z-scores on per-minute signals + minimum-VP agreement.

Input: the per-collector per-minute aggregates written by `ingest-day` (AGG_DIR/<collector>/<date>.parquet).
Output: candidate windows (start, end, peak agreement, peak z, dominant signal), one row per candidate.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import polars as pl

from . import config

SIGNALS = ["n_ann", "n_wd", "n_prefixes", "n_origins", "n_paths"]


@dataclass
class IdentifierParams:
    window_min: int = 1440  # trailing window for median/MAD (24 h)
    z_thresh: float = 8.0  # robust z above which a collector-minute is "exceeding"
    min_vps: int = 3  # collectors that must exceed in the same minute
    merge_gap_min: int = 5  # merge candidate minutes closer than this
    min_duration_min: int = 1
    min_periods: int = 180  # need this many minutes of history before scoring
    log_transform: bool = True  # z on log1p(count): count signals are heavy-tailed, MAD≈0 otherwise
    min_consecutive: int = 2  # a collector must exceed for this many consecutive minutes
    signals: tuple[str, ...] = tuple(SIGNALS)  # which per-minute signals to score (sprint 3: ("n_wd",) for withdrawal waves)


def load_aggregates(collectors: list[str], start: str, end: str) -> pl.DataFrame:
    a, b = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    days = [(a + dt.timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]
    paths = [
        str(config.AGG_DIR / c / f"{d}.parquet")
        for c in collectors
        for d in days
        if (config.AGG_DIR / c / f"{d}.parquet").exists()
    ]
    if not paths:
        raise FileNotFoundError("no aggregate parquet for the requested collectors/days")
    # per-file read: aggregates written before 2026-09-05 carry a Categorical collector, side-table ones a String
    df = pl.concat([pl.read_parquet(f).with_columns(pl.col("collector").cast(pl.String)) for f in paths], how="diagonal_relaxed")
    # dense minute grid per collector (missing minutes → 0 activity, which is itself a signal)
    grid = (
        df.group_by("collector")
        .agg(lo=pl.col("minute").min(), hi=pl.col("minute").max())
        .with_columns(minute=pl.datetime_ranges("lo", "hi", interval="1m", time_zone="UTC"))
        .explode("minute")
        .select("collector", "minute")
    )
    df = (
        grid.join(df, on=["collector", "minute"], how="left")
        .fill_null(0)
        .sort("collector", "minute")
    )
    return df


def robust_z(df: pl.DataFrame, p: IdentifierParams) -> pl.DataFrame:
    """Per collector and signal: z = (x − rolling_median) / (1.4826·rolling_MAD + 1)."""

    def x(s):
        v = pl.col(s).cast(pl.Float64)
        return v.log1p() if p.log_transform else v

    exprs = []
    for s in p.signals:
        med = (
            x(s)
            .rolling_median(window_size=p.window_min, min_samples=p.min_periods)
            .over("collector")
        )
        exprs.append(med.alias(f"{s}_med"))
    df = df.with_columns(exprs)
    exprs = []
    for s in p.signals:
        dev = (x(s) - pl.col(f"{s}_med")).abs()
        mad = dev.rolling_median(window_size=p.window_min, min_samples=p.min_periods).over(
            "collector"
        )
        floor = (
            0.05 if p.log_transform else 1.0
        )  # MAD floor: 5 % in log space ≈ 5 % relative change
        exprs.append(((x(s) - pl.col(f"{s}_med")) / (1.4826 * mad + floor)).alias(f"{s}_z"))
    df = df.with_columns(exprs)
    return df.with_columns(
        z_max=pl.max_horizontal([pl.col(f"{s}_z") for s in p.signals]),
        z_signal=pl.concat_list([pl.col(f"{s}_z") for s in p.signals])
        .list.arg_max()
        .replace_strict({i: s for i, s in enumerate(p.signals)}, default="?"),
    )


def candidates(z: pl.DataFrame, p: IdentifierParams) -> pl.DataFrame:
    """Minutes where ≥ min_vps collectors exceed z_thresh, merged into windows."""
    z = z.sort("collector", "minute").with_columns(exc=(pl.col("z_max") > p.z_thresh).cast(pl.Int8))
    if p.min_consecutive > 1:
        # a collector-minute counts only if the previous (min_consecutive-1) minutes also exceeded
        z = z.with_columns(
            run=pl.col("exc")
            .rolling_sum(window_size=p.min_consecutive, min_samples=p.min_consecutive)
            .over("collector")
        )
        exceed = z.filter(pl.col("run") >= p.min_consecutive)
    else:
        exceed = z.filter(pl.col("exc") == 1)
    per_min = (
        exceed.group_by("minute")
        .agg(
            n_vps=pl.col("collector").n_unique(),
            peak_z=pl.col("z_max").max(),
            signal=pl.col("z_signal").mode().first(),
            collectors=pl.col("collector").unique().sort(),
        )
        .filter(pl.col("n_vps") >= p.min_vps)
        .sort("minute")
    )
    if per_min.is_empty():
        return per_min.with_columns(start=pl.col("minute"), end=pl.col("minute"))
    gap = (pl.col("minute") - pl.col("minute").shift(1)).dt.total_minutes().fill_null(10**9)
    per_min = per_min.with_columns(win=(gap > p.merge_gap_min).cast(pl.Int64).cum_sum())
    out = (
        per_min.group_by("win")
        .agg(
            start=pl.col("minute").min(),
            end=pl.col("minute").max() + pl.duration(minutes=1),
            minutes=pl.len(),
            peak_vps=pl.col("n_vps").max(),
            peak_z=pl.col("peak_z").max(),
            signal=pl.col("signal").mode().first(),
            collectors=pl.col("collectors").flatten().unique().sort(),
        )
        .with_columns(duration_min=(pl.col("end") - pl.col("start")).dt.total_minutes())
        .filter(pl.col("duration_min") >= p.min_duration_min)
        .sort("start")
        .drop("win")
    )
    return out


def run(
    collectors: list[str],
    start: str,
    end: str,
    p: IdentifierParams | None = None,
    out_dir: Path | None = None,
) -> dict:
    p = p or IdentifierParams()
    df = load_aggregates(collectors, start, end)
    z = robust_z(df, p)
    cand = candidates(z, p)
    tag = f"z{p.z_thresh:g}_m{p.min_vps}_c{p.min_consecutive}_{'log' if p.log_transform else 'raw'}" + ("" if tuple(p.signals) == tuple(SIGNALS) else "_" + "-".join(p.signals))
    out_dir = out_dir or (config.DATA_ROOT / "identifier" / f"{start}_{end}" / tag)
    out_dir.mkdir(parents=True, exist_ok=True)
    z.select("collector", "minute", *p.signals, "z_max", "z_signal").write_parquet(
        out_dir / "zscores.parquet", compression="zstd"
    )
    cand.with_columns(pl.col("collectors").list.join(",")).write_csv(out_dir / "candidates.csv")
    tot_min = int(cand["duration_min"].sum()) if cand.height else 0
    top_of_hour = int(cand.filter(pl.col("start").dt.minute() <= 1).height) if cand.height else 0
    return {
        "collectors": len(collectors),
        "minutes": df.height,
        "candidates": cand.height,
        "candidate_minutes": tot_min,
        "frac_time_in_candidate": round(tot_min / (df.height / len(collectors)), 4),
        "starting_at_top_of_hour": top_of_hour,
        "params": p.__dict__,
        "out": str(out_dir),
    }


def overlap_with_labels(
    cand: pl.DataFrame, labels: pl.DataFrame, ts_col: str, slack_min: int = 10
) -> dict:
    """Fraction of labelled events whose timestamp falls inside (or within slack of) a candidate window,
    and fraction of candidates that contain at least one labelled event."""
    if cand.is_empty() or labels.is_empty():
        return {
            "labels": labels.height,
            "candidates": cand.height,
            "labels_hit": 0,
            "candidates_with_label": 0,
        }
    lab = labels.select(pl.col(ts_col).alias("t")).drop_nulls()
    c = cand.select("start", "end").with_row_index("cid")
    j = lab.join(c, how="cross").filter(
        (pl.col("t") >= pl.col("start") - pl.duration(minutes=slack_min))
        & (pl.col("t") <= pl.col("end") + pl.duration(minutes=slack_min))
    )
    return {
        "labels": lab.height,
        "candidates": cand.height,
        "labels_hit": j["t"].n_unique(),
        "labels_hit_frac": round(j["t"].n_unique() / lab.height, 3),
        "candidates_with_label": j["cid"].n_unique(),
        "candidates_with_label_frac": round(j["cid"].n_unique() / cand.height, 3),
    }


def overlap_by_size(
    cand: pl.DataFrame,
    labels: pl.DataFrame,
    ts_col: str,
    size_col: str,
    buckets: tuple[int, ...] = (1, 10, 50, 200),
    slack_min: int = 10,
    n_random: int = 20,
    span: tuple[dt.datetime, dt.datetime] | None = None,
    seed: int = 0,
) -> pl.DataFrame:
    """Recall of labelled events by visibility bucket (size_col, e.g. Cloudflare peer_ip_count), for the
    real candidate windows and for `n_random` uniformly re-placed copies of the same windows (null model)."""
    import numpy as np

    lab = labels.select(
        pl.col(ts_col).alias("t"), pl.col(size_col).cast(pl.Float64, strict=False).alias("size")
    ).drop_nulls()
    edges = list(buckets) + [10**9]
    lab = lab.with_columns(
        bucket=pl.col("size").cut(
            breaks=edges[1:-1],
            labels=[
                f"{edges[i]}-{edges[i + 1] - 1}" if edges[i + 1] < 10**9 else f"{edges[i]}+"
                for i in range(len(edges) - 1)
            ],
        )
    )

    def hits(c: pl.DataFrame) -> pl.DataFrame:
        cw = c.select("start", "end").with_row_index("cid")
        j = (
            lab.with_row_index("lid")
            .join(cw, how="cross")
            .filter(
                (pl.col("t") >= pl.col("start") - pl.duration(minutes=slack_min))
                & (pl.col("t") <= pl.col("end") + pl.duration(minutes=slack_min))
            )
            .select("lid")
            .unique()
        )
        return lab.with_row_index("lid").with_columns(hit=pl.col("lid").is_in(j["lid"]))

    real = hits(cand).group_by("bucket").agg(n=pl.len(), recall=pl.col("hit").mean())
    if span is None:
        span = (lab["t"].min(), lab["t"].max())
    rng = np.random.default_rng(seed)
    total_s = (span[1] - span[0]).total_seconds()
    durs = (cand["end"] - cand["start"]).dt.total_seconds().to_numpy()
    rand_rows = []
    for _ in range(n_random):
        starts = [
            span[0] + dt.timedelta(seconds=float(x))
            for x in rng.uniform(0, total_s, size=len(durs))
        ]
        rc = pl.DataFrame({"start": starts}).with_columns(
            end=pl.col("start") + pl.duration(seconds=pl.Series(durs))
        )
        rand_rows.append(hits(rc).group_by("bucket").agg(recall=pl.col("hit").mean()))
    rand = pl.concat(rand_rows).group_by("bucket").agg(random_recall=pl.col("recall").mean())
    return real.join(rand, on="bucket", how="left").sort("bucket")
