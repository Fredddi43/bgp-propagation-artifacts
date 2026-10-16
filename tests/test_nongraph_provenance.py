import importlib.util
import json
from pathlib import Path
import pytest
import polars as pl


def test_non_graph_completion_refuses_source_changed_during_task(tmp_path, monkeypatch):
    source = Path(__file__).parents[1]/'scripts/rerun_nongraph.py'
    spec = importlib.util.spec_from_file_location('nongraph_runner', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    task = {'index':0,'kind':'radar_prefix_agreement','year':2024}
    (tmp_path/'nongraph-plan.json').write_text(json.dumps([task]))
    (tmp_path/'crossday-leak-2023-2025-complete.json').write_text('{}')
    event_table = tmp_path/'data/eventset/2024_leak/events.parquet'
    event_table.parent.mkdir(parents=True)
    pl.DataFrame({'event_id':['one'], 'asns_final_2h':[10]}).write_parquet(event_table)
    for name in ['scripts/label_leak_prefixes.py','scripts/rerun_nongraph.py','jobs/nongraph_corrections.sh','src/bgbench/config.py','src/bgbench/graph_metrics.py']:
        path=tmp_path/'code'/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text('# frozen producer')
    monkeypatch.setattr(module.subprocess,'run',lambda *a,**k:pl.DataFrame({'event_id':['one'], 'asns_final_2h':[11]}).write_parquet(event_table))
    with pytest.raises(RuntimeError,match='changed during execution'):
        module.execute(tmp_path,0)
    assert not (tmp_path/'nongraph-final/2024/000_radar_prefix_agreement/complete.json').exists()


def test_decoded_source_fingerprint_preserves_reencoding_but_detects_value_changes(tmp_path):
    source = Path(__file__).parents[1]/'scripts/rerun_nongraph.py'
    spec = importlib.util.spec_from_file_location('nongraph_runner', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    table = pl.DataFrame({'event_id':['b','a'],'value':[1,2]})
    a,b=tmp_path/'a.parquet',tmp_path/'b.parquet'
    table.write_parquet(a,compression='uncompressed')
    table.reverse().select('value','event_id').write_parquet(b,compression='zstd')
    assert module.fingerprint(a) != module.fingerprint(b)
    assert module.table_content_fingerprint(a) == module.table_content_fingerprint(b)
    table.with_columns(pl.lit(9).alias('value')).write_parquet(b)
    assert module.table_content_fingerprint(a) != module.table_content_fingerprint(b)
