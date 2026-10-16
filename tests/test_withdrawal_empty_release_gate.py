from pathlib import Path
import json,sys
import polars as pl
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from verify_corrected_release import verify
import verify_withdrawal_baselines


def test_empty_population_requires_successful_exact_year_proof(tmp_path,monkeypatch):
    directory=tmp_path/'eventset/2022_withdrawal';directory.mkdir(parents=True)
    pl.DataFrame({'event_id':['x'],'error':['missing_required_weekly_rib'],'split':['test']}).write_parquet(directory/'events.parquet')
    paths={k:f'{k}.json' for k in ('revision','availability','verification')}
    for p in paths.values():(tmp_path/p).write_text('{}')
    (tmp_path/'revision.json').write_text(json.dumps({'tables':[{'path':'eventset/2022_withdrawal/events.parquet','usable_after':0}]}))
    expected={'event_tables':['2022_withdrawal'],'pair_tables':[],'model_tables':[]}
    assert any(f['kind']=='no_usable_events' for f in verify(tmp_path,expected)['failures'])
    expected['withdrawal_baseline']=paths
    monkeypatch.setattr(verify_withdrawal_baselines,'verify',lambda *a,**kw:{'status':'passed','failures':[],'source_sha256':{}})
    assert not any(f['kind']=='no_usable_events' for f in verify(tmp_path,expected)['failures'])
    monkeypatch.setattr(verify_withdrawal_baselines,'verify',lambda *a,**kw:{'status':'failed','failures':['bad proof'],'source_sha256':{}})
    assert any(f['kind']=='no_usable_events' for f in verify(tmp_path,expected)['failures'])
