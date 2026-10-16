import importlib.util
from pathlib import Path

import polars as pl
import pytest


spec = importlib.util.spec_from_file_location("fill_derived_event_counts", Path(__file__).parents[1] / "scripts/fill_derived_event_counts.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture():
    data = {"event_id": ["a", "b", "c"], "error": [None, None, "excluded"], "other": [7, 8, 9]}
    for horizon in ("d30s", "d1m", "d5m", "d15m"):
        data[f"asns_{horizon}"] = [None, 2, None]
        data[f"set_{horizon}"] = [[1], [1, 2], None]
    return pl.DataFrame(data)


def test_fill_preserves_other_columns_and_exclusions():
    before = fixture()
    after, changed = module.filled_counts(before)
    assert after["asns_d30s"].to_list() == [1, 2, None]
    assert all(ids == ["a"] for ids in changed.values())
    assert before.drop(module.COLUMNS).equals(after.drop(module.COLUMNS))


def test_fill_rejects_existing_inconsistent_nonnull_count():
    before = fixture().with_columns(pl.lit(99).alias("asns_d1m"))
    with pytest.raises(ValueError, match="Existing non-null"):
        module.filled_counts(before)


def test_fill_rejects_missing_usable_set():
    before = fixture().with_columns(pl.lit(None, dtype=pl.List(pl.Int64)).alias("set_d30s"), pl.lit(None, dtype=pl.Int64).alias("asns_d30s"))
    with pytest.raises(ValueError, match="Usable event"):
        module.filled_counts(before)
