import datetime as dt
import json

import polars as pl

from bgbench import config
from bgbench.replay import PASS_COLLECTORS
from bgbench.replay_day import _withdrawal_baselines, merge_withdrawal


T0 = dt.datetime(2024, 1, 8, tzinfo=dt.UTC)


def test_weekly_baseline_boundary_and_missing_collector(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'RIB_DIR', tmp_path/'ribs')
    for collector in PASS_COLLECTORS:
        folder = config.RIB_DIR/collector
        folder.mkdir(parents=True)
        (folder/'2024-01-01T0000.parquet').touch()
        (folder/'2024-01-09T0000.parquet').touch()  # A future file cannot repair a stale baseline.
    paths, policy = _withdrawal_baselines(T0)
    assert len(paths) == 10 and not policy['missing_collectors'] and not policy['stale_collectors']
    assert {row['age_seconds'] for row in policy['selected']} == {604800}
    _, policy = _withdrawal_baselines(T0+dt.timedelta(seconds=1))
    assert set(policy['stale_collectors']) == set(PASS_COLLECTORS)
    (config.RIB_DIR/PASS_COLLECTORS[0]/'2024-01-01T0000.parquet').unlink()
    _, policy = _withdrawal_baselines(T0)
    assert policy['missing_collectors'] == [PASS_COLLECTORS[0]]


def test_merge_without_rib_is_explicitly_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'RIB_DIR', tmp_path/'ribs')
    parts = tmp_path/'events_replay_parts_withdrawal'/'wave'
    parts.mkdir(parents=True)
    pl.DataFrame({'collector':['rrc00'],'ts':[T0]}).write_parquet(parts/'rrc00.parquet')
    result = merge_withdrawal('wave', T0, T0)
    assert result['error'] == 'missing_required_weekly_rib'
    assert len(result['withdrawal_baseline']['missing_collectors']) == 10
    assert 'extent' not in result
    assert json.loads((tmp_path/'events_replay_withdrawal/wave/summary.json').read_text()) == result


def test_supported_merge_retains_observed_path_loss(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'RIB_DIR', tmp_path/'ribs')
    for collector in PASS_COLLECTORS:
        folder = config.RIB_DIR/collector
        folder.mkdir(parents=True)
        pl.DataFrame({'collector':[collector]*3,'peer_ip':['a','b','c'],
                      'prefix':['192.0.2.0/24']*3,'as_path':['1 2 3']*3}).write_parquet(folder/'2024-01-01T0000.parquet')
    parts=tmp_path/'events_replay_parts_withdrawal/wave';parts.mkdir(parents=True)
    pl.DataFrame({'collector':['rrc00']*3,'peer_ip':['a','b','c'],'prefix':['192.0.2.0/24']*3,
                  'ts':[T0]*3,'elem_type':['W']*3,'as_path':[None]*3},
                 schema_overrides={'as_path':pl.String}).write_parquet(parts/'rrc00.parquet')
    result=merge_withdrawal('wave',T0,T0)
    assert result.get('error') is None
    assert result['extent']['final_2h']['asns_pooled']==3
    assert result['rib_vp_prefix_rows']==30
    assert result['vp_prefix_changed']==3
    assert len(result['withdrawal_baseline']['selected'])==10
