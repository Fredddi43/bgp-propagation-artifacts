"""Stable-peer secondary: fixed24 cells, own truth, original numerical scorers.

The enclosing one-opening R2 caller supplies bound documents, logs reads and
authorizes execution. This component neither opens labels nor issues authority.
"""
import copy
import hashlib
import types
from pathlib import Path
from bgbench import forecast_stable_peer as stable

HERE=Path(__file__).resolve().parent
raw=(HERE/'reviewed_membership.py').read_bytes()
if hashlib.sha256(raw).hexdigest()!='5cd8c4720675273f232940d39b3dfe7bbdc7a1a72d7c6b21b24f3823575fbfde':
    raise ValueError('Reviewed membership component changed')
m=types.ModuleType('stable_reviewed_membership');m.__file__=str(HERE/'reviewed_membership.py')
exec(compile(raw,m.__file__,'exec'),m.__dict__)
need=m.need


def roles():
    return ([dict(family='neural',variant='stable',training='updated',panel='reference',history='on',
                  message_passing=model,horizon_seconds=d,seed=s)
             for model in ('sage','none') for d in (30,60) for s in range(5)]
          + [dict(family='baseline',variant='stable',panel='reference',baseline=model,candidates='matched',
                  library='online',horizon_seconds=d)
             for model in ('persistence','history-knn-mean') for d in (30,60)])


def source_evidence(evidence,read_json):
    """Bind actual stable stage/masters and unchanged primary population prelabel."""
    need(evidence['input_only'] is True and set(evidence['masters'])==set(evidence['primary_masters'])=={'30','60'},
         'Stable and primary dual masters required')
    stage=read_json(evidence['stable_source'],'stable source stage')
    need(stage['kind']=='newperiod_stable_source_stage_v1' and stage['passed'] is True
         and stage['sensitivity']==stable.sensitivity()
         and stage['selection']['sha256']==stable.STABLE_SELECTION_FILE_SHA256,'Frozen stable source required')
    masters={};cohorts={};metadata={}
    for d,ref in evidence['masters'].items():
        master=read_json(ref,'stable own-target master');primary=read_json(evidence['primary_masters'][d],'primary population metadata')
        need(master['delta_s']==primary['delta_s']==int(d) and master['manifest_kind']==primary['manifest_kind']=='custodian_master'
             and primary['source_manifest_sha256']==stage['primary_queries'][d]['sha256']
             and master['stable_source']==evidence['stable_source'] and master['stable_peer']==stable.sensitivity()
             and master['history_root']==stage['history_root'] and master['history_source_digest']==stage['history_source_digest'],
             'Stable master/source/history differs')
        project=lambda doc:sorted((r['event_id'],r['onset'],r['incident_id']) for r in doc['events'])
        need(project(master)==project(primary),'Stable changed primary IDs or clock')
        ids=[r[0] for r in project(master)]
        need(ids==sorted(set(ids))==stage['full_query_ids'],'Stable full population differs')
        masters[d]=master;cohorts[d]=ids;metadata[d]=project(master)
    need(cohorts['30']==cohorts['60'],'Stable horizons lost primary IDs')
    return dict(input_only=True,cohort_ids=cohorts,label_horizon={'30':'30','60':'60'},
        validated_target_scope={'stable_source':evidence['stable_source'],'selection':stage['selection']},
        target_masters=masters,expected_label_masters=evidence['masters'],metadata=metadata,
        target_scope='stable_peer_only',source_stage=stage)


def prepare_sealed(custody,seal,family_freeze,evidence,read_json,read_input):
    """All 24 retained cells checked before any target-bearing section is opened."""
    e=source_evidence(evidence,read_json)
    arms=family_freeze['arms'];expected={m.key(r) for r in roles()}
    need(len(arms)==24 and {m.key(a['role']) for a in arms}==expected and len({a['arm_id'] for a in arms})==24,
         'Complete24 fixed stable identities required')
    committed={a['arm_id']:a for a in custody['arms']};failed={a['arm_id']:a for a in custody.get('retained_failures',[])}
    sealed={a['arm_id']:a for a in seal['arms']}
    need(len(committed)==len(custody['arms']) and len(failed)==len(custody.get('retained_failures',[]))
         and len(sealed)==len(seal['arms']) and not set(committed)&set(failed),'Conflicting global retention')
    relevant=[a for a in [*committed.values(),*failed.values()] if a.get('role',{}).get('variant')=='stable']
    need({a['arm_id']:a for a in relevant}=={a['arm_id']:a for a in arms},'Stable global/family retention differs')
    cells={}
    for arm in arms:
        name=arm['arm_id'];d=str(arm['role']['horizon_seconds'])
        if arm['status']=='not_executable':
            need(failed.get(name)==arm and arm.get('failure_chain'),'Retained upstream failure required')
            for ref in arm['failure_chain']:read_json(ref,'stable upstream failure')
            cells[name]=dict(status='not_estimable',role=arm['role'],failure_chain=arm['failure_chain']);continue
        need(arm['status']=='committed_for_prediction' and committed.get(name)==arm and name in sealed,'Exact sealed stable cell required')
        bound=sealed[name]
        commitment=read_json({'path':arm['commitment_path'],'sha256':bound['commitment_sha256']},'sealed stable commitment')
        need(commitment['predictions_sha256']==bound['predictions_sha256']
             and commitment['stable_source']==evidence['stable_source'] and commitment['stable_peer']==stable.sensitivity(),
             'Stable commitment/source scope differs')
        manifest=read_json({'path':arm['manifest_path'],'sha256':arm['manifest_sha256']},'stable issue-input manifest')
        need(manifest['parent_master_sha256']==evidence['masters'][d]['sha256'],'Stable export has another master')
        predictions=read_json({'path':arm['predictions_path'],'sha256':bound['predictions_sha256']},'sealed stable predictions')
        inputs={}
        for row in manifest['events']:
            if row['input_status']!='available':continue
            data=read_input({'path':row['input_path'],'sha256':row['input_sha256']},'stable issue-time input')
            need(data['event_id']==row['event_id'],'Stable input identity differs');inputs[row['event_id']]=data
        cell=m.check_cell(arm,dict(manifest=manifest,predictions=predictions,commitment=commitment,inputs=inputs),e,family='stable')
        if arm['role'].get('baseline')=='persistence':
            for row in predictions:
                need(set(row['predicted_asns'])==set(row['seed_asns']), 'Persistence must predict exactly its observed seeds')
                need(all(value==0 for asn,value in zip(row['candidate_asns'],row.get('ranking_scores',[]),strict=True)
                         if asn not in row['seed_asns']),'Persistence has no nonseed ranking')
        need(sorted((r['event_id'],r['onset'],r['incident_id']) for r in cell['rows'])==e['metadata'][d],
             'Stable export changed primary metadata')
        if arm['role']['family']=='neural':
            role={**arm['role'],'variant':'core'}
            primary=[a for a in committed.values() if m.key(a['role'])==m.key(role)]
            need(len(primary)==1 and primary[0]['status']=='committed_for_prediction'
                 and primary[0]['arm_id'] in sealed and arm['model_sha256']==primary[0]['model_sha256'],
                 'Stable must reuse matching sealed updated N-core checkpoint')
        cells[name]=cell
    # Derive the input-available comparison before seeing any target. Different
    # statuses across methods would make that comparison outcome-dependent.
    available={}
    for d in ('30','60'):
        views=[[(r['event_id'],r['input_status']) for r in c['rows']] for c in cells.values()
               if c['status']=='committed' and str(c['role']['horizon_seconds'])==d]
        need(not views or all(v==views[0] for v in views),'Stable methods use different input populations')
        available[d]=[eid for eid,status in views[0] if status=='available'] if views else []
    return copy.deepcopy(dict(cells=cells,evidence=e,available=available))


def evaluate(prepared,stable_table):
    """Already captured own-target section only; full-reference truth is refused."""
    e=prepared['evidence']
    need(stable_table['kind']=='custodian_stable_label_table' and stable_table['target_scope']=='stable_peer_only'
         and stable_table['provenance']['reference_scope']==e['validated_target_scope']
         and stable_table['provenance']['masters']==e['expected_label_masters'],'Stable own-target lineage required')
    need(set(stable_table['horizons'])=={'30','60'},'Exact stable horizons required')
    for d,labels in stable_table['horizons'].items():
        need(set(labels)==set(e['cohort_ids'][d]),'Stable truth lost full primary population')
        for truth in labels.values():
            need(truth['target_scope']=='stable_peer_only' and truth['target_status'] in ('scorable','censored'),
                 'Stable truth status/scope differs')
            if truth['target_status']=='censored':
                need('target_asns' not in truth and 'target_counts' not in truth,'Censored stable truth cannot be imputed')
            else:need(truth['selection_sha256']==stable.STABLE_SELECTION_SHA256,'Stable truth selection differs')
    cells={}
    for name,cell in prepared['cells'].items():
        report=(persistence(cell,e,stable_table) if cell['status']=='committed'
                and cell['role'].get('baseline')=='persistence' else m.score_cell(cell,e,stable_table))
        if report['status']=='scored':
            allowed=set(prepared['available'][str(cell['role']['horizon_seconds'])])
            report['input_available_rows']=[r for r in report['rows'] if r['event_id'] in allowed]
        cells[name]=report
    return dict(kind='newperiod_stable_secondary_v1',target_scope='stable_peer_only',cells=cells,
        input_available_cohort=prepared['available'],declares_primary_finding=False,formal_tests=False,
        intervals_computed=False,fits=0,model_input_distribution='stable-filtered inputs, unchanged updated N-core weights')


def persistence(cell,evidence,table):
    """Original Jaccard and empty-ranking semantics, without invented scores.

    Custody baselines use ranking_scores, whereas the retrospective persistence
    row schema differs. Persistence has no ranking (original evaluator note),
    so score the empty new-member ranking instead of assigning tied candidates.
    """
    from collections import Counter
    from bgbench.forecast_ranking import event_ranking_metrics
    labels=m.labels_for(cell,evidence,table)
    rows=m.original.per_event_rows(cell['predictions'],cell['rows'],labels,baseline=True,inputs=cell['inputs'],candidates='matched')
    for row in rows:
        truth=labels[row['event_id']]
        ranking=event_ranking_metrics([],[],truth['target_asns'],row['seed_asns'],status=row['ranking_status'])
        row.update({k:ranking[k] for k in ('average_precision','precision_at','recall_at','coverage_ceiling')})
        row.update(probability_calibration=None,calibration_eligible=False,predicted_count=None,smape_2h=None,
                   curve_smape=None,curve_cover80=None,count_forecast_status='not_committed_in_numeric_custody_schema')
        if row['input_status']!='available':
            penalty=dict(event_id=row['event_id'],baseline='history-knn-mean',candidate_asns=[],seed_asns=[],predicted_asns=[],ranking_scores=[],extent=0.)
            target=dict(event_id=row['event_id'],asn=m.np.asarray([]),seed_asns=m.np.asarray([]),target_asns=m.np.asarray(truth['target_asns']))
            point=m.scoring.score_membership([penalty],[target])[0]
            row.update(predicted_count=0.,smape_2h=point['smape_2h'],abstention_count_penalty=True)
    return dict(status='scored',role=cell['role'],rows=rows,reference_events=len(labels),scorable_events=len(rows),
        censored_events=len(labels)-len(rows),input_status_counts=dict(Counter(r['input_status'] for r in cell['rows'])))
