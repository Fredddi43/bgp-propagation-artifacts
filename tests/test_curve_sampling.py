import datetime as dt

import polars as pl

from bgbench.curve_eventset import _series, event_series


def test_minute_boundary_does_not_include_future_seconds(tmp_path):
    file = tmp_path / "curve.csv"
    pl.DataFrame({"rel_s": [0, 1, 59, 60, 61], "N": [1, 2, 3, 4, 5]}).write_csv(file)
    assert _series(file, 2).tolist() == [1, 4, 5]


def test_count_series_uses_observed_onset_and_pooled_first_seen(tmp_path):
    onset = dt.datetime(2025, 1, 1, tzinfo=dt.UTC)
    pl.DataFrame({"asn": [1, 1, 2, 3], "first_seen": [onset, onset+dt.timedelta(seconds=10), onset+dt.timedelta(seconds=59), onset+dt.timedelta(seconds=61)]}).write_parquet(tmp_path / "membership.parquet")
    assert event_series(tmp_path, onset.isoformat(), horizon_min=2).tolist() == [1, 2, 3]


def test_followup_exclusion_keeps_exact_two_hour_boundary(tmp_path, monkeypatch):
    from scripts import exclude_incomplete_followup as correction
    from bgbench import config
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    folder=tmp_path/'eventset'/'2025_leak'
    folder.mkdir(parents=True)
    pl.DataFrame({'event_id':['boundary','short'], 'error':[None,None], 'observation_lag_s':[3600.,3600.1], 'set_final_2h':[[1],[2]], 'asns_final_2h':[1,1], 't90_s':[0.,0.], 'labelled':['a','b']}).write_parquet(folder/'events.parquet')
    captured=[]
    monkeypatch.setattr(correction,'run',lambda year,tag,table_override:captured.append(table_override))
    report=correction.exclude([2025],['leak'])
    assert report[0]['excluded_events']==['short']
    assert captured[0]['set_final_2h'].to_list()==[[1],None]
    assert captured[0]['labelled'].to_list()==['a','b']
