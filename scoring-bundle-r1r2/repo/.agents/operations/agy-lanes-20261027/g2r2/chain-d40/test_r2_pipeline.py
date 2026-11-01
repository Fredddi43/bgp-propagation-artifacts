"""Whole back-end path on ONE synthetic world: G3 seal -> arm spec -> (one label opening) PINNED persistence runner
-> primary-scores sidecar -> forecast_full_report_facts -> forecast_report_latex -> quote post-fix. Invented data only.
(G4's own bundle world is a different synthetic world: see test_g4.py. Here the fixture's label table plays G4's artifact.)"""
import hashlib
import json
import re
import subprocess
import sys
import types
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common  # noqa: E402
import g3_seal, make_arm_spec, r2_plan  # noqa: E402

OPS = common.REPO / ".agents/operations"
PERSIST = OPS / "newperiod-single-r2-persistence-20261024/runner.py"
INTEG = OPS / "newperiod-single-r2-execution-20261023/test_integration.py"


def load(path, name):
    m = types.ModuleType(name)
    m.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), "exec"), m.__dict__)
    return m


def ref(p):
    return {"path": str(p), "sha256": hashlib.sha256(Path(p).read_bytes()).hexdigest()}


def save(p, doc):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(doc, sort_keys=True))
    return ref(p)


def test_whole_back_end_path(tmp_path, monkeypatch):
    f = load(INTEG, "r2_pipeline_fixture")
    r = load(PERSIST, "r2_pipeline_persistence")
    from bgbench import forecast_custodian_eval as original, forecast_custody as custody
    from bgbench import forecast_retrospective_scoring as scores
    plan, old_reader, _reads, _ = f.fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(r, "BOOTSTRAP", f.r.BOOTSTRAP)
    # --- G3 seal + arm spec with OUR scripts over the fixture freeze
    freeze = Path(plan["freeze"]["path"])
    arms = json.loads(freeze.read_bytes())["arms"]
    seal = tmp_path / "g3" / "seal.json"
    g3_seal.main(["--freeze", str(freeze), "--expected-freeze-sha256", plan["freeze"]["sha256"],
                  "--expected-arms", str(len(arms)), "--out", str(seal)])
    ours = tmp_path / "g3" / "arm-spec.json"
    make_arm_spec.main(["--freeze", str(freeze), "--extension-decision", plan["extension_decision"]["path"],
                        "--slice-rules", plan["slice_rules"]["path"],
                        *sum([["--issue-time-table", d, t["path"]] for d, t in plan["issue_time_tables"].items()], []),
                        "--repetitions", "200", "--out", str(ours)])
    assert json.loads(ours.read_bytes()) == json.loads(Path(plan["arm_spec"]["path"]).read_bytes())  # mechanical derivation == fixture's spec
    plan["seal"], plan["arm_spec"] = ref(seal), ref(ours)
    review = json.loads(Path(plan["full_retention_review"]["path"]).read_bytes())
    review["seal"] = plan["seal"]
    plan["full_retention_review"] = save(plan["full_retention_review"]["path"], review)
    # --- persistence runner plan fields (as its own test configures them) and OUR inventory
    records = tmp_path / "persistence-records"
    records.mkdir()
    plan.update(records=str(records), primary_output=str(plan["primary_output"]), primary_scores_output=str(records / "primary-scores.json"),
                source_closure=save(tmp_path / "closure.json", {"scientific_pins_sha256": r.PINS_SHA}),
                bounds=dict(output_file_bytes=256 << 20, access_log_bytes=1 << 20, output_total_bytes=(6 * 256 + 1) << 20))
    inventory = r2_plan.build_inventory(plan, extra_paths=[Path(original.__file__).resolve(), Path(scores.__file__).resolve()])
    theirs = {x["path"]: x for x in old_reader.items.values()}
    missing = sorted(set(theirs) - {x["path"] for x in inventory})
    extra_kinds = [x for x in inventory if x["path"] in theirs and theirs[x["path"]]["kind"] == "label" and x["kind"] != "label"]
    assert not extra_kinds, extra_kinds
    bounds = {k: 1 << 30 for k in ("metadata_bytes", "input_bytes", "checkpoint_bytes", "label_bytes", "total_unique_bytes",
                                   "total_read_bytes", "input_view_cache_bytes")}
    reads = []
    reader = r.Reader(inventory, bounds | {"runtime_file_bytes": 1 << 30}, lambda p, w: reads.append((p, w)), plan["labels"])
    receipts = []
    orig_item = r.Reader.item
    def traced(self, path, expected=None):
        try:
            return orig_item(self, path, expected)
        except ValueError:
            print("OUTSIDE", path); raise
    monkeypatch.setattr(r.Reader, "item", traced)
    result = r.evaluate(plan, reader, original, custody, r.components(), score_receipts=receipts)
    assert reader.label_reads == 1 and sum(p == plan["labels"]["path"] and w == "Custodian label table" for p, w in reads) == 1
    assert result["kind"] == "newperiod_all_retained_R2_evaluation_v1" and result["full_newperiod_coverage"] is True
    side = json.loads(Path(receipts[0]["path"]).read_bytes())
    assert side["kind"] == "newperiod_primary_computed_scores_v1" and side["metrics_recomputed"] is False
    # --- paper generators (plan section 3 commands) + quote post-fix
    report = tmp_path / "r2-report.json"
    raw = (json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    report.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    py = [sys.executable, "-B"]
    env = {"PYTHONPATH": str(common.REPO / "src"), "PATH": "/usr/bin:/bin"}
    facts = tmp_path / "paper" / "facts"
    subprocess.run([*py, str(common.REPO / "scripts/forecast_full_report_facts.py"), str(report), str(facts),
                    "--expected-report-sha256", digest], check=True, capture_output=True, env=env)
    facts_sha = hashlib.sha256((facts / "facts.json").read_bytes()).hexdigest()
    tables = tmp_path / "paper" / "tables"
    subprocess.run([*py, str(common.REPO / "scripts/forecast_report_latex.py"), str(facts / "facts.json"), str(tables),
                    "--expected-facts-sha256", facts_sha], check=True, capture_output=True, env=env)
    for name in ("main.tex", "supplement.tex"):
        path = tables / name
        text = path.read_text()
        fixed = re.sub(r"``not reported\. ", "``not reported''. ", text)
        if "``not reported''" not in text:
            assert fixed != text      # the known unbalanced-quote bug is present; the post-fix restores it
            path.write_text(fixed)
        assert "``not reported''" in path.read_text()


def test_r2_exec_documents_satisfy_the_pinned_runners_authority_and_runtime(tmp_path, monkeypatch):
    """The wrapper's plan/approval/readiness/runtime docs pass the PINNED runner's own authority() and runtime() checks."""
    import r2_exec
    f = load(INTEG, "r2_exec_fixture")
    r = load(PERSIST, "r2_exec_persistence")
    from bgbench import forecast_custodian_eval as original
    from bgbench import forecast_retrospective_scoring as scores
    plan0, _reader, _reads, _ = f.fixture(tmp_path, monkeypatch)
    keys = ("freeze", "seal", "arm_spec", "labels", "count_freeze", "membership_freezes", "evidence", "stable_freeze", "stable_evidence",
            "origin_freeze", "origin_evidence", "baseline_freeze", "baseline_evidence", "extension_decision", "slice_rules",
            "issue_time_tables", "full_retention_review", "pre_R2_implementation_binding")
    controls = {k: plan0[k] for k in keys}
    controls["source_closure"] = save(tmp_path / "closure.json", {"scientific_pins_sha256": r.PINS_SHA})
    log = tmp_path / "access.jsonl"
    template, inventory = r2_plan.build_template(controls, source_root=tmp_path / "src", access_log=log,
                                                 extra_paths=[Path(original.__file__).resolve(), Path(scores.__file__).resolve()])
    assert template["records"].endswith("/single-R2-v1/arms/000/attempt") and template["bounds"]["output_total_bytes"] >= 6 * template["bounds"]["output_file_bytes"] + template["bounds"]["access_log_bytes"]
    b = template["bounds"]   # generous by construction (NO SELF-IMPOSED LIMITS): >= 16x measured need, fixed floors 16x the q22 recommendation
    assert b["output_file_bytes"] == 16 << 30 and b["access_log_bytes"] == 4 << 30 and b["runtime_file_bytes"] == 4 << 30 \
        and b["input_view_cache_bytes"] == 64 << 30
    total = sum(x["size_bytes"] for x in inventory)
    assert b["total_unique_bytes"] >= 16 * total and b["total_read_bytes"] >= 16 * total
    for kind in ("metadata", "input", "checkpoint", "label"):
        biggest = max([x["size_bytes"] for x in inventory if x["kind"] == kind] or [1])
        assert b[kind + "_bytes"] >= 16 * biggest and b[kind + "_bytes"] >= 16 << 30, kind
    go = tmp_path / "GO.txt"
    go.write_text("synthetic go")
    spec = {"go_file": str(go), "work": str(tmp_path / "work"), "template": save(tmp_path / "template.json", template),
            "inventory": inventory, "runner": ref(PERSIST)}
    cpus = 64   # the wrapper now refuses an allocation below the generous floors (RESOURCE-POLICY heavy tier)
    env = {"SLURM_JOB_ID": "4242", "SLURM_JOB_PARTITION": "cpu", "SLURM_CPUS_PER_TASK": str(cpus), "SLURM_MEM_PER_NODE": "1000000",
           "SLURM_RESTART_COUNT": "0", "CUSTODIAN_ACCESS_LOG": str(log), **{k: str(cpus) for k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "POLARS_MAX_THREADS")}}
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    pref, aref = r2_exec.prepare(spec)
    plan = r.authority(pref, aref)        # pinned runner: exact approval
    r.runtime(plan)                       # pinned runner: allocation, bounds, admission, runtime evidence
    r.Reader(inventory, plan["bounds"], lambda p, w: None, plan["labels"])   # derived bounds admit the inventory
    monkeypatch.delenv("CUSTODIAN_ACCESS_LOG")
    with pytest.raises(SystemExit):       # unset/mismatched access log refused
        r2_exec.prepare(dict(spec, work=str(tmp_path / "work2")), env={k: v for k, v in env.items() if k != "CUSTODIAN_ACCESS_LOG"})
    monkeypatch.setenv("CUSTODIAN_ACCESS_LOG", str(log))
    with pytest.raises(SystemExit):       # under-allocation refused at prepare time (generous floors, RESOURCE-POLICY)
        r2_exec.prepare(dict(spec, work=str(tmp_path / "work4")), env={**env, "SLURM_CPUS_PER_TASK": "4"})
    stingy = save(tmp_path / "template-old.json", dict(template, bounds=dict(template["bounds"], output_file_bytes=1 << 30)))
    with pytest.raises(SystemExit):       # a template built by the old derive_bounds is refused: re-stage it
        r2_exec.prepare(dict(spec, work=str(tmp_path / "work5"), template=stingy), env=env)
    big_log = tmp_path / "big.jsonl"
    with big_log.open("wb") as stream:      # sparse: 13 GiB stat size + 4 GiB growth > 16 GiB FSIZE bound (runner.py:325 mirror)
        stream.truncate(13 << 30)
    log_template = save(tmp_path / "template-biglog.json", dict(template, access_log=str(big_log)))
    with pytest.raises(SystemExit):
        r2_exec.prepare(dict(spec, work=str(tmp_path / "work6"), template=log_template),
                        env={**env, "CUSTODIAN_ACCESS_LOG": str(big_log)})
    go.unlink()
    with pytest.raises(SystemExit):
        r2_exec.prepare(dict(spec, work=str(tmp_path / "work3")), env=env)


def test_inventory_never_drops_a_reachable_file_and_fails_loudly_when_it_cannot_follow(tmp_path, monkeypatch):
    """q22 §5: a non-binary document over the follow cap used to be SKIPPED SILENTLY (every reference nested
    inside it vanished from the inventory -> the runner refuses 'Read outside exact source inventory' late).
    Now: inventory inclusion is never size-gated, and a too-large reachable document fails the build loudly."""
    monkeypatch.setattr(r2_plan, "FOLLOW_CAP", 1 << 10)
    (tmp_path / "freeze").mkdir()
    freeze = tmp_path / "freeze" / "freeze.json"
    freeze.write_text('{"arms": []}')
    labels = tmp_path / "labels.json"
    labels.write_text('{"kind": "synthetic-labels"}')
    payload = tmp_path / "big.pt"                                   # binary payload: inventoried, never followed
    payload.write_bytes(b"\0" * 2048)
    doc = tmp_path / "freeze" / "manifest.json"
    doc.write_text(json.dumps({"payload": ref(payload), "pad": "x" * 2048}, sort_keys=True))
    plan = {"freeze": ref(freeze), "labels": ref(labels), "manifest": ref(doc)}
    with pytest.raises(ValueError, match="too large to follow"):
        r2_plan.build_inventory(plan)                               # loud, not silent (nested refs must not vanish)
    monkeypatch.setattr(r2_plan, "FOLLOW_CAP", 1 << 30)
    inventory = {x["path"]: x for x in r2_plan.build_inventory(plan)}
    assert str(doc) in inventory and str(payload) in inventory      # every reachable file is inventoried
    b = r2_plan.derive_bounds(list(inventory.values()))
    assert b["output_file_bytes"] == 16 << 30 and b["access_log_bytes"] == 4 << 30 and b["input_view_cache_bytes"] == 64 << 30
    assert all(b[k + "_bytes"] >= 16 << 30 for k in ("metadata", "input", "checkpoint", "label", "total_unique", "total_read"))
