"""Fixed count secondaries beside original primary scoring, one captured label table.

Custody execution component only. Call inside the separately authorized R2 runner
after its actual source/runtime/resource/retention checks. No launcher or approval
issuer. The original one-batch marker and every original primary check remain.
"""
import hashlib
import json
import types
from pathlib import Path
import numpy as np

TARGETS=(300,900,3600,7200)
PRIMARY_SHA='1619b3286cc5a61c6ceb4aee1ae7bb32c78262c47faf5ea4730c3b647f6fe078'
SCORING_SHA='740bf610afc2d2cdaae40e8726ab6bd8ab9b38d5e6db262a4f0b7f7a14bc4c3d'

def need(ok,why):
    if not ok:raise ValueError(why)

def private_primary(original):
    """Preserve all original functions; route nonprimary baseline variants separately."""
    private=types.ModuleType(original.__name__+'_private_r2')
    private.__dict__.update(original.__dict__)
    for name,value in list(private.__dict__.items()):
        if isinstance(value,types.FunctionType) and value.__globals__ is original.__dict__:
            fn=types.FunctionType(value.__code__,private.__dict__,value.__name__,value.__defaults__,value.__closure__)
            fn.__kwdefaults__=value.__kwdefaults__;private.__dict__[name]=fn
    old=private.role_arm
    def role_arm(role):
        if role.get('family')=='baseline' and role.get('variant') not in (None,'core'):return None
        return old(role)
    private.role_arm=role_arm
    return private

def count_roles():
    return ([dict(family='N-counts',model=m,bin_seconds=b,horizon_seconds=d,seed=0)
             for m in ('boosted','saturating','persistence') for b in (1,15) for d in (30,60)]
          + [dict(family='N-tsfm',model=m,bin_seconds=b,horizon_seconds=d,seed=0)
             for m in ('chronos','moirai','timesfm') for b in (1,15) for d in (30,60)]
          + [dict(family='N-chronos-ad',model='chronos',bin_seconds=15,horizon_seconds=d,seed=s)
             for s in range(5) for d in (30,60)])

def cell_id(role):return '{family}-{model}-bin{bin_seconds}-d{horizon_seconds}-s{seed}'.format(**role)

def prepare_counts(custody,seal,family_freeze,read_json):
    """Validate all count forecast bytes BEFORE the single label opening.

    read_json(ref,purpose) must be the caller's bounded, hash-checking logged
    reader. Upstream failures must be frozen in BOTH global and family retention.
    They remain explicit not-estimable entries; no forecast is fabricated.
    """
    expected={cell_id(role):role for role in count_roles()}
    declared=family_freeze['arms']
    need(len(declared)==34 and {a['arm_id']:a['role'] for a in declared}==expected,'Exact34 count-family retention required')
    committed={a['arm_id']:a for a in custody['arms']}
    sealed={a['arm_id']:a for a in seal['arms']}
    failed={a['arm_id']:a for a in custody.get('retained_failures',[])}
    need(len(committed)==len(custody['arms']) and len(sealed)==len(seal['arms'])
         and len(failed)==len(custody.get('retained_failures',[])) and not set(committed)&set(failed),'Duplicate/conflicting retention status')
    need({a['arm_id']:a['role'] for a in list(committed.values())+list(failed.values())
          if a.get('role',{}).get('family') in ('N-counts','N-tsfm','N-chronos-ad')}==expected,'Global count-family retention differs')
    prepared={}
    for arm in declared:
        name=arm['arm_id'];role=arm['role']
        if arm['status']=='not_executable':
            need(name in failed and failed[name]==arm and arm.get('failure_chain'),'Globally retained original upstream failure required')
            for cause in arm['failure_chain']:read_json(cause,'retained count upstream failure')
            prepared[name]={'status':'not_estimable','role':role,'failure_chain':arm['failure_chain']};continue
        need(arm['status']=='committed_for_prediction' and name in committed and name in sealed,'Missing sealed count forecast')
        bound=committed[name]
        need(all(bound.get(key)==value for key,value in arm.items()),'Global/family count freeze mismatch')
        commitment=read_json({'path':arm['commitment_path'],'sha256':sealed[name]['commitment_sha256']},'sealed count commitment')
        need(commitment['role']==role and commitment['arm_id']==name and commitment['label_free_input_files'] is True
             and commitment['test_labels_used'] is False and commitment['fitting_performed'] is False
             and commitment['calibration_changed'] is False,'Count commitment scientific identity differs')
        for key in ('manifest','input_gate','checkpoint'):
            need(commitment[key+'_sha256']==arm[('model' if key=='checkpoint' else key)+'_sha256'],'Count commitment input/model differs')
        need(commitment['predictions_sha256']==sealed[name]['predictions_sha256']
             and commitment['sidecar']['path']==arm['sidecar_path'],'Sealed count prediction/sidecar differs')
        manifest=read_json({'path':arm['manifest_path'],'sha256':arm['manifest_sha256']},'sealed count manifest')
        need(manifest['delta_s']==role['horizon_seconds'] and manifest['bin_seconds']==role['bin_seconds'],'Count grid differs')
        rows=manifest['events'];ids=sorted(x['event_id'] for x in rows)
        need(ids==arm['event_ids'] and len(ids)==len(set(ids)),'Exact count event population required')
        predictions=read_json({'path':arm['predictions_path'],'sha256':sealed[name]['predictions_sha256']},'sealed count predictions')
        need([x['event_id'] for x in predictions]==ids and commitment['event_ids']==ids,'Count forecasts reordered or missing')
        q=np.asarray([x['curve_log_quantiles'] for x in predictions],dtype=float)
        need(q.shape==(len(ids),4,3) and np.isfinite(q).all() and (q>=0).all()
             and (np.diff(q,axis=1)>=0).all() and (np.diff(q,axis=2)>=0).all(),'Malformed count forecasts')
        need(all(x['observation_cutoff_s']==role['horizon_seconds'] for x in predictions),'Count cutoff differs')
        probabilistic=role['family']!='N-counts' or role['model']=='boosted'
        need(probabilistic or np.array_equal(q[:,:,0],q[:,:,1]) and np.array_equal(q[:,:,1],q[:,:,2]),'Point controls must repeat a point')
        statuses={x['event_id']:x['input_status'] for x in rows}
        sidecar=read_json(commitment['sidecar'],'sealed count raw/trajectory/status sidecar')
        available=[eid for eid in ids if statuses[eid]=='available']
        need(sidecar['statuses']==statuses and sidecar['event_ids']==available and sidecar['targets_s']==list(TARGETS),'Count sidecar population/status differs')
        for i,eid in enumerate(ids):
            need(statuses[eid] in ('available','unavailable_no_input','source_failure','parser_failure','technical_failure'),'Unclassified count input status')
            if statuses[eid]!='available':need((q[i]==0).all(),'Flagged abstention forecast must be zero')
        if role['family']!='N-counts':
            for key in ('raw_count_quantiles','trajectory_log_quantiles'):
                values=np.asarray(sidecar[key],dtype=float)
                if not available and sidecar[key]==[]:values=values.reshape(0,4,3)
                need(values.shape==(len(available),4,3) and np.isfinite(values).all(),'Incomplete reference sidecar')
        prepared[name]={'status':'committed','role':role,'event_ids':ids,'quantiles':q,'input_statuses':statuses,
                        'probabilistic':probabilistic,'manifest_rows':rows,'commitment':sealed[name]}
    return prepared

def score_counts(prepared,label_table,original_score_curves):
    """Original fixed count metrics; censored truth absent, abstentions flagged."""
    need(label_table.get('kind')=='custodian_label_table','Original custody label table required')
    report={}
    for name,cell in prepared.items():
        if cell['status']=='not_estimable':report[name]=dict(cell,declares_primary_finding=False);continue
        role=cell['role'];labels=label_table['horizons'][str(role['horizon_seconds'])]
        need(set(labels)==set(cell['event_ids']),'Count truth must cover full reference population')
        indices=[];targets=[];censored=[]
        for i,eid in enumerate(cell['event_ids']):
            label=labels[eid];need(label['target_status'] in ('scorable','censored'),'Explicit target status required')
            if label['target_status']=='censored':censored.append(eid);continue
            counts=label['target_counts'];need(set(counts)=={str(t) for t in TARGETS},'Allfour original count targets required')
            values=[counts[str(t)] for t in TARGETS]
            need(all(type(v) is int and v>=0 for v in values) and values==sorted(values)
                 and values[-1]==len(set(label['target_asns'])),'Invalid raw-first-seen count truth')
            indices.append(i);targets.append(values)
        ids=[cell['event_ids'][i] for i in indices]
        scored=original_score_curves({'event_ids':ids,'log_quantiles':cell['quantiles'][indices]},
            {'event_ids':ids,'target':np.asarray(targets).reshape(-1,4)},target_seconds=TARGETS,
            context_seconds=np.arange(0,role['horizon_seconds']+1,role['bin_seconds']),probabilistic=cell['probabilistic'])
        for row in scored:
            state=cell['input_statuses'][row['event_id']];row['input_status']=state
            if state!='available':
                row.update(calibration_eligible=False,calibration_status='no_input' if state=='unavailable_no_input' else 'technical_failure',
                           curve_cover80=None,curve_log_pinball=None,curve_interval80_width=None)
        report[name]={'status':'scored' if scored else 'not_estimable','role':role,'declares_primary_finding':False,
            'reference_events':len(cell['event_ids']),'scorable_events':len(scored),'censored_event_ids':censored,
            'mean_smape':float(np.mean([row['curve_smape'] for row in scored])) if scored else None,
            'per_event':scored,'commitment':cell['commitment']}
    return {'kind':'newperiod_count_secondaries_v1','declares_primary_finding':False,'targets_s':list(TARGETS),'cells':report}

def evaluate_with_counts(original,primary_args,primary_kwargs,prepared,original_score_curves):
    """Run original primary evaluator and score counts from the SAME captured label read.

    prepared must come from prepare_counts before invocation, under exact caller
    approval. This never opens a second label table or resets an original marker.
    """
    need(hashlib.sha256(Path(original.__file__).read_bytes()).hexdigest()==PRIMARY_SHA
         and original_score_curves.__name__=='score_curves'
         and hashlib.sha256(Path(original_score_curves.__globals__['__file__']).read_bytes()).hexdigest()==SCORING_SHA,
         'Original primary and count numerical sources required')
    need(set(prepared)=={cell_id(role) for role in count_roles()},'Complete34-cell prepared count retention required')
    private=private_primary(original);old=private.bound_json;captured=[]
    def bound_json(path,sha,what):
        value=old(path,sha,what)
        if what=='Custodian label table':
            need(not captured,'Second label opening refused');captured.append(value)
        return value
    private.bound_json=bound_json
    primary=private.evaluate_new_period(*primary_args,**primary_kwargs)
    need(len(captured)==1,'Original one-batch label capture missing')
    secondary=score_counts(prepared,captured[0],original_score_curves)
    return primary,secondary
