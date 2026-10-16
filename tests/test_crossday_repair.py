import datetime as dt
import importlib.util
import json
from pathlib import Path

import polars as pl

from bgbench import config


def module():
    path = Path(__file__).parents[1] / "scripts" / "repair_crossday_replays.py"
    spec = importlib.util.spec_from_file_location("repair", path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_archive_blocks_include_partial_first_block_and_union_overlap():
    repair = module()
    lo = dt.datetime(2025, 1, 1, 23, 58, tzinfo=dt.UTC)
    hi = lo + dt.timedelta(minutes=8)
    intervals, step = repair.block_intervals([(lo, hi), (lo + dt.timedelta(minutes=3), hi)], "rrc00")
    assert step == 300
    assert intervals == [[int(lo.replace(minute=55).timestamp()), int(hi.replace(minute=10).timestamp())]]


def test_plan_has_distinct_both_day_slices_and_prioritizes_graph_events(tmp_path, monkeypatch):
    repair = module()
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    inventory = tmp_path / "inventory" / "2025"
    inventory.mkdir(parents=True)
    pl.DataFrame({"event_id": ["midnight"], "prefix": ["192.0.2.0/24"], "new_origin": [100],
                  "t0": ["2025-01-01T23:30:00"], "split": ["train"], "reason": ["stratified"]}).write_csv(inventory / "replay_manifest.tsv", separator="\t")
    graph = tmp_path / "tgn" / "2025_leak200" / "d30s"
    graph.mkdir(parents=True)
    (graph / "midnight.pt").touch()
    plan_file = tmp_path / "repair-plan.json"
    repair.prepare(plan_file)
    plan = json.loads(plan_file.read_text())
    assert len(plan["tasks"]) == 20
    assert len(plan["events"]["origin:midnight"]["tasks"]) == 20
    assert {task["label"] for task in plan["tasks"]} == {"2025-01-01", "2025-01-02"}
    assert all(task["priority"] for task in plan["tasks"])


def test_replay_overlay_redirects_only_repaired_event_and_preserves_original(tmp_path):
    path = Path(__file__).parents[1] / "scripts" / "replay_overlay.py"
    spec = importlib.util.spec_from_file_location("overlay", path)
    overlay = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(overlay)
    original, corrected, target = (tmp_path / name for name in ("original", "corrected", "overlay"))
    corrected.mkdir()
    for name in overlay.FAMILIES.values():
        (original / name / "keep").mkdir(parents=True)
        (original / name / "fix").mkdir()
        (corrected / name).symlink_to(original / name)
    overlay.prepare(original, corrected, target, 2)
    assert (corrected / "events_replay" / "keep").resolve() == original / "events_replay" / "keep"
    repair = tmp_path / "repair"
    patched = repair / "events" / "origin" / "fix"
    patched.mkdir(parents=True)
    (patched / "summary.json").write_text('{}')
    report = tmp_path / "merge.json"
    report.write_text(json.dumps([{"event_id": "fix", "tag": "", "status": "merged"}]))
    overlay.publish(target, repair, report)
    assert (corrected / "events_replay" / "fix").resolve() == patched
    assert (original / "events_replay" / "fix").is_dir()
    assert not (original / "events_replay" / "fix" / "summary.json").exists()


def test_excluded_repair_clears_stale_measurement_preserves_labels():
    import polars as pl
    from scripts.repair_crossday_replays import patch_measurements
    before = pl.DataFrame({'event_id': ['a', 'b'], 'error': [None, None], 'asns_final_2h': [50, 60],
                           'set_final_2h': [[1, 2], [3]], 'labelled': ['valid', 'invalid'], 'split': ['train', 'test']})
    repair = pl.DataFrame({'event_id': ['a'], 'error': ['incomplete_crossday_archive_coverage'], 'labelled': ['wrong']})
    after = patch_measurements(before, repair)
    assert after['asns_final_2h'].to_list() == [None, 1]
    assert after['set_final_2h'].to_list() == [None, [3]]
    assert after['labelled'].to_list() == ['valid', 'invalid']
    assert after['split'].to_list() == ['train', 'test']


def test_partial_publication_materializes_new_counts_for_untouched_rows():
    from scripts.repair_crossday_replays import patch_measurements
    before = pl.DataFrame({
        'event_id': ['repaired', 'untouched'], 'error': [None, None],
        'set_d30s': [[1], [7, 8]], 'set_d1m': [[1], [7, 8, 9]],
        'set_d5m': [[1], [7, 8, 9]], 'set_d15m': [[1], [7, 8, 9, 10]],
        'set_final_2h': [[1], [7, 8, 9, 10]], 'split': ['train', 'test'],
    })
    repaired = pl.DataFrame({
        'event_id': ['repaired'], 'error': [None],
        'set_d30s': [[1, 2]], 'asns_d30s': [2],
        'set_d1m': [[1, 2]], 'asns_d1m': [2],
        'set_d5m': [[1, 2, 3]], 'asns_d5m': [3],
        'set_d15m': [[1, 2, 3]], 'asns_d15m': [3],
        'set_final_2h': [[1, 2, 3]], 'asns_final_2h': [3],
    })
    after = patch_measurements(before, repaired)
    for horizon in ('d30s', 'd1m', 'd5m', 'd15m', 'final_2h'):
        assert after['asns_' + horizon].to_list() == after['set_' + horizon].list.len().to_list()
    assert after['asns_d30s'].to_list() == [2, 2]
    assert after['asns_d15m'].to_list() == [3, 4]
    assert after['split'].to_list() == ['train', 'test']


def test_archive_gap_only_excludes_intersecting_event_windows():
    repair = module()
    base = dt.datetime(2024, 6, 5, tzinfo=dt.UTC)
    gap = int((base+dt.timedelta(hours=3,minutes=15)).timestamp())
    task = {'step':900}
    report = {'status':'archive_gaps', 'missing_index_timestamps':[gap], 'failed':[]}
    early = {'w_start':base, 'w_end':base+dt.timedelta(hours=3,minutes=6)}
    late = {'w_start':base+dt.timedelta(hours=22), 'w_end':base+dt.timedelta(hours=23)}
    affected = {'w_start':base, 'w_end':base+dt.timedelta(hours=3,minutes=51)}
    assert repair.event_task_coverage(early,task,report) == ('complete',[])
    assert repair.event_task_coverage(late,task,report) == ('complete',[])
    assert repair.event_task_coverage(affected,task,report) == ('archive_gaps',[gap])
    report = {'status':'archive_gaps','failed':[{'url':'https://archive.routeviews.org/route-views3/bgpdata/2024.06/UPDATES/updates.20240605.0315.bz2','error':'404'}]}
    assert repair.event_task_coverage(early,task,report) == ('complete',[])
    assert repair.event_task_coverage(affected,task,report) == ('archive_gaps',[gap])


def test_all_missing_archives_are_explicit_terminal_gaps():
    no_downloaded_archives_report = module().no_downloaded_archives_report
    report = no_downloaded_archives_report(5, {0, 900}, {}, [], [0, 900], [])
    assert report["status"] == "archive_gaps"
    assert report["fetched_blocks"] == 0
    assert report["missing_index_timestamps"] == [0, 900]
    assert report["parse"]["engine"] == "not_run_no_archives"


def test_empty_downloads_without_gap_evidence_are_not_called_archive_outage():
    import pytest
    no_downloaded_archives_report = module().no_downloaded_archives_report
    with pytest.raises(ValueError):
        no_downloaded_archives_report(5, {0}, {}, [], [], [])
