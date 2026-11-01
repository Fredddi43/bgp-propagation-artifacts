#!/usr/bin/env python3
"""Integration proof for the D-A39 v2 driver's PRIVATE parallel-adapter attach points.

Loads the REAL pinned runner consumers (runner.components() / compose.components(), every file
sha-checked by the pinned loaders), attaches through the driver's own install_parallel_adapters in
the driver's own order, and proves: the shared bgbench modules and the primary evaluator are
untouched; membership's wrapped scorer is the ALREADY-selected float32 score_membership while
stable/origin/baseline keep plain float64; evaluate_new_period and every other attribute pass
through by identity; the consumers' own functions are not rebound (inert before the label, no
prep-path change); installs are idempotent and recorded; checkpoint fingerprints are bit-identical
across the attach; the adapter file stays OUT of the checkpoint keys; pins and options are fixed.

Run: /path/repo/.venv/bin/python -m pytest test_r2_parallel_integration.py -q
"""
import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "src" / "bgbench").is_dir())
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

import bgbench.forecast_custodian_eval as CE  # noqa: E402
import bgbench.forecast_retrospective_scoring as S  # noqa: E402
import r2_checkpoint  # noqa: E402
import r2_float32_scoring as F32  # noqa: E402
import r2_parallel_scoring as P  # noqa: E402
import r2_rescore_secondary as D  # noqa: E402
import test_r2_parallel_scoring as TS  # noqa: E402  (fixture builder + deep_eq only)

RUNNER_DIR = ROOT / ".agents/operations/newperiod-single-r2-persistence-20261024"
CHECKPOINT_SHA = "97382e4abe67240152e5c01763eb970b0fc5c32eedfb77f0e7453d3dcb580be4"

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")  # fork under pytest host threads


@pytest.fixture(scope="module")
def pinned():
    """The REAL secondary consumers, loaded exactly as r2_exec does (sha-pinned at every hop)."""
    spec = importlib.util.spec_from_file_location("pinned_runner", RUNNER_DIR / "runner.py")
    runner = importlib.util.module_from_spec(spec)
    sys.modules["pinned_runner"] = runner
    spec.loader.exec_module(runner)                         # sha-checks runtime_helpers
    loaded = runner.components()                            # sha-checks baseline/composition/origin
    composition = loaded["composition"].components()        # sha-checks stable/count/membership
    try:
        yield {"origin": loaded["origin"], "baseline": loaded["baseline"],
               "membership": composition["membership"], "stable": composition["stable"]}
    finally:
        sys.modules.pop("pinned_runner", None)


def shared_snapshot():
    """Every attribute of the two SHARED scorer modules, held by object identity."""
    return {name: dict(vars(module)) for name, module in (("scoring", S), ("eval", CE))}


def assert_attrs_unchanged(before, after, label):
    """Same attribute names, every value the SAME object (identity, never numpy ==)."""
    assert set(after) == set(before), label
    for key, value in after.items():
        assert value is before[key], (label, key)


def consumer_callables(module):
    return {name: obj for name, obj in vars(module).items() if callable(obj)}


def attach(consumers):
    """The driver's own attach sequence for all four secondary consumers."""
    F32.patch(consumers["membership"])                      # composition_components runs this first
    D.install_parallel_adapters(consumers["membership"], "membership")
    D.install_parallel_adapters(consumers["stable"].m, "stable")
    D.install_parallel_adapters(consumers["origin"].m, "origin")
    D.install_parallel_adapters(consumers["baseline"].m, "baseline")


def test_pins_options_and_checkpoint_keys_are_fixed():
    assert hashlib.sha256((HERE / "r2_checkpoint.py").read_bytes()).hexdigest() == CHECKPOINT_SHA
    assert D.PARALLEL_ADAPTER_OPTIONS == {"max_workers": 8, "min_parallel_rows": 8192, "chunks_per_worker": 4}
    assert P.MAX_WORKERS == 8 and D.PARALLEL_ADAPTER_OPTIONS["max_workers"] <= P.MAX_WORKERS
    assert "r2_parallel_scoring.py" not in r2_checkpoint.COMMON_FILES
    assert all("r2_parallel_scoring.py" not in names for names in r2_checkpoint.STAGE_FILES.values())


def test_attach_points_private_only_float32_selected_others_float64(pinned):
    D.STATE["parallel_installs"] = []
    before_shared = shared_snapshot()
    before_fp = {stage: r2_checkpoint.code_fingerprint(stage=stage) for stage in r2_checkpoint.STAGE_FILES}
    before_self = {name: consumer_callables(module) for name, module in pinned.items()}
    assert pinned["membership"].scoring is S and getattr(S, F32.MARK, False) is False

    f32 = F32.patch(pinned["membership"])                   # capture the SELECTED float32 module
    attach(pinned)                                          # second patch call is idempotent by design

    # --- recorded installs: exactly eight, scoring before original, in driver order -------------
    assert D.STATE["parallel_installs"] == [
        "membership.scoring", "membership.original", "stable.scoring", "stable.original",
        "origin.scoring", "origin.original", "baseline.scoring", "baseline.original"]

    # --- membership: the parallel copy wraps the ALREADY-selected float32 score_membership ------
    m_scoring = pinned["membership"].scoring
    assert m_scoring is not S and getattr(m_scoring, P.MARK) is True
    assert getattr(m_scoring, F32.MARK) is True                       # float32 marker survives the copy
    assert m_scoring.__dict__[P.UNDERLYING] is f32.score_membership   # the selected function, not the shared one

    # --- stable/origin/baseline: plain float64 selected, no float32 anywhere --------------------
    for name, consumer in (("stable", pinned["stable"].m), ("origin", pinned["origin"].m),
                           ("baseline", pinned["baseline"].m)):
        scoring = consumer.scoring
        assert scoring is not S and getattr(scoring, P.MARK) is True, name
        assert getattr(scoring, F32.MARK, False) is False, name
        assert scoring.__dict__[P.UNDERLYING] is S.score_membership, name   # untouched float64 function

    # --- originals: only per_event_rows is replaced; the primary evaluator path passes through --
    for name, consumer in (("membership", pinned["membership"]), ("stable", pinned["stable"].m),
                           ("origin", pinned["origin"].m), ("baseline", pinned["baseline"].m)):
        original = consumer.original
        assert getattr(original, P.MARK) is True and original is not CE, name
        assert original.__dict__[P.UNDERLYING] is CE.per_event_rows, name
        assert original.evaluate_new_period is CE.evaluate_new_period, name        # NEVER wrapped
        assert original.check_rows_label_free is CE.check_rows_label_free, name

    # --- shared modules and the primary evaluator are byte-for-byte the same objects ------------
    for name, module in (("scoring", S), ("eval", CE)):
        assert_attrs_unchanged(before_shared[name], dict(vars(module)), f"shared:{name}")
    assert getattr(S, P.MARK, False) is False and getattr(CE, P.MARK, False) is False
    assert S.score_membership is before_shared["scoring"]["score_membership"]
    assert CE.per_event_rows is before_shared["eval"]["per_event_rows"]

    # --- the consumers' own functions are never rebound: inert before the label, prep unchanged -
    for name, module in pinned.items():
        assert_attrs_unchanged({k: v for k, v in before_self[name].items()},
                               consumer_callables(module), f"consumer:{name}")

    # --- checkpoint keys cannot shift: fingerprint identical across the attach ------------------
    assert {stage: r2_checkpoint.code_fingerprint(stage=stage) for stage in r2_checkpoint.STAGE_FILES} == before_fp

    # --- idempotent: re-attaching changes nothing and records nothing ----------------------------
    recorded = list(D.STATE["parallel_installs"])
    targets = [(pinned["membership"].scoring, pinned["membership"].original),
               (pinned["stable"].m.scoring, pinned["stable"].m.original),
               (pinned["origin"].m.scoring, pinned["origin"].m.original),
               (pinned["baseline"].m.scoring, pinned["baseline"].m.original)]
    attach(pinned)
    assert D.STATE["parallel_installs"] == recorded
    assert [(pinned["membership"].scoring, pinned["membership"].original),
            (pinned["stable"].m.scoring, pinned["stable"].m.original),
            (pinned["origin"].m.scoring, pinned["origin"].m.original),
            (pinned["baseline"].m.scoring, pinned["baseline"].m.original)] == targets

    # --- end to end below the threshold: output equals the SELECTED serial scorer exactly -------
    predictions, events, rules = TS.build_mixed(120)
    wrapped = m_scoring.score_membership(predictions, events, rules)
    assert TS.deep_eq(wrapped, f32.score_membership(predictions, events, rules))
    stable_rows = TS.build_mixed(60)
    assert TS.deep_eq(pinned["stable"].m.scoring.score_membership(*stable_rows),
                      S.score_membership(*stable_rows))              # float64 float64-equal
