"""Observable return waves in retained announcement histories.

These are announcement transitions at collector sessions, not reconstructed RIB
states: legacy replay parts do not retain withdrawals. A session without an
observed preceding hijack announcement is censored, never assumed to recover.
"""
from __future__ import annotations

import datetime as dt

import polars as pl

KEYS = ["collector", "peer_ip", "prefix"]
DEFINITION = "first_post_identifier_bad_to_good_announcement_run_v1"


def return_wave(rows: pl.DataFrame, legitimate: int, hijacker: int,
                identified_at: dt.datetime) -> tuple[pl.DataFrame, pl.DataFrame, dict]:
    """Retain each session's first qualifying legitimate announcement run.

The run must begin at/after the return identifier, immediately following a
hijacker-origin announcement in the retained history. Later returns after a
second hijack are separate episodes and excluded. Conflicting origins at the
same timestamp reset the observed state rather than imposing an arbitrary order.
All paths announced within the first return run contribute path membership;
this does not assert that every AS along those paths switched its own route.
"""
    if legitimate == hijacker:
        raise ValueError("recovery requires distinct legitimate and hijacking origins")
    rows = rows.unique().sort(*KEYS, "ts")
    states = (rows.group_by(*KEYS, "ts")
              .agg(n_origins=pl.col("origin_asn").n_unique(), origin=pl.col("origin_asn").first())
              .with_columns(origin=pl.when(pl.col("n_origins") == 1).then(pl.col("origin")).otherwise(None))
              .sort(*KEYS, "ts")
              .with_columns(previous=pl.col("origin").shift().over(KEYS)))
    states = states.with_columns(
        new_run=(pl.col("origin").ne_missing(pl.col("previous"))).cast(pl.UInt32),
        transition=(
            (pl.col("origin") == legitimate) & (pl.col("previous") == hijacker)
            & (pl.col("ts") >= pl.lit(identified_at))
        ).fill_null(False),
    ).with_columns(run=pl.col("new_run").cum_sum().over(KEYS))
    transitions = (states.filter(pl.col("transition")).group_by(KEYS)
                   .agg(first_return=pl.col("ts").min(), return_run=pl.col("run").first()))
    qualified = (states.join(transitions, on=KEYS, how="inner", validate="m:1")
                 .filter(pl.col("run") == pl.col("return_run")).select(*KEYS, "ts"))
    wave = rows.join(qualified, on=[*KEYS, "ts"], how="semi")
    sessions = rows.select(KEYS).unique().height
    bad_sessions = rows.filter(pl.col("origin_asn") == hijacker).select(KEYS).unique().height
    metadata = {
        "recovery_definition": DEFINITION,
        "recovery_prev_origin": int(hijacker),
        "recovery_sessions_observed": sessions,
        "recovery_sessions_with_hijack_announcement": bad_sessions,
        "recovery_sessions_confirmed_return": transitions.height,
        "recovery_sessions_without_observed_hijack": sessions - bad_sessions,
        "recovery_ambiguous_session_timestamps": states.filter(pl.col("n_origins") != 1).height,
        "recovery_history_start": rows["ts"].min().isoformat() if rows.height else None,
        "recovery_history_end": rows["ts"].max().isoformat() if rows.height else None,
        "recovery_withdrawals_observed": False,
    }
    return wave, transitions, metadata


def first_return_paths(changes: pl.DataFrame, legitimate: int, hijacker: int,
                       identified_at: dt.datetime) -> pl.DataFrame:
    """First recorded bad-to-good transition path per session, no later updates.

The ingestion side tables retain MRT announcement order, including same-second
changes, and explicitly store the previously observed origin within the day.
Their midnight reset is a left-censoring limitation, not a missing-file repair.
"""
    good = changes.filter(
        (pl.col("new_origin") == legitimate) & (pl.col("prev_origin") == hijacker)
        & (pl.col("ts") >= pl.lit(identified_at))
    )
    # The first timestamp can have multiple paths at coarse timestamp precision.
    # Keep every tied first transition path rather than inventing a new ordering.
    firsts = good.group_by(KEYS).agg(first_return=pl.col("ts").min())
    return (good.join(firsts, on=KEYS, validate="m:1")
            .filter(pl.col("ts") == pl.col("first_return"))
            .drop("first_return").unique())


def write_first_return_measurement(event: dict, changes: pl.DataFrame, output, coverage: dict) -> dict:
    """Write the standard event payload for the explicitly conditional target."""
    import json
    from .extent import TARGETS_S, growth_curve, membership

    output.mkdir(parents=True, exist_ok=True)
    t0 = event["first_ts"]
    wave = first_return_paths(changes, int(event["new_origin"]), int(event["prev_origin"]), t0)
    wave = wave.rename({"new_origin": "origin_asn"})
    first_obs = wave["ts"].min() if wave.height else None
    onset = first_obs or t0
    anom = wave.with_columns(hops=pl.col("as_path").str.replace_all(r"[{}]", "").str.split(" ")
                            .list.eval(pl.element().cast(pl.UInt32, strict=False)))
    mem = membership(anom, onset, [int(event["new_origin"])])
    vp = wave.group_by("collector", "peer_ip").agg(first=pl.col("ts").min())
    window_end = t0 + dt.timedelta(hours=3)
    def extent(seconds):
        at = onset + dt.timedelta(seconds=seconds)
        subset = mem.filter(pl.col("first_seen") <= pl.lit(at))
        return {"asns_pooled": subset["asn"].n_unique(),
                "vp_sessions": vp.filter(pl.col("first") <= pl.lit(at)).height,
                "per_collector_asns": subset.group_by("collector").agg(pl.col("asn").n_unique().alias("n")).to_dicts()}
    summary = {
        "event_id": event["event_id"], "kind": event.get("kind", "recovery"), "prefix": event["prefix"],
        "new_origin": int(event["new_origin"]), "t0": t0.isoformat(),
        "first_observation": first_obs.isoformat() if first_obs else None,
        "measurement_onset": first_obs.isoformat() if first_obs else None,
        "observation_lag_s": (first_obs - t0).total_seconds() if first_obs else None,
        "anomalous_msgs": wave.height,
        "collectors_seeing": sorted(wave["collector"].unique().to_list()),
        "sessions_carrying_prefix": None, "sessions_switched_to_new_origin": vp.height,
        "extent": {key: extent(seconds) for key, seconds in TARGETS_S.items()},
        "recovery_definition": "first_post_identifier_bad_to_good_transition_paths_v1",
        "measurement_definition": "first_post_identifier_origin_transition_paths_v1",
        "recovery_prev_origin": int(event["prev_origin"]),
        "recovery_sessions_confirmed_return": vp.height,
        "recovery_left_censored_at_midnight": True,
        "recovery_withdrawals_observed": False,
        "recovery_observation_window_end": window_end.isoformat(),
        **coverage,
    }
    if coverage.get("recovery_missing_source_files", 0):
        summary["error"] = "incomplete origin-change source coverage"
    elif first_obs is None:
        summary["error"] = "no observed post-identifier hijack-to-legitimate announcement transition"
    elif onset + dt.timedelta(hours=2) > window_end:
        summary["error"] = "insufficient follow-up after first observed return"
    wave.write_parquet(output / "anomalous.parquet", compression="zstd")
    mem.write_parquet(output / "membership.parquet", compression="zstd")
    vp.write_parquet(output / "vp_first.parquet", compression="zstd")
    wave.write_parquet(output / "recovery_transitions.parquet", compression="zstd")
    if mem.height:
        growth_curve(mem, onset).write_csv(output / "curve_asn.csv")
    (output / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    return summary
