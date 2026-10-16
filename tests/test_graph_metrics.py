import numpy as np
import pytest

from bgbench.graph_metrics import membership_metrics


def test_outside_truth_counts_as_miss_and_outside_seeds_are_retained():
    event = {"asn": np.array([10, 20, 30]), "target_asns": np.array([10, 20, 40, 50]), "seed_asns": np.array([10, 40])}
    result = membership_metrics(event, np.array([True, True, False]))
    assert result["jaccard"] == 3 / 4
    assert result["jaccard_persist"] == 1 / 2
    assert result["candidate_jaccard"] == 1
    assert result["candidate_jaccard_persist"] == 1 / 2
    assert result["candidate_target_coverage"] == 1 / 2
    assert result["true_outside_candidates"] == 2


def test_false_positive_changes_union_not_truth():
    event = {"asn": [10, 20, 30], "target_asns": [10, 20, 40], "seed_asns": [10]}
    result = membership_metrics(event, [True, True, True])
    assert result["jaccard"] == 1 / 2
    assert result["recall"] == 2 / 3
    assert result["precision"] == 2 / 3


def test_old_tensors_cannot_silently_report_restricted_scores():
    with pytest.raises(ValueError, match="refresh graph tensors"):
        membership_metrics({"asn": [10]}, [True])


def test_message_stream_uses_asns_not_caida_row_numbers():
    from datetime import datetime, timedelta, timezone
    from bgbench.graph_metrics import message_stream
    onset = datetime(2025, 1, 1, tzinfo=timezone.utc)
    got = message_stream([onset + timedelta(seconds=2)], [[64501, 64502, 64503]], [64503, 64501, 64502], onset)
    assert got.tolist() == [[2.0, 2.0, 1.0], [2.0, 0.0, 2.0]]


def test_history_waits_for_complete_horizon_and_excludes_same_onset():
    from bgbench.graph_metrics import completed_event_histories
    onsets = {"a": "2025-01-01T00:00:00+00:00", "b": "2025-01-01T00:00:00+00:00",
              "c": "2025-01-01T01:59:59+00:00", "d": "2025-01-01T02:00:00+00:00"}
    histories = completed_event_histories(onsets, {"a": [10, 20], "b": [10, 30], "c": [40]})
    assert histories["a"] == histories["b"] == histories["c"] == {}
    assert histories["d"] == {10: 2, 20: 1, 30: 1}
    early = completed_event_histories(onsets, {"a": [10], "b": [20]}, query_offset_seconds=-30)
    assert early['d'] == {}


def test_legacy_midnight_window_flag():
    from bgbench.graph_metrics import legacy_window_crosses_midnight
    assert legacy_window_crosses_midnight("20250101T003000_leak_1")
    assert legacy_window_crosses_midnight("20250101T213000_leak_1")
    assert not legacy_window_crosses_midnight("20250101T120000_leak_1")


def test_legality_learning_follows_origin_side_of_as_path():
    from bgbench.graph_metrics import learned_from_customers
    # Collector 10 receives from customer 20; 20 receives from provider 30.
    # Reversing the path would incorrectly identify node 30 instead of node 10.
    rel = {(10, 20): "customer", (20, 10): "provider", (20, 30): "provider", (30, 20): "customer"}
    assert learned_from_customers([[10, 20, 30]], rel) == {10}


def test_prospective_training_embargo_includes_complete_boundary_only():
    from bgbench.graph_metrics import embargo_training_events
    tr = [{'event_id': 'complete'}, {'event_id': 'overlap'}]
    onsets = {'complete': '2025-08-31T22:00:00+00:00', 'overlap': '2025-08-31T22:00:01+00:00', 'test': '2025-09-01T00:00:00+00:00'}
    kept, metadata = embargo_training_events(tr, [{'event_id': 'test'}], onsets)
    assert kept == [tr[0]]
    assert metadata['dropped_training_ids'] == ['overlap']
