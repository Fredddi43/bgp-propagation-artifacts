import datetime as dt
import sys
from types import SimpleNamespace

import numpy as np
import polars as pl
import pytest

from bgbench.tgn_data import observed_membership


def test_origin_actor_loop_does_not_turn_suffix_asn_into_onset_seed(tmp_path):
    onset = dt.datetime(2024, 9, 21, 13, 24, 46, tzinfo=dt.timezone.utc)
    # Actor 215439 repeats; 215590 is beyond its first occurrence. The replay
    # sees 215590 propagate the route only 323 seconds later on another path.
    pl.DataFrame({'ts': [onset], 'as_path': ['59919 215439 215590 215439']}).write_parquet(tmp_path / 'anomalous.parquet')
    pl.DataFrame({'collector': ['rrc00'] * 3 + ['rrc25'], 'asn': [59919, 215439, 215590, 215590],
                  'first_seen': [onset, onset, onset + dt.timedelta(seconds=323), onset + dt.timedelta(seconds=400)]}).write_parquet(tmp_path / 'membership.parquet')
    members = observed_membership(tmp_path)
    assert set(members.filter(pl.col('first') <= onset + dt.timedelta(seconds=30))['asn']) == {59919, 215439}
    assert members.filter(pl.col('asn') == 215590)['first'][0] == onset + dt.timedelta(seconds=323)
    assert observed_membership(tmp_path, 'rrc25')['first'][0] == onset + dt.timedelta(seconds=400)


def test_graph_membership_requires_canonical_replay_table(tmp_path):
    with pytest.raises(FileNotFoundError):
        observed_membership(tmp_path)


@pytest.mark.parametrize('tag', ['', 'rpkivalid', 'rpkiinvalid', 'rpkivalid@v=3'])
def test_origin_cache_rejects_precanonical_membership(tmp_path, monkeypatch, tag):
    from bgbench import tgn_data

    cached = _cached_graph_fixture(tmp_path, monkeypatch, tag, version=2)
    with pytest.raises(ValueError, match='Stale graph tensor'):
        tgn_data.build_split(tag=tag)
    cached['measurement_version'] = 3
    assert tgn_data.build_split(tag=tag)['built'] == 1


@pytest.mark.parametrize('tag', ['leak', 'leak200', 'withdrawal'])
def test_nonorigin_cache_keeps_existing_measurement_version(tmp_path, monkeypatch, tag):
    from bgbench import tgn_data

    _cached_graph_fixture(tmp_path, monkeypatch, tag, version=2)
    assert tgn_data.build_split(tag=tag)['built'] == 1


def _cached_graph_fixture(tmp_path, monkeypatch, tag, version):
    from bgbench import tgn_data

    monkeypatch.setattr(tgn_data.config, 'DATA_ROOT', tmp_path)
    family = tgn_data.replay_tag(tag)
    source = tmp_path / 'eventset' / ('2024_' + family if family else '2024')
    source.mkdir(parents=True)
    pl.DataFrame({'event_id': ['event'], 'error': [None], 'split': ['train'],
                  't0_obs': ['2024-01-01T00:00:00+00:00'],
                  'set_final_2h': [list(range(200))], 'observation_lag_s': [0]}).write_parquet(source / 'events.parquet')
    base = tgn_data.parse_tag(tag)[0]
    if base in ('rpkivalid', 'rpkiinvalid'):
        pl.DataFrame({'event_id': ['event'], 'validity': [base[4:]]}).write_parquet(source / 'rpki_validity.parquet')
    directory = tmp_path / 'cached'
    directory.mkdir()
    (directory / 'event.pt').touch()
    monkeypatch.setattr(tgn_data.config, 'tgn_dir', lambda *_: directory)
    cached = {'measurement_version': version, 'history_version': 2,
              'x': np.zeros((1, tgn_data.feature_width(tag))), 'split': 'train',
              'n_nodes': 1, 'n_seed': 1, 'n_pos': 1, 'msgs': np.empty((0, 3))}
    monkeypatch.setitem(sys.modules, 'torch', SimpleNamespace(load=lambda *args, **kwargs: cached))
    return cached
