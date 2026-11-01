"""Evidence builders vs the pinned consumers on the persistence package's synthetic world (invented data only).

Oracle 1: for every family my label-free evidence equals the fixture's hand-written evidence on the shared keys.
Oracle 2: the PINNED runner's evaluate() accepts MY evidence documents (prepare + one label opening) end to end.
The timing label map used here is the fixture's own test choice, NOT a protocol decision."""
import copy
import hashlib
import json
import sys
import types
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import common  # noqa: E402
import build_evidence as be  # noqa: E402
import build_review as br  # noqa: E402
import r2_plan  # noqa: E402

OPS = common.REPO / ".agents/operations"
PERSIST = OPS / "newperiod-single-r2-persistence-20261024/runner.py"
INTEG = OPS / "newperiod-single-r2-execution-20261023/test_integration.py"
FIXTURE_TIMING_MAP = {"5": "30", "10": "30", "30": "30", "60": "60", "300": "30", "900": "30"}


def load(path, name):
    m = types.ModuleType(name)
    m.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), "exec"), m.__dict__)
    return m


def save(p, doc):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(doc, sort_keys=True))
    return be.ref(p)


def read(r):
    return json.loads(Path(r["path"]).read_bytes())


def build_world(tmp_path, monkeypatch):
    f = load(INTEG, "evidence_fixture")
    plan, reader, reads, _ = f.fixture(tmp_path, monkeypatch)
    fixture_ev = {k: read(v) for k, v in plan["evidence"].items()}
    # H1 slice/issue-time refs live on the frozen arms in production: materialize them from the fixture's own tables
    h1 = fixture_ev["h1"]
    rules = save(tmp_path / "ev/slice-rules.json", {"horizons": h1["slice_rules"]})
    tables = {h: save(tmp_path / f"ev/issue-{h}.json", {"input_only": True, "events": h1["issue_time"][h]}) for h in ("30", "60")}
    h1_slice = {"slice_rules": rules, "issue_time_tables": tables}
    # H3 availability ledgers in the forecast_panel_reference shape
    avail = {}
    for h in ("30", "60"):
        avail[h] = {}
        for view, rows in fixture_ev["h3"]["availability"][h].items():
            avail[h][view] = save(tmp_path / f"ev/avail-{view}-{h}.json", {"rows": [
                {"event_id": e, "status": v["status"], "partial_panel_input": v["partial_panel_input"],
                 "input_seed_asns": fixture_ev["h3"]["reference_seeds"][h][e] if view == "reference" else []} for e, v in rows.items()]})
    # G4-plan-shaped refs from the fixture's own bundle/origin/stable documents
    base_ev = read(plan["baseline_evidence"])["pooled_target_lineage"]
    stable = read(plan["stable_evidence"])
    g4 = {"base": {"ordinary": {"masters": base_ev["masters"], "source_inventories": base_ev["source_inventories"],
                                "collector_inventory": base_ev["collector_inventory"], "recipe": base_ev["recipe"]},
                   "stable": {"masters": stable["masters"]}, "stable_source": stable["stable_source"]},
          "origin_evidence": read(plan["origin_evidence"])}
    g4["base"]["ordinary"]["masters"] = stable["primary_masters"] if False else base_ev["masters"]
    g4_path = tmp_path / "ev/g4-plan.json"
    save(g4_path, g4)
    # the stable evidence's primary_masters must be the ordinary scope's masters
    g4["base"]["ordinary"]["masters"] = stable["primary_masters"]
    save(g4_path, g4)
    groups = {k: Path(v["path"]) for k, v in plan["membership_freezes"].items()}
    groups["baseline"] = Path(plan["baseline_freeze"]["path"])
    groups.update(count=Path(plan["count_freeze"]["path"]), stable=Path(plan["stable_freeze"]["path"]), origin=Path(plan["origin_freeze"]["path"]))
    ctx = be.Context(Path(plan["freeze"]["path"]), groups, g4_plan=g4_path, h3_availability=avail, timing_label_map=FIXTURE_TIMING_MAP, h1_slice_decisions=h1_slice)
    return f, plan, fixture_ev, ctx, g4


def test_membership_evidence_equals_fixture_on_shared_keys(tmp_path, monkeypatch):
    f, plan, fixture_ev, ctx, g4 = build_world(tmp_path, monkeypatch)
    for family in be.FAMILIES:
        mine, theirs = be.membership_evidence(ctx, family), fixture_ev[family]
        for key in ("input_only", "target_scope", "cohort_ids", "label_horizon", "availability", "reference_seeds", "slice_rules"):
            if key in mine and key in theirs:
                assert mine[key] == theirs[key], (family, key)
        assert set(mine["comparator_arm_ids"]) == set(theirs.get("comparator_arm_ids", [])), family
    assert be.stable_evidence(ctx) == read(plan["stable_evidence"])
    assert be.origin_evidence(ctx) == read(plan["origin_evidence"])
    base = be.baseline_evidence(ctx)
    assert base["pooled_target_lineage"] == read(plan["baseline_evidence"])["pooled_target_lineage"] and base["cohort_ids"] == read(plan["baseline_evidence"])["cohort_ids"]


def test_builders_refuse_what_the_protocol_leaves_open(tmp_path, monkeypatch):
    f, plan, fixture_ev, ctx, g4 = build_world(tmp_path, monkeypatch)
    ctx.timing_label_map = None
    with pytest.raises(ValueError, match="timing label-horizon map"):
        be.membership_evidence(ctx, "timing")
    ctx.timing_label_map = {k: "45" for k in FIXTURE_TIMING_MAP}
    with pytest.raises(ValueError):
        be.membership_evidence(ctx, "timing")
    # an ambiguous comparator (two retained arms for one key) is refused, never chosen
    dup = copy.deepcopy(next(a for a in ctx.freeze["arms"] if a["role"].get("family") == "neural" and a["role"].get("training") == "updated"
                             and a["role"].get("history") == "on" and a["role"].get("variant") in (None, "core")))
    dup["arm_id"] = "duplicate-comparator"
    ctx.global_arms["duplicate-comparator"] = dup
    with pytest.raises(ValueError, match="AMBIGUOUS"):
        be.comparator_ids(ctx, "h1")


def test_pinned_runner_accepts_my_evidence_and_review(tmp_path, monkeypatch):
    f, plan, fixture_ev, ctx, g4 = build_world(tmp_path, monkeypatch)
    r = load(PERSIST, "evidence_persistence")
    from bgbench import forecast_custodian_eval as original, forecast_custody as custody
    from bgbench import forecast_retrospective_scoring as scores
    monkeypatch.setattr(r, "BOOTSTRAP", f.r.BOOTSTRAP)
    refs = be.build_all(ctx, tmp_path / "mine")
    plan.update(evidence=refs["evidence"], stable_evidence=refs["stable_evidence"], origin_evidence=refs["origin_evidence"],
                baseline_evidence=refs["baseline_evidence"])
    # drafted review, signed the way root does it (signoff flips verdict), then derived for the runner
    draft = br.draft_review(ctx, plan, tmp_path / "review-draft.json")
    assert draft["verdict"] == "PENDING_ROOT" and draft["passed"] is False and draft["reviewer_session"] == "root-session"
    with pytest.raises(ValueError):
        br.signed_review(tmp_path / "review-draft.json", tmp_path / "review-signed.json")
    import subprocess
    subprocess.run(["bash", str(OPS / "agy-lanes-20261027/signoff.sh"), str(tmp_path / "review-draft.json")], check=True, capture_output=True)
    plan["full_retention_review"] = br.signed_review(tmp_path / "review-draft.json", tmp_path / "review-signed.json")
    records = tmp_path / "persistence-records"
    records.mkdir()
    plan.update(records=str(records), primary_output=str(plan["primary_output"]), primary_scores_output=str(records / "primary-scores.json"),
                source_closure=save(tmp_path / "closure.json", {"scientific_pins_sha256": r.PINS_SHA}),
                bounds=dict(output_file_bytes=256 << 20, access_log_bytes=1 << 20, output_total_bytes=(6 * 256 + 1) << 20))
    inventory = r2_plan.build_inventory(plan, extra_paths=[Path(original.__file__).resolve(), Path(scores.__file__).resolve()])
    bounds = {k: 1 << 30 for k in ("metadata_bytes", "input_bytes", "checkpoint_bytes", "label_bytes", "total_unique_bytes", "total_read_bytes", "input_view_cache_bytes")}
    reads = []
    reader = r.Reader(inventory, bounds | {"runtime_file_bytes": 1 << 30}, lambda p, w: reads.append((p, w)), plan["labels"])
    result = r.evaluate(plan, reader, original, custody, r.components(), score_receipts=[])
    assert reader.label_reads == 1 and result["full_newperiod_coverage"] is True
    assert set(result["membership"]) == set(be.FAMILIES) and result["origin"] and result["stable"] and result["additional_baselines"]


def test_timing_equivalence_check_is_label_free_metadata_only(tmp_path, monkeypatch):
    f, plan, fixture_ev, ctx, g4 = build_world(tmp_path, monkeypatch)
    res = be.timing_label_equivalence(ctx)
    assert set(res) == {"timing_cohort_events", "missing_in_a_master", "differing", "equivalent"} and res["timing_cohort_events"] == 40
