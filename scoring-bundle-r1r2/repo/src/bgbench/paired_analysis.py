"""Identity-safe recovery joins and uncertainty for links sharing replay events."""
from __future__ import annotations

import numpy as np
import polars as pl


def unique_payload(frame: pl.DataFrame, key: str = "event_id") -> pl.DataFrame:
    """Collapse identical payload copies, but refuse inconsistent measurements."""
    unique = frame.unique(maintain_order=True)
    if unique[key].n_unique() != unique.height:
        raise ValueError(f"Conflicting payloads for {key}; rebuild the event table")
    return unique


def pair_events(selection: pl.DataFrame, recovery: pl.DataFrame, hijack: pl.DataFrame) -> pl.DataFrame:
    """One row per intended link; one return may legitimately have several hijacks."""
    selection = selection.unique(maintain_order=True)
    if selection.select("event_id", "hijack_id").unique().height != selection.height:
        raise ValueError("Conflicting metadata for a hijack–recovery link")
    return selection.join(unique_payload(recovery), on="event_id", validate="m:1").join(
        unique_payload(hijack, "hijack_id"), on="hijack_id", validate="m:1"
    )


def link_components(pairs: pl.DataFrame) -> list[str]:
    """Connected events are one resampling unit, including repeated hijack IDs."""
    parents: dict[str, str] = {}

    def root(node: str) -> str:
        parents.setdefault(node, node)
        while parents[node] != node:
            parents[node] = parents[parents[node]]
            node = parents[node]
        return node

    for r, h in pairs.select("event_id", "hijack_id").iter_rows():
        parents[root(r)] = root(h)
    return [root(r) for r in pairs["event_id"]]


def clustered_mean_ci(values, groups, *, seed: int = 0, resamples: int = 1000):
    """Percentile CI for a link-weighted mean, resampling whole event components."""
    values = np.asarray(values, dtype=float)
    groups = np.asarray(groups)
    keep = np.isfinite(values)
    values, groups = values[keep], groups[keep]
    _, indices = np.unique(groups, return_inverse=True)
    n = int(indices.max()) + 1 if indices.size else 0
    if n < 20:
        return None
    totals = np.bincount(indices, weights=values, minlength=n)
    counts = np.bincount(indices, minlength=n)
    rng = np.random.default_rng(seed)
    draws = np.empty(resamples)
    for i in range(resamples):
        sampled = rng.integers(0, n, size=n)
        draws[i] = totals[sampled].sum() / counts[sampled].sum()
    return [round(float(x), 4) for x in np.percentile(draws, [2.5, 97.5])]


def add_pair_arguments(parser):
    from pathlib import Path
    parser.add_argument("--hijack-events", type=Path, help="explicit hijack measurement event table")
    parser.add_argument("--recovery-events", type=Path, help="explicit return measurement event table")
    parser.add_argument("--selection", type=Path, help="explicit selected-link table")
    parser.add_argument("--output-dir", type=Path, help="isolated directory for paired outputs")
    parser.add_argument("--require-matched-definition", action="store_true", help="refuse differently defined H/R memberships")
    parser.add_argument("--require-valid-hijack", action="store_true", help="retain only currently invalid origins displacing valid origins")


def read_pair_inputs(args, year):
    from . import config
    base = config.DATA_ROOT / "eventset"
    h = pl.read_parquet(args.hijack_events or base / str(year) / "events.parquet").filter(pl.col("error").is_null())
    r = pl.read_parquet(args.recovery_events or base / f"{year}_recovery" / "events.parquet").filter(pl.col("error").is_null())
    if args.require_matched_definition:
        def definition(frame):
            field = "measurement_definition" if "measurement_definition" in frame.columns else "recovery_definition"
            if field not in frame.columns or frame[field].null_count():
                raise ValueError("Missing explicit measurement definition")
            values = frame[field].unique().to_list()
            if len(values) != 1:
                raise ValueError("Mixed measurement definitions")
            return values[0]
        if definition(h) != definition(r):
            raise ValueError("Hijack and recovery measurement definitions differ")
    args._hijack_source, args._recovery_source = h, r
    output = args.output_dir or base / f"{year}_recovery"
    output.mkdir(parents=True, exist_ok=True)
    selection = args.selection or config.DATA_ROOT / "inventory" / str(year) / "recovery_replay_selection.parquet"
    return h, r, output, selection


def filter_hijack_population(frame, args, year, key="hijack_id"):
    from . import config
    base = config.DATA_ROOT / "eventset" / str(year)
    if args.require_valid_hijack:
        valid = pl.read_parquet(base / "rpki_validity.parquet").filter(
            (pl.col("validity") == "invalid") & (pl.col("prev_validity") == "valid")
        ).select(pl.col("event_id").alias(key))
        frame = frame.join(valid.unique(), on=key, how="semi")
    if args.only_reason or args.exclude_reason:
        reason = unique_payload(pl.read_parquet(base / "events.parquet").select(pl.col("event_id").alias(key), "reason"), key)
        frame = frame.join(reason, on=key, how="left", validate="m:1")
        if args.only_reason:
            frame = frame.filter(pl.col("reason") == args.only_reason)
        if args.exclude_reason:
            frame = frame.filter(pl.col("reason") != args.exclude_reason)
        frame = frame.drop("reason")
    args.chronology_exclusions = []
    if args.require_matched_definition:
        h = unique_payload(args._hijack_source.select(pl.col("event_id").alias(key), pl.col("t0_obs").alias("_h_onset")), key)
        r = unique_payload(args._recovery_source.select("event_id", pl.col("t0_obs").alias("_r_onset")))
        frame = frame.join(h, on=key, validate="m:1").join(r, on="event_id", validate="m:1")
        if frame["_h_onset"].null_count() or frame["_r_onset"].null_count():
            raise ValueError("Matched primary pairs require observed onsets")
        frame = frame.with_columns(_observed_gap_s=(
            pl.col("_r_onset").str.to_datetime(time_zone="UTC") - pl.col("_h_onset").str.to_datetime(time_zone="UTC")
        ).dt.total_microseconds() / 1e6)
        args.chronology_exclusions = frame.filter(pl.col("_observed_gap_s") < 0).select(
            "event_id", key, pl.col("_observed_gap_s").alias("observed_gap_s")
        ).to_dicts()
        frame = frame.filter(pl.col("_observed_gap_s") >= 0).drop("_h_onset", "_r_onset", "_observed_gap_s")
    return frame


def pair_cli_options(args):
    options = []
    for key in ("hijack_events", "recovery_events", "selection", "output_dir"):
        value = getattr(args, key, None)
        if value is not None:
            options += ["--" + key.replace("_", "-"), str(value)]
    for key in ("require_matched_definition", "require_valid_hijack"):
        if getattr(args, key, False):
            options.append("--" + key.replace("_", "-"))
    return options
