import datetime as dt
import polars as pl
from scripts.rebuild_pch_comparison import horizon_sets


def test_pch_common_public_clock_does_not_extend_late_pch_horizon():
    public = dt.datetime(2024, 5, 1, 12, tzinfo=dt.UTC)
    first = pl.DataFrame({'asn':[1,2,3], 'first':[public-dt.timedelta(seconds=10), public+dt.timedelta(seconds=31), public+dt.timedelta(hours=2,minutes=1)]})
    sets = horizon_sets(first, public)
    assert sets['d30s'] == [1]
    assert sets['final_2h'] == [1,2]
    assert 3 in horizon_sets(first, public+dt.timedelta(minutes=2))['final_2h']


def test_pch_vp_horizons_and_collectors_use_public_clock():
    from scripts.rebuild_pch_comparison import vp_counts
    t0 = dt.datetime(2024, 5, 1, 12, tzinfo=dt.UTC)
    vp = pl.DataFrame({'collector': ['a', 'a', 'b', 'c'], 'first': [t0, t0+dt.timedelta(seconds=31), t0+dt.timedelta(minutes=1), t0+dt.timedelta(hours=2,seconds=1)]})
    counts = vp_counts(vp, t0)
    assert counts['vp_d30s'] == 1
    assert counts['vp_d1m'] == 3
    assert counts['vp_final_2h'] == 3
    assert counts['collectors_seeing'] == 2
