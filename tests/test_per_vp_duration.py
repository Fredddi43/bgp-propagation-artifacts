import datetime as dt
import polars as pl
import pytest
from bgbench import config
from bgbench.eventset import per_vp_and_duration


def test_per_collector_nested_sets_and_durations(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    table = tmp_path / 'eventset/2024'
    replay = tmp_path / 'events_replay/e'
    table.mkdir(parents=True); replay.mkdir(parents=True)
    onset=dt.datetime(2024,1,1,tzinfo=dt.timezone.utc)
    pl.DataFrame({'event_id':['e'],'error':[None],'split':['test'],'t0_obs':[onset.isoformat()],
                  'set_d30s':[[1]],'set_d1m':[[1,2]],'set_d5m':[[1,2]],'set_d15m':[[1,2,3]],
                  'set_final_2h':[[1,2,3]]}).write_parquet(table/'events.parquet')
    pl.DataFrame({'collector':['A','A','A','A','A','B','B'],'asn':[1,1,2,3,4,2,3],
                  'first_seen':[onset+dt.timedelta(seconds=s) for s in (0,0,30.1,500,8000,30.1,500)]}).write_parquet(replay/'membership.parquet')
    pl.DataFrame({'ts':[onset+dt.timedelta(seconds=s) for s in (0,50,9000)]}).write_parquet(replay/'anomalous.parquet')
    result=per_vp_and_duration(2024)
    rows={(r['collector'],r['delta']):r['jaccard_mean'] for r in result['per_vp_test']}
    assert rows=={('A','d30s'):.333,('A','d1m'):.667,('A','d5m'):.667,('A','d15m'):1.,
                  ('B','d30s'):0.,('B','d1m'):.5,('B','d5m'):.5,('B','d15m'):1.}
    durations=pl.read_parquet(table/'durations.parquet')
    assert durations['duration_s'].to_list()==[50.]
    assert durations['bucket'].to_list()==['ephemeral <60 s']
    (replay/'membership.parquet').unlink()
    with pytest.raises(FileNotFoundError,match='Usable event'):
        per_vp_and_duration(2024)
