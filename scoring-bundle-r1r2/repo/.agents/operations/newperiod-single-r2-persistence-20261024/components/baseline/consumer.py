"""Declared deterministic baseline secondaries, same captured R2 reference truth.

No fits, new rankings, acquisition or label opening. Original committed decision
and ranking numerics are reused; fixed roles are additional to the six primary
online history cells. Actual complete batch retention remains the owner's guard.
"""
import copy,hashlib,types
from pathlib import Path
HERE=Path(__file__).resolve().parent
raw=(HERE/'reviewed_membership.py').read_bytes()
if hashlib.sha256(raw).hexdigest()!='2f40bf28ea95bf69df378c81fc1c57abacf306f9be59a55028397a70be36e006':
    raise ValueError('Reviewed membership scorer changed')
m=types.ModuleType('baseline_reviewed_membership');m.__file__=str(HERE/'reviewed_membership.py')
exec(compile(raw,m.__file__,'exec'),m.__dict__)
need=m.need

def roles():
    return [dict(family='baseline',variant='core',panel='reference',baseline=b,candidates=c,library=lib,horizon_seconds=h)
            for b,c,lib in (('history-knn-median','native','online'),('topology-seed-adjacency','matched','online'),
                            ('history-knn-mean','matched','frozen_2026_09_01')) for h in (30,60)]

def prepare_sealed(custody,seal,freeze,evidence,read_json,read_input):
    records=freeze['arms'];expected={m.key(r) for r in roles()}
    need(len(records)==6 and len({a['arm_id'] for a in records})==6 and {m.key(a['role']) for a in records}==expected,
         'All six fixed additional baseline cells required')
    committed={a['arm_id']:a for a in custody['arms']};failed={a['arm_id']:a for a in custody.get('retained_failures',[])}
    sealed={a['arm_id']:a for a in seal['arms']}
    need(len(committed)==len(custody['arms']) and len(failed)==len(custody.get('retained_failures',[]))
         and len(sealed)==len(seal['arms']) and not set(committed)&set(failed),'Conflicting global baseline retention')
    relevant=[a for a in [*committed.values(),*failed.values()] if m.key(a['role']) in expected]
    need({a['arm_id']:a for a in relevant}=={a['arm_id']:a for a in records},'Global baseline retention differs')
    e=copy.deepcopy(evidence)
    need(e.get('input_only') is True and e['target_scope']==dict(panel='reference',kind='full_reference_membership',collectors=list(m.REFERENCE)),
         'Full original reference target scope required')
    need('validated_target_scope' not in e and 'target_masters' not in e,'Derived lineage cannot be supplied')
    need(set(e['cohort_ids'])==set(e['label_horizon'])=={'30','60'} and e['label_horizon']=={'30':'30','60':'60'}
         and all(ids==sorted(set(ids)) for ids in e['cohort_ids'].values()),'Exact complete reference horizons required')
    # Production always supplies concrete pooled lineage; its receipt bytes are
    # read/logged by the owning caller before this pure scope validator.
    line=e['pooled_target_lineage'];masters=line['masters'];docs={h:m.target_scope.document(v) for h,v in masters.items()}
    collectors,scope=m.target_scope.reference_panel(masters,docs,line['collector_inventory'],line['source_inventories'],line['recipe'])
    need(collectors==list(m.REFERENCE),'Original ten-collector target panel required')
    e.update(validated_target_scope=scope,target_masters=docs,expected_label_masters={h:m.target_scope.reference(v) for h,v in masters.items()})
    for h,master in docs.items():
        need(sorted(r['event_id'] for r in master['events'])==e['cohort_ids'][h],'Complete target-master population required')
    cells={}
    for a in records:
        name=a['arm_id']
        if a['status']=='not_executable':
            need(failed.get(name)==a and name not in sealed and a.get('failure_chain'),'Retained original baseline failure required')
            for ref in a['failure_chain']:read_json(ref,'original retained baseline failure')
            cells[name]=dict(status='not_estimable',role=a['role'],failure_chain=a['failure_chain']);continue
        need(a['status']=='committed_for_prediction' and committed.get(name)==a and name in sealed,'Exact sealed baseline required')
        bound=sealed[name]
        com=read_json(dict(path=a['commitment_path'],sha256=bound['commitment_sha256']),'sealed baseline commitment')
        need(com['kind']=='newperiod_baseline_commitment_v1' and com['predictions_sha256']==bound['predictions_sha256'],
             'Original deterministic producer and seal required')
        config=read_json(dict(path=a['model_path'],sha256=a['model_sha256']),'sealed deterministic baseline configuration')
        role=a['role'];frozen='2026-09-01T00:00:00+00:00' if role['library']=='frozen_2026_09_01' else None
        need(config==dict(baseline=role['baseline'],candidates=role['candidates'],k=20,frozen_at=frozen,horizon_seconds=role['horizon_seconds']),
             'Original fixed configuration differs')
        manifest=read_json(dict(path=a['manifest_path'],sha256=a['manifest_sha256']),'sealed baseline issue inputs')
        predictions=read_json(dict(path=a['predictions_path'],sha256=bound['predictions_sha256']),'sealed baseline decisions and ranks')
        inputs={}
        for row in manifest['events']:
            if row['input_status']!='available':continue
            value=read_input(dict(path=row['input_path'],sha256=row['input_sha256']),'baseline issue-time tensor')
            need(value['event_id']==row['event_id'],'Baseline input identity differs');inputs[row['event_id']]=value
        cells[name]=m.check_cell(a,dict(manifest=manifest,predictions=predictions,commitment=com,inputs=inputs),e,family='baseline_secondary')
    return copy.deepcopy(dict(cells=cells,evidence=e))

def evaluate(prepared,label_table):
    e=prepared['evidence']
    need(label_table['kind']=='custodian_label_table' and label_table['provenance']['reference_scope']==e['validated_target_scope']
         and label_table['provenance']['masters']==e['expected_label_masters'],'Same captured full-reference truth required')
    need(set(label_table['horizons'])=={'30','60'},'Both original truth horizons required')
    for h,labels in label_table['horizons'].items():
        need(set(labels)==set(e['cohort_ids'][h]),'Complete target population required')
        for row in labels.values():
            need(row['target_status'] in ('scorable','censored'),'Explicit target status required')
            if row['target_status']=='censored':need('target_asns' not in row and 'target_counts' not in row,'No censored target imputation')
    return dict(kind='newperiod_additional_baseline_secondaries_v1',cells={k:m.score_cell(v,e,label_table) for k,v in prepared['cells'].items()},
                declares_primary_finding=False,formal_tests=False,intervals_computed=False,fits=0,
                persistence_note=m.original.PERSISTENCE_NOTE)
