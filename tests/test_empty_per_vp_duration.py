from pathlib import Path
import polars as pl
from bgbench import config,replay_day
from bgbench import eventset


def test_no_usable_events_writes_explicit_empty_tables(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'DATA_ROOT',tmp_path)
    monkeypatch.setattr(replay_day,'roots',lambda tag:(tmp_path,tmp_path/'replay'))
    output=tmp_path/'eventset/2022_withdrawal';output.mkdir(parents=True)
    pl.DataFrame({'event_id':['x'],'error':['missing source'],'split':['test'],'t0_obs':['2022-01-01T00:00:00+00:00'],
                  **{f'set_{k}':[[]] for k in eventset.DELTAS_S},'set_final_2h':[[]]},
                 schema_overrides={**{f'set_{k}':pl.List(pl.Int64) for k in eventset.DELTAS_S},'set_final_2h':pl.List(pl.Int64)}).write_parquet(output/'events.parquet')
    result=eventset.per_vp_and_duration(2022,'withdrawal')
    assert result['events']==0 and result['per_vp_test']==[] and result['duration_share_all']==[]
    assert pl.read_parquet(output/'durations.parquet').columns==['event_id','split','duration_s','bucket']
    assert pl.read_csv(output/'persistence_per_vp_test.csv').height==0
