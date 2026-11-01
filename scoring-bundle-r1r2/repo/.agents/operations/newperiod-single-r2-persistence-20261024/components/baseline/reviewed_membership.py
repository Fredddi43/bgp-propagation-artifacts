"""Fixed sensitivity scores from already sealed payloads and ONE captured label table.

Pure in-memory consumer: no file reads, label opening, calibration or inference.
The owning R2 caller verifies the seal, hashes, provenance and authority before
passing these documents; prepare() runs before its original one-time label barrier.
"""
import copy
import ast
import json
import math
import hashlib
import types
from pathlib import Path, PurePosixPath
from collections import Counter
import numpy as np
from bgbench import forecast_custodian_eval as original
from bgbench import forecast_retrospective_scoring as scoring
from bgbench import forecast_panel_scoring as panel

HORIZONS=(30,60)
TARGETS=(300,900,3600,7200)
FAMILIES=('h1','h3','timing','history','ordinary')
TARGET_SCOPE_SHA='a932948e9226f1b9da3971f808e508a0137d0d5ba6b9dddb4955c8d630a68474'
target_source=Path(__file__).with_name('reviewed_target_scope.py').read_bytes()
if hashlib.sha256(target_source).hexdigest()!=TARGET_SCOPE_SHA:raise ValueError('Reviewed target-scope helper changed')
from bgbench.forecast_inputs import panel as normalize_panel
target_scope=types.ModuleType('reviewed_target_scope')
target_scope.__dict__.update(copy=copy,json=json,hashlib=hashlib,PurePosixPath=PurePosixPath,normalize_panel=normalize_panel)
_target_names={'need','checked_bytes','document','reference','reference_panel'}
_target_nodes=[n for n in ast.parse(target_source).body if isinstance(n,ast.FunctionDef) and n.name in _target_names or isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='COLLECTOR_RECIPE_SHA256' for t in n.targets)]
exec(compile(ast.Module(body=_target_nodes,type_ignores=[]),'<reviewed target scope>','exec'),target_scope.__dict__)

REFERENCE=('route-views.linx','route-views2','route-views3','rrc00','rrc01','rrc03','rrc12','rrc15','rrc20','rrc25')

def need(ok,why):
    if not ok:raise ValueError(why)

def roles(family):
    if family=='ordinary':
        return ([dict(family='temporal',variant='core',training='updated',panel='reference',history='on',model=m,horizon_seconds=d,seed=s)
                 for m in ('gru','tgn','mean') for d in HORIZONS for s in range(5)]
                +[dict(family='gbdt',variant='core',training='updated',panel='reference',history='on',model='gbdt_membership',horizon_seconds=d,seed=0) for d in HORIZONS])
    if family=='h1':
        return [dict(family='neural',variant='h1',training='updated',panel='reference',history='on',candidate_history_k=500,
                     message_passing=m,horizon_seconds=d,seed=s) for m in ('sage','none') for d in HORIZONS for s in range(5)]
    if family=='timing':
        return [dict(family='neural',variant='timing',training='updated',panel='reference',history='on',message_passing=m,
                     horizon_seconds=d,seed=s) for m in ('sage','none') for d in (5,10,30,60,300,900) for s in range(5)]
    if family=='h3':
        return [dict(stage=stage,panel=p,message_passing=m,history='on',horizon_seconds=d,seed=s)
                for stage in ('frozen','refit') for p in ('ris7','mixed7') for m in ('sage','none') for d in HORIZONS for s in range(5)]
    need(family=='history','Undeclared sensitivity family')
    result=[]
    for v in ('delay900','delay1800','withhold'):
        for d in HORIZONS:
            for m in (('sage','none') if v=='withhold' else ('sage',)):
                for s in range(5):result.append(dict(family='neural',variant=v,training='updated',panel='reference',history='on',message_passing=m,horizon_seconds=d,seed=s))
            for candidates in (('matched','native') if v=='withhold' else ('matched',)):
                result.append(dict(family='baseline',variant=v,panel='reference',baseline='history-knn-mean',candidates=candidates,library='online',horizon_seconds=d))
    return result

def key(role):
    # JSON-like canonical identity without the bool==int pitfall.
    return tuple(sorted((k,type(v).__name__,v) for k,v in role.items()))

def comparator_key(role):
    if role.get('family')=='baseline':return ('baseline',role['candidates'],role['horizon_seconds'],None)
    return ('neural',role['message_passing'],role['horizon_seconds'],role['seed'])

def check_target_selector(arm,manifest,evidence):
    selector=manifest['reference_collectors']
    if selector==list(REFERENCE):return
    need(selector=='pooled' and evidence.get('validated_target_scope') is not None,'Exact bound pooled target lineage required')
    delta=evidence['label_horizon'][str(manifest['delta_s'])]
    primary=evidence['target_masters'][delta]
    need(primary['reference_collectors']=='pooled','Pooled selector changed')
    original_rows={r['event_id']:r for r in primary['events']}
    need(all(row['event_id'] in original_rows and all(row[k]==original_rows[row['event_id']][k] for k in ('event_id','onset','incident_id')) for row in manifest['events']), 'Pooled target identity/source cohort differs')


def check_cell(arm,data,evidence,*,family):
    role=arm['role'];d=role['horizon_seconds'];manifest=data['manifest'];predictions=data['predictions'];commitment=data['commitment'];inputs=data['inputs']
    rows=sorted(manifest['events'],key=lambda r:r['event_id']);ids=[r['event_id'] for r in rows]
    need(ids==arm['event_ids'] and len(ids)==len(set(ids)) and manifest['delta_s']==d,'Exact arm population/horizon required')
    expected=evidence['cohort_ids'][str(d)]
    need(ids==expected,'Frozen input-only cohort differs')
    need(commitment['arm_id']==arm['arm_id'] and commitment['label_free_input_files'] is True,'Sealed scientific identity differs')
    if commitment.get('kind')=='newperiod_baseline_commitment_v1':
        # The original deterministic producer binds its configuration hash and
        # source refs, rather than repeating the already frozen arm role.
        need(role.get('family')=='baseline' and role.get('variant') in (None,'core')
             and commitment['sources']==arm['baseline_sources']
             and commitment['predictor_received_source_graphs'] is False
             and commitment['predictor_received_full_history_library'] is False,
             'Original baseline commitment/source binding differs')
        need('role' not in commitment and 'test_labels_used' not in commitment,
             'Unexpected original baseline commitment schema')
    else:
        need(commitment['role']==role and commitment['test_labels_used'] is False,'Sealed scientific identity differs')
    need(all(not ({'baseline','candidate_protocol','extent'} & set(row)) for row in predictions),
         'Prediction descriptions/extent are outside the original custody schema')
    need(commitment['manifest_sha256']==arm['manifest_sha256'] and commitment['input_gate_sha256']==arm['input_gate_sha256']
         and commitment['checkpoint_sha256']==arm['model_sha256'],'Sealed input/model binding differs')
    check_target_selector(arm,manifest,evidence)
    need(set(inputs)=={r['event_id'] for r in rows if r['input_status']=='available'},'Exact available issue-input population required')
    baseline=role.get('family')=='baseline';candidates=role.get('candidates','matched') if baseline else 'matched'
    issue=evidence.get('issue_time',{}).get(str(d));rule=evidence.get('slice_rules',{}).get(str(d)) if family=='h1' else None
    need(family!='h1' or issue is not None and rule is not None,'H1 requires its fixed common slice and committed decisions')
    original.check_rows_label_free(predictions,rows,baseline=baseline,inputs=inputs,candidates=candidates,issue_time=issue,slice_rule=rule)
    indexed={r['event_id']:r for r in predictions}
    for meta in rows:
        row=indexed[meta['event_id']]
        if meta['input_status']!='available':continue
        if not baseline:
            probabilities=np.asarray(row['probabilities'],dtype=float)
            need(np.isfinite(probabilities).all() and ((0<=probabilities)&(probabilities<=1)).all()
                 and type(row['threshold']) in (int,float) and math.isfinite(row['threshold']),'Finite committed probabilities/threshold required')
            predicted=set(row['seed_asns'])|{a for a,p in zip(row['candidate_asns'],probabilities,strict=True) if p>=row['threshold']}
            need(predicted==set(row['predicted_asns']),'Committed global decision differs')
        if 'curve_log_quantiles' in row:
            panel.check_curve(row['curve_log_quantiles'],len(row['seed_asns']),temporal_monotone=True)
            need(row['observation_cutoff_s']==d,'Committed curve cutoff differs')
    cell=dict(status='committed',arm_id=arm['arm_id'],role=role,rows=rows,predictions=predictions,inputs=inputs,
              commitment=commitment,baseline=baseline,candidates=candidates,issue_time=issue,slice_rule=rule)
    if family=='h3':
        aligned=commitment['panel_alignment'];need([r['event_id'] for r in aligned]==ids,'Sealed H3 alignment lost rows')
        for meta,a in zip(rows,aligned,strict=True):
            p=indexed[meta['event_id']];available=meta['input_status']=='available'
            need(a['arm']==role['panel'] and a['horizon_seconds']==d and a['family']=='learned'
                 and a['forecast_available'] is available,'H3 alignment identity/availability differs')
            if available:
                need(a['input_status']=='available' and a['candidate_asns']==p['candidate_asns']
                     and a['input_seed_asns']==p['seed_asns'] and a['predicted_asns']==p['predicted_asns']
                     and np.array_equal(a['curve_log_quantiles'],p['curve_log_quantiles'])
                     and a['predicted_count']==panel.point_count(p['curve_log_quantiles']), 'H3 alignment changed a committed forecast')
            else:
                expected_status='no_input' if meta['input_status']=='unavailable_no_input' else meta['input_status']
                need(a['input_status']==expected_status and a['predicted_count']==0 and a['candidate_asns']==a['predicted_asns']==[]
                     and not a['calibration_eligible'],'H3 technical/no-input distinctions must remain explicit')
        cell['aligned']=aligned
    return cell

def prepare(family,records,loaded,evidence):
    """All input-only checks, no labels. `loaded` has hash-verified sealed documents.

    evidence contains full-reference target scope, exact cohort IDs, explicit
    label_horizon mapping, and already sealed primary comparator cells. Each
    comparator entry has `arm` and `data` in the same shape as a family cell.
    The owning caller binds evidence and every declared failure to the same seal.
    """
    evidence=copy.deepcopy(evidence)
    need(family in FAMILIES and evidence['input_only'] is True,'Fixed input-only family required')
    need('validated_target_scope' not in evidence and 'target_masters' not in evidence,'Derived target lineage cannot be supplied')
    if 'pooled_target_lineage' in evidence:
        line=evidence['pooled_target_lineage'];masters=line['masters']
        docs={d:target_scope.document(v) for d,v in masters.items()}
        collectors,scope=target_scope.reference_panel(masters,docs,line['collector_inventory'],line['source_inventories'],line['recipe'])
        need(collectors==list(REFERENCE),'Fixed full reference collector universe differs')
        evidence['validated_target_scope']=scope;evidence['target_masters']=docs
        evidence['expected_label_masters']={d:target_scope.reference(v) for d,v in masters.items()}
    need(evidence['target_scope']=={'panel':'reference','kind':'full_reference_membership','collectors':list(REFERENCE)},'Explicit full reference target scope required')
    need(len(records)==len(roles(family)) and {key(a['role']) for a in records}=={key(r) for r in roles(family)}
         and len({a['arm_id'] for a in records})==len(records),'Complete exact frozen family required')
    horizons={str(r['horizon_seconds']) for r in roles(family)}
    need(set(evidence['cohort_ids'])==set(evidence['label_horizon'])==horizons
         and all(ids==sorted(set(ids)) for ids in evidence['cohort_ids'].values())
         and all(v in ('30','60') for v in evidence['label_horizon'].values()),'Explicit cohort/primary-label mapping required')
    if family=='timing':need(len({tuple(v) for v in evidence['cohort_ids'].values()})==1,'All six timing horizons use one frozen cohort')
    need(set(loaded)=={a['arm_id'] for a in records if a['status']=='committed_for_prediction'},'No omitted or extra sealed payloads')
    if family=='ordinary':
        need(evidence['comparators']==[], 'Ordinary methods have no newly declared contrasts')
        need(all(a['status']=='not_executable' and a.get('selection_sha256')=='52d1a0f0a2effcb0400837180da74facb1ef7749d17f8269529c5c01ddf9ae1b'
                 for a in records if a['role']['model'] in ('tgn','mean')), 'Original TGN/Mean failed selection must remain retained')
    cells={}
    for arm in records:
        if arm['status']=='not_executable':
            need(arm.get('failure_chain'),'Original terminal failure chain required')
            cells[arm['arm_id']]=dict(status='not_estimable',role=arm['role'],failure_chain=arm['failure_chain']);continue
        need(arm['status']=='committed_for_prediction','Undeclared cell disposition')
        cells[arm['arm_id']]=check_cell(arm,loaded[arm['arm_id']],evidence,family=family)
    populations={}
    for cell in cells.values():
        if cell['status']!='committed':continue
        projection=[(r['event_id'],r['onset'],r['incident_id']) for r in cell['rows']]
        need(populations.setdefault(cell['role']['horizon_seconds'],projection)==projection,'Same-horizon reference metadata differs')
    comparators={}
    if family not in ('timing','ordinary'):
        required={comparator_key(r) for r in roles(family)}
        for item in evidence['comparators']:
            arm=item['arm'];role=arm['role'];k=comparator_key(role)
            need(k not in comparators and k in required and role.get('variant') in (None,'core')
                 and role.get('panel')=='reference' and (role.get('family')=='baseline' and role.get('baseline')=='history-knn-mean'
                 and role.get('library')=='online' or role.get('family')=='neural' and role.get('training')=='updated' and role.get('history')=='on'), 'Exact matching N-core/history comparator required')
            if arm['status']=='not_executable':
                need(arm.get('failure_chain'),'Retained primary failure required');comparators[k]=dict(status='not_estimable',role=role,failure_chain=arm['failure_chain'])
            else:comparators[k]=check_cell(arm,item['data'],evidence,family='h1' if family=='h1' else 'primary')
        need(set(comparators)==required,'Every fixed comparator must be retained')
    for cell in cells.values():
        if cell['status']!='committed' or family in ('timing','ordinary'):continue
        base=comparators[comparator_key(cell['role'])]
        if base['status']!='committed':continue
        if family=='history' and not cell['baseline'] or family=='h3' and cell['role']['stage']=='frozen':
            need(cell['commitment']['checkpoint_sha256']==base['commitment']['checkpoint_sha256'],'Frozen sensitivity must reuse matching N-core checkpoint')
        if family=='h3':
            need([(r['event_id'],r['onset'],r['incident_id']) for r in cell['rows']]==[(r['event_id'],r['onset'],r['incident_id']) for r in base['rows']],'Panel/reference metadata differs')
            continue
        need([(r['event_id'],r['onset'],r['incident_id'],r['input_status']) for r in cell['rows']]
             ==[(r['event_id'],r['onset'],r['incident_id'],r['input_status']) for r in base['rows']], 'Paired full reference metadata differs')
        need([r['seed_asns'] for r in cell['predictions']]==[r['seed_asns'] for r in base['predictions']], 'History/H1 paired seeds differ')
    evidence=copy.deepcopy(evidence)
    if family=='h3':
        evidence['h3_cohorts']={}
        for delta in HORIZONS:
            d=str(delta);ids=evidence['cohort_ids'][d];views=evidence['availability'][d]
            need(set(views)=={'reference','ris7','mixed7'} and set(evidence['reference_seeds'][d])==set(ids),'Full reference seeds/three-panel availability required')
            for name,view in views.items():
                need(set(view)==set(ids) and all(v['status'] in ('available','no_input','technical_failure','source_failure','parser_failure')
                     and type(v['partial_panel_input']) is bool for v in view.values()),'Explicit full panel availability required')
            available=[eid for eid in ids if all(view[eid]['status']=='available' for view in views.values())]
            complete=[eid for eid in available if not any(view[eid]['partial_panel_input'] for view in views.values())]
            evidence['h3_cohorts'][d]={'full_reference':ids,'common_available':available,'common_complete':complete}
            for cell in cells.values():
                if cell['status']!='committed' or cell['role']['horizon_seconds']!=delta:continue
                view=views[cell['role']['panel']]
                need(all(view[r['event_id']]['status']==r['input_status'] and view[r['event_id']]['partial_panel_input']==r['partial_panel_input'] for r in cell['aligned']), 'H3 committed alignment differs from frozen availability')
            for k,cell in comparators.items():
                if cell['status']!='committed' or cell['role']['horizon_seconds']!=delta:continue
                pred={r['event_id']:r for r in cell['predictions']}
                for row in cell['rows']:
                    eid=row['event_id'];status='no_input' if row['input_status']=='unavailable_no_input' else row['input_status']
                    need(views['reference'][eid]['status']==status and sorted(pred[eid]['seed_asns'])==evidence['reference_seeds'][d][eid], 'Primary reference availability/seeds differ')
    return copy.deepcopy(dict(family=family,cells=cells,comparators=comparators,evidence=evidence))

def labels_for(cell,evidence,label_table):
    d=str(cell['role']['horizon_seconds']);labels=label_table['horizons'][evidence['label_horizon'][d]]
    ids=[r['event_id'] for r in cell['rows']]
    need(set(ids)<=set(labels),'Captured full reference labels missing cohort rows')
    if evidence.get('family')!='timing':
        # Timing alone is a prospective subset; primary labels otherwise cover full N.
        need(set(ids)==set(labels),'Full N reference denominator differs')
    return {eid:labels[eid] for eid in ids}

def event(meta,inputs,label):
    counts=label['target_counts'];need(set(counts)=={str(t) for t in TARGETS},'All original curve targets required')
    curve=np.asarray([counts[str(t)] for t in TARGETS])
    need(all(type(counts[str(t)]) is int and counts[str(t)]>=0 for t in TARGETS)
         and (np.diff(curve)>=0).all() and curve[-1]==len(set(label['target_asns'])),'Invalid reference count/membership truth')
    return dict(event_id=meta['event_id'],asn=np.asarray(inputs['asn']),seed_asns=np.asarray(inputs['seed_asns']),
                target_asns=np.asarray(label['target_asns']),curve=curve)

def score_cell(cell,evidence,label_table,*,reference_cell=None):
    if cell['status']!='committed':return copy.deepcopy(cell)
    labels=labels_for(cell,evidence,label_table)
    need(all(x['target_status'] in ('scorable','censored') for x in labels.values()),'Explicit target disposition required')
    rows=original.per_event_rows(cell['predictions'],cell['rows'],labels,baseline=cell['baseline'],inputs=cell['inputs'],
        candidates=cell['candidates'],issue_time=cell['issue_time'],slice_rule=cell['slice_rule'])
    available=[m for m in cell['rows'] if labels[m['event_id']]['target_status']=='scorable' and m['input_status']=='available']
    preds={p['event_id']:p for p in cell['predictions']}
    # The numeric-only custody schema deliberately omits these two descriptions.
    # Recover them from the already sealed role, never from labels or row guesses.
    scoring_rows=[]
    for meta in available:
        prediction=copy.deepcopy(preds[meta['event_id']])
        if cell['baseline']:
            prediction.update(baseline=cell['role']['baseline'],candidate_protocol=(
                'native_history_union' if cell['candidates']=='native' else 'matched'))
        scoring_rows.append(prediction)
    detail=scoring.score_membership(scoring_rows,
         [event(m,cell['inputs'][m['event_id']],labels[m['event_id']]) for m in available])
    detail={r['event_id']:r for r in detail}
    for row in rows:
        extra=detail.get(row['event_id'])
        if extra:
            need(extra['jaccard']==row['jaccard'],'Original membership evaluators disagree')
            row.update({k:v for k,v in extra.items() if k not in row})
            if cell['baseline'] or cell['role'].get('family')=='gbdt':
                # Neither original baseline producer commits an extent forecast.
                # Membership cardinality is not a substitute count prediction.
                row.update(predicted_count=None,smape_2h=None,curve_smape=None,curve_cover80=None,
                           count_forecast_status='not_committed_in_numeric_custody_schema')
        else:
            eid=row['event_id'];truth=labels[eid];d=cell['role']['horizon_seconds']
            # The protocol declares a zero-count operational penalty, never a
            # probabilistic forecast. Censored rows never reach this branch.
            penalty=dict(event_id=eid,baseline='history-knn-mean',candidate_asns=[],seed_asns=[],
                         predicted_asns=[],ranking_scores=[],extent=0.)
            point=scoring.score_membership([penalty],[dict(event_id=eid,asn=np.asarray([]),seed_asns=np.asarray([]),target_asns=np.asarray(truth['target_asns']))])[0]
            row.update(predicted_count=point['predicted_count'],smape_2h=point['smape_2h'],probability_calibration=None,
                       curve_smape=None,curve_cover80=None,calibration_eligible=False,abstention_count_penalty=True)
            if not cell['baseline'] and cell['role'].get('family')!='gbdt':
                target=event({'event_id':eid},{'asn':[],'seed_asns':[]},truth)['curve']
                curve=scoring.score_curves({'event_ids':[eid],'log_quantiles':np.zeros((1,4,3))},
                    {'event_ids':[eid],'target':target.reshape(1,4)},target_seconds=TARGETS,context_seconds=np.asarray([0,d]),probabilistic=False)[0]
                row['curve_smape']=curve['curve_smape']
    if 'aligned' in cell:
        scorable={r['event_id'] for r in rows};meta={r['event_id']:r for r in cell['rows']}
        events=[]
        for eid in sorted(scorable):
            reference={'asn':[], 'seed_asns':evidence['reference_seeds'][str(cell['role']['horizon_seconds'])][eid]}
            events.append(event(meta[eid],reference,labels[eid]))
        h3=scoring.score_panel([r for r in cell['aligned'] if r['event_id'] in scorable],
                              [p for p in cell['predictions'] if p['event_id'] in scorable],events)
        by_id={r['event_id']:r for r in h3}
        for row in rows:
            result=by_id[row['event_id']]
            # Preserve technical status from the custodian membership scorer; panel
            # arithmetic returns no_input for any unavailable forecast internally.
            row.update({k:v for k,v in result.items() if k not in ('input_status','ranking_status') and not (row.get('abstention_count_penalty') and k=='curve_smape')})
    return dict(status='scored',role=cell['role'],rows=rows,reference_events=len(labels),scorable_events=len(rows),
        censored_events=len(labels)-len(rows),input_status_counts=dict(Counter(m['input_status'] for m in cell['rows'])))

def paired(left,right,ids,metric='jaccard'):
    if left['status']!='scored' or right['status']!='scored':return dict(status='not_estimable',reason='A retained paired cell did not execute')
    a={r['event_id']:r for r in left['rows']};b={r['event_id']:r for r in right['rows']}
    need(set(a)==set(b),'Paired scorable population differs')
    ids=[eid for eid in ids if eid in a]
    return dict(status='scored',events=len(ids),metric='full_target_jaccard' if metric=='jaccard' else 'committed_two_threshold_jaccard',
        event_differences=[dict(event_id=eid,difference=a[eid][metric]-b[eid][metric]) for eid in ids],
        mean_difference=float(np.mean([a[eid][metric]-b[eid][metric] for eid in ids])) if ids else None)

def evaluate(prepared,label_table):
    """Consume the SAME captured original label table; never open or reload it."""
    need(label_table.get('kind')=='custodian_label_table','Original captured label table required')
    if prepared['evidence'].get('validated_target_scope') is not None:
        need(label_table['provenance']['reference_scope']==prepared['evidence']['validated_target_scope']
             and label_table['provenance']['masters']==prepared['evidence']['expected_label_masters'],'Captured labels use another pooled source scope')
    family=prepared['family'];evidence={**prepared['evidence'],'family':family};base={}
    for k,cell in prepared['comparators'].items():base[k]=score_cell(cell,evidence,label_table)
    scored={};contrasts=[]
    for name,cell in prepared['cells'].items():
        ref=None if family=='ordinary' else prepared['comparators'].get(comparator_key(cell['role']))
        scored[name]=score_cell(cell,evidence,label_table,reference_cell=ref)
    for name,cell in prepared['cells'].items():
        if family=='ordinary':continue
        role=cell['role'];d=role['horizon_seconds'];ids=evidence['cohort_ids'][str(d)]
        if family=='timing':
            if d==30:continue
            other=next(n for n,c in prepared['cells'].items() if c['role']['message_passing']==role['message_passing'] and c['role']['seed']==role['seed'] and c['role']['horizon_seconds']==30)
            right=scored[other];comparator=other
        else:comparator=str(comparator_key(role));right=base[comparator_key(role)]
        cohorts=evidence['h3_cohorts'][str(d)] if family=='h3' else {'fixed_timing' if family=='timing' else 'full_reference':ids}
        for cohort,selected in cohorts.items():
            for metric in (('jaccard','two_threshold_jaccard') if family=='h1' else ('jaccard',)):
                contrasts.append(dict(arm_id=name,comparator=comparator,training_seed=role.get('seed'),cohort=cohort,**paired(scored[name],right,selected,metric)))
    population=[]
    if family=='ordinary':
        for model in ('gru','tgn','mean','gbdt_membership'):
            for delta in HORIZONS:
                group=[cell for cell in scored.values() if cell['role']['model']==model and cell['role']['horizon_seconds']==delta]
                complete=all(cell['status']=='scored' for cell in group)
                population.append(dict(model=model,horizon_seconds=delta,planned_seeds=sorted(cell['role']['seed'] for cell in group),
                    completed_seeds=sorted(cell['role']['seed'] for cell in group if cell['status']=='scored'),
                    status='complete_planned_population' if complete else 'not_estimable',
                    partial_seed_reporting='descriptive_only' if not complete else None))
    return dict(kind='newperiod_membership_sensitivity_report_v1',family=family,declares_primary_finding=False,
        formal_tests=False,intervals_computed=False,selection_performed=False,cells=scored,contrasts=contrasts,
        planned_seed_population=population if family=='ordinary' else None,
        target_scope=evidence['target_scope'],label_horizon=evidence['label_horizon'],cohort_ids=evidence['cohort_ids'],
        h3_cohorts=evidence.get('h3_cohorts'),broader_training_reused_at_30_60_seconds=family=='timing')


def prepare_sealed(family,custody,seal,family_freeze,evidence,read_json,read_input):
    """Concrete prelabel reader chain, called under the owning one-batch guard.

    Both supplied readers MUST hash-check and durably log before reading bytes.
    evidence.comparator_arm_ids selects only the fixed identities validated by
    prepare(), never a scientific choice. The original owning batch still calls
    authorize_outcome_join for the complete custody seal before opening labels.
    """
    records=family_freeze['arms'];committed={a['arm_id']:a for a in custody['arms']}
    failed={a['arm_id']:a for a in custody.get('retained_failures',[])};sealed={a['arm_id']:a for a in seal['arms']}
    need(len(committed)==len(custody['arms']) and len(failed)==len(custody.get('retained_failures',[]))
         and len(sealed)==len(seal['arms']) and not set(committed)&set(failed),'No duplicate or conflicting global retention')
    expected={key(r) for r in roles(family)}
    relevant=[a for a in list(committed.values())+list(failed.values()) if key(a['role']) in expected]
    need(len(relevant)==len(records) and {a['arm_id']:a for a in relevant}=={a['arm_id']:a for a in records},'Global and family sensitivity retention must agree exactly')
    def load(arm):
        name=arm['arm_id']
        if arm['status']=='not_executable':
            need(failed.get(name)==arm and arm.get('failure_chain'),'Original globally retained upstream failure required')
            for ref in arm['failure_chain']:read_json(ref,'retained sensitivity failure chain')
            return None
        need(committed.get(name)==arm and name in sealed,'Exact sealed sensitivity/comparator cell required')
        bound=sealed[name]
        commitment=read_json({'path':arm['commitment_path'],'sha256':bound['commitment_sha256']},'sealed sensitivity commitment')
        need(commitment['predictions_sha256']==bound['predictions_sha256'],'Commitment and seal prediction hash differ')
        predictions=read_json({'path':arm['predictions_path'],'sha256':bound['predictions_sha256']},'sealed sensitivity predictions')
        manifest=read_json({'path':arm['manifest_path'],'sha256':arm['manifest_sha256']},'sealed sensitivity manifest')
        inputs={}
        for row in manifest['events']:
            if row['input_status']!='available':continue
            value=read_input({'path':row['input_path'],'sha256':row['input_sha256']},'sealed sensitivity issue-time input')
            need(value['event_id']==row['event_id'],'Issue-time payload identity differs');inputs[row['event_id']]=value
        return dict(manifest=manifest,predictions=predictions,commitment=commitment,inputs=inputs)
    loaded={}
    for arm in records:
        data=load(arm)
        if data is not None:loaded[arm['arm_id']]=data
    evidence=copy.deepcopy(evidence);names=evidence.pop('comparator_arm_ids')
    need(len(names)==len(set(names)) and not set(names)&{a['arm_id'] for a in records},'Comparator identities must be distinct')
    evidence['comparators']=[]
    for name in names:
        need(name in committed or name in failed,'Missing globally retained primary comparator')
        arm=committed.get(name,failed.get(name));evidence['comparators'].append(dict(arm=arm,data=load(arm)))
    return prepare(family,records,loaded,evidence)
