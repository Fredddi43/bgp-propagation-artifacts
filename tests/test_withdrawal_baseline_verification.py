import hashlib
import importlib.util
import json
from pathlib import Path

import polars as pl


spec = importlib.util.spec_from_file_location('withdrawal_verifier', Path(__file__).parents[1]/'scripts/verify_withdrawal_baselines.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def save(path, value):
    path.write_text(json.dumps(value))


def fixture(tmp_path):
    collectors = [f'collector{i}' for i in range(10)]
    policy = {'required_collectors':collectors,'maximum_age_seconds':604800}
    audit = {'status':'passed','policy':policy,'events':[],'rib_filename_inventory':{c:[] for c in collectors}}
    tables, selected = [], {}
    for year, count in zip(range(2022,2027), (46,83,50,57,65)):
        before = [{'event_id':f'{year}-{i}', 'error':None,'set_final_2h':[1],'asns_final_2h':1,'t90_s':0.} for i in range(count)]
        after = [dict(r,error='missing_required_weekly_rib',set_final_2h=None,asns_final_2h=None,t90_s=None) for r in before]
        table = pl.DataFrame(after,schema={'event_id':pl.String,'error':pl.String,'set_final_2h':pl.List(pl.Int64),'asns_final_2h':pl.Int64,'t90_s':pl.Float64})
        relative = f'eventset/{year}_withdrawal/events.parquet';path=tmp_path/relative;path.parent.mkdir(parents=True);table.write_parquet(path)
        selected[relative]=module.sha(path)
        tables.append({'year':year,'path':relative,'selected':count,'before_content_sha256':module.row_digest(before),
                       'after_content_sha256':module.row_digest(after),'after_sha256':module.sha(path),
                       'columns':table.columns,'usable_after':0,'nulled_columns':['set_final_2h','asns_final_2h','t90_s'],
                       'changes':[{'event_id':a['event_id'],'reason':'missing_required_weekly_rib','before':b,'after':a} for b,a in zip(before,after)]})
        for row in before:
            audit['events'].append({'event_id':row['event_id'],'year':year,'t0':f'{year}-01-01T00:00:00+00:00',
                                   'existing_error':None,'supported':False,'missing_baseline_collectors':collectors,'stale_baseline_collectors':[],
                                   'collectors':[{'collector':c,'rib_path':None,'rib_timestamp':None,'age_seconds':None,'status':'missing'} for c in collectors]})
    revision={'status':'complete','policy':policy,'tables':tables,'selected_artifact_sha256':selected,'source_gate_sha256':'original'}
    revision_path=tmp_path/'revision.json';audit_path=tmp_path/'audit.json';proof_path=tmp_path/'proof.json'
    save(audit_path,audit)
    revision['availability_audit_sha256']=module.sha(audit_path)
    save(revision_path,revision)
    proof={'mode':'private_source_audit','status':'passed','failures':[],'revision_sha256':module.sha(revision_path),
           'audit_sha256':module.sha(audit_path),'source_sha256':selected,'supported_baseline_sha256':{},
           'source_gate_sha256':'original'}
    save(proof_path,proof)
    return revision_path,audit_path,proof_path


def test_public_reconstruction_accepts_explicit_unavailable_rows(tmp_path):
    paths=fixture(tmp_path)
    result=module.verify(tmp_path,*paths)
    assert result['status']=='passed',result['failures']
    assert result['events']==301 and result['new_exclusions']==301


def test_public_reconstruction_rejects_changed_label_and_file_binding(tmp_path):
    paths=fixture(tmp_path)
    path=tmp_path/'eventset/2022_withdrawal/events.parquet'
    table=pl.read_parquet(path).with_columns(pl.lit(0).alias('asns_final_2h'))
    table.write_parquet(path)
    result=module.verify(tmp_path,*paths)
    assert result['status']=='failed'
    assert any('exact permitted change' in failure for failure in result['failures'])
    assert any('selected artifact bytes' in failure for failure in result['failures'])


def test_public_proof_rejects_disconnected_historical_source(tmp_path):
    paths=fixture(tmp_path)
    proof=json.loads(paths[2].read_text())
    proof['source_gate_sha256']='another-source'
    save(paths[2],proof)
    result=module.verify(tmp_path,*paths)
    assert 'private proof historical source gate' in result['failures']


def test_revision_must_bind_the_actual_availability_audit(tmp_path):
    paths=fixture(tmp_path)
    revision=json.loads(paths[0].read_text())
    revision['availability_audit_sha256']='another-audit'
    save(paths[0],revision)
    proof=json.loads(paths[2].read_text())
    proof['revision_sha256']=module.sha(paths[0])
    save(paths[2],proof)
    result=module.verify(tmp_path,*paths)
    assert 'revision availability binding' in result['failures']
