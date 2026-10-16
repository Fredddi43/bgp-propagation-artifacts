import numpy as np
import polars as pl
import pytest

from bgbench.paired_analysis import clustered_mean_ci, link_components, pair_events
from bgbench.rov_history import ratio_at


def test_duplicate_payloads_do_not_multiply_legitimate_links():
    selection = pl.DataFrame({"event_id": ["r", "r"], "hijack_id": ["h1", "h2"]})
    recovery = pl.DataFrame({"event_id": ["r", "r"], "reach": [20, 20]})
    hijack = pl.DataFrame({"hijack_id": ["h1", "h2"], "h_reach": [2, 3]})
    pairs = pair_events(selection, recovery, hijack)
    assert pairs.height == 2
    assert pairs["hijack_id"].n_unique() == 2
    assert len(set(link_components(pairs))) == 1
    with pytest.raises(ValueError, match="Conflicting payloads"):
        pair_events(selection, recovery.with_columns(pl.Series("reach", [20, 21])), hijack)


def test_reused_hijacks_connect_bootstrap_components():
    pairs = pl.DataFrame({"event_id": ["r1", "r1", "r2", "r3"], "hijack_id": ["h1", "h2", "h2", "h3"]})
    groups = link_components(pairs)
    assert groups[0] == groups[1] == groups[2]
    assert groups[3] != groups[0]


def test_cluster_ci_treats_repeated_measurements_as_one_unit():
    values = np.arange(30, dtype=float)
    reference = clustered_mean_ci(values, np.arange(30))
    assert clustered_mean_ci(np.repeat(values, 3), np.repeat(np.arange(30), 3)) == reference
    assert clustered_mean_ci(values, np.zeros(30)) is None


def test_rov_never_uses_future_measurements():
    series = {42: (["2024-02-01", "2024-05-01"], [0.2, 0.8])}
    assert ratio_at(series, 42, "2024-01-31") is None
    assert ratio_at(series, 42, "2024-02-01") == 0.2
    assert ratio_at(series, 42, "2024-04-30") == 0.2
    assert ratio_at(series, 42, "2024-05-01") == 0.8
    assert ratio_at(series, 43, "2024-05-01") is None


def test_pair_command_uses_continuous_times_and_set_cardinality(tmp_path):
    import json
    import os
    from pathlib import Path
    import subprocess
    import sys

    for directory in ("eventset/2024", "eventset/2024_recovery", "inventory/2024"):
        (tmp_path / directory).mkdir(parents=True)
    base = {"error": [None, None], "measurement_definition": ["first_transition", "first_transition"],
            "t0_obs": ["2024-01-01T00:00:00+00:00", "2024-01-01T00:00:01+00:00"], "duration_min": [3.0, 4.0], "asns_final_2h": [999, 999],
            "set_d30s": [[1], [2]], "set_final_2h": [[1, 3], [2, 4]], "t90_s": [12.5, 20.25]}
    pl.DataFrame({**base, "event_id": ["h1", "h2"]}).write_parquet(tmp_path / "eventset/2024/events.parquet")
    pl.DataFrame({**base, "event_id": ["r1", "r2"], "t90_s": [45.5, 95.75]}).write_parquet(tmp_path / "eventset/2024_recovery/events.parquet")
    pl.DataFrame({"event_id": ["r1", "r2"], "hijack_id": ["h1", "h2"], "gap_s": [20, 40], "split": ["test", "test"]}).write_parquet(tmp_path / "inventory/2024/recovery_replay_selection.parquet")
    script = Path(__file__).resolve().parents[1] / "scripts/recovery_pairs_full.py"
    subprocess.run([sys.executable, str(script), "2024"], env={**os.environ, "BGBENCH_DATA_ROOT": str(tmp_path)}, check=True, capture_output=True)
    pairs = pl.read_parquet(tmp_path / "eventset/2024_recovery/pairs.parquet")
    assert pairs.sort("event_id")["r_t90_s"].to_list() == [45.5, 95.75]
    assert pairs["r_reach"].to_list() == [2, 2]
    assert json.loads((tmp_path / "eventset/2024_recovery/pairs_summary.json").read_text())["paired_j30_diff_recovery_minus_hijack"]["ci95"] is None
    recovery = pl.read_parquet(tmp_path / "eventset/2024_recovery/events.parquet")
    recovery = recovery.with_columns(pl.Series("t0_obs", ["2023-12-31T23:59:00+00:00", "2024-01-01T00:00:01+00:00"]))
    recovery.write_parquet(tmp_path / "eventset/2024_recovery/events.parquet")
    failed = subprocess.run([sys.executable, str(script), "2024", "--require-matched-definition"],
                            env={**os.environ, "BGBENCH_DATA_ROOT": str(tmp_path)}, capture_output=True, text=True)
    assert failed.returncode == 0, failed.stderr
    result = json.loads((tmp_path / "eventset/2024_recovery/pairs_summary.json").read_text())
    assert result["pairs"] == 1
    assert result["chronologically_unmatched_count"] == 1
    assert result["chronologically_unmatched_links"][0]["event_id"] == "r1"


def test_primary_pair_input_rejects_mismatched_measurements(tmp_path):
    from types import SimpleNamespace
    from bgbench.paired_analysis import read_pair_inputs
    h, r = tmp_path / "h.parquet", tmp_path / "r.parquet"
    pl.DataFrame({"event_id": ["h"], "error": [None], "measurement_definition": ["all_announcements"]}).write_parquet(h)
    pl.DataFrame({"event_id": ["r"], "error": [None], "measurement_definition": ["first_transition"]}).write_parquet(r)
    args = SimpleNamespace(hijack_events=h, recovery_events=r, output_dir=tmp_path,
                           selection=tmp_path / "selection.parquet", require_matched_definition=True)
    with pytest.raises(ValueError, match="definitions differ"):
        read_pair_inputs(args, 2024)
