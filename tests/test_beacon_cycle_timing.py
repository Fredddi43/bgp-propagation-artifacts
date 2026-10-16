"""Cycle delay belongs to the first received announcement and its own origin."""
import datetime as dt

import polars as pl

from bgbench.beacon_analysis import first_observation_per_cycle, per_vp_summary, per_vp_summary_by_feed


def observation(seconds,origin,kind="A"):
    base=dt.datetime(2024,6,10,tzinfo=dt.timezone.utc)
    return {"prefix":"192.0.2.0/24","kind":"beacon","setup":"test","collector":"rrc00",
            "peer_ip":"192.0.2.1","peer_asn":1,"slot_ts":base,"ts":base+dt.timedelta(seconds=seconds),
            "orig_ts":base+dt.timedelta(seconds=origin) if origin is not None else None,
            "sched_wd_ts":base+dt.timedelta(hours=2),"elem_type":kind,"delay_s":seconds-origin if origin is not None else None}


def test_first_announcement_never_combines_independent_minima():
    obs=pl.DataFrame([observation(10,0),observation(15,14),observation(7205,-14400),observation(7210,None,"W")])
    row=first_observation_per_cycle(obs).filter(pl.col("slot_ts")==observation(0,0)["slot_ts"]).row(0,named=True)
    assert row["a_delay_s"]==10
    assert row["first_a_ts"]-row["orig_ts"]==dt.timedelta(seconds=10)
    assert row["w_delay_s"]==10
    assert not row["first_a_origin_ambiguous"]


def test_ambiguous_first_origin_is_reported_and_excluded():
    rows=[observation(10,0),observation(10,1),observation(7210,None,"W")]
    cycles=first_observation_per_cycle(pl.DataFrame(rows))
    assert cycles["first_a_origin_ambiguous"].item()
    assert per_vp_summary(cycles).is_empty()
    assert per_vp_summary_by_feed(cycles.with_columns(full_feed=pl.lit(True))).is_empty()


def test_stale_previous_cycle_and_fresh_current_cycle_keep_separate_clocks():
    stale=observation(1240,0)
    fresh=observation(1260,1200)
    base=stale["slot_ts"]
    for row in (stale,fresh):
        row["kind"]="fast"
        row["slot_ts"]=base+dt.timedelta(minutes=20)
    cycles=first_observation_per_cycle(pl.DataFrame([stale,fresh]))
    assert cycles.height==2
    assert cycles["a_delay_s"].to_list()==[1240.,60.]
    assert cycles["slot_ts"].to_list()==[base,base+dt.timedelta(minutes=20)]
    assert per_vp_summary(cycles)["n_cycles"].item()==2


def test_unknown_origin_does_not_hide_known_origin_in_same_arrival_slot():
    cycles=first_observation_per_cycle(pl.DataFrame([observation(1,None),observation(2,0)]))
    assert cycles.height==2
    assert per_vp_summary(cycles)["a_delay_p50"].item()==2
