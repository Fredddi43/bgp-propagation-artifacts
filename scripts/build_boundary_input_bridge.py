"""Freeze a reversible compact bridge before canonical boundary publication."""
from pathlib import Path
import argparse
import json
import polars as pl
from boundary_input_bridge import make_record,content_hash
from verify_nongraph_boundary_inputs import sha


def build(run):
    candidate=json.loads((run/'boundary-audit/candidate-manifest.json').read_text())
    assert candidate['status']=='ready'
    rawpath=run/'boundary-audit/nongraph-input-equivalence.json'
    raw=json.loads(rawpath.read_text())
    assert raw['status']=='passed' and raw['equivalent_tasks']==[i for i in range(98) if i!=62] and raw['rerun_tasks']==[62]
    before=run/'data';after=Path(candidate['candidate_data_root'])
    paths={r['event_table'] for r in raw['tasks']}
    countbridge=json.loads((run/'derived-count-fill-bridge.json').read_text())
    paths.update(r['path'] for r in countbridge['tables'])
    records=[make_record(path,pl.read_parquet(before/path),pl.read_parquet(after/path)) for path in sorted(paths)]
    floorpath='eventset/2025_leak/prefix_floor.parquet'
    floor=pl.read_parquet(before/floorpath)
    removed=raw['tasks'][62]['removed_event_ids']
    revised=floor.filter(~pl.col('event_id').is_in(removed))
    floorrecord={'path':floorpath,'before_columns':floor.columns,'before_content_sha256':content_hash(floor),
                 'after_content_sha256':content_hash(revised),'removed_rows':floor.filter(pl.col('event_id').is_in(removed)).to_dicts(),
                 'before_rows':floor.height,'after_rows':revised.height}
    assert len(floorrecord['removed_rows'])==1
    return {'schema_version':1,'transformation':'archive_predecessor_correction_with_explicit_input_equivalence_v1',
            'tables':records,'prefix_floor':floorrecord,'tasks':json.loads((run/'nongraph-plan.json').read_text()),
            'equivalent_tasks':raw['equivalent_tasks'],'rerun_tasks':[62],
            'private_equivalence_sha256':sha(rawpath),'candidate_manifest_sha256':sha(run/'boundary-audit/candidate-manifest.json')}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);a=p.parse_args()
    output=a.run/'boundary-input-bridge.json';assert not output.exists(),'preserve frozen bridge'
    output.write_text(json.dumps(build(a.run),indent=2,default=str)+'\n')
