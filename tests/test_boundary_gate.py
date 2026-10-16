import importlib.util
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import verify_archive_boundaries as gate


def test_boundary_gate_rejects_unscoped_or_transient_terminal_reports():
    task={'index':3,'events':['leak:example'],'url':'https://example/archive','collector':'rrc00'}
    report={'task':3,'events':task['events'],'url':task['url'],'boundary_plan_sha256':'p','code_sha256':'c','status':'complete','archive_sha256':'a','collector':'rrc00','transport_url':'https://example/archive','bytes':5,'in_window_rows':{'leak:example':0},'parts':{}}
    assert gate.task_failures(task,report,'p','c')==[]
    assert 'task_scope_mismatch' in gate.task_failures(task,{**report,'events':[]},'p','c')
    assert 'task_provenance_mismatch' in gate.task_failures(task,report,'other','c')
    assert 'transient_failure_reported_as_gap' in gate.task_failures(task,{**report,'status':'archive_gap','error':'timeout'},'p','c')

    assert 'invalid_event_counts' in gate.task_failures(task,{**report,'in_window_rows':{}},'p','c')
    changed={**report,'in_window_rows':{'leak:example':1},'parts':{'leak:example':'wrong.parquet'}}
    assert 'unexpected_part_path' in gate.task_failures(task,changed,'p','c')
