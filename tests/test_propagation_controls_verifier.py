import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('controls',Path(__file__).parents[1]/'scripts/verify_propagation_controls.py')
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)


def test_controls_test_incident_weight_and_quantiles():
    rows=[]
    for i,(eid,split,j) in enumerate([('20240101T010001_a','train',0.),('20240101T010002_b','test',1.),('20240101T020001_c','test',.5)]):
        rows.append(dict(event_id=eid,split=split,j30=j,validity='invalid',new_origin=1,reason='radar',
            asns_final_2h=10*(i+1),duration_min=5.,growing30=j<1,labelled=True,collectors_seeing=2,
            plen=24,prev_validity='valid',invalid_reason='asn',cone=1,n_providers=2,
            grip_labelled=False,grip_rpki_newcomer=None))
    result=module.summary(rows,2024,None)
    assert result['by_validity_incident_weighted']['invalid']['persist_j30_incident_mean']==.75
    assert result['by_validity']['invalid']['asns_final_2h_p90']==30
    assert result['by_validity']['invalid']['persist_j30_test_mean']==.75
    assert result['by_validity_x_prev']=={} # small strata are not reported
    corrupted={**result['by_validity_incident_weighted']['invalid'],'persist_j30_incident_mean':.5}
    with pytest.raises(AssertionError):
        module.equal(corrupted,result['by_validity_incident_weighted']['invalid'],'incident')


def test_collector_average_then_spread_and_class_grouping():
    scores=[dict(collector=c,delta='d30s',validity=v,jaccard=j) for c,v,j in
            [('a','valid',0.),('a','valid',1.),('a','invalid',1.),('b','valid',0.)]]
    rows=module.collector_rows(scores,True)
    assert next(r for r in rows if r['collector']=='a' and r['validity']=='valid')['jaccard_mean']==.5
    valid=next(r for r in module.spread(rows,True) if r['validity']=='valid')
    assert valid==dict(validity='valid',delta='d30s',collectors=2,min=0.,max=.5,std=.354)


def test_independent_controls_match_producer_on_full_synthetic_populations(tmp_path,monkeypatch,capsys):
    import datetime as dt
    import json
    import polars as pl
    producer_spec=importlib.util.spec_from_file_location('rpki_producer',Path(__file__).parents[1]/'scripts/rpki_validity_events.py')
    producer=importlib.util.module_from_spec(producer_spec);producer_spec.loader.exec_module(producer)
    monkeypatch.setattr(producer.config,'DATA_ROOT',tmp_path)
    event_dir=tmp_path/'eventset/2024';event_dir.mkdir(parents=True)
    inventory=tmp_path/'inventory/2024';inventory.mkdir(parents=True)
    rows=[];labels=[];manifest=[];ranked=[];independent=[]
    for i in range(100):
        clock=dt.datetime(2024,1,1)+dt.timedelta(seconds=i)
        prefix=f'10.0.{i}.0/24';origin=100+i//10
        eid=f'{clock:%Y%m%dT%H%M%S}_{prefix.replace("/","-")}_{origin}'
        validity='invalid' if i<60 else 'valid' if i<80 else 'unknown'
        row=dict(event_id=eid,error=None,split='train' if i%3==0 else 'test',labelled=i%2==0,
            reason='rpki_invalid_sample' if i<10 else 'stratified',set_d30s=[1] if i%2 else [1,2],
            set_final_2h=[1,2,3],asns_final_2h=3,collectors_seeing=2,duration_min=float(i))
        label=dict(event_id=eid,validity=validity,prev_validity='valid',invalid_reason='asn' if i<60 else None,
            cone=1,n_providers=2,grip_labelled=i%2==0,grip_rpki_newcomer='rpki-invalid-newcomer')
        rows.append(row);labels.append(label)
        manifest.append(dict(event_id=eid,prefix=prefix,new_origin=origin,t0=clock.isoformat()))
        ranked.append(dict(first_ts=clock,prefix=prefix,new_origin=origin,prev_origins='[99]',plen=24))
        independent.append({**row,**label,'plen':24,'new_origin':origin,'j30':len(row['set_d30s'])/3,'growing30':True})
    pl.DataFrame(rows).write_parquet(event_dir/'events.parquet')
    pl.DataFrame(labels).write_parquet(event_dir/'rpki_validity.parquet')
    pl.DataFrame(manifest).write_csv(inventory/'replay_manifest.tsv',separator='\t')
    pl.DataFrame(ranked).write_parquet(inventory/'events_ranked.parquet')
    for suffix,exclude in [('',None),('_labelled','rpki_invalid_sample')]:
        producer.main(2024,True,exclude,suffix)
        actual=json.loads((event_dir/f'rpki_validity_summary{suffix}.json').read_text())
        expected=json.loads(json.dumps(module.summary(independent,2024,exclude)))
        module.equal(actual,expected,'synthetic controls')


def test_top_category_ties_allow_equal_counts_but_reject_smaller_categories():
    module.validate_top_counts({'a':10,'c':2},{'a':10,'b':2,'c':2},2)
    with pytest.raises(AssertionError):
        module.validate_top_counts({'a':10,'c':1},{'a':10,'b':2,'c':1},2)
