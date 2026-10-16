"""Independently replay a compact, explicit boundary source-equivalence bridge."""
from __future__ import annotations
import argparse
import json
import time
from pathlib import Path
import polars as pl
from boundary_input_bridge import content_hash,restore_table,restore_floor
from verify_nongraph_boundary_inputs import eligible,consumed_columns,content,sha

BRIDGE='analysis/boundary-input-bridge.json'
EQUIVALENCE='analysis/nongraph-boundary-input-equivalence.json'
PROOF='analysis/boundary-input-verification.json'


def verify(data,bridge_path,equivalence_path,proof_path,private=False,floor_path=None):
    bridge=json.loads(bridge_path.read_text());raw=json.loads(equivalence_path.read_text())
    assert bridge['schema_version']==1 and bridge['transformation']=='archive_predecessor_correction_with_explicit_input_equivalence_v1'
    assert raw['status']=='passed' and raw['mode']=='private_consumed_input_equivalence'
    assert sha(equivalence_path)==bridge['private_equivalence_sha256']
    wanted=[i for i in range(98) if i!=62]
    assert bridge['equivalent_tasks']==raw['equivalent_tasks']==wanted
    assert bridge['rerun_tasks']==raw['rerun_tasks']==[62]
    tasks=bridge['tasks'];assert [t['index'] for t in tasks]==list(range(98))
    assert len(raw['tasks'])==98 and [t['task_index'] for t in raw['tasks']]==list(range(98))
    records={r['path']:r for r in bridge['tables']}
    assert len(records)==len(bridge['tables'])
    old={};new={};sources={}
    for path,record in records.items():
        new[path]=pl.read_parquet(data/path);old[path]=restore_table(new[path],record)
        sources[path]=sha(data/path)
    floorrecord=bridge['prefix_floor'];floorrelative=floorrecord['path']
    actualfloor=floor_path or data/floorrelative
    floor_new=pl.read_parquet(actualfloor);floor_old=restore_floor(floor_new,floorrecord)
    sources[floorrelative]=sha(actualfloor)
    for task,claim in zip(tasks,raw['tasks']):
        assert claim['task_index']==task['index'] and claim['kind']==task['kind'] and claim['year']==task['year']
        path=claim['event_table'];assert path in records
        floor=None
        if task['kind'] in ('prefix_model','prefix_features'):
            if task['year']==2025:floor=floor_old
            else:
                rel=f"eventset/{task['year']}_leak/prefix_floor.parquet"
                floor=pl.read_parquet(data/rel);sources[rel]=sha(data/rel)
        columns=[c for c in consumed_columns(task) if c in old[path].columns]
        assert columns==claim['consumed_columns']
        before=eligible(old[path],task,floor).select(columns)
        after=eligible(new[path],task,floor).select(columns)
        assert content(before)==claim['before_input_sha256'] and content(after)==claim['after_input_sha256'], ('projection hash mismatch',task['index'])
        assert before.height==claim['before_rows'] and after.height==claim['after_rows']
        assert sorted(set(before['event_id'])-set(after['event_id']))==claim['removed_event_ids']
        assert sorted(set(after['event_id'])-set(before['event_id']))==claim['added_event_ids']
        if task['index']!=62:
            assert before.equals(after,null_equal=True) and claim['status']=='equivalent' and not claim['raw_changed'], ('non-equivalent preserved task',task['index'])
        else:
            assert claim['status']=='rerun_required' and len(claim['removed_event_ids'])==1 and not claim['added_event_ids']
            assert set(claim['removed_event_ids'])=={r['event_id'] for r in floorrecord['removed_rows']}
    evidence={BRIDGE:sha(bridge_path),EQUIVALENCE:sha(equivalence_path)}
    proof={'status':'passed','mode':'private_source_audit','equivalent_tasks':wanted,'rerun_tasks':[62],
           'source_sha256':sources,'evidence_sha256':evidence,'table_content':{p:{k:v[k] for k in ('before_content_sha256','after_content_sha256')} for p,v in records.items()}}
    for relative,digest in sources.items():
        path=actualfloor if relative==floorrelative else data/relative
        assert sha(path)==digest, ('source changed during verification',relative)
    assert sha(bridge_path)==evidence[BRIDGE] and sha(equivalence_path)==evidence[EQUIVALENCE]
    if private:
        proof_path.write_text(json.dumps(proof,indent=2)+'\n')
    else:
        saved=json.loads(proof_path.read_text())
        for key in ('status','mode','equivalent_tasks','rerun_tasks','source_sha256','evidence_sha256','table_content'):
            assert saved[key]==proof[key], ('boundary proof mismatch',key)
    return {'tables':records,'prefix_floor':floorrecord,'restored_tables':old,'restored_floor':floor_old,'proof':proof,'equivalence':raw}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--wait-for-marker',type=Path,action='append',default=[]);a=p.parse_args()
    while not all(x.is_file() for x in a.wait_for_marker):time.sleep(10)
    manifest=json.loads((a.run/'expected-nongraph.json').read_text())
    spec=next(s for s in manifest['nongraph_tables'] if s['kind']=='prefix_floor' and s['event_table']=='2025_leak')
    root=json.loads((a.run/'nongraph-release-complete.json').read_text())['data_root']
    floor=a.run/root/spec['rows'].removeprefix('analysis/nongraph/')
    result=verify(a.run/'data',a.run/'boundary-input-bridge.json',a.run/'boundary-audit/nongraph-input-equivalence.json',a.run/'boundary-input-verification.json',True,floor)
    print(json.dumps({'status':result['proof']['status'],'equivalent_tasks':len(result['proof']['equivalent_tasks'])}))
