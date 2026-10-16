import importlib.util
import json
from pathlib import Path
import polars as pl
import pytest

spec = importlib.util.spec_from_file_location('auxiliary_audit',Path(__file__).parents[1]/'scripts/verify_graph_auxiliary.py')
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)


def fixture(tmp_path):
    table = tmp_path/'eventset/2024_leak/events.parquet'; table.parent.mkdir(parents=True)
    pl.DataFrame({'event_id':['e'],'set_final_2h':[[1,2,3]],'set_d30s':[[1]],'t0_obs':['2024-09-01T00:00:00']}).write_parquet(table)
    row = {'event_id':'e','target_asns':'[1,2,3]','seed_asns':'[1]','predicted_asns_tuned':'[1,2]',
           'predicted_asns_at05':'[1,2]','candidate_asns':'[1,2,4]','candidate_probabilities':'[0.1,0.8,0.2]',
           'pos':3,'seeds':1,'curve_true_2h':3,'curve_pred_2h':2.5,
           'jaccard_thr':2/3,'jaccard_05':2/3,'jaccard_persist':1/3,'auprc_new':1.}
    return module.Audit(tmp_path),row


def test_auxiliary_recomputes_full_target_and_rejects_pruning(tmp_path):
    audit,row=fixture(tmp_path)
    audit.check_row(row,'2024_leak200',30,'cross')
    row.update(target_asns='[1,2]',pos=2,curve_true_2h=2,jaccard_thr=1.,jaccard_05=1.,jaccard_persist=.5)
    with pytest.raises(AssertionError,match='source target mismatch'):
        audit.check_row(row,'2024_leak200',30,'cross')


def test_auxiliary_rejects_bad_score_and_missing_seed(tmp_path):
    audit,row=fixture(tmp_path)
    row['jaccard_thr']=.9
    with pytest.raises(AssertionError): audit.check_row(row,'2024_leak200',30,'cross')
    row['jaccard_thr']=2/3;row['predicted_asns_tuned']='[2]'
    with pytest.raises(AssertionError,match='omitted observed seed'): audit.check_row(row,'2024_leak200',30,'cross')


def test_shifted_observation_independent_raw_membership(tmp_path):
    audit,row=fixture(tmp_path)
    folder=tmp_path/'events_replay_leak/e';folder.mkdir(parents=True)
    from datetime import datetime,timedelta
    onset=datetime(2024,9,1)
    pl.DataFrame({'asn':[1,2,3],'collector':['vp']*3,'first_seen':[onset,onset+timedelta(seconds=45),onset+timedelta(seconds=120)]}).write_parquet(folder/'membership.parquet')
    row.update(seed_asns='[1,2]',seeds=2,jaccard_persist=2/3,auprc_new=float('nan'))
    audit.check_row(row,'2024_leak200@t0=60',30,'cross')
    row.update(seed_asns='[1]',seeds=1,jaccard_persist=1/3,auprc_new=1.)
    with pytest.raises(AssertionError,match='raw membership seed mismatch'):audit.check_row(row,'2024_leak200@t0=60',30,'cross')


def test_ap_ties_are_grouped():
    assert module.ap_score({2},[1,2,3],[.9,.5,.5],{1}) == .5


def test_public_evidence_requires_private_source_audit_hash(tmp_path):
    evidence=tmp_path/'evidence.csv';evidence.write_text('event_id,score\ne,0.5\n')
    report=tmp_path/module.REPORT;report.parent.mkdir(parents=True)
    report.write_text(json.dumps({'status':'passed','mode':'private_source_audit','source_sha256':{},
                                  'evidence_sha256':{'evidence.csv':module.digest(evidence)}}))
    audit=module.Audit(tmp_path,public=True)
    audit.hashed('evidence.csv')
    evidence.write_text('event_id,score\ne,0.9\n')
    with pytest.raises(AssertionError,match='changed audited evidence'):audit.hashed('evidence.csv')
