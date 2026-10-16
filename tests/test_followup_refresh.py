import sys
from pathlib import Path
import polars as pl
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import exclude_incomplete_followup as followup


def test_existing_followup_flag_recomputed_without_new_exclusions(tmp_path,monkeypatch):
    folder=tmp_path/'eventset/2024';folder.mkdir(parents=True)
    pl.DataFrame({'event_id':['ok','excluded'],'error':[None,'insufficient_planned_followup'],
                  'observation_lag_s':[1.,3700.],'measurement_full_followup_within_planned_window':[None,False]}).write_parquet(folder/'events.parquet')
    monkeypatch.setattr(followup.config,'DATA_ROOT',tmp_path)
    output=[]
    monkeypatch.setattr(followup,'run',lambda year,tag,table_override:output.append(table_override))
    assert followup.exclude([2024],[''])==[]
    assert output[0]['measurement_full_followup_within_planned_window'].to_list()==[True,False]
    assert output[0]['error'].to_list()==[None,'insufficient_planned_followup']
