from pathlib import Path
import sys
import polars as pl
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from verify_nongraph_boundary_inputs import eligible


def test_full_training_population_and_distinct_model_gates():
    table=pl.DataFrame({'event_id':['train','small','badlag','error'],'split':['train','test','test','test'],
                        'error':[None,None,None,'gap'],'observation_lag_s':[0.,0.,-3600.,0.],
                        'asns_final_2h':[201,134,500,600]})
    floor=pl.DataFrame({'event_id':['train','small','badlag','error'],'prefixes_2h':[12,1,20,30]})
    assert eligible(table,{'kind':'tsfm'},None)['event_id'].to_list()==['train']
    assert eligible(table,{'kind':'prefix_floor'},None)['event_id'].to_list()==['train','small']
    assert eligible(table,{'kind':'prefix_features'},floor)['event_id'].to_list()==['train']
    assert eligible(table,{'kind':'radar_prefix_agreement'},None)['event_id'].to_list()==['train','small','badlag']
    assert eligible(table,{'kind':'cascade','args':{'set_tag':'leak','min_asns':200}},None)['event_id'].to_list()==['train']


def test_boundary_bridge_reconstructs_whole_source_and_rejects_other_changes():
    import pytest
    from boundary_input_bridge import make_record,restore_table
    old=pl.DataFrame({'event_id':['a','b'],'error':[None,None],'set_d30s':[[1],[2]],'asns_d30s':[1,1]},schema_overrides={'error':pl.String})
    new=old.with_columns(pl.when(pl.col('event_id')=='b').then(pl.lit('gap')).otherwise(pl.col('error')).alias('error'),pl.lit(None,dtype=pl.String).alias('measurement_predecessor_gap_tasks'))
    record=make_record('eventset/x/events.parquet',old,new)
    assert restore_table(new,record).equals(old)
    with pytest.raises(AssertionError):restore_table(new.with_columns(pl.lit(2).alias('asns_d30s')),record)
    record['changed_rows'][0]['before']['set_d30s']=[999]
    with pytest.raises(AssertionError):restore_table(new,record)


def test_dtype_roundtrip_nested_struct_without_code_execution():
    import pytest
    from boundary_input_bridge import parse_dtype
    dtype=pl.Struct({'95':pl.List(pl.Int64),'flag':pl.String})
    assert parse_dtype(str(dtype))==dtype
    with pytest.raises(AssertionError):parse_dtype("__import__('os').system('false')")


def test_boundary_restoration_composes_with_count_fill():
    from boundary_input_bridge import make_record,restore_table
    from verify_derived_counts import COLUMNS,verify_tables
    old=pl.DataFrame({'event_id':['a','b'],'error':[None,None],**{c:[None,1] for c in COLUMNS},
                     **{'set_'+c.removeprefix('asns_'):[[1],[2]] for c in COLUMNS}},
                     schema_overrides={'error':pl.String,**{c:pl.Int64 for c in COLUMNS}})
    filled=old.with_columns([pl.col('set_'+c.removeprefix('asns_')).list.len().cast(pl.Int64).alias(c) for c in COLUMNS])
    final=filled.with_columns(pl.when(pl.col('event_id')=='b').then(pl.lit('gap')).otherwise(pl.col('error')).alias('error'))
    restored=restore_table(final,make_record('x',filled,final))
    verify_tables(old,restored)


def test_release_marker_binds_revision_and_selected_bytes(tmp_path):
    import hashlib,json
    from verify_nongraph_release import verify_nongraph
    old='2025/062_prefix_floor/complete.json';new='2025/062_prefix_floor_boundary_v2/complete.json'
    original=tmp_path/'analysis/nongraph'/old;original.parent.mkdir(parents=True);original.write_text('{}')
    original_hash=hashlib.sha256(original.read_bytes()).hexdigest()
    replacement=tmp_path/'analysis/nongraph'/new;replacement.parent.mkdir(parents=True)
    replacement.write_text(json.dumps({'replacement_for':{'path':'nongraph-final/'+old,'sha256':original_hash}}))
    replacement_hash=hashlib.sha256(replacement.read_bytes()).hexdigest()
    release={'status':'complete','data_root':'nongraph-release','selected_artifact_sha256':{old:original_hash,new:replacement_hash},
             'revisions':[{'index':62,'year':2025,'original_folder':'2025/062_prefix_floor','replacement_folder':'2025/062_prefix_floor_boundary_v2','completion_sha256':replacement_hash}]}
    marker=tmp_path/'analysis/nongraph-release-complete.json';marker.write_text(json.dumps(release))
    failures=[]
    check=lambda yes,kind,**kwargs:None if yes else failures.append(kind)
    verify_nongraph({'nongraph_release':'analysis/nongraph-release-complete.json'},lambda p:tmp_path/p,None,check,None,data_root=tmp_path)
    assert failures==[]
    replacement.write_text('{}')
    verify_nongraph({'nongraph_release':'analysis/nongraph-release-complete.json'},lambda p:tmp_path/p,None,check,None,data_root=tmp_path)
    assert 'nongraph_release_file_hash' in failures and 'nongraph_release_original_completion_binding' in failures
