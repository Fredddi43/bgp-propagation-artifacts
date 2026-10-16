"""Corrupted targets and aggregates must fail without experiment-code imports."""
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import polars as pl

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from verify_nongraph_release import average_precision, verify_nongraph


def run_check(tmp_path, spec, source):
    failures=[]
    def check(condition,kind,**details):
        if not condition:
            failures.append(kind)
    def require(name):
        path=tmp_path/name
        check(path.is_file(),"missing_required_file")
        return path if path.is_file() else None
    def close(a,b,tolerance=.000051):
        return a is None and b is None if a is None or b is None else bool(abs(a-b)<=tolerance or np.isnan(a) and np.isnan(b))
    verify_nongraph({"nongraph_tables":[spec]},require,lambda _:source,check,close)
    return failures


def test_cascade_verification_checks_full_truth_and_tied_ap(tmp_path):
    source=pl.DataFrame({"event_id":["other","e"],"error":[None,None],"split":["test","test"],
                         "set_d30s":[[999],[999]],"set_final_2h":[[999,2],[999,2]]})
    scores=[1.,0.,0.]
    assert np.isclose(average_precision([True,True,False],scores),5/6)
    assert np.isclose(average_precision([True,False,True],scores),5/6)
    row={"event_id":"e","seeds":1,"final":2,"persist_jaccard":.5,"persist_recall":.5,
         "persist_size_smape":2/3,"cascade_expected_size":1.,"cascade_size_smape":2/3,
         "cascade_jaccard":.5,"cascade_precision":1.,"cascade_recall":.5,"cascade_auprc":round(5/6,4),
         "scored_asns":[999,2,3],"scored_probabilities":scores,"prediction_candidate_asns":[999,3]}
    pl.DataFrame([row]).write_parquet(tmp_path/"rows.parquet")
    saved={"delta":"d30s","target":"final_2h","events_scored":1,"cascade_jaccard_mean":.5,"cascade_beats_persistence_frac":0.,
           "sample_requested":1,"sampling_seed":0,"growing_test_events_total":2}
    (tmp_path/"summary.json").write_text(json.dumps(saved))
    spec={"kind":"cascade","summary":"summary.json","rows":"rows.parquet","event_table":"2024_leak"}
    assert run_check(tmp_path,spec,source)==[]
    saved["growing_test_events_total"]=1
    (tmp_path/"summary.json").write_text(json.dumps(saved))
    assert "nongraph_metric" in run_check(tmp_path,spec,source)
    saved["growing_test_events_total"]=2
    (tmp_path/"summary.json").write_text(json.dumps(saved))
    row["scored_asns"]=[999,3]
    row["scored_probabilities"]=[1.,0.]
    pl.DataFrame([row]).write_parquet(tmp_path/"rows.parquet")
    assert "cascade_pruned_truth_or_seeds" in run_check(tmp_path,spec,source)


def test_curve_verification_checks_minute_targets_and_aggregates(tmp_path):
    source=pl.DataFrame({"event_id":["e"],"error":[None],"split":["test"],"observation_lag_s":[0.],
        "asns_final_2h":[2],"asns_T5m":[1],"set_d1m":[[1]],"set_T15m":[[1,2]]})
    row={"event_id":"e","model":"persistence","delta_min":1,"horizon_min":15,"truth":2.,"prediction":1.,"smape":2/3}
    pl.DataFrame([row]).write_parquet(tmp_path/"rows.parquet")
    saved={"set_tag":"leak","min_asns":0,"sampled_event_ids":["e"],"events_used":1,"d1m":{"persistence:T15m":.667}}
    (tmp_path/"summary.json").write_text(json.dumps(saved))
    spec={"kind":"curve_naive","summary":"summary.json","rows":"rows.parquet","event_table":"2024_leak","sample":400}
    assert run_check(tmp_path,spec,source)==[]
    row["truth"]=1.
    pl.DataFrame([row]).write_parquet(tmp_path/"rows.parquet")
    assert "nongraph_metric" in run_check(tmp_path,spec,source)


def test_prefix_verification_recomputes_full_set_metrics_and_bootstrap(tmp_path):
    source=pl.DataFrame({"event_id":["e"],"error":[None]})
    prefix_dir=tmp_path/"prefix_predictions"
    prefix_dir.mkdir()
    pl.DataFrame({"event_id":["e"]*3,"prefix":["a","b","c"],"y":[1,1,0],"seen_delta":[1,0,0],
        "in_candidate":[1,0,1],"share_src":[0.,0.,1.],"share_peer":[0.,0.,0.],"share_prov":[0.,0.,0.],
        "p":[.2,.9,.1]}).write_parquet(prefix_dir/"e.parquet")
    pl.DataFrame({"event_id":["e"],"set_d30s":[["a"]],"set_final_2h":[["a","b"]]}).write_parquet(tmp_path/"floor.parquet")
    row={"event_id":"e","n_cand":2,"n_leaked":2,"n_seen":1,"unreachable_truth":1,
        "j_persist":.5,"j_model":.5,"j_rule_src":1/3,"j_rule_nonprov":1/3}
    pl.DataFrame([row]).write_parquet(tmp_path/"rows.parquet")
    saved={"events_test":1,"threshold":.5,"candidates_per_event_p50":2,"leaked_per_event_p50":2,
        "jaccard_test_mean":{k:round(row[k],4) for k in row if k.startswith("j_")},
        "model_minus_persist_ci95":[0.,0.],"rule_src_minus_persist_ci95":[-.1667,-.1667]}
    (tmp_path/"summary.json").write_text(json.dumps(saved))
    spec={"kind":"prefix_model","summary":"summary.json","rows":"rows.parquet","event_table":"2024_leak",
        "predictions_dir":"prefix_predictions","prefix_floor":"floor.parquet"}
    assert run_check(tmp_path,spec,source)==[]
    pl.DataFrame({"event_id":["e"],"set_d30s":[["a"]],"set_final_2h":[["a","b","omitted"]]}).write_parquet(tmp_path/"floor.parquet")
    assert "prefix_pruned_truth_or_seeds" in run_check(tmp_path,spec,source)


def test_prefix_floor_verification_checks_source_population(tmp_path):
    source=pl.DataFrame({"event_id":["e","old-clock"],"error":[None,None],"split":["test","test"],
        "observation_lag_s":[0.,-100.],"set_final_2h":[[1,2],[3]]})
    row={"event_id":"e","split":"test","prefixes_2h":2,"asns_2h":2,"set_final_2h":["a","b"]}
    for horizon in ("d30s","d1m","d5m","d15m"):
        row.update({"set_"+horizon:["a"],"j_"+horizon:.5,"grow_"+horizon:True})
    pl.DataFrame([row]).write_parquet(tmp_path/"rows.parquet")
    saved={"events":1,"test":1,"prefixes_2h_p50_p90":[2,2],
        "persistence_prefix_jaccard_test":{h:.5 for h in ("d30s","d1m","d5m","d15m")},
        "still_growing_prefixes":{h:1. for h in ("d30s","d1m","d5m","d15m")}}
    (tmp_path/"summary.json").write_text(json.dumps(saved))
    spec={"kind":"prefix_floor","summary":"summary.json","rows":"rows.parquet","event_table":"2024_leak"}
    assert run_check(tmp_path,spec,source)==[]
    source=source.with_columns(observation_lag_s=pl.lit(0.))
    assert "prefix_floor_population" in run_check(tmp_path,spec,source)


def test_chronos_eligibility_is_raw_audited_and_bound_through_reencoding(tmp_path):
    import datetime as dt
    import hashlib
    from verify_nongraph_release import verify_curve_eligibility
    onset=dt.datetime(2025,1,1,tzinfo=dt.timezone.utc)
    source=pl.DataFrame({"event_id":["growing","instant"],"error":[None,None],"split":["test","test"],
        "t0_obs":[onset.isoformat()]*2,"asns_final_2h":[2,2],"observation_lag_s":[0.,0.],"set_final_2h":[[1,2],[1,2]]})
    folder=tmp_path/"eventset/2025_leak"
    folder.mkdir(parents=True)
    source.write_parquet(folder/"events.parquet")
    eligibility=[]
    for eid,delay in (("growing",60),("instant",0)):
        path=tmp_path/f"events_replay_leak/{eid}/membership.parquet"
        path.parent.mkdir(parents=True)
        pl.DataFrame({"asn":[1,2],"first_seen":[onset,onset+dt.timedelta(seconds=delay)]}).write_parquet(path)
        eligibility.append({"event_id":eid,"split":"test","t0_obs":onset.isoformat(),
            "observed_zero_count":1 if delay else 2,"final_count":2,"eligible_growth":bool(delay),
            "membership_sha256":hashlib.sha256(path.read_bytes()).hexdigest()})
    path=tmp_path/"curve_eligibility.parquet"
    pl.DataFrame(eligibility).write_parquet(path)
    failures=[]
    check=lambda ok,kind,**details: failures.append(kind) if not ok else None
    def require(relative):
        target=tmp_path/relative
        check(target.exists(),"missing_required_file")
        return target if target.exists() else None
    spec={"summary":"summary.json","eligibility":path.name,"event_table":"2025_leak"}
    assert verify_curve_eligibility(spec,{"min_asns":0},source,require,check,raw_sources=True)=={"growing"}
    assert not failures
    original=path.read_bytes()
    pl.read_parquet(path).write_parquet(path,compression="gzip")
    assert original!=path.read_bytes()
    assert verify_curve_eligibility(spec,{"min_asns":0},source,require,check)=={"growing"}
    assert not failures
    pl.read_parquet(path).with_columns(observed_zero_count=pl.lit(2),eligible_growth=pl.lit(False)).write_parquet(path)
    verify_curve_eligibility(spec,{"min_asns":0},source,require,check)
    assert "curve_eligibility_proof_mismatch" in failures


def test_cascade_paired_bootstrap_rejects_altered_interval(tmp_path):
    import hashlib
    from bootstrap_cascade_release import summarize
    from verify_nongraph_release import verify_cascade_bootstrap
    records=[];specs=[]
    for index in range(49,60):
        folder=tmp_path/f'analysis/nongraph/2025/{index:03d}_cascade';folder.mkdir(parents=True)
        rows=pl.DataFrame({'event_id':['c','a','b'],'cascade_jaccard':[.2,.8,.4],'persist_jaccard':[.3,.5,.4]})
        path=folder/'predictions.parquet';rows.write_parquet(path)
        configuration={'delta':'d30s'}
        (folder/'complete.json').write_text(json.dumps({'task':{'index':index,'args':configuration}}))
        relative=str(path.relative_to(tmp_path))
        records.append({'task_index':index,'configuration':configuration,'source_rows':relative,
                        'source_rows_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),**summarize(rows)})
        specs.append({'kind':'cascade','event_table':'2025_leak','rows':relative})
    result={'schema_version':1,'comparison':'cascade_minus_persistence_jaccard','resampling_unit':'event',
            'paired':True,'resamples':2000,'seed':0,'seed_reset_per_configuration':True,
            'interval':'two_sided_percentile_95','quantile_method':'linear','event_order':'event_id_ascending',
            'configurations':records}
    relative='analysis/nongraph-cascade-bootstrap.json';path=tmp_path/relative
    path.write_text(json.dumps(result))
    failures=[]
    def check(condition,kind,**kw):
        if not condition:failures.append(kind)
    expected={'cascade_bootstrap':relative,'nongraph_tables':specs}
    verify_cascade_bootstrap(expected,lambda name:tmp_path/name,check,lambda a,b,t:abs(a-b)<=t)
    assert failures==[]
    result['configurations'][0]['paired_difference_ci95'][0]+=.01
    path.write_text(json.dumps(result))
    verify_cascade_bootstrap(expected,lambda name:tmp_path/name,check,lambda a,b,t:abs(a-b)<=t)
    assert failures==['cascade_bootstrap_interval']
