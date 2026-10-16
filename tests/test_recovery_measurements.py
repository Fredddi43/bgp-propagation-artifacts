import datetime as dt
import json

import polars as pl
import pytest

from bgbench import config
from bgbench.eventset import build_table
from bgbench.recovery import return_wave
from bgbench.replay_day import merge_event

T0 = dt.datetime(2025, 1, 1, 12, tzinfo=dt.UTC)


def announcements(spec):
    return pl.DataFrame([
        {"ts": T0 + dt.timedelta(seconds=seconds), "collector": "rrc00", "peer_ip": peer,
         "peer_asn": 10, "prefix": "192.0.2.0/24", "origin_asn": origin,
         "as_path": f"10 {extra} {origin}"}
        for seconds, peer, origin, extra in spec
    ])


def test_first_observed_return_run_excludes_history_and_later_cycles():
    rows = announcements([
        (-3500, "a", 100, 11), (-20, "a", 200, 12), (1, "a", 100, 13),
        (5, "a", 100, 14), (10, "a", 200, 15), (20, "a", 100, 16),
        (-20, "b", 100, 17), (2, "b", 100, 18),  # never observed hijack
        (-20, "c", 200, 19), (-1, "c", 100, 20), (3, "c", 100, 21),  # earlier return
        (-20, "d", 200, 22), (-10, "d", 300, 23), (4, "d", 100, 24), # third origin
    ])
    wave, transitions, meta = return_wave(rows, 100, 200, T0)
    assert wave["as_path"].to_list() == ["10 13 100", "10 14 100"]
    assert transitions.height == 1
    assert meta["recovery_sessions_without_observed_hijack"] == 1
    assert not meta["recovery_withdrawals_observed"]


def test_conflicting_timestamp_does_not_impose_an_origin_order():
    rows = announcements([(-10, "a", 200, 1), (1, "a", 200, 2),
                          (1, "a", 100, 3), (2, "a", 100, 4)])
    wave, _, meta = return_wave(rows, 100, 200, T0)
    assert wave.is_empty()
    assert meta["recovery_ambiguous_session_timestamps"] == 1


def test_merge_and_eventset_have_one_clock_and_unique_payloads(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    event_id = "return"
    parts = tmp_path / "events_replay_parts_recovery" / event_id
    parts.mkdir(parents=True)
    rows = announcements([(-3500, "a", 100, 11), (-20, "a", 200, 12),
                          (10, "a", 100, 13), (7205, "a", 100, 14),
                          (7211, "a", 100, 15)])
    rows.write_parquet(parts / "rrc00.parquet")
    summary = merge_event(event_id, "192.0.2.0/24", 100, T0, tag="recovery", recovery_prev_origin=200)
    assert summary["first_observation"] == (T0 + dt.timedelta(seconds=10)).isoformat()
    assert summary["extent"]["final_2h"]["asns_pooled"] == 4  # include t=7205, exclude7211
    sel = pl.DataFrame({"event_id": [event_id, event_id], "split": ["train", "test"], "first_ts": [T0, T0],
                       "reason": ["recovery"] * 2, "vis_bucket": ["1"] * 2,
                       "dur_bucket": ["5"] * 2, "flip_back": [False] * 2,
                       "labelled": [False] * 2, "max_collectors": [1] * 2,
                       "max_peers": [1] * 2, "duration_min": [5] * 2})
    inv = tmp_path / "inventory" / "2025"
    inv.mkdir(parents=True)
    sel.write_parquet(inv / "recovery_replay_selection.parquet")
    table = build_table(2025, "recovery")
    assert table.height == 1
    row = table.row(0, named=True)
    assert row["asns_final_2h"] == len(row["set_final_2h"]) == 4
    assert row["set_final_2h"] == [10, 13, 14, 100]
    assert row["t90_s"] == 7195
    assert row["vp_final_2h"] == 1
    assert build_table(2025, "recovery", event_ids={event_id}).equals(table)
    assert build_table(2025, "recovery", event_ids=set()).is_empty()
    with pytest.raises(ValueError, match="unselected event"):
        build_table(2025, "recovery", event_ids={"not_selected"})


def test_first_transition_paths_do_not_include_later_paths_or_bounces(tmp_path):
    from bgbench.recovery import first_return_paths, write_first_return_measurement
    rows = announcements([(0, "a", 100, 1), (10, "a", 100, 2), (20, "b", 100, 3)])
    changes = rows.rename({"origin_asn": "new_origin"}).with_columns(prev_origin=pl.lit(200, pl.UInt32))
    first = first_return_paths(changes, 100, 200, T0)
    assert sorted(first["as_path"].to_list()) == ["10 1 100", "10 3 100"]
    event = {"event_id": "return", "prefix": "192.0.2.0/24", "new_origin": 100,
             "prev_origin": 200, "first_ts": T0}
    s = write_first_return_measurement(event, changes, tmp_path, {"recovery_missing_source_files": 0})
    assert "error" not in s
    assert s["extent"]["final_2h"]["asns_pooled"] == 4
    assert s["recovery_sessions_confirmed_return"] == 2
    assert s["recovery_left_censored_at_midnight"] is True
    bad = write_first_return_measurement(event, changes, tmp_path, {"recovery_missing_source_files": 1})
    assert bad["error"] == "incomplete origin-change source coverage"


def test_no_return_has_no_invented_onset(tmp_path):
    from bgbench.recovery import write_first_return_measurement
    schema = announcements([(0, "a", 100, 1)]).rename({"origin_asn": "new_origin"}).with_columns(prev_origin=pl.lit(200, pl.UInt32)).clear()
    event = {"event_id": "return", "prefix": "192.0.2.0/24", "new_origin": 100,
             "prev_origin": 200, "first_ts": T0}
    s = write_first_return_measurement(event, schema, tmp_path, {"recovery_missing_source_files": 0})
    assert s["first_observation"] is None
    assert s["error"].startswith("no observed")


def test_primary_driver_builds_matched_hijack_and_recovery(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path
    script = Path(__file__).parents[1] / "scripts" / "rebuild_recovery_transitions.py"
    spec = importlib.util.spec_from_file_location("transition_driver", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "COLLECTORS", ["rrc00"])
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    metadata = {"split": "test", "reason": "stratified", "vis_bucket": "1", "dur_bucket": "5",
                "flip_back": False, "labelled": False, "max_collectors": 1, "max_peers": 1, "duration_min": 5}
    inv = tmp_path / "inventory" / "2025"
    inv.mkdir(parents=True)
    h = {**metadata, "event_id": "h", "prefix": "192.0.2.0/24", "new_origin": 200,
         "first_ts": T0 - dt.timedelta(seconds=20)}
    r = {**metadata, "event_id": "r", "prefix": "192.0.2.0/24", "new_origin": 100,
         "prev_origin": 200, "first_ts": T0, "hijack_id": "h", "reason": "recovery"}
    pl.DataFrame([h]).write_parquet(inv / "replay_selection.parquet")
    pl.DataFrame([r]).write_parquet(inv / "recovery_replay_selection.parquet")
    src = tmp_path / "source" / "rrc00"
    src.mkdir(parents=True)
    changes = announcements([(-20, "a", 200, 1), (0, "a", 100, 2)]).rename({"origin_asn": "new_origin"}).with_columns(prev_origin=pl.Series([100, 200], dtype=pl.UInt32), new_origin=pl.col("new_origin").cast(pl.UInt32))
    changes.write_parquet(src / "2025-01-01.origin_changes.parquet")
    module.rebuild(2025, src.parent, 1)
    for kind in ("hijack", "recovery"):
        table = pl.read_parquet(tmp_path / "eventset" / f"2025_{kind}_first_transition" / "events.parquet")
        assert table.height == 1
        assert table["measurement_definition"][0] == "first_post_identifier_origin_transition_paths_v1"
        assert table["asns_final_2h"][0] == len(table["set_final_2h"][0]) == 3
        assert table["error"][0] is None


def test_multiday_parts_preserve_both_days_without_double_counting(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    event_id = "midnight"
    parts = tmp_path / "events_replay_parts" / event_id
    parts.mkdir(parents=True)
    rows = announcements([(0, "a", 200, 11), (60, "a", 200, 12)])
    rows.head(1).write_parquet(parts / "rrc00__2025-01-01.parquet")
    rows.tail(1).write_parquet(parts / "rrc00__2025-01-02.parquet")
    rows.tail(1).write_parquet(parts / "rrc00.parquet")  # old overwritten survivor
    s = merge_event(event_id, "192.0.2.0/24", 200, T0)
    assert s["collectors_with_parts"] == 1
    assert s["anomalous_msgs"] == 2
    assert s["extent"]["final_2h"]["asns_pooled"] == 4
