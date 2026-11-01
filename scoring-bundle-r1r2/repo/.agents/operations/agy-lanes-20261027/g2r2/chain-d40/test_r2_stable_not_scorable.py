"""D-A40: synthetic tests of the stable-lane not-scorable rule (r2_stable_not_scorable.py) through the REAL pinned stable consumer.

The stable consumer is compiled from its pinned, sha-checked source exactly as compose.components() does, the D-A40 attach order of
the driver is used (private parallel adapters on m, then the rule), and the consumer's own evaluate scores synthetic cells: a neural
cell (m.score_cell), a history-knn-mean baseline cell (m.score_cell) and a persistence cell (consumer.persistence). No label table
exists anywhere near these tests; nothing outside a temp directory is read or written.

Covered: the D-A39 failure reproduces without the rule; with it, every empty-target AND empty-forecast event is excluded from every
metric of every cell and counted, identically across the arms of a horizon; every other event is scored exactly as the unchanged
pinned code scores it; no exclusion leaves the report unchanged except the added count; the exclusion set depends on target and
forecast emptiness only; the label-free pre-check refuses unpaired arms and slice rules; the wrapper refuses without (or against)
the frozen pre-check; pins and call-site shapes are checked.

Run: .venv/bin/python -B -m pytest -q -p no:cacheprovider test_r2_stable_not_scorable.py
"""
import copy
import hashlib
import random
import sys
import types
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "src" / "bgbench").is_dir())
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

import bgbench.forecast_custodian_eval as CE  # noqa: E402
import bgbench.forecast_retrospective_scoring as S  # noqa: E402
from bgbench.forecast_stable_peer import STABLE_SELECTION_SHA256  # noqa: E402
import r2_rescore_stable as D  # noqa: E402
import r2_stable_not_scorable as NS  # noqa: E402

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")
STABLE_DIR = ROOT / ".agents/operations/newperiod-single-r2-persistence-20261024/components/composition/components/stable"
CONSUMER_SHA = "deb124b1931cfa36f0dff0fdc3a2a4d592edbd2147c0d662e44986c09aabb712"   # compose.py COMPONENTS['stable']
D39_FAILURE = "Empty target and prediction: Jaccard undefined on a scorable event"
NO_INPUT = "unavailable_no_input"
CURVE = [[0.5, 1.0, 1.5], [1.0, 1.5, 2.0], [1.5, 2.0, 2.5], [2.0, 2.5, 3.0]]   # float32-exact, monotone log quantiles


def load_stable():
    """The pinned stable consumer, compiled from its sha-checked source as compose.components() does."""
    path = STABLE_DIR / "consumer.py"
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == CONSUMER_SHA
    module = types.ModuleType("secondary_composition_stable")
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


def attach(consumer):
    """The driver's own attach order on the stable consumer (composition_components)."""
    D.install_parallel_adapters(consumer.m, "stable")
    NS.install(consumer)
    return consumer


@pytest.fixture(autouse=True)
def clean():
    NS.reset()
    D.STATE["parallel_installs"] = []
    yield
    NS.reset()


# ------------------------------------------------------------------------------------------------------------- synthetic data
# event: (event_id, input_status, seeds, candidates, probabilities, target or None for censored)
EVENTS = [
    ("e1", "available", [1], [1, 2, 3], [0.9, 0.8, 0.1], [1, 2, 4]),
    ("e2", NO_INPUT, [], [], [], []),                      # abstention, empty target: empty/empty -> not scorable
    ("e3", NO_INPUT, [], [], [], [5, 6]),                  # abstention, non-empty target: the pinned penalty scores it
    ("e4", NO_INPUT, [], [], [], None),                    # abstention, censored: stays censored
    ("e5", "available", [7], [7, 8], [0.2, 0.3], []),      # empty target, non-empty forecast (the seed): Jaccard 0, scored
    ("e6", "available", [9], [9, 10, 11], [0.95, 0.6, 0.4], [9, 10]),
]


def truth(target):
    if target is None:
        return {"target_scope": "stable_peer_only", "target_status": "censored"}
    asns = sorted(set(target))
    return {"target_scope": "stable_peer_only", "target_status": "scorable", "selection_sha256": STABLE_SELECTION_SHA256,
            "target_asns": asns, "target_counts": {str(t): len(asns) for t in (300, 900, 3600, 7200)}}


def rows_for(events):
    return [{"event_id": eid, "onset": f"2026-09-0{1 + i % 9}T00:00:00+00:00", "incident_id": f"inc-{eid}", "input_status": status}
            for i, (eid, status, *_rest) in enumerate(events)]


def inputs_for(events):
    return {eid: {"event_id": eid, "asn": list(c), "seed_asns": list(s)} for eid, status, s, c, _p, _t in events if status == "available"}


def neural_cell(events, arm="stable-neural-d30-s0", horizon=30):
    predictions = []
    for eid, status, seeds, candidates, probabilities, _t in events:
        if status != "available":
            predictions.append({"event_id": eid, "seed_asns": [], "predicted_asns": [], "curve_log_quantiles": [[0.0] * 3] * 4,
                                "observation_cutoff_s": horizon})
            continue
        predicted = sorted(set(seeds) | {a for a, p in zip(candidates, probabilities) if p >= 0.5})
        predictions.append({"event_id": eid, "seed_asns": list(seeds), "candidate_asns": list(candidates),
                            "probabilities": list(probabilities), "threshold": 0.5, "predicted_asns": predicted,
                            "curve_log_quantiles": CURVE, "observation_cutoff_s": horizon})
    role = dict(family="neural", variant="stable", training="updated", panel="reference", history="on", message_passing="sage",
                horizon_seconds=horizon, seed=0)
    return dict(status="committed", arm_id=arm, role=role, rows=rows_for(events), predictions=predictions, inputs=inputs_for(events),
                commitment={}, baseline=False, candidates="matched", issue_time=None, slice_rule=None)


def baseline_cell(events, model, arm, horizon=30, extra=None):
    predictions = []
    for eid, status, seeds, candidates, probabilities, _t in events:
        if status != "available":
            predictions.append({"event_id": eid, "seed_asns": [], "predicted_asns": []})
            continue
        if model == "persistence":
            scores, predicted = [1.0 if a in seeds else 0.0 for a in candidates], sorted(seeds)
        else:
            scores = list(probabilities)
            predicted = sorted(set(seeds) | {a for a, p in zip(candidates, probabilities) if p >= 0.5})
        if extra and eid in extra:
            predicted = sorted(set(predicted) | set(extra[eid]))
        predictions.append({"event_id": eid, "seed_asns": list(seeds), "candidate_asns": list(candidates),
                            "ranking_scores": scores, "predicted_asns": predicted})
    role = dict(family="baseline", variant="stable", panel="reference", baseline=model, candidates="matched", library="online",
                horizon_seconds=horizon)
    return dict(status="committed", arm_id=arm, role=role, rows=rows_for(events), predictions=predictions, inputs=inputs_for(events),
                commitment={}, baseline=True, candidates="matched", issue_time=None, slice_rule=None)


def prepared_for(events, cells, horizons=("30", "60")):
    ids = sorted(e[0] for e in events)
    evidence = {"validated_target_scope": {"stable_source": "synthetic", "selection": "synthetic"},
                "expected_label_masters": {h: f"master-{h}" for h in horizons}, "cohort_ids": {h: ids for h in horizons},
                "label_horizon": {h: h for h in horizons}, "target_scope": "stable_peer_only"}
    available = sorted(eid for eid, status, *_ in events if status == "available")
    return {"cells": cells, "evidence": evidence, "available": {h: available for h in horizons}}


def table_for(prepared, events, horizons=("30", "60")):
    e = prepared["evidence"]
    return {"kind": "custodian_stable_label_table", "target_scope": "stable_peer_only",
            "provenance": {"reference_scope": e["validated_target_scope"], "masters": e["expected_label_masters"]},
            "horizons": {h: {eid: truth(target) for eid, _s, _se, _c, _p, target in events} for h in horizons}}


def three_arms(events, extra=None):
    cells = {"neural": neural_cell(events), "knn": baseline_cell(events, "history-knn-mean", "stable-knn-d30", extra=extra),
             "persistence": baseline_cell(events, "persistence", "stable-persistence-d30"),
             "failed": {"status": "not_estimable", "role": {"horizon_seconds": 30, "variant": "stable"}, "failure_chain": ["x"]}}
    prepared = prepared_for(events, cells)
    return prepared, table_for(prepared, events)


def pre_check_and_freeze(prepared):
    check = NS.check_prepared([prepared])
    NS.freeze_expected(check)
    return check


def without(report_cell, field=NS.FIELD):
    return {k: v for k, v in report_cell.items() if k != field}


# ------------------------------------------------------------------------------------------------------------------- tests

def test_d39_failure_reproduces_without_the_rule():
    prepared, table = three_arms(EVENTS)
    consumer = load_stable()
    D.install_parallel_adapters(consumer.m, "stable")
    with pytest.raises(ValueError, match=D39_FAILURE):
        consumer.evaluate(prepared, table)


def test_empty_empty_excluded_counted_and_paired_across_arms():
    prepared, table = three_arms(EVENTS)
    consumer = attach(load_stable())
    check = pre_check_and_freeze(prepared)
    assert check["paired"] is True and check["horizons"]["30"]["distinct_empty_forecast_sets"] == 1
    assert {a: c["empty_forecast_ids"] for a, c in check["cells"].items()} == {
        "stable-neural-d30-s0": ["e2", "e3", "e4"], "stable-knn-d30": ["e2", "e3", "e4"], "stable-persistence-d30": ["e2", "e3", "e4"]}
    assert all(c["empty_forecast_equals_input_abstentions"] for c in check["cells"].values())
    report = consumer.evaluate(prepared, table)
    for name in ("neural", "knn", "persistence"):
        cell = report["cells"][name]
        field = cell[NS.FIELD]
        assert field["count"] == 1 and field["event_ids"] == ["e2"] and field["input_status_counts"] == {NO_INPUT: 1}, name
        scored = [r["event_id"] for r in cell["rows"]]
        assert "e2" not in scored and "e4" not in scored and scored == ["e1", "e3", "e5", "e6"], (name, scored)
        assert "e2" not in [r["event_id"] for r in cell["input_available_rows"]]
        assert (cell["reference_events"], cell["scorable_events"], cell["censored_events"]) == (6, 4, 1), name
        assert cell["reference_events"] == cell["scorable_events"] + cell["censored_events"] + field["count"]
        assert cell["input_status_counts"] == {"available": 3, NO_INPUT: 3}, name   # the full cell, as the pinned scorer reports it
    assert report["cells"]["failed"] == prepared["cells"]["failed"]           # a not-estimable cell passes through untouched
    assert sorted((r["arm_id"], r["path"], r["event_ids"]) for r in NS.RECORDS) == [
        ("stable-knn-d30", "score_cell", ["e2"]), ("stable-neural-d30-s0", "score_cell", ["e2"]),
        ("stable-persistence-d30", "persistence", ["e2"])]


def test_every_other_event_scored_exactly_as_the_pinned_code():
    """Independent reference: the UNPATCHED consumer on the same cells, with only e2's target made non-empty (per-event scoring is
    independent), must give byte-identical rows for every other event and the same population counts."""
    prepared, table = three_arms(EVENTS)
    consumer = attach(load_stable())
    pre_check_and_freeze(prepared)
    patched = consumer.evaluate(copy.deepcopy(prepared), table)
    events_ref = [(e[0], e[1], e[2], e[3], e[4], [99] if e[0] == "e2" else e[5]) for e in EVENTS]
    reference_prepared, reference_table = three_arms(events_ref)
    plain = load_stable()
    D.install_parallel_adapters(plain.m, "stable")
    reference = plain.evaluate(reference_prepared, reference_table)
    for name in ("neural", "knn", "persistence"):
        ours = {r["event_id"]: r for r in patched["cells"][name]["rows"]}
        theirs = {r["event_id"]: r for r in reference["cells"][name]["rows"] if r["event_id"] != "e2"}
        assert ours == theirs, name                                             # every metric of every other event
        assert [r["event_id"] for r in patched["cells"][name]["input_available_rows"]] == \
            [r["event_id"] for r in reference["cells"][name]["input_available_rows"]]
        for key in ("reference_events", "censored_events", "input_status_counts", "role", "status"):
            assert patched["cells"][name][key] == reference["cells"][name][key], (name, key)
        assert patched["cells"][name]["scorable_events"] == reference["cells"][name]["scorable_events"] - 1
    assert {k: v for k, v in patched.items() if k != "cells"} == {k: v for k, v in reference.items() if k != "cells"}


def test_no_exclusion_leaves_the_report_unchanged_except_the_count():
    events = [e for e in EVENTS if e[0] != "e2"]                                 # no empty/empty event at all
    prepared, table = three_arms(events)
    plain = load_stable()
    D.install_parallel_adapters(plain.m, "stable")
    expected = plain.evaluate(copy.deepcopy(prepared), table)
    consumer = attach(load_stable())
    pre_check_and_freeze(prepared)
    got = consumer.evaluate(prepared, table)
    assert {k: v for k, v in got.items() if k != "cells"} == {k: v for k, v in expected.items() if k != "cells"}
    for name, cell in got["cells"].items():
        if cell.get("status") != "scored":
            assert cell == expected["cells"][name]
            continue
        assert cell[NS.FIELD] == {"rule": NS.RULE, "count": 0, "event_ids": [], "input_status_counts": {}}
        assert without(cell) == expected["cells"][name], name


def test_available_input_with_empty_forecast_follows_the_same_rule():
    events = EVENTS + [("e7", "available", [], [12, 13], [0.1, 0.2], [])]       # no seed, nothing above threshold, empty target
    prepared, table = three_arms(events)
    consumer = attach(load_stable())
    check = pre_check_and_freeze(prepared)
    assert all(c["empty_forecast_ids"] == ["e2", "e3", "e4", "e7"] and not c["empty_forecast_equals_input_abstentions"]
               for c in check["cells"].values())
    report = consumer.evaluate(prepared, table)
    for name in ("neural", "knn", "persistence"):
        cell = report["cells"][name]
        assert cell[NS.FIELD]["event_ids"] == ["e2", "e7"] and cell[NS.FIELD]["input_status_counts"] == {NO_INPUT: 1, "available": 1}
        assert {"e2", "e7"}.isdisjoint(r["event_id"] for r in cell["rows"])
        assert {"e2", "e7"}.isdisjoint(r["event_id"] for r in cell["input_available_rows"])
        assert (cell["reference_events"], cell["scorable_events"], cell["censored_events"]) == (7, 4, 1)


def test_unpaired_empty_forecasts_refused_before_any_label():
    events = EVENTS + [("e7", "available", [], [12, 13], [0.1, 0.2], [])]
    prepared, _table = three_arms(events, extra={"e7": [12]})                  # the knn arm forecasts something on e7, the others not
    check = NS.check_prepared([prepared])
    assert check["paired"] is False and check["horizons"]["30"]["distinct_empty_forecast_sets"] == 2
    assert any("differ between the committed cells" in p for p in check["problems"])
    with pytest.raises(ValueError, match="pre-check did not pass"):
        NS.freeze_expected(check)
    assert NS.EXPECTED == {}


def test_slice_rule_and_duplicate_arm_refused_by_the_pre_check():
    prepared, _ = three_arms(EVENTS)
    prepared["cells"]["neural"]["slice_rule"] = {"variable": "seeds_at_issue", "cut": 2}
    check = NS.check_prepared([prepared])
    assert check["paired"] is False and any("slice rule" in p for p in check["problems"])
    prepared, _ = three_arms(EVENTS)
    prepared["cells"]["knn"]["arm_id"] = prepared["cells"]["neural"]["arm_id"]
    check = NS.check_prepared([prepared])
    assert check["paired"] is False and any("duplicate arm id" in p for p in check["problems"])


def test_wrapper_refuses_without_or_against_the_frozen_pre_check():
    prepared, table = three_arms(EVENTS)
    consumer = attach(load_stable())
    with pytest.raises(ValueError, match="no label-free empty-forecast record"):
        consumer.evaluate(prepared, table)
    pre_check_and_freeze(prepared)
    changed = copy.deepcopy(prepared)
    row = next(p for p in changed["cells"]["neural"]["predictions"] if p["event_id"] == "e5")
    row["predicted_asns"], row["seed_asns"] = [], []                          # the cell no longer matches what was frozen
    changed["cells"]["neural"]["inputs"]["e5"]["seed_asns"] = []
    with pytest.raises(ValueError, match="differ from the label-free pre-check"):
        consumer.evaluate(changed, table)
    other = NS.check_prepared([three_arms(EVENTS + [("e7", "available", [], [12, 13], [0.1, 0.2], [])])[0]])
    with pytest.raises(ValueError, match="fixed once per run"):
        NS.freeze_expected(other)


def test_exclusion_depends_on_target_and_forecast_emptiness_only():
    """Random cells: the excluded set is exactly {scorable, empty target, empty forecast}; censored or non-empty-target events and
    every other label value (other targets, counts) never move an event in or out."""
    rng = random.Random(20261101)
    exclusions = 0
    for trial in range(25):
        two_arms = trial % 2 == 0      # even: neural + persistence (every available row keeps a seed, so both forecast it);
        events = []                    # odd: one neural arm, where an available row may also forecast nothing
        for i in range(14):
            eid = f"r{trial}-{i:02d}"
            kind = rng.choice(["available", NO_INPUT])
            target = rng.choice([None, [], [], [100 + i], [i, 200 + i]])
            if kind == "available":
                seeds = [i] if two_arms else rng.choice([[], [i]])
                candidates = [i, 300 + i, 400 + i] if seeds else [300 + i, 400 + i]
                probabilities = [rng.choice([0.1, 0.7]) for _ in candidates]
                events.append((eid, kind, seeds, candidates, probabilities, target))
            else:
                events.append((eid, kind, [], [], [], target))
        cells = {"neural": neural_cell(events)}
        if two_arms:
            cells["persistence"] = baseline_cell(events, "persistence", "stable-persistence-d30")
        prepared = prepared_for(events, cells)
        check = NS.check_prepared([prepared])
        assert check["paired"] is True, trial
        table = table_for(prepared, events)
        NS.reset()
        consumer = attach(load_stable())
        NS.freeze_expected(check)
        report = consumer.evaluate(prepared, table)
        empty_forecast = set(check["cells"]["stable-neural-d30-s0"]["empty_forecast_ids"])
        expected = sorted(eid for eid, _s, _se, _c, _p, target in events if target == [] and eid in empty_forecast)
        exclusions += len(expected)
        for name in cells:
            assert report["cells"][name][NS.FIELD]["event_ids"] == expected, (trial, name)
            scored = {r["event_id"] for r in report["cells"][name]["rows"]}
            censored = {eid for eid, _s, _se, _c, _p, target in events if target is None}
            assert scored == {e[0] for e in events} - set(expected) - censored, (trial, name)
        # perturb every label value that is not target emptiness: the exclusion must not move
        perturbed = copy.deepcopy(table)
        for labels in perturbed["horizons"].values():
            for label in labels.values():
                if label["target_status"] == "scorable" and label["target_asns"]:
                    label["target_asns"] = sorted(set(label["target_asns"]) | {999})
                    label["target_counts"] = {k: len(label["target_asns"]) for k in label["target_counts"]}
        NS.RECORDS.clear()
        again = consumer.evaluate(prepared, perturbed)
        for name in cells:
            assert again["cells"][name][NS.FIELD]["event_ids"] == expected, (trial, name)
    assert exclusions >= 25, exclusions                                         # the property was exercised, not vacuous


def test_install_pins_shapes_and_idempotence(tmp_path):
    consumer = attach(load_stable())
    first = (consumer.persistence, consumer.m.score_cell)
    assert NS.installed(consumer) and all(getattr(f, NS.MARK) for f in first)
    NS.install(consumer)
    assert (consumer.persistence, consumer.m.score_cell) == first             # idempotent
    # shared bgbench modules untouched; only the consumer's own two entry points and m's scoring/original are rebound
    assert CE.per_event_rows is consumer.m.original.__dict__["_r2_parallel_underlying"]
    assert S.score_membership is consumer.m.scoring.__dict__["_r2_parallel_underlying"]
    assert not hasattr(CE, NS.MARK) and not hasattr(S, NS.MARK)
    fresh = load_stable()                                                     # every other function keeps its pinned code
    changed = sorted(n for n, v in vars(consumer).items()
                     if isinstance(v, types.FunctionType) and vars(fresh)[n].__code__ != v.__code__)
    changed_m = sorted(n for n, v in vars(consumer.m).items()
                       if isinstance(v, types.FunctionType) and vars(fresh.m)[n].__code__ != v.__code__)
    assert changed == ["persistence"] and changed_m == ["score_cell"], (changed, changed_m)
    assert consumer.persistence.__wrapped__.__code__ == fresh.persistence.__code__
    assert consumer.m.score_cell.__wrapped__.__code__ == fresh.m.score_cell.__code__
    assert getattr(fresh.persistence, NS.MARK, False) is False
    # a consumer whose bytes differ from the pin is refused before anything is wrapped
    copy_path = tmp_path / "consumer.py"
    copy_path.write_bytes((STABLE_DIR / "consumer.py").read_bytes() + b"\n# changed\n")
    impostor = types.SimpleNamespace(__file__=str(copy_path), m=fresh.m, persistence=fresh.persistence)
    with pytest.raises(ValueError, match="consumer.py differs from its pinned hash"):
        NS.install(impostor)
    assert getattr(impostor.persistence, NS.MARK, False) is False


def test_pins_match_the_pinned_sources():
    assert hashlib.sha256((STABLE_DIR / "consumer.py").read_bytes()).hexdigest() == NS.CONSUMER_SHA
    assert hashlib.sha256((STABLE_DIR / "reviewed_membership.py").read_bytes()).hexdigest() == NS.MEMBERSHIP_SHA
    assert hashlib.sha256(Path(CE.__file__).read_bytes()).hexdigest() == NS.CUSTODIAN_EVAL_SHA
    consumer = load_stable()
    NS.check_shape(consumer)                                                    # the call sites the wrapper relies on
    assert "_jaccard" in Path(CE.__file__).read_text()
