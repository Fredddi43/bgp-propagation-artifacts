#!/usr/bin/env python3
"""Integration proof for the D-A40 driver's attach points (adapted from chain-d39-v2's D-A39 v2 version).

Loads the REAL pinned runner consumers (runner.components() / compose.components(), every file
sha-checked by the pinned loaders), attaches through the driver's own install_parallel_adapters and
r2_stable_not_scorable.install in the driver's own order (stable only: D-A40 scores no other lane),
and proves: the shared bgbench modules and the primary evaluator are untouched; the stable consumer's
private copies wrap the plain float64 scorers (no float32 anywhere); membership, origin and baseline
are not attached at all; evaluate_new_period and every other attribute pass through by identity; of
the consumers' own functions only the stable consumer's persistence and its m.score_cell are rebound
(to the D-A40 wrapper of the same code), nothing on the preparation path; installs are idempotent and
recorded; checkpoint fingerprints are bit-identical across the attach; the adapter and the rule stay
OUT of the checkpoint keys; pins and options are fixed.

Run: /path/repo/.venv/bin/python -m pytest test_r2_parallel_integration.py -q
"""
import hashlib
import importlib.util
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
import r2_checkpoint  # noqa: E402
import r2_float32_scoring as F32  # noqa: E402
import r2_parallel_scoring as P  # noqa: E402
import r2_rescore_stable as D  # noqa: E402
import r2_stable_not_scorable as NS  # noqa: E402
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
    """The D-A40 driver's own attach sequence (composition_components): the stable consumer only."""
    D.install_parallel_adapters(consumers["stable"].m, "stable")
    NS.install(consumers["stable"])


def test_pins_options_and_checkpoint_keys_are_fixed():
    assert hashlib.sha256((HERE / "r2_checkpoint.py").read_bytes()).hexdigest() == CHECKPOINT_SHA
    assert D.PARALLEL_ADAPTER_OPTIONS == {"max_workers": 8, "min_parallel_rows": 8192, "chunks_per_worker": 4}
    assert P.MAX_WORKERS == 8 and D.PARALLEL_ADAPTER_OPTIONS["max_workers"] <= P.MAX_WORKERS
    for name in ("r2_parallel_scoring.py", "r2_stable_not_scorable.py", "r2_rescore_stable.py"):
        assert name not in r2_checkpoint.COMMON_FILES
        assert all(name not in names for names in r2_checkpoint.STAGE_FILES.values())


def test_checkpoint_key_files_identical_to_d39():
    """code_fingerprint hashes these files by name and content in this directory: they must be the chain-d39-v2 bytes, so every
    checkpoint key (and the D-A39 binding the driver requires) is unchanged."""
    d39 = HERE.parent / "chain-d39-v2"
    names = set(r2_checkpoint.COMMON_FILES) | {f for files in r2_checkpoint.STAGE_FILES.values() for f in files}
    assert names == {"r2_checkpoint.py", "r2_parallel_origin.py", "r2_input_cache.py", "r2_fast_json.py",
                     "r2_float32_decision.py", "r2_stable_persistence.py"}
    if d39.is_dir():   # the sibling copy is the reference where it exists (the repo checkout); the pinned sha covers the rest
        for name in sorted(names):
            assert (HERE / name).read_bytes() == (d39 / name).read_bytes(), name
        for stage in r2_checkpoint.STAGE_FILES:
            assert r2_checkpoint.code_fingerprint(directory=HERE, stage=stage) == r2_checkpoint.code_fingerprint(directory=d39, stage=stage)


def test_attach_points_stable_only_float64_private(pinned):
    D.STATE["parallel_installs"] = []
    before_shared = shared_snapshot()
    before_fp = {stage: r2_checkpoint.code_fingerprint(stage=stage) for stage in r2_checkpoint.STAGE_FILES}
    before_self = {name: consumer_callables(module) for name, module in pinned.items()}
    before_m = consumer_callables(pinned["stable"].m)
    others = {name: (c.scoring, c.original) for name, c in (("membership", pinned["membership"]), ("origin", pinned["origin"].m),
                                                            ("baseline", pinned["baseline"].m))}

    attach(pinned)

    # --- recorded installs: exactly two, scoring before original, stable only ---------------------
    assert D.STATE["parallel_installs"] == ["stable.scoring", "stable.original"]

    # --- stable: plain float64 selected, no float32 anywhere -------------------------------------
    scoring = pinned["stable"].m.scoring
    assert scoring is not S and getattr(scoring, P.MARK) is True
    assert getattr(scoring, F32.MARK, False) is False
    assert scoring.__dict__[P.UNDERLYING] is S.score_membership                  # untouched float64 function
    original = pinned["stable"].m.original
    assert getattr(original, P.MARK) is True and original is not CE
    assert original.__dict__[P.UNDERLYING] is CE.per_event_rows
    assert original.evaluate_new_period is CE.evaluate_new_period               # NEVER wrapped
    assert original.check_rows_label_free is CE.check_rows_label_free

    # --- membership / origin / baseline: not attached at all (D-A40 does not score them) ---------
    for name, consumer in (("membership", pinned["membership"]), ("origin", pinned["origin"].m),
                           ("baseline", pinned["baseline"].m)):
        assert (consumer.scoring, consumer.original) == others[name], name
        assert getattr(consumer.scoring, P.MARK, False) is False and getattr(consumer.scoring, F32.MARK, False) is False, name

    # --- shared modules and the primary evaluator are byte-for-byte the same objects ------------
    for name, module in (("scoring", S), ("eval", CE)):
        assert_attrs_unchanged(before_shared[name], dict(vars(module)), f"shared:{name}")
    assert getattr(S, P.MARK, False) is False and getattr(CE, P.MARK, False) is False
    assert not hasattr(S, NS.MARK) and not hasattr(CE, NS.MARK)

    # --- consumers' own functions: only stable.persistence and stable.m.score_cell are rebound --
    for name, module in pinned.items():
        after = consumer_callables(module)
        expected = {k: v for k, v in before_self[name].items()}
        if name == "stable":
            assert after["persistence"] is not expected["persistence"] and getattr(after["persistence"], NS.MARK) is True
            assert after["persistence"].__wrapped__ is expected["persistence"]
            after = {k: v for k, v in after.items() if k != "persistence"}
            expected = {k: v for k, v in expected.items() if k != "persistence"}
        assert_attrs_unchanged(expected, after, f"consumer:{name}")
    after_m = consumer_callables(pinned["stable"].m)
    assert getattr(after_m["score_cell"], NS.MARK) is True and after_m["score_cell"].__wrapped__ is before_m["score_cell"]
    assert_attrs_unchanged({k: v for k, v in before_m.items() if k not in ("score_cell", "scoring", "original")},
                           {k: v for k, v in after_m.items() if k not in ("score_cell", "scoring", "original")}, "stable.m")
    assert pinned["stable"].prepare_sealed is before_self["stable"]["prepare_sealed"]   # the preparation path is untouched

    # --- checkpoint keys cannot shift: fingerprint identical across the attach ------------------
    assert {stage: r2_checkpoint.code_fingerprint(stage=stage) for stage in r2_checkpoint.STAGE_FILES} == before_fp

    # --- idempotent: re-attaching changes nothing and records nothing ----------------------------
    recorded = list(D.STATE["parallel_installs"])
    targets = (pinned["stable"].m.scoring, pinned["stable"].m.original, pinned["stable"].persistence, pinned["stable"].m.score_cell)
    attach(pinned)
    assert D.STATE["parallel_installs"] == recorded
    assert (pinned["stable"].m.scoring, pinned["stable"].m.original, pinned["stable"].persistence,
            pinned["stable"].m.score_cell) == targets

    # --- end to end below the threshold: output equals the plain float64 serial scorer exactly ---
    stable_rows = TS.build_mixed(60)
    assert TS.deep_eq(pinned["stable"].m.scoring.score_membership(*stable_rows), S.score_membership(*stable_rows))
    assert isinstance(pinned["stable"].m, types.ModuleType)
