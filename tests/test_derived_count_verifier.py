import json
from pathlib import Path
import sys

import polars as pl
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from verify_derived_counts import COLUMNS, TRANSFORMATION, content_hash, sha, verify_bridge, verify_tables


def fixture():
    values={'event_id':['b','a','excluded'],'error':[None,None,'missing'],'unchanged':[4,3,2]}
    for column in COLUMNS:
        values[column]=[None,1,None]
        values['set_'+column.removeprefix('asns_')]=[[1,2],[1],None]
    before=pl.DataFrame(values)
    after=before.with_columns([pl.Series(c,[2,1,None]) for c in COLUMNS])
    return before,after


def test_count_fill_rejects_other_changes_and_bad_counts():
    before,after=fixture()
    assert verify_tables(before,after)=={column:['b'] for column in COLUMNS}
    with pytest.raises(AssertionError,match='non-count'):
        verify_tables(before,after.with_columns(pl.lit(9).alias('unchanged')))
    with pytest.raises(AssertionError,match='not materialized'):
        verify_tables(before,after.with_columns(pl.lit(8).alias(COLUMNS[0])))
    with pytest.raises(AssertionError,match='old non-null'):
        verify_tables(before.with_columns(pl.lit(5).alias(COLUMNS[0])),after)


def write_bridge(tmp_path):
    before,after=fixture()
    data=tmp_path/'data';(data/'eventset/2024').mkdir(parents=True)
    current=data/'eventset/2024/events.parquet';after.write_parquet(current)
    original=tmp_path/'before.parquet';before.write_parquet(original)
    sidecar=data/'verification/counts.parquet';sidecar.parent.mkdir();before.select('event_id',*COLUMNS).write_parquet(sidecar)
    marker=tmp_path/'nongraph-final-complete.json';marker.write_text('{}')
    record={'path':'eventset/2024/events.parquet','before_path':'before.parquet','before_sha256':sha(original),
            'before_content_sha256':content_hash(before),'after_sha256':sha(current),'after_content_sha256':content_hash(after),
            'before_counts_path':'verification/counts.parquet','before_counts_sha256':sha(sidecar),
            'before_counts_content_sha256':content_hash(pl.read_parquet(sidecar)), 'before_columns':before.columns,
            'rows':3,'columns':COLUMNS,'changed_event_ids_by_column':{column:['b'] for column in COLUMNS}}
    bridge=tmp_path/'bridge.json';proof=tmp_path/'proof.json'
    bridge.write_text(json.dumps({'schema_version':1,'transformation':TRANSFORMATION,'tables':[record],
            'source_completion_marker':marker.name,'source_completion_marker_sha256':sha(marker)}))
    verify_bridge(data,bridge,proof,tmp_path)
    return data,bridge,proof,before,after,current


def test_public_reconstruction_binds_original_full_contents(tmp_path):
    data,bridge,proof,before,after,current=write_bridge(tmp_path)
    assert verify_bridge(data,bridge,proof)['status']=='passed'
    after.with_columns(pl.lit(99).alias('unchanged')).write_parquet(current)
    with pytest.raises(AssertionError,match='reconstructed original content'):
        verify_bridge(data,bridge,proof)


def test_completion_input_digest_requires_verified_narrow_bridge(tmp_path):
    from verify_nongraph_release import verify_nongraph
    data,bridge,proof,before,after,current=write_bridge(tmp_path)
    relative='analysis/nongraph/2024/000_cascade/complete.json'
    marker=data/relative;marker.parent.mkdir(parents=True)
    source='eventset/2024/events.parquet'
    marker.write_text(json.dumps({'correction_run':{'inputs_unchanged':True,'code_unchanged':True,
        'input_content_sha256':{source:content_hash(before)},'inputs':{source:'original bytes'},'inputs_after':{source:'original bytes'}}}))
    contract={'manifest':'analysis/derived-count-fill-bridge.json','verification':'analysis/derived-count-fill-verification.json'}
    expected={'required_files':[relative],'nongraph_tables':[],'derived_count_bridge':contract}
    def run(manifest):
        failures=[]
        def check(condition,kind,**details):
            if not condition:failures.append(kind)
        def require(name):
            return {contract['manifest']:bridge,contract['verification']:proof}.get(name,data/name)
        verify_nongraph(manifest,require,None,check,None,data_root=data)
        return failures
    assert run(expected)==[]
    del expected['derived_count_bridge']
    assert run(expected)==['nongraph_execution_source_changed']
