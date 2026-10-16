import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from verify_radar_agreement import check_prefix_summary,check_rpki_summary,tag


def test_prefix_agreement_uses_prefix_lists_and_zero_denominator_rule():
    rows=[dict(radar_id='a',prefixes='["10.0.0.0/24"]',our_prefix_count=1,radar_prefix_count=1),
          dict(radar_id='b',prefixes='[]',our_prefix_count=0,radar_prefix_count=0),
          dict(radar_id='c',prefixes='["10.0.1.0/24"]',our_prefix_count=1,radar_prefix_count=2)]
    summary={'measurement_definition':'nearest_identifier_match_complete_radar_window_observed_prefixes_v1',
             'matched_to_our_events':3,'exact_count_match':2,'our_ge_radar':2,
             'ratio_p10_p50_p90':[0.,.5,1.],'radar_prefix_count_p50':1.,'our_prefix_count_p50':1.}
    check_prefix_summary(rows,summary)
    rows[0]['prefixes']='[]'
    with pytest.raises(AssertionError):check_prefix_summary(rows,summary)


def test_rpki_confusion_requires_source_validity_and_correct_tags():
    rows=[dict(event_id='e',ours='invalid',radar='valid')]
    summary={'matched_events':1,'agreement':0.,'confusion_ours_vs_radar':{'invalid|valid':1},
             'match_policy':'exclude conflicting RPKI tags; nearest timestamp then Radar ID among same-tag matches',
             'conflicting_tag_event_ids':[], 'conflicting_tag_events_excluded':0,
             'matched_events_before_ambiguity_filter':1,'multiple_match_events':0}
    check_rpki_summary(rows,summary,{'e':'invalid'})
    assert tag(json.dumps([{'name':'rpki_new_origin_invalid'}]))=='invalid'
    with pytest.raises(AssertionError):check_rpki_summary(rows,summary,{'e':'valid'})


def test_rpki_matching_excludes_fractional_second_outside_window(tmp_path):
    import os
    import subprocess
    import polars as pl
    root=Path(__file__).parents[1]
    inventory=tmp_path/'inventory/2024';inventory.mkdir(parents=True)
    eventset=tmp_path/'eventset/2024';eventset.mkdir(parents=True)
    labels=tmp_path/'labels/2024-01-01_2025-01-01';labels.mkdir(parents=True)
    ids=['before','boundary','after']
    pl.DataFrame({'event_id':ids,'prefix':['10.0.0.0/24']*3,'new_origin':[42]*3,
                  't0':['2024-01-01T00:09:59.845Z','2024-01-01T00:10:00Z','2024-01-01T00:30:00.155Z']}).write_csv(inventory/'replay_manifest.tsv',separator='\t')
    pl.DataFrame({'event_id':ids,'validity':['invalid']*3}).write_parquet(eventset/'rpki_validity.parquet')
    pl.DataFrame({'id':['radar'],'hijacker_asn':['42'],'prefixes':['["10.0.0.0/24"]'],
                  'min_hijack_ts':['2024-01-01T00:20:00Z'],'tags':['[{"name":"rpki_new_origin_invalid"}]'],
                  'confidence_score':[100]}).write_parquet(labels/'cloudflare_hijacks.parquet')
    env=os.environ.copy();env['BGBENCH_DATA_ROOT']=str(tmp_path);env['PYTHONPATH']=str(root/'src')
    subprocess.run([sys.executable,str(root/'scripts/radar_rpki_agreement.py'),'2024'],env=env,check=True,capture_output=True)
    assert pl.read_parquet(eventset/'radar_rpki_agreement.parquet')['event_id'].to_list()==['boundary']


def test_rpki_matching_excludes_conflicts_and_breaks_same_tag_ties_by_id(tmp_path):
    import os
    import subprocess
    import polars as pl
    root=Path(__file__).parents[1]
    inventory=tmp_path/'inventory/2024';inventory.mkdir(parents=True)
    eventset=tmp_path/'eventset/2024';eventset.mkdir(parents=True)
    labels=tmp_path/'labels/2024-01-01_2025-01-01';labels.mkdir(parents=True)
    pl.DataFrame({'event_id':['conflict','tie'],'prefix':['10.0.0.0/24']*2,'new_origin':[43,44],
                  't0':['2024-01-01T00:20:00Z','2024-01-01T00:21:00Z']}).write_csv(inventory/'replay_manifest.tsv',separator='\t')
    pl.DataFrame({'event_id':['conflict','tie'],'validity':['invalid']*2}).write_parquet(eventset/'rpki_validity.parquet')
    frame=pl.DataFrame({'id':['conflict1','conflict2','z','a'],'hijacker_asn':['43','43','44','44'],
                       'prefixes':['["10.0.0.0/24"]']*4,
                       'min_hijack_ts':['2024-01-01T00:20:00Z','2024-01-01T00:20:01Z','2024-01-01T00:20:00Z','2024-01-01T00:22:00Z'],
                       'tags':[json.dumps([{'name':'rpki_new_origin_'+v}]) for v in ['invalid','unknown','invalid','invalid']],
                       'confidence_score':[100]*4})
    env=os.environ.copy();env['BGBENCH_DATA_ROOT']=str(tmp_path);env['PYTHONPATH']=str(root/'src')
    for candidate in [frame,frame.reverse()]:
        candidate.write_parquet(labels/'cloudflare_hijacks.parquet')
        subprocess.run([sys.executable,str(root/'scripts/radar_rpki_agreement.py'),'2024'],env=env,check=True,capture_output=True)
        rows=pl.read_parquet(eventset/'radar_rpki_agreement.parquet').to_dicts()
        assert len(rows)==1 and rows[0]['event_id']=='tie' and rows[0]['radar_id']=='a'
        summary=json.loads((eventset/'radar_rpki_agreement.json').read_text())
        assert summary['matched_events_before_ambiguity_filter']==2
        assert summary['conflicting_tag_events_excluded']==1
        assert summary['conflicting_tag_event_ids']==['conflict']
