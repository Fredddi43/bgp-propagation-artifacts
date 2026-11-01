"""Dry test of the G4 wrapper on the bundle's own synthetic four-scope world."""
import json
import sys
import types
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common  # noqa: E402
import g4_labels  # noqa: E402

BUNDLE_TEST = common.REPO / ".agents/operations/newperiod-complete-label-bundle-20261023/test_bundle.py"


def fixture_module():
    m = types.ModuleType("bundle_fixture")
    m.__file__ = str(BUNDLE_TEST)
    m.__dict__["__name__"] = "bundle_fixture"
    exec(compile(BUNDLE_TEST.read_bytes(), str(BUNDLE_TEST), "exec"), m.__dict__)
    return m


def test_g4_prepares_one_four_scope_artifact(tmp_path, monkeypatch):
    fx = fixture_module()
    plan = fx.world(tmp_path, monkeypatch)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan))
    seal = tmp_path / "seal.json"
    seal.write_text("{}")
    go = tmp_path / "GO.txt"
    go.write_text("synthetic go")
    g4_labels.main(["--plan", str(plan_path), "--seal", str(seal), "--go-file", str(go)])
    out = Path(plan["base"]["ordinary"]["output"])
    table = json.loads(out.read_text())
    assert table["kind"] == "custodian_label_table" and set(table) >= {"stable", "origin_change_invalid", "origin_change_valid"}
    assert out.with_name(out.stem + ".g4-receipt.json").exists()
    with pytest.raises(SystemExit):
        g4_labels.main(["--plan", str(plan_path), "--seal", str(seal), "--go-file", str(go)])


def test_g4_refuses_without_go(tmp_path, monkeypatch):
    fx = fixture_module()
    plan = fx.world(tmp_path, monkeypatch)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan))
    with pytest.raises(SystemExit):
        g4_labels.main(["--plan", str(plan_path), "--seal", str(plan_path), "--go-file", str(tmp_path / "none")])
    assert not Path(plan["base"]["ordinary"]["output"]).exists()
