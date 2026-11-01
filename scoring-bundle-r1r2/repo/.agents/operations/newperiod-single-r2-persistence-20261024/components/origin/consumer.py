"""Fixed own-family secondaries from the single captured R2 label bundle.

No acquisition, label opening, fit, calibration, or operation authority. Actual
own-family source/fit admissions are separately reviewed and externally bound.
"""
import copy,hashlib,types,posixpath
from pathlib import Path
from datetime import timedelta
from bgbench.forecast_protocol import utc
HERE=Path(__file__).resolve().parent
raw=(HERE/'reviewed_membership.py').read_bytes()
if hashlib.sha256(raw).hexdigest()!='2f40bf28ea95bf69df378c81fc1c57abacf306f9be59a55028397a70be36e006':
    raise ValueError('Reviewed numerical consumer changed')
m=types.ModuleType('origin_reviewed_membership');m.__file__=str(HERE/'reviewed_membership.py')
exec(compile(raw,m.__file__,'exec'),m.__dict__)
need=m.need
FAMILIES=('origin_change_invalid','origin_change_valid')


def independent(review):
    for key in ('reviewer_worker','reviewer_session'):
        value=review.get(key)
        need(isinstance(value,str) and value.startswith('/root/') and posixpath.normpath(value)==value
             and not any(c.isspace() for c in value) and value!='/root', 'Separate canonical origin reviewer required')
    need(review.get('reviewer_model'),'Truthful independent reviewer model required')


def roles(family):
    need(family in FAMILIES,'Exact RFC6811 origin stratum required')
    return [dict(family='neural',variant=family,training='updated',panel='reference',history='on',
        message_passing=model,horizon_seconds=h,seed=s)
        for model in ('sage','none') for h in (30,60) for s in range(5)]


def branch(projection):
    need(projection.get('kind')=='newperiod_family_metadata_projection_v1' and projection.get('metadata_only') is True
         and set(projection['internal'])==set(FAMILIES),'Reviewed complete origin metadata projection required')
    valid=projection['internal']['origin_change_valid'];n=valid['incident_count']
    need(type(n)is int and n>=0,'Exact incident count required')
    end=utc(valid['manifests']['30']['windows']['test_end']);base=utc('2026-10-16T00:00:00+00:00')
    weeks=(end-base).total_seconds()/(7*86400)
    need(weeks.is_integer() and 0<=weeks<=8,'Frozen whole-week limit required')
    expected='fit_twenty' if n>=100 else 'descriptive_only' if weeks==8 else 'extend_one_week'
    need(projection['valid_family_branch']==expected and projection['preseal_disclosure']=={'valid_family_incident_count':n}
         and projection['next_end_exclusive']==((end+timedelta(days=7)).isoformat() if expected=='extend_one_week' else None),
         'Frozen count-only branch differs')
    need(expected!='extend_one_week','Valid family still awaits its predeclared count-only calendar extension')
    return expected


def source_evidence(evidence,read):
    need(evidence.get('input_only') is True and set(evidence['masters'])==set(FAMILIES),'Both own origin strata required')
    projection=read(evidence['metadata_projection'],'origin cohort metadata');decision=branch(projection)
    review=read(evidence['source_review'],'origin source and sampling review');independent(review)
    need(review.get('passed') is True and review.get('scope')=='newperiod-family-source-cohort'
         and review.get('metadata_projection')==evidence['metadata_projection']
         and review.get('masters')==evidence['masters'] and review.get('source_coverage')==projection['coverage']
         and review.get('sampling_rule')==evidence['sampling_rule'],'Exact actual source/cohort/sampling evidence required')
    read(evidence['sampling_rule'],'prospectively bound origin acquisition rule')
    result={}
    for family in FAMILIES:
        refs=evidence['masters'][family];need(set(refs)=={'30','60'},'Both own family masters required')
        masters={h:read(ref,'own origin target master') for h,ref in refs.items()};ids={};metadata={}
        for h,master in masters.items():
            expected=projection['internal'][family]['manifests'][h]
            rows=[r for r in expected['events'] if r['split']=='test']
            project=lambda values:sorted((r['event_id'],utc(r['onset']),r['incident_id']) for r in values)
            need(master['manifest_kind']=='custodian_master' and master['event_family']==family and master['delta_s']==int(h)
                 and master['family_metadata_projection']==evidence['metadata_projection']
                 and master['family_sampling_rule']==evidence['sampling_rule']
                 and project(master['events'])==project(rows),'Own family population/clock/source differs')
            ids[h]=sorted(r['event_id'] for r in rows);metadata[h]=project(rows)
            info=projection['internal'][family];first={}
            for row in rows:
                if row['incident_id'] not in first or utc(row['onset'])<utc(first[row['incident_id']]['onset']):first[row['incident_id']]=row
            collapsed=len({(row['actor'],utc(row['onset']).date().isoformat()) for row in first.values()})
            need(info['incident_count']==len(first) and info['actor_day_collapsed_count']==collapsed
                 and info['limited_independent_support'] is (collapsed<100),'Original incident/actor-day metadata differs')
            need(len(ids[h])==len(set(ids[h])),'Duplicate family query')
            need(master['library_protocol']['family']=='' and master['library_protocol']['mode']=='shared_completed'
                 and master['feature_contract']['width']==16 and master['history_feature_indices']==[10],
                 'Original16-feature full origin history required')
        need(metadata['30']==metadata['60'],'Own family horizons disagree')
        result[family]=dict(input_only=True,cohort_ids=ids,metadata=metadata,label_horizon={'30':'30','60':'60'},
            target_masters=masters,expected_label_masters=refs,
            validated_target_scope={'event_family':family,'metadata_projection':evidence['metadata_projection'],
                                    'sampling_rule':evidence['sampling_rule']})
    return projection,decision,result


def prepare_sealed(custody,seal,freeze,evidence,read_json,read_input):
    projection,decision,scopes=source_evidence(evidence,read_json)
    arms=freeze['arms'];expected={m.key(r) for f in FAMILIES for r in roles(f)}
    need(len(arms)==40 and len({a['arm_id'] for a in arms})==40 and {m.key(a['role']) for a in arms}==expected,
         'All40 fixed family cells required')
    global_arms=custody['arms'];failures=custody.get('retained_failures',[])
    committed={a['arm_id']:a for a in global_arms};failed={a['arm_id']:a for a in failures};sealed={a['arm_id']:a for a in seal['arms']}
    need(len(committed)==len(global_arms) and len(failed)==len(failures) and len(sealed)==len(seal['arms'])
         and not set(committed)&set(failed),'Conflicting global family retention')
    relevant=[a for a in [*global_arms,*failures] if a.get('role',{}).get('variant') in FAMILIES]
    need({a['arm_id']:a for a in relevant}=={a['arm_id']:a for a in arms},'Global/own family retention differs')
    cells={}
    for a in arms:
        name=a['arm_id'];role=a['role'];family=role['variant'];h=str(role['horizon_seconds']);scope=scopes[family]
        if family=='origin_change_valid' and decision=='descriptive_only':
            need(a['status']=='not_executable' and failed.get(name)==a and a.get('disposition')=='descriptive_only_no_ranking'
                 and a.get('metadata_projection')==evidence['metadata_projection'] and name not in sealed,
                 'Eight-week descriptive branch must retain cells without model predictions/ranking')
            cells[name]=dict(status='descriptive_only_no_ranking',role=role);continue
        if a['status']=='not_executable':
            need(failed.get(name)==a and a.get('failure_chain') and name not in sealed,'Original upstream failure must remain global')
            for ref in a['failure_chain']:read_json(ref,'original origin family upstream failure')
            cells[name]=dict(status='not_estimable',role=role,failure_chain=a['failure_chain']);continue
        need(a['status']=='committed_for_prediction' and committed.get(name)==a and name in sealed,'Exact own-family sealed cell required')
        bound=sealed[name]
        commitment=read_json({'path':a['commitment_path'],'sha256':bound['commitment_sha256']},'sealed origin commitment')
        manifest=read_json({'path':a['manifest_path'],'sha256':a['manifest_sha256']},'own origin issue input')
        need(manifest['parent_master_sha256']==evidence['masters'][family][h]['sha256']
             and manifest['feature_contract']['width']==16
             and manifest['history_feature_indices']==[10],'Own16-feature origin export required')
        need(commitment['predictions_sha256']==bound['predictions_sha256']
             and commitment['family_metadata_projection']==evidence['metadata_projection']
             and commitment['family_sampling_rule']==evidence['sampling_rule'],'Own origin prediction lineage differs')
        fit=a['family_fit'];dev=read_json(fit['manifest'],'own family training provenance')
        receipt=read_json(fit['receipt'],'own family validation threshold')
        reviewed=read_json(fit['review'],'actual completed family fit review');independent(reviewed)
        need(dev['event_family']==family and dev['delta_s']==int(h) and dev['feature_contract']['width']==16
             and dev['history_feature_indices']==[10] and dev['family_metadata_projection']==evidence['metadata_projection']
             and receipt['manifest_sha256']==fit['manifest']['sha256'] and receipt['feature_contract']==dev['feature_contract']
             and receipt['seed']==role['seed'] and receipt['history']=='on' and receipt['test_inputs_opened'] is False
             and receipt['model']['message_passing']==role['message_passing'] and receipt['model']['in_dim']==16
             and receipt['threshold_calibration_split']=='validation','Own family fit/calibration required')
        need(reviewed.get('passed') is True and reviewed.get('scope')=='newperiod-family-completed-fit'
             and reviewed.get('role')==role and reviewed.get('manifest')==fit['manifest'] and reviewed.get('receipt')==fit['receipt']
             and reviewed.get('checkpoint')=={'path':a['model_path'],'sha256':a['model_sha256']},'Completed own fit review differs')
        predictions=read_json({'path':a['predictions_path'],'sha256':bound['predictions_sha256']},'sealed origin predictions')
        inputs={}
        for row in manifest['events']:
            if row['input_status']!='available':continue
            data=read_input({'path':row['input_path'],'sha256':row['input_sha256']},'own origin issue-time tensor')
            need(data['event_id']==row['event_id'],'Origin input identity differs');inputs[row['event_id']]=data
        cell=m.check_cell(a,dict(manifest=manifest,predictions=predictions,commitment=commitment,inputs=inputs),scope,family='origin')
        need(sorted((r['event_id'],utc(r['onset']),r['incident_id']) for r in cell['rows'])==scope['metadata'][h],
             'Own family export metadata differs')
        need(all(p['threshold']==receipt['threshold'] for p in predictions if p['event_id'] in inputs),'Own global validation threshold changed')
        cells[name]=cell
    return copy.deepcopy(dict(cells=cells,evidence=scopes,projection=projection,valid_branch=decision))


def evaluate(prepared,family_tables):
    need(set(family_tables)==set(FAMILIES),'Both captured own-family label sections required')
    result={}
    for family,table in family_tables.items():
        e=prepared['evidence'][family]
        need(table['kind']=='custodian_origin_label_table' and table['event_family']==family
             and table['target_scope']=='own_origin_family' and table['provenance']['reference_scope']==e['validated_target_scope']
             and table['provenance']['masters']==e['expected_label_masters'],'Own family truth provenance required')
        need(set(table['horizons'])=={'30','60'},'Both own target horizons required')
        for h,labels in table['horizons'].items():
            need(set(labels)==set(e['cohort_ids'][h]),'Missing own family targets')
            for truth in labels.values():
                need(truth['target_status'] in ('scorable','censored') and truth['event_family']==family,'Own family target status required')
                if truth['target_status']=='censored':need('target_asns' not in truth and 'target_counts' not in truth,'Censored truth cannot be imputed')
        cells={name:m.score_cell(cell,e,table) for name,cell in prepared['cells'].items() if cell['role']['variant']==family}
        metadata=prepared['projection']['internal'][family]
        result[family]=dict(cells=cells,incident_count=metadata['incident_count'],actor_day_collapsed_count=metadata['actor_day_collapsed_count'],
            limited_independent_support=metadata['limited_independent_support'],declares_primary_finding=False,formal_tests=False,intervals_computed=False,
            interpretation='RFC6811 origin-validity stratum, not confirmed hijacks')
    return dict(kind='newperiod_origin_family_secondaries_v1',families=result,valid_family_branch=prepared['valid_branch'],fits=0,
                declares_primary_finding=False,source_sampling_comparability='Bound prospective acquisition rule must be disclosed')
