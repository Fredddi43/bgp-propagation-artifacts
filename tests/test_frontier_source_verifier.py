import importlib.util
import json
from pathlib import Path

import numpy as np
import polars as pl
import pytest


spec = importlib.util.spec_from_file_location("frontier_sources", Path(__file__).parents[1] / "scripts/verify_frontier_sources.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_raw_frontier_reconstruction_and_public_binding(tmp_path):
    root = tmp_path / "eventset/2024"
    root.mkdir(parents=True)
    eid = "20240102_origin_test"
    pl.DataFrame({"event_id": [eid], "split": ["test"], "error": [None], "set_final_2h": [[1, 2]], "reason": ["radar"]}).write_parquet(root / "events.parquet")
    pl.DataFrame({"event_id": [eid], "validity": ["invalid"]}).write_parquet(root / "rpki_validity.parquet")
    (tmp_path / "graphs").mkdir()
    pl.DataFrame({"u": [1, 1, 2, 3], "v": [2, 3, 4, 5]}).write_parquet(tmp_path / "graphs/20240101.rel.parquet")
    (tmp_path / "rpki/rovista").mkdir(parents=True)
    pl.DataFrame({"asn": [1, 2, 3, 3, 4], "date": ["2024-01-01", "2024-01-03", "2024-01-01", "2024-01-03", "2024-01-01"],
                  "ratio": [.0, 1., 1., .0, 1.], "total": [20, 20, 20, 20, 1]}).write_parquet(tmp_path / "rpki/rovista/as_rov_series.parquet")
    summary = {"threshold": .5, "min_total": 10, "by_validity": {"invalid": {
        "future_only_carrier_observations_excluded": 1, "future_only_frontier_observations_excluded": 0}}}
    relative = "eventset/2024/rov_frontier.json"
    (root / "rov_frontier.json").write_text(json.dumps(summary))
    row = {"event_id": eid, "split": "test", "validity": "invalid", "carriers": 2, "frontier": 2,
           "carriers_measured": 1, "carriers_enforcing": 0, "frontier_measured": 1, "frontier_enforcing": 1,
           "log_odds": float(np.log(9))}
    pl.DataFrame([row]).write_parquet(root / "rov_frontier.parquet")
    result = module.audit_year(tmp_path, [relative])
    proof = tmp_path / "proof.json"
    proof.write_text(json.dumps({**result, "status": "passed", "mode": "private_source_audit"}))
    assert module.verify_public(tmp_path, proof, [relative])["rows"] == 1
    row["frontier_enforcing"] = 0
    pl.DataFrame([row]).write_parquet(root / "rov_frontier.parquet")
    with pytest.raises(AssertionError, match="hash mismatch"):
        module.verify_public(tmp_path, proof, [relative])
    with pytest.raises(AssertionError, match="frontier_enforcing"):
        module.audit_year(tmp_path, [relative])
