"""Declare expected non-graph evidence from the frozen task plan, never outputs."""
import argparse
import json
from pathlib import Path


def build(plan):
    required, tables = [], []
    for task in plan:
        year, kind = task['year'], task['kind']
        folder = f"analysis/nongraph/{year}/{task['index']:03d}_{kind}"
        required.append(folder+'/complete.json')
        spec = {'kind':kind,'event_table':f'{year}_leak'}
        if kind == 'cascade':
            a = task['args']
            tag = a.get('set_tag','')
            suffix = ('_coaffection' if a.get('coaffection') else '') + (f'_{tag}' if tag else '')
            suffix += f"_ge{a['min_asns']}" if a.get('min_asns') else ''
            suffix += f"_sir{a['rec']}" if a.get('rec',1)<1 else ''
            suffix += '_vf' if a.get('valley_free') else ''
            name = f"cascade_vs_persistence_{a.get('delta','d5m')}_{a.get('target','final_2h')}{suffix}"
            spec.update(summary=folder+'/'+name+'.json',rows=folder+'/'+name+'.parquet',event_table=f'{year}_{tag}' if tag else str(year))
        elif kind == 'curve_naive':
            name = 'curve_baselines_leak_ge200_asn'
            spec.update(summary=folder+'/'+name+'.json',rows=folder+'/'+name+'_predictions.parquet',sample=400)
        elif kind in ('tsfm','chronos_lora'):
            spec.update(summary=folder+'/summary.json',rows=folder+'/summary.predictions.parquet')
            if kind == 'tsfm': spec['sample']=150
            if kind == 'chronos_lora':
                spec['eligibility'] = folder+'/curve_eligibility.parquet'
                required.append(spec['eligibility'])
                required += [folder+'/chronos2_lora_final/'+name for name in ('reproduction.json','adapter_config.json','adapter_model.safetensors')]
        elif kind == 'prefix_floor':
            spec.update(summary=folder+'/prefix_floor_summary.json',rows=folder+'/prefix_floor.parquet')
        elif kind == 'prefix_model':
            required += [folder+'/prefix_model.joblib',folder+'/prefix_model_metadata.json']
            floor = next(t for t in plan if t['year']==year and t['kind']=='prefix_floor')
            spec.update(summary=folder+'/prefix_model_summary_d30s.json',rows=folder+'/prefix_model_test_d30s.parquet',predictions_dir=folder+'/prefix_predictions',prefix_floor=f"analysis/nongraph/{year}/{floor['index']:03d}_prefix_floor/prefix_floor.parquet")
        elif kind == 'radar_prefix_agreement':
            required += [folder+'/cloudflare_leaks_prefixes_reconstructed'+suffix for suffix in ('.json','.parquet')]
            continue
        else:
            assert kind == 'prefix_features'
            continue
        tables.append(spec)
        required += [spec['summary'],spec['rows']]
    result = {'nongraph_tables':tables,'required_files':required}
    cascade_2025 = {t['index'] for t in plan if t['kind'] == 'cascade' and t['year'] == 2025}
    if set(range(49, 60)) <= cascade_2025:
        result['cascade_bootstrap'] = 'analysis/nongraph-cascade-bootstrap.json'
        required.append(result['cascade_bootstrap'])
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    result=build(json.loads(args.plan.read_text()))
    args.output.write_text(json.dumps(result,indent=1)+'\n')
    print(json.dumps({'tables':len(result['nongraph_tables']),'required_files':len(result['required_files'])}))
