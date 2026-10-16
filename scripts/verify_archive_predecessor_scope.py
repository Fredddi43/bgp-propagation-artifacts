"""Independently check predecessor request/reuse coverage using the retained hash audit."""
import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
from pathlib import Path


def verify(run):
    bound=run/'boundary-audit';hashes={}
    def read(path):
        payload=path.read_bytes();hashes[str(path.relative_to(run))]=hashlib.sha256(payload).hexdigest()
        return json.loads(payload)
    original=read(run/'crossday-repair-plan.json');plan=read(bound/'plan.json')
    reused=read(bound/'already-fetched-predecessors.json');attestation=read(bound/'reused-parts-sha256.json')
    assert plan['source_plan_sha256']==hashes['crossday-repair-plan.json']
    assert plan['reuse_proof_sha256']==hashes['boundary-audit/already-fetched-predecessors.json']==attestation['reuse_proof_sha256']
    assert attestation['status']=='passed'
    assert plan['events']==original['events']
    expected={}
    for key,event in original['events'].items():
        start=dt.datetime.fromisoformat(event['w_start']).timestamp();assert start.is_integer()
        for i in event['tasks']:
            task=original['tasks'][i];collector=task['collector'];step=task['step']
            value=(int(start)//step*step-step,step)
            assert key in task['events']
            if (key,collector) in expected:assert expected[key,collector]==value
            expected[key,collector]=value
    accounted={};parts={};reports={};counts=Counter()
    for entry in reused:
        i=entry['source_task'];task=original['tasks'][i];collector=entry['collector']
        assert task['collector']==collector
        report=f'crossday-repair/tasks/{i}.json'
        assert entry['source_report']==report
        assert entry['source_report_sha256']==attestation['source_report_sha256'][report]
        reports[report]=entry['source_report_sha256']
        for key,part in entry['event_parts'].items():
            event=original['events'][key];pair=(key,collector)
            assert key in task['events'] and pair not in accounted
            assert entry['ts_start']==expected[pair][0]
            wanted=f"crossday-repair/parts/{event['tag'] or 'origin'}/{event['event_id']}/{collector}__{i}.parquet"
            assert part==wanted and part in attestation['parts_sha256']
            parts[part]=attestation['parts_sha256'][part];accounted[pair]='reused'
            counts['reused_'+(event['tag'] or 'origin')]+=1
    assert reports==attestation['source_report_sha256']
    assert parts==attestation['parts_sha256'] and len(parts)==attestation['parts']
    for i,task in enumerate(plan['tasks']):
        assert task['index']==i
        for key in task['events']:
            pair=(key,task['collector']);assert pair not in accounted
            assert (task['ts_start'],task['step'])==expected[pair]
            accounted[pair]='requested';counts['requested_'+(original['events'][key]['tag'] or 'origin')]+=1
    assert set(accounted)==set(expected)
    assert sum(v=='reused' for v in accounted.values())==plan['already_fetched_predecessor_event_collector_pairs']
    assert len(expected)==plan['event_collector_pairs']
    return {'status':'passed','scope':'Exact event/collector predecessor partition and frozen reuse-hash attestation; no repeated part scan',
            'event_collector_pairs':len(expected),'boundary_tasks':len(plan['tasks']),'counts':dict(counts),'inputs_sha256':hashes,
            'limitations':['Withdrawal reused parts establish metric sufficiency only if predecessor timestamps remain before identifier; they do not establish all-row retention.',
                           'One-predecessor coverage requires declared bounded archive spillover; final task report provenance and overhang bounds must be checked separately.']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=verify(a.run);a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
