"""Collect final forecast numbers and their exact input hashes for manuscript editing.

This is a factual intermediate, not an interpretation or a source of new metrics.
Numerical verification must already have passed before invoking this collector.
"""
import argparse
import hashlib
import json
from pathlib import Path
import polars as pl

parser=argparse.ArgumentParser()
parser.add_argument('data',type=Path)
parser.add_argument('model_manifest',type=Path)
parser.add_argument('auxiliary_manifest',type=Path)
parser.add_argument('output',type=Path)
parser.add_argument('--nongraph-manifest',type=Path)
parser.add_argument('--nongraph-root',type=Path)
args=parser.parse_args()
models=json.loads(args.model_manifest.read_text())
auxiliary=json.loads(args.auxiliary_manifest.read_text())
sources={}
def read_json(relative):
    path=(args.nongraph_root/relative.removeprefix('analysis/nongraph/')) if args.nongraph_root and relative.startswith('analysis/nongraph/') else args.data/relative
    sources[relative]=hashlib.sha256(path.read_bytes()).hexdigest()
    return json.loads(path.read_text())
proof=read_json('analysis/graph_auxiliary_verification.json')
assert proof['status']=='passed', 'Final auxiliary source audit is required'
facts={'models':{},'auxiliary':{},'cohorts':{}}
for csv in models['model_tables']:
    relative=csv.replace('_test_per_event.csv','_summary.json')
    summary=read_json(relative)
    facts['models'][csv]={'metrics':summary.get('final_test',summary),
        'training_events':summary.get('train_events',summary.get('n_train')),
        'test_events':summary.get('test_events',summary.get('n_test')),
        'protocol':summary.get('split_protocol')}
    sources[csv]=hashlib.sha256((args.data/csv).read_bytes()).hexdigest()
for relative in auxiliary['auxiliary_files']:
    if relative.endswith('.json') and not relative.endswith('graph_auxiliary_verification.json'):
        facts['auxiliary'][relative]=read_json(relative)
    elif relative.endswith('.csv') and not relative.endswith('_per_event.csv'):
        path=args.data/relative
        sources[relative]=hashlib.sha256(path.read_bytes()).hexdigest()
        facts['auxiliary'][relative]=pl.read_csv(path).to_dicts()
for contract in models['model_cohorts'].values():
    for relative in contract['index_tables']:
        if relative in facts['cohorts']:continue
        path=args.data/relative
        sources[relative]=hashlib.sha256(path.read_bytes()).hexdigest()
        facts['cohorts'][relative]=pl.read_csv(path).group_by('split').len().sort('split').to_dicts()
if args.nongraph_manifest:
    nongraph=json.loads(args.nongraph_manifest.read_text())
    facts['nongraph']={spec['summary']:read_json(spec['summary']) for spec in nongraph['nongraph_tables']}
    if nongraph.get('cascade_bootstrap'):
        facts['cascade_bootstrap']=read_json(nongraph['cascade_bootstrap'])
facts['source_sha256']=sources
facts['generator_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_text(json.dumps(facts,indent=2))
print(json.dumps({'models':len(facts['models']),'auxiliary':len(facts['auxiliary']),'cohorts':len(facts['cohorts'])}))
