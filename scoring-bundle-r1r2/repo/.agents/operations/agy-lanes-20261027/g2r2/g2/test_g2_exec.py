"""Dry test: the generic G2 executor drives the unchanged ordinary-family runner on its synthetic fixture (no real data)."""
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
REPO = HERE.parents[4]
OPS = REPO / ".agents/operations"
FAMILY = OPS / "newperiod-ordinary-inference-20261023"


def load(path, name):
    m = types.ModuleType(name)
    m.__file__ = str(path)
    m.__dict__["__name__"] = name
    exec(compile(path.read_bytes(), str(path), "exec"), m.__dict__)
    return m


def ref(path):
    import hashlib
    return {"path": str(path), "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}


def run_exec(tmp_path, spec, attempt=1):
    return subprocess.run([sys.executable, "-I", "-B", str(HERE / "g2_exec.py"), "--spec", str(spec), "--index", "0",
                           "--attempt", str(attempt)], capture_output=True, text=True, timeout=120)


def test_executor_runs_ordinary_arm_and_refuses_retry(tmp_path, monkeypatch):
    ot = load(FAMILY / "test_runner.py", "ordinary_fixture_tests")
    w, arm = ot.world(tmp_path, monkeypatch, "gbdt_membership")
    template = {k: v for k, v in w.plan.items() if k not in ("records", "runtime", "resource_readiness")}
    template["resources"] = {k: v for k, v in w.plan["resources"].items() if k != "job_id"}
    import stage_source
    root = tmp_path / "source"
    stage_source.stage([FAMILY], root, root)
    template["source_root"] = str(root)
    template["scientific_source_closure"] = ref(root / "scientific-closure.json")
    template_path = tmp_path / "template.json"
    template_path.write_text(json.dumps(template))
    go = tmp_path / "GO.txt"
    go.write_text("synthetic go")
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"go_file": str(go), "work": str(tmp_path / "work"), "arms": [{
        "arm_id": template["arm_id"], "template": ref(template_path), "runner": ref(FAMILY / "runner.py"),
        "kernel": ref(FAMILY / "kernel.py"), "readiness_flags": ["resident_inputs_and_model_fit"]}]}))
    done = run_exec(tmp_path, spec)
    assert done.returncode == 0, done.stderr[-1500:]
    from bgbench import forecast_custody as custody
    assert custody.verify_arm(arm)["events"] == 4
    assert (tmp_path / "work/arms/000/result-1.json").exists()
    again = run_exec(tmp_path, spec, attempt=2)           # outputs exist: the runner refuses, failure is recorded
    assert again.returncode != 0
    assert (tmp_path / "work/arms/000/failure-2.json").exists()


def test_executor_refuses_without_go_file(tmp_path, monkeypatch):
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"go_file": str(tmp_path / "none"), "work": str(tmp_path / "w"), "arms": [{"arm_id": "x"}]}))
    done = run_exec(tmp_path, spec)
    assert done.returncode != 0 and "go file" in done.stderr
