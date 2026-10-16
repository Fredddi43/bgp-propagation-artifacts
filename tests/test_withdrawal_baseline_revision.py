import importlib.util
from pathlib import Path

import polars as pl

spec = importlib.util.spec_from_file_location('withdrawal_revision', Path(__file__).parents[1]/'scripts/revise_withdrawal_baselines.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_missing_stale_and_existing_exclusions_preserve_selection():
    table = pl.DataFrame({'event_id':['missing','stale','supported','already'],
                          'error':[None,None,None,'archive_gap'], 'set_final_2h':[[1],[2],[3],None],
                          'asns_final_2h':[1,1,1,None], 'vp_final_2h':[1,1,1,None],
                          't90_s':[0.,1.,2.,None], 'sessions_carrying':[4,5,6,None],
                          't0_obs':['a','b','c','d'], 'anomalous_msgs':[9,8,7,6]})
    events = [{'event_id':row['event_id'], 'existing_error':row['error'],
               'missing_baseline_collectors':['c'] if row['event_id'] in ('missing','already') else [],
               'stale_baseline_collectors':['c'] if row['event_id']=='stale' else [],
               'supported':row['event_id']=='supported'} for row in table.iter_rows(named=True)]
    revised, reasons, _ = module.classify(table, events)
    assert reasons == {'missing':'missing_required_weekly_rib','stale':'stale_required_weekly_rib'}
    assert revised['set_final_2h'].to_list() == [None,None,[3],None]
    assert revised['sessions_carrying'].to_list() == [None,None,6,None]
    assert revised['error'].to_list()[-1] == 'archive_gap'
    assert revised.select('event_id','t0_obs','anomalous_msgs').equals(table.select('event_id','t0_obs','anomalous_msgs'))


def test_supported_table_is_returned_without_reencoding():
    table = pl.DataFrame({'event_id':['a'], 'error':[None], 'set_final_2h':[[1]]}, schema_overrides={'error':pl.String})
    result, reasons, _ = module.classify(table, [{'event_id':'a','existing_error':None,'supported':True,
                                               'missing_baseline_collectors':[], 'stale_baseline_collectors':[]}])
    assert result is table
    assert reasons == {}
