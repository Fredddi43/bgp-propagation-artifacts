"""Gate source publication on complete, scoped predecessor archive evidence."""
from __future__ import annotations
import argparse
from collections import defaultdict
import datetime as dt
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import polars as pl
from assess_archive_predecessors import metrics


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path,value):
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(value,indent=1));temporary.replace(path)


def task_failures(task,report,plan_hash,code_hash):
    errors=[]
    if report.get('task')!=task['index'] or report.get('events')!=task['events'] or report.get('url')!=task['url'] or report.get('collector')!=task['collector']:
        errors.append('task_scope_mismatch')
    if report.get('boundary_plan_sha256')!=plan_hash or report.get('code_sha256')!=code_hash:
        errors.append('task_provenance_mismatch')
    if report.get('status') not in ('complete','archive_gap'):
        errors.append('nonterminal_task_status')
    if report.get('status')=='archive_gap' and report.get('error')!='404':
        errors.append('transient_failure_reported_as_gap')
    if report.get('status')=='complete' and not report.get('archive_sha256'):
        errors.append('missing_archive_digest')
    if report.get('status')=='complete':
        counts=report.get('in_window_rows',{});parts=report.get('parts',{})
        if set(counts)!=set(task['events']) or any(type(n)!=int or n<0 for n in counts.values()):
            errors.append('invalid_event_counts')
        elif set(parts)!={key for key,n in counts.items() if n>0}:
            errors.append('event_parts_do_not_match_counts')
        for key,path in parts.items():
            family,eid=key.split(':',1)
            expected=f"parts/{family}/{eid}/{task['collector']}__predecessor_{task['index']}.parquet"
            if path!=expected:errors.append('unexpected_part_path')
        if not report.get('transport_url') or report.get('bytes',0)<=0:
            errors.append('missing_archive_transport_provenance')
    return errors


def pre(run,repair=None):
    repair=repair or run/'crossday-repair'
    root=run/'boundary-audit';plan=json.loads((root/'plan.json').read_text());impact=json.loads((root/'impact.json').read_text())
    dispatch=json.loads((root/'dispatch.json').read_text());plan_hash=sha(root/'plan.json');code_hash=sha(run/'code/scripts/audit_archive_predecessors.py')
    failures=[];bindings={};reports={}
    if any(dt.datetime.fromisoformat(event['w_start']).microsecond for event in plan['events'].values()):
        raise ValueError('MRT header cutoff requires integral event window starts')
    if [task['index'] for task in plan['tasks']]!=list(range(len(plan['tasks']))):
        raise ValueError('boundary plan task IDs are not exact sequential scope')
    actual_ids={int(p.stem) for p in (root/'tasks').glob('*.json')}
    if actual_ids!=set(range(len(plan['tasks']))):
        raise ValueError('boundary terminal report IDs do not match exact plan scope')
    scope_file=root/'scope-verification.json'
    scope=json.loads(scope_file.read_text())
    if scope.get('status')!='passed':failures.append({'reason':'event_collector_scope_proof_failed'})
    if dispatch['plan_sha256']!=plan_hash or dispatch['code_sha256']!=code_hash or impact['plan_sha256']!=plan_hash:
        failures.append({'reason':'frozen_plan_or_worker_changed'})
    def read(task):
        file=root/'tasks'/f"{task['index']}.json"
        return task['index'],json.loads(file.read_text()),str(file.relative_to(run)),sha(file)
    with ThreadPoolExecutor(max_workers=16) as pool:
        for index,report,path,digest in pool.map(read,plan['tasks']):
            reports[index]=report;bindings[path]=digest
            for reason in task_failures(plan['tasks'][index],report,plan_hash,code_hash):failures.append({'task':index,'reason':reason})
    if impact['expected_tasks']!=len(plan['tasks']) or impact['completed_tasks']!=len(plan['tasks']):
        failures.append({'reason':'incomplete_impact_population'})
    if impact.get('overhang_exceeding_one_period'):
        failures.append({'reason':'additional_predecessor_period_required','tasks':impact['overhang_exceeding_one_period']})
    reuse=json.loads((root/'reused-parts-sha256.json').read_text())
    if reuse.get('status')!='passed' or reuse.get('reuse_proof_sha256')!=sha(root/'already-fetched-predecessors.json') or plan['reuse_proof_sha256']!=reuse.get('reuse_proof_sha256'):
        failures.append({'reason':'reused_parts_proof_failed_or_stale'})
    for path,digest in scope.get('inputs_sha256',{}).items():
        if sha(run/path)!=digest:failures.append({'path':path,'reason':'stale_scope_proof'})
    def validate_parts(item):
        index,report=item;errors=[];task=plan['tasks'][index]
        for key,path in report.get('parts',{}).items():
            part=root/path
            count=pl.scan_parquet(part).select(pl.len()).collect().item()
            if count!=report['in_window_rows'][key]:errors.append({'task':index,'event':key,'reason':'part_row_count_mismatch'})
        if report.get('status')=='complete' and report.get('retained_mrt_records')==0:
            earliest=min(dt.datetime.fromisoformat(plan['events'][key]['w_start']).timestamp() for key in task['events'])
            latest=report.get('archive_timestamp_max')
            if (latest and dt.datetime.fromisoformat(latest).timestamp()>=earliest) or any(report['in_window_rows'].values()):
                errors.append({'task':index,'reason':'invalid_zero_retained_record_skip'})
        if report.get('archive_timestamp_max'):
            maximum=dt.datetime.fromisoformat(report['archive_timestamp_max']).timestamp()
            if maximum>task['ts_start']+2*task['step']:
                errors.append({'task':index,'reason':'archive_overhang_exceeds_one_period'})
        return errors
    with ThreadPoolExecutor(max_workers=16) as pool:
        for errors in pool.map(validate_parts,reports.items()):failures.extend(errors)
    expected_events=defaultdict(set)
    for task in plan['tasks']:
        for key in task['events']:expected_events[key].add(task['index'])
    actual_events={(event['tag'] or 'origin')+':'+event['event_id']:event for event in impact['events']}
    if len(actual_events)!=len(impact['events']) or set(actual_events)!=set(expected_events):
        failures.append({'reason':'impact_event_population_mismatch'})
    for key,event in actual_events.items():
        if set(event['source_tasks'])!=expected_events.get(key,set()):failures.append({'event':key,'reason':'impact_task_scope_mismatch'})
        expected_gaps={i for i in expected_events[key] if reports[i]['status']=='archive_gap'}
        if set(event['archive_gap_tasks'])!=expected_gaps:failures.append({'event':key,'reason':'impact_gap_scope_mismatch'})
        if event['predecessor_rows']!=sum(reports[i].get('in_window_rows',{}).get(key,0) for i in expected_events[key]):
            failures.append({'event':key,'reason':'impact_row_count_mismatch'})
        if bool(expected_gaps)!=(event['status']=='coverage_gap'):
            failures.append({'event':key,'reason':'impact_gap_status_mismatch'})
    canonical={};unresolved=[];gap_exclusions=[]
    for event in impact['events']:
        family=event['tag'] or 'origin';folder=repair/'events'/family/event['event_id']
        summary=json.loads((folder/'summary.json').read_text())
        if event['status']=='coverage_gap':
            canonical[str((folder/'summary.json').relative_to(run))]=sha(folder/'summary.json')
            if not summary.get('error'):
                unresolved.append({'event_id':event['event_id'],'tag':event['tag'],'tasks':event['archive_gap_tasks']})
            else:gap_exclusions.append({'event_id':event['event_id'],'tag':event['tag'],'error':summary['error'],'tasks':event['archive_gap_tasks']})
        if event['status']=='candidate':
            if metrics(folder)!=event['new']:
                failures.append({'event_id':event['event_id'],'reason':'canonical_measurements_differ_from_boundary_candidate'})
            candidate=run/event['candidate_replay']
            for name,digest in event['candidate_files_sha256'].items():
                if sha(candidate/name)!=digest or not (folder/name).is_file() or sha(folder/name)!=digest:
                    failures.append({'event_id':event['event_id'],'file':name,'reason':'canonical_candidate_file_mismatch'})
            for file in folder.iterdir():
                if file.is_file():canonical[str(file.relative_to(run))]=sha(file)
        for path,digest in event['added_parts_sha256'].items():
            if sha(run/path)!=digest:failures.append({'path':path,'reason':'predecessor_part_changed'})
            bindings[path]=digest
    if unresolved:failures.append({'reason':'unresolved_predecessor_gaps','events':unresolved})
    audit_file=run/'full-replay-invariants.json';audit=json.loads(audit_file.read_text());changes=repair/'input-changes.json'
    if audit.get('failures')!=[] or sha(changes) not in audit.get('inputs_sha256',{}).values():
        failures.append({'reason':'full_replay_audit_not_bound_to_final_comparison'})
    incremental_file=repair/'incremental-comparison-verification.json'
    if incremental_file.exists():
        incremental=json.loads(incremental_file.read_text())
        if incremental.get('status')!='passed' or incremental.get('comparison_sha256')!=sha(changes):
            failures.append({'reason':'incremental_comparison_proof_failed'})
        for path,digest in incremental.get('source_sha256',{}).items():
            if sha(run/path)!=digest:failures.append({'path':path,'reason':'incremental_comparison_source_changed'})
        bindings[str(incremental_file.relative_to(run))]=sha(incremental_file)
        original_comparison=run/'crossday-repair/input-changes.json'
        bindings[str(original_comparison.relative_to(run))]=sha(original_comparison)
    for file in [root/'plan.json' ,root/'dispatch.json',root/'impact.json',root/'already-fetched-predecessors.json',root/'reused-parts-sha256.json',scope_file,audit_file,changes]:
        bindings[str(file.relative_to(run))]=sha(file)
    for file in [run/'code/scripts/verify_archive_boundaries.py',run/'code/scripts/assess_archive_predecessors.py',run/'code/rust/bgbench-parse/target/release/bgbench-parse',run/'code/rust/bgbench-parse/Cargo.lock',run/'code/rust/bgbench-parse/src/main.rs']:
        bindings[str(file.relative_to(run))]=sha(file)
    result={'status':'passed' if not failures else 'failed','passed':not failures,'repair_root':str(repair),'expected_tasks':len(plan['tasks']),'terminal_tasks':len(reports),
            'task_status_counts':{status:sum(r['status']==status for r in reports.values()) for status in ('complete','archive_gap')},
            'scoped_reused_parts':reuse.get('parts'),'changed_events':impact['changed_events'],'explicit_gap_exclusions':gap_exclusions,'unresolved_gaps':unresolved,
            'max_archive_overhang_s':impact['max_archive_overhang_s'],'source_files_sha256':bindings,'canonical_replay_files_sha256':canonical,
            'prepublication_event_tables_sha256':table_hashes(run),'failures':failures}
    atomic(run/'boundary-prepublication-verification.json',result);return result


def table_hashes(run):
    return {f"eventset/{year}{'_'+tag if tag else ''}/events.parquet":sha(run/'data/eventset'/(str(year)+('_'+tag if tag else ''))/'events.parquet')
            for year in range(2022,2027) for tag in ('','leak','withdrawal')}


def final(run):
    pre_file=run/'boundary-prepublication-verification.json';previous=json.loads(pre_file.read_text());failures=[]
    if previous.get('status')!='passed':failures.append({'reason':'prepublication_boundary_proof_failed'})
    bindings={**previous['source_files_sha256'],**previous['canonical_replay_files_sha256']}
    def check(item):
        path,digest=item
        return None if sha(run/path)==digest else {'path':path,'reason':'source_changed_after_prepublication_check'}
    with ThreadPoolExecutor(max_workers=16) as pool:failures.extend(x for x in pool.map(check,bindings.items()) if x)
    result={'status':'passed' if not failures else 'failed','passed':not failures,'prepublication_verification_sha256':sha(pre_file),
            'published_event_tables_sha256':table_hashes(run),'expected_tasks':previous['expected_tasks'],'terminal_tasks':previous['terminal_tasks'],'repair_root':previous['repair_root'],
            'unresolved_gaps':previous['unresolved_gaps'],'explicit_gap_exclusions':previous['explicit_gap_exclusions'],'failures':failures,
            'validation_scope':'Complete predecessor coverage and canonical replay binding; full-publication-verification.json independently checks every published repaired row after source-marker creation.'}
    atomic(run/'boundary-source-verification.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['pre','final']);p.add_argument('run',type=Path);p.add_argument('--repair-root',type=Path);a=p.parse_args()
    result=pre(a.run,a.repair_root) if a.mode=='pre' else final(a.run)
    print(json.dumps({k:v for k,v in result.items() if k not in ('source_files_sha256','canonical_replay_files_sha256')},indent=1),flush=True)
    raise SystemExit(0 if result['status']=='passed' else 1)
