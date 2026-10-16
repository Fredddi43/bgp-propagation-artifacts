import importlib.util
from pathlib import Path

import polars as pl


spec = importlib.util.spec_from_file_location("bootstrap_cascade_release", Path(__file__).parents[1] / "scripts/bootstrap_cascade_release.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_bootstrap_pairs_events_and_is_order_invariant():
    rows = pl.DataFrame({"event_id": ["b", "a", "c"], "cascade_jaccard": [.75, .5, 1.0], "persist_jaccard": [.5, .25, .75]})
    a = module.summarize(rows)
    b = module.summarize(rows.reverse())
    assert a == b
    assert a["mean_paired_difference"] == .25
    assert a["paired_difference_ci95"] == [.25, .25]
