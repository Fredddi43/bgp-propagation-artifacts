"""The whole chain on a SYNTHETIC AMENDED freeze (one frozen_sage_on d30 seed-0 cell moved to retained_failures; invented data only):
G3 seal -> arm spec -> evidence + DRAFT review + signed review -> pinned persistence runner evaluate() (one label opening) -> report scripts.
Same synthetic world as test_evidence.py / test_r2_pipeline.py (the persistence package's fixture); the full-freeze twins of every step are the
existing tests, which must keep passing with the wrapper not engaged."""
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import common  # noqa: E402
import amend_wiring  # noqa: E402
import build_evidence as be  # noqa: E402
import build_review as br  # noqa: E402
import g3_seal, make_arm_spec, r2_plan  # noqa: E402
import test_evidence as te  # noqa: E402

TARGET = "frozen_sage_on-d30-s0"
BOUNDS = ("metadata_bytes", "input_bytes", "checkpoint_bytes", "label_bytes", "total_unique_bytes", "total_read_bytes", "input_view_cache_bytes")


def amended_world(tmp_path, monkeypatch):
    f, plan, fixture_ev, ctx, g4 = te.build_world(tmp_path, monkeypatch)
    freeze_path = Path(plan["freeze"]["path"])
    full = json.loads(freeze_path.read_bytes())
    full_spec = json.loads(Path(plan["arm_spec"]["path"]).read_bytes())
    doc = json.loads(freeze_path.read_bytes())
    target = next(a for a in doc["arms"] if a["arm_id"] == TARGET)
    doc["arms"].remove(target)
    note = te.save(tmp_path / "amend/failure-evidence.json", {"synthetic": True})
    doc["retained_failures"].append({"arm_id": TARGET, "role": target["role"], "status": "not_executable", "failure_chain": [note]})
    te.save(freeze_path, doc)                                   # amended freeze (same path: the fixture's seal/plan point at it)
    plan["freeze"] = te.be.ref(freeze_path)
    seal = tmp_path / "g3" / "seal.json"
    g3_seal.main(["--freeze", str(freeze_path), "--expected-freeze-sha256", plan["freeze"]["sha256"],
                  "--expected-arms", str(len(doc["arms"])), "--out", str(seal)])
    spec = tmp_path / "g3" / "arm-spec.json"
    make_arm_spec.main(["--freeze", str(freeze_path), "--extension-decision", plan["extension_decision"]["path"],
                        "--slice-rules", plan["slice_rules"]["path"],
                        *sum([["--issue-time-table", d, t["path"]] for d, t in plan["issue_time_tables"].items()], []),
                        "--repetitions", "200", "--out", str(spec)])
    plan["seal"], plan["arm_spec"] = te.be.ref(seal), te.be.ref(spec)
    ctx.freeze_ref, ctx.freeze = plan["freeze"], doc            # the evidence context reads the amended freeze
    ctx.global_arms = {a["arm_id"]: a for a in doc["arms"] + doc["retained_failures"]}
    return f, plan, ctx, doc, full, full_spec


def finish_plan(plan, ctx, tmp_path, r, original, sign=True):
    refs = be.build_all(ctx, tmp_path / "mine")
    plan.update(evidence=refs["evidence"], stable_evidence=refs["stable_evidence"], origin_evidence=refs["origin_evidence"],
                baseline_evidence=refs["baseline_evidence"])
    draft = br.draft_review(ctx, plan, tmp_path / "review-draft.json")
    subprocess.run(["bash", str(te.OPS / "agy-lanes-20261027/signoff.sh"), str(tmp_path / "review-draft.json")], check=True, capture_output=True)
    plan["full_retention_review"] = br.signed_review(tmp_path / "review-draft.json", tmp_path / "review-signed.json")
    records = tmp_path / "persistence-records"
    records.mkdir()
    plan.update(records=str(records), primary_output=str(plan["primary_output"]), primary_scores_output=str(records / "primary-scores.json"),
                source_closure=te.save(tmp_path / "closure.json", {"scientific_pins_sha256": r.PINS_SHA}),
                bounds=dict(output_file_bytes=256 << 20, access_log_bytes=1 << 20, output_total_bytes=(6 * 256 + 1) << 20))
    from bgbench import forecast_retrospective_scoring as scores
    return draft, r2_plan.build_inventory(plan, extra_paths=[Path(original.__file__).resolve(), Path(scores.__file__).resolve()])


def make_reader(r, inventory, plan):
    reads = []
    return r.Reader(inventory, {k: 1 << 30 for k in BOUNDS} | {"runtime_file_bytes": 1 << 30}, lambda p, w: reads.append((p, w)), plan["labels"]), reads


def test_amended_chain_end_to_end(tmp_path, monkeypatch):
    f, plan, ctx, doc, full, full_spec = amended_world(tmp_path, monkeypatch)
    from bgbench import forecast_custodian_eval as ev, forecast_custody as custody
    r = te.load(te.PERSIST, "amended_persistence")
    monkeypatch.setattr(r, "BOOTSTRAP", f.r.BOOTSTRAP)
    assert amend_wiring.is_amended(doc) and not amend_wiring.is_amended(full)
    # --- arm spec: frozen_sage_on at "60" only; every other evaluation arm exactly as the full freeze derives it
    spec = json.loads(Path(plan["arm_spec"]["path"]).read_bytes())
    assert set(spec["arms"]["frozen_sage_on"]) == {"60"} and spec["custody_spec_sha256"] == plan["freeze"]["sha256"]
    assert {k: v for k, v in spec["arms"].items() if k != "frozen_sage_on"} == {k: v for k, v in full_spec["arms"].items() if k != "frozen_sage_on"}
    assert spec["arms"]["frozen_sage_on"]["60"] == full_spec["arms"]["frozen_sage_on"]["60"]
    assert {k: v for k, v in spec.items() if k not in ("arms", "custody_spec_sha256")} == {k: v for k, v in full_spec.items() if k not in ("arms", "custody_spec_sha256")}
    # --- the review partition needs the unevaluated frozen d30 ids; without them it refuses (negative control), with them it drafts
    assert amend_wiring.unevaluated_ids(doc, ev) == sorted(f"frozen_sage_on-d30-s{s}" for s in range(5))
    real = amend_wiring.unevaluated_ids
    monkeypatch.setattr(amend_wiring, "unevaluated_ids", lambda freeze, ev_: [])
    refs = be.build_all(ctx, tmp_path / "neg")
    with pytest.raises(ValueError, match="partition"):
        br.draft_review(ctx, dict(refs, seal=plan["seal"], pre_R2_implementation_binding=plan["pre_R2_implementation_binding"]), tmp_path / "neg-draft.json")
    monkeypatch.setattr(amend_wiring, "unevaluated_ids", real)
    original = amend_wiring.fresh_installed(ev)
    draft, inventory = finish_plan(plan, ctx, tmp_path, r, ev)
    ids = next(s for s in draft["statements"] if s["statement"].startswith("Primary evaluation arms"))["evidence"]
    assert ids["unevaluated_frozen_d30_ids"] == real(doc, ev) and ids["union"] == ids["retained"] == 400
    # --- pinned runner, NOT engaged: refuses the amended freeze at derive, before any label is opened
    reader, reads = make_reader(r, inventory, plan)
    with pytest.raises(ValueError):
        r.evaluate(plan, reader, ev, custody, r.components(), score_receipts=[])
    assert reader.label_reads == 0 and not any(p == plan["labels"]["path"] for p, _ in reads)
    # --- engaged exactly as r2_exec does it (engage_runner(runner, freeze) before run); evaluator copy = what scientific_modules returns
    runner = te.load(te.PERSIST, "amended_persistence_engaged")
    monkeypatch.setattr(runner, "BOOTSTRAP", f.r.BOOTSTRAP)
    assert amend_wiring.engage_runner(runner, doc) is True
    assert runner.evaluate.__code__.co_filename.startswith("<d60_only")
    reader, reads = make_reader(runner, inventory, plan)
    receipts = []
    result = runner.evaluate(plan, reader, original, custody, runner.components(), score_receipts=receipts)
    assert reader.label_reads == 1 and sum(p == plan["labels"]["path"] and w == "Custodian label table" for p, w in reads) == 1
    assert result["kind"] == "newperiod_all_retained_R2_evaluation_v1" and result["full_newperiod_coverage"] is True
    primary = result["primary"]
    assert set(primary["arms"]["frozen_sage_on"]) == {"60"} and primary["d60_only_deviation"]["not_available"]
    assert len(receipts) == 1
    # --- report scripts (row 24): the repo scripts refuse the 51-vs-56 mismatch unpatched; run_report_script.py --d60-only passes
    report = tmp_path / "r2-report.json"
    raw = (json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    report.write_bytes(raw)
    digest = te.hashlib.sha256(raw).hexdigest()
    env = {"PYTHONPATH": str(common.REPO / "src"), "PATH": "/usr/bin:/bin"}
    py, driver = [sys.executable, "-B"], str(HERE.parent / "run_report_script.py")
    plain = subprocess.run([*py, str(common.REPO / "scripts/forecast_full_report_facts.py"), str(report), str(tmp_path / "plain"),
                            "--expected-report-sha256", digest], capture_output=True, env=env)
    assert plain.returncode != 0                                  # unpatched facts projection expects 56 primary identities
    facts = tmp_path / "facts"
    subprocess.run([*py, driver, "--d60-only", "forecast_full_report_facts.py", str(report), str(facts), "--expected-report-sha256", digest],
                   check=True, capture_output=True, env=env)
    facts_sha = te.hashlib.sha256((facts / "facts.json").read_bytes()).hexdigest()
    subprocess.run([*py, driver, "--d60-only", "forecast_report_latex.py", str(facts / "facts.json"), str(tmp_path / "tables"),
                    "--expected-facts-sha256", facts_sha], check=True, capture_output=True, env=env)
    assert (tmp_path / "tables" / "main.tex").is_file()


def test_engage_runner_wraps_scientific_modules_and_leaves_full_freeze_alone(tmp_path, monkeypatch):
    from bgbench import forecast_custodian_eval as ev, forecast_custody as custody
    runner = te.load(te.PERSIST, "engage_only")
    before = (runner.evaluate, runner.scientific_modules)
    assert amend_wiring.engage_runner(runner, {"arms": [], "retained_failures": []}) is False
    assert (runner.evaluate, runner.scientific_modules) == before and not runner.__dict__.get("_D60_ONLY_INSTALLED")
    freeze = {"arms": [], "retained_failures": [{"arm_id": "x", "role": {"family": "neural", "variant": "core", "panel": "reference", "message_passing": "sage",
                                                                         "history": "on", "training": "frozen_2025", "seed": 0, "horizon_seconds": 30}}]}
    fresh = types.ModuleType("fresh_eval")
    fresh.__dict__.update({"__file__": ev.__file__})
    monkeypatch.setattr(runner, "scientific_modules", lambda plan: (amend_wiring.fresh_installed(ev), custody))
    # engage wraps whatever scientific_modules is; the wrapper installs d60 on the evaluator it returns (idempotent on an installed one)
    assert amend_wiring.engage_runner(runner, freeze) is True
    evaluator, _ = runner.scientific_modules({})
    assert evaluator.__dict__.get("_D60_ONLY_INSTALLED") and not ev.__dict__.get("_D60_ONLY_INSTALLED")   # sys.modules evaluator untouched here
