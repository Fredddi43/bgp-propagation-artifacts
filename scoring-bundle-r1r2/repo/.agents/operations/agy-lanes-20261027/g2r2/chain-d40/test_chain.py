"""Dry test of G3 seal -> arm spec -> R2 on the repo's synthetic custody fixture. Invented data only."""
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common  # noqa: E402,F401  (sets sys.path for bgbench)
sys.path.insert(0, str(common.REPO / "tests"))
import test_forecast_custodian_eval as fx  # noqa: E402
import g3_seal, make_arm_spec  # noqa: E402


def world(tmp_path, monkeypatch):
    spec, _fixture_seal, labels, tables, rules = fx.custody_fixture(tmp_path)
    monkeypatch.setenv("CUSTODIAN_ACCESS_LOG", str(tmp_path / "access.jsonl"))
    import custodian_access_log
    monkeypatch.setattr(custodian_access_log, "LOG", tmp_path / "access.jsonl")
    seal = tmp_path / "g3-seal.json"
    g3_seal.main(["--freeze", str(spec), "--expected-freeze-sha256", fx.sha(spec), "--expected-arms",
                  str(len(json.loads(spec.read_text())["arms"])), "--out", str(seal)])
    arm_spec = tmp_path / "g4-arm-spec.json"
    make_arm_spec.main(["--freeze", str(spec), "--extension-decision", str(tmp_path / "extension-decision.json"),
                        "--slice-rules", str(rules), "--issue-time-table", "30", tables["30"]["path"],
                        "--issue-time-table", "60", tables["60"]["path"], "--repetitions", "200", "--out", str(arm_spec)])
    go = tmp_path / "GO.txt"
    go.write_text("synthetic go")
    args = ["--seal", str(seal), "--arm-spec", str(arm_spec), "--labels", str(labels),
            "--extension-decision", str(tmp_path / "extension-decision.json"), "--slice-rules", str(rules),
            "--issue-time-table", "30", tables["30"]["path"], "--issue-time-table", "60", tables["60"]["path"],
            "--repetitions", "200", "--go-file", str(go), "--out", str(tmp_path / "r2.json")]
    return spec, seal, args, go


def test_seal_refuses_incomplete_g2(tmp_path, monkeypatch):
    spec, _s, labels, tables, rules = fx.custody_fixture(tmp_path)
    arms = json.loads(spec.read_text())["arms"]
    Path(arms[0]["predictions_path"]).unlink()
    with pytest.raises(SystemExit):
        g3_seal.main(["--freeze", str(spec), "--expected-freeze-sha256", fx.sha(spec), "--expected-arms",
                      str(len(arms)), "--out", str(tmp_path / "s2.json")])
