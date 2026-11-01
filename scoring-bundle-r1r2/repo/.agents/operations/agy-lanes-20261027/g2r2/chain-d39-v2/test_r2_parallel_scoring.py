"""Exact-equivalence tests for r2_parallel_scoring against the REAL bgbench score_membership.

Synthetic only — no labels, no cluster, no driver. The adapter must be observationally identical to
the serial function it wraps: same nested rows in the same event order, same failures, no input
mutation, and the float32-patched membership arithmetic preserved through the parallel path.

Run:  .venv/bin/python -m pytest scratch/experiment-finish-20261030/performance/test_r2_parallel_scoring.py -q
"""

import gc
import hashlib
import os
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "src" / "bgbench").is_dir())  # repo root, from performance/ or chain-d39-v2/
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))  # r2_parallel_scoring and r2_float32_scoring resolve from THIS directory

import bgbench.forecast_retrospective_scoring as S  # noqa: E402
from bgbench.forecast_retrospective_scoring import score_membership  # noqa: E402
import r2_parallel_scoring as P  # noqa: E402
import r2_float32_scoring as F32  # noqa: E402  (read-only patcher)

BASELINES = ("history-knn-mean", "history-knn-median", "topology-seed-adjacency")
CURVE_HORIZONS = np.asarray([300, 900, 3600, 7200])

# pytest's host process is multi-threaded, so fork() warns; the child does bounded pure work and
# returns fast (no deadlock), and real scoring calls run single-threaded. Silence that one warning.
pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


# --------------------------------------------------------------------------- deep equality / fingerprints
def deep_eq(a, b):
    """Structural equality that treats NaN==NaN and checks types (exact nested output equality)."""
    if isinstance(a, float) or isinstance(a, np.floating):
        if isinstance(b, float) or isinstance(b, np.floating):
            fa, fb = float(a), float(b)
            return (fa != fa and fb != fb) or fa == fb
        return False
    if isinstance(a, dict):
        return isinstance(b, dict) and set(a) == set(b) and all(deep_eq(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)):
        return (
            isinstance(b, (list, tuple))
            and len(a) == len(b)
            and all(deep_eq(x, y) for x, y in zip(a, b))
        )
    if isinstance(a, np.ndarray):
        return (
            isinstance(b, np.ndarray)
            and a.shape == b.shape
            and a.dtype == b.dtype
            and np.array_equal(a, b)
        )
    if isinstance(a, (int, np.integer)) and not isinstance(a, bool):
        return isinstance(b, (int, np.integer)) and not isinstance(b, bool) and int(a) == int(b)
    return type(a) is type(b) and a == b


def fingerprint(value):
    """Order/type-sensitive digest of a Python/NumPy object, for input-immutability checks."""
    h = hashlib.sha256()

    def walk(v):
        if isinstance(v, np.ndarray):
            h.update(b"A" + str(v.dtype).encode() + str(v.shape).encode() + v.tobytes())
        elif isinstance(v, dict):
            h.update(b"D")
            for k in sorted(v, key=repr):
                walk(k)
                walk(v[k])
        elif isinstance(v, (list, tuple)):
            h.update(b"L" + str(len(v)).encode())
            for x in v:
                walk(x)
        elif isinstance(v, (np.generic,)):
            walk(v.item())
        elif isinstance(v, (int, float, str, bool)) or v is None:
            h.update(f"{type(v).__name__}:{v!r}".encode())
        else:
            raise TypeError(f"unfingerprintable {type(v).__name__}")

    walk(value)
    return h.hexdigest()


def collect_nones(value, path="", out=None):
    out = out if out is not None else []
    if value is None:
        out.append(path)
    elif isinstance(value, dict):
        for k in value:
            collect_nones(value[k], f"{path}/{k}", out)
    elif isinstance(value, (list, tuple)):
        for i, x in enumerate(value):
            collect_nones(x, f"{path}[{i}]", out)
    return out


# --------------------------------------------------------------------------- synthetic row/event builders
def _probabilities(rng, n, seed_shift):
    """Exactly n probabilities in [0,1]; the first two pinned to 1.0 so committed seeds stay selected."""
    return [1.0, 1.0] + [float(p) for p in rng.random(n - 2)]


def neural_row(rng, i, *, n_candidates=25, threshold=0.5, curve=False, extent=None, history=False):
    candidates = [10000 + i * 100 + k for k in range(n_candidates)]
    seeds = candidates[:2]
    probs = _probabilities(rng, n_candidates, i)
    selected = [c for c, p in zip(candidates, probs) if p >= threshold]
    predicted = sorted(set(seeds) | set(selected))
    row = {
        "event_id": f"e{i:05d}",
        "candidate_asns": candidates,
        "seed_asns": seeds,
        "predicted_asns": predicted,
        "threshold": threshold,
        "probabilities": probs,
    }
    if curve:  # float32-exact log1p quantiles (covered_float32_log_interval requires exact float32)
        q = np.log1p(
            np.asarray(
                [[1.0, 2.0, 3.0], [2.0, 3.0, 4.0], [3.0, 4.0, 5.0], [4.0, 5.0, 6.0]],
                dtype=np.float32,
            )
        ).tolist()
        row.update(curve_log_quantiles=q, observation_cutoff_s=30)
    if extent is not None:
        row["extent"] = extent
    return row, candidates, seeds, threshold, curve, history


def event_for(
    event_id, candidates, seeds, *, grow=6, curve=False, history=False, empty_target=False
):
    target = (
        [] if empty_target else list(candidates[:2]) + [c for c in candidates if c % 7 == 0][:grow]
    )
    event = {
        "event_id": event_id,
        "asn": np.asarray(candidates, dtype=np.int64),
        "seed_asns": np.asarray(seeds, dtype=np.int64),
        "target_asns": np.asarray(sorted(set(map(int, target))), dtype=np.int64),
    }
    if curve:
        event["curve"] = np.asarray([1.0, 3.0, 3.0, 5.0])
    if history:
        event["history_signature"] = np.asarray(np.log1p([4.0, 7.0, 10.0]), dtype=np.float64)
    return event


def baseline_row(i, *, n_candidates=20, baseline="history-knn-mean"):
    candidates = [5000 + i * 100 + k for k in range(n_candidates)]
    seeds = candidates[:2]
    predicted = seeds + candidates[2:8]
    scores = list(range(n_candidates, 0, -1))
    row = {
        "event_id": f"b{i:05d}",
        "candidate_asns": candidates,
        "seed_asns": seeds,
        "predicted_asns": sorted(predicted),
        "ranking_scores": scores,
        "baseline": baseline,
        "candidate_protocol": "matched",
    }
    return row, candidates, seeds


def build_mixed(n=500, seed=20261030):
    """A shuffled mix of neural / baseline / curve / extent / history rows.

    Every event carries an issue-time signature and one rules dict is applied to the whole list, so
    the score_membership slice branch (rules -> two-threshold decision) runs for every row.
    """
    rng = np.random.default_rng(seed)
    predictions, events = [], []
    for i in range(n):
        kind = i % 6
        if kind == 5:  # deterministic baseline arm (ranking_scores, committed decision)
            row, cands, seeds = baseline_row(i)
            events.append(event_for(row["event_id"], cands, seeds, history=True))
        else:
            curve = kind == 1
            extent = float(1000 + i) if kind == 3 else None
            row, cands, seeds, *_ = neural_row(
                rng, i, n_candidates=20 + (i % 15), curve=curve, extent=extent
            )
            events.append(event_for(row["event_id"], cands, seeds, curve=curve, history=True))
        predictions.append(row)
    order = rng.permutation(n)
    predictions = [predictions[i] for i in order]
    events = [events[i] for i in order]
    rules = {
        "global_threshold": 0.5,
        "slice_rule": {"variable": "seeds_at_issue", "cut": 2},
        "slice_threshold": 0.4,
        "remainder_threshold": 0.6,
    }
    return predictions, events, rules


# --------------------------------------------------------------------------- tests
def test_exact_output_serial_vs_parallel_2_and_4_workers():
    predictions, events, rules = build_mixed(600)
    serial = score_membership(predictions, events, rules)
    for workers in (2, 4):
        par = P.parallel_score_membership(
            score_membership,
            predictions,
            events,
            rules,
            force=True,
            workers=workers,
            chunks_per_worker=3,
        )
        assert deep_eq(serial, par), f"nested output differs at workers={workers}"
        assert [r["event_id"] for r in serial] == [r["event_id"] for r in par]


def test_ordering_and_chunk_boundaries_are_exact_across_chunk_sizes():
    predictions, events, rules = build_mixed(401)  # not divisible by any worker count below
    serial = score_membership(predictions, events, rules)
    expected_ids = [e["event_id"] for e in events]
    for workers, cpw in ((1, 1), (3, 1), (3, 5), (7, 1), (7, 4), (8, 9), (64, 1)):
        par = P.parallel_score_membership(
            score_membership,
            predictions,
            events,
            rules,
            force=True,
            workers=workers,
            chunks_per_worker=cpw,
        )
        assert [r["event_id"] for r in par] == expected_ids  # strict event order, no dupes/drops
        assert len(par) == len(events)
        assert deep_eq(serial, par), f"chunk grid workers={workers} cpw={cpw}"


def test_parallel_really_runs_across_processes():
    def pid_fn(prediction_list, events, rules=None):
        return [{"event_id": e["event_id"], "pid": os.getpid()} for e in events]

    n = 8000
    preds = [
        {"event_id": f"p{i}", "candidate_asns": [], "seed_asns": [], "predicted_asns": []}
        for i in range(n)
    ]
    evs = [
        {
            "event_id": f"p{i}",
            "asn": np.zeros(0, int),
            "seed_asns": np.zeros(0, int),
            "target_asns": np.zeros(0, int),
        }
        for i in range(n)
    ]
    serial_pids = {r["pid"] for r in pid_fn(preds, evs, None)}
    par_pids = {
        r["pid"]
        for r in P.parallel_score_membership(pid_fn, preds, evs, None, force=True, workers=4)
    }
    assert len(serial_pids) == 1 and len(par_pids) > 1


def test_serial_fallback_below_threshold_and_force_false():
    calls = {"n": 0}

    def spy(prediction_list, events, rules=None):
        calls["n"] += 1
        return score_membership(prediction_list, events, rules)

    predictions, events, rules = build_mixed(200)  # < 8192 -> auto serial
    assert P.parallel_score_membership(spy, predictions, events, rules) == score_membership(
        predictions, events, rules
    )
    assert calls["n"] == 1
    # force=False forces serial even above the threshold
    big = build_mixed(9000)
    assert P.parallel_score_membership(
        score_membership, big[0], big[1], big[2], force=False
    ) == score_membership(big[0], big[1], big[2])


def test_threshold_edge_under_the_float32_patch_is_preserved_by_parallel():
    """The D-A36/D-A39 edge: p = float32(0.94) < 0.94 in float64, == float32(0.94) in float32."""
    edge = float(np.float32(0.94))
    n = 300
    predictions, events = [], []
    for i in range(n):
        cands = [1000 * i + k for k in range(4)]
        probs = [
            1.0,
            1.0,
            0.99,
            edge if i % 2 else 0.5,
        ]  # the edge candidate is committed-in-float32
        seeds = cands[:2]
        # committed decision as the producer made it: compare in float32 (selects the edge on odd rows)
        predicted = sorted(
            set(seeds) | {c for c, p in zip(cands, probs) if np.float32(p) >= np.float32(0.94)}
        )
        predictions.append(
            {
                "event_id": f"t{i:04d}",
                "candidate_asns": cands,
                "seed_asns": seeds,
                "predicted_asns": predicted,
                "threshold": 0.94,
                "probabilities": probs,
            }
        )
        events.append(
            {
                "event_id": f"t{i:04d}",
                "asn": np.asarray(cands),
                "seed_asns": np.asarray(seeds),
                "target_asns": np.asarray(cands[:2]),
            }
        )
    # Unpatched rejects the committed decision (proves the edge is real); patched accepts it.
    with pytest.raises(ValueError, match="Committed decision differs"):
        score_membership(predictions, events)
    patched = F32.patched_scoring(S)
    serial_patched = patched.score_membership(predictions, events)
    assert serial_patched and len(serial_patched) == n
    for workers in (2, 4):
        par = P.parallel_score_membership(
            patched.score_membership,
            predictions,
            events,
            None,
            force=True,
            workers=workers,
            chunks_per_worker=2,
        )
        assert deep_eq(serial_patched, par)


def test_history_slice_rules_match_serial_including_two_threshold_decision():
    # build a history-heavy set and a rules dict; the two-threshold branch runs for every row
    rng = np.random.default_rng(99)
    n = 240
    predictions, events = [], []
    for i in range(n):
        cands = [100000 + i * 30 + k for k in range(12)]
        seeds = cands[:2]
        probs = [1.0, 1.0] + [float(x) for x in rng.random(10)]
        predicted = sorted(set(seeds) | {c for c, p in zip(cands, probs) if p >= 0.5})
        predictions.append(
            {
                "event_id": f"h{i:04d}",
                "candidate_asns": cands,
                "seed_asns": seeds,
                "predicted_asns": predicted,
                "threshold": 0.5,
                "probabilities": probs,
            }
        )
        event = {
            "event_id": f"h{i:04d}",
            "asn": np.asarray(cands),
            "seed_asns": np.asarray(seeds),
            "target_asns": np.asarray(cands[:2] + [c for c in cands if c % 5 == 0]),
            "history_signature": np.asarray(np.log1p([4.0, 7.0, float(10 + (i % 3))])),
        }
        events.append(event)
    rules = {
        "global_threshold": 0.5,
        "slice_rule": {"variable": "early_growth", "cut": 3},
        "slice_threshold": 0.3,
        "remainder_threshold": 0.7,
    }
    serial = score_membership(predictions, events, rules)
    par = P.parallel_score_membership(
        score_membership, predictions, events, rules, force=True, workers=4, chunks_per_worker=3
    )
    assert deep_eq(serial, par)
    assert any("two_threshold_decision_threshold" in r for r in serial)  # branch really exercised


def test_none_and_nan_normalised_identically_in_serial_and_parallel():
    """No-growth / abstention-ish / baseline rows produce None fields; NaN is normalised to None at
    line 143 of the original. Parallel must place the identical Nones and leak no NaN."""
    predictions, events = [], []
    # (a) no new members: target == seeds  -> average_precision/coverage_ceiling/new_* None
    c = [7, 8, 9]
    predictions.append(
        {
            "event_id": "n0",
            "candidate_asns": c,
            "seed_asns": c,
            "predicted_asns": c,
            "threshold": 0.5,
            "probabilities": [0.9, 0.2, 0.1],
        }
    )
    events.append(
        {"event_id": "n0", "asn": np.array(c), "seed_asns": np.array(c), "target_asns": np.array(c)}
    )
    # (b) baseline row -> probability_calibration None
    row, cands, seeds = baseline_row(1)
    predictions.append(row)
    events.append(event_for(row["event_id"], cands, seeds))
    # (c) empty target -> new_recall None, no_growth True
    c = [11, 12, 13]
    predictions.append(
        {
            "event_id": "n2",
            "candidate_asns": c,
            "seed_asns": [11],
            "predicted_asns": [11, 12],
            "threshold": 0.5,
            "probabilities": [0.9, 0.6, 0.1],
        }
    )
    events.append(
        {
            "event_id": "n2",
            "asn": np.array(c),
            "seed_asns": np.array([11]),
            "target_asns": np.array([], dtype=int),
        }
    )
    # (d) curve with cutoff past every horizon -> curve_smape/cover80 None
    rng = np.random.default_rng(3)
    row, cands, seeds, *_ = neural_row(rng, 4, n_candidates=8, curve=True)
    row["observation_cutoff_s"] = 100000  # future mask empty
    row["predicted_asns"] = sorted(
        set(seeds) | {cc for cc, p in zip(cands, row["probabilities"]) if p >= 0.5}
    )
    predictions.append(row)
    events.append(event_for(row["event_id"], cands, seeds, curve=True))
    for i in range(20):  # pad to cross a chunk boundary at workers>1
        row, cands, seeds, *_ = neural_row(rng, 100 + i)
        predictions.append(row)
        events.append(event_for(row["event_id"], cands, seeds))

    serial = score_membership(predictions, events)
    par = P.parallel_score_membership(
        score_membership, predictions, events, force=True, workers=4, chunks_per_worker=1
    )
    assert deep_eq(serial, par)
    assert collect_nones(serial) == collect_nones(par)
    assert not any(
        v != v for r in par for v in r.values() if isinstance(v, float)
    )  # no NaN survived


def test_input_objects_are_not_mutated_by_serial_or_parallel():
    predictions, events, rules = build_mixed(300)
    before_preds, before_events = fingerprint(predictions), fingerprint(events)
    score_membership(predictions, events, rules)
    P.parallel_score_membership(
        score_membership, predictions, events, rules, force=True, workers=4, chunks_per_worker=3
    )
    assert fingerprint(predictions) == before_preds
    assert fingerprint(events) == before_events
    # a second serial run is still stable (parallel left nothing behind)
    assert fingerprint(predictions) == before_preds


def test_worker_error_propagates_with_original_type_and_message():
    predictions, events, _ = build_mixed(800)
    # break the committed-decision invariant in one late row (the row may be neural or baseline)
    predictions[700] = {
        **predictions[700],
        "predicted_asns": [predictions[700]["candidate_asns"][0]],
    }
    with pytest.raises(ValueError) as serial_err:
        score_membership(predictions, events)
    with pytest.raises(ValueError) as par_err:
        P.parallel_score_membership(
            score_membership, predictions, events, force=True, workers=4, chunks_per_worker=4
        )
    assert str(par_err.value) == str(
        serial_err.value
    )  # same failure crosses the IPC boundary intact


def test_first_error_in_event_order_is_reproduced_with_the_earliest_event_id():
    predictions, events, _ = build_mixed(1000)

    def break_seed(r):
        r = dict(r)
        r["seed_asns"] = [r["seed_asns"][0] + 99999999]
        return r  # sorted-seed mismatch -> id in message

    ids = [e["event_id"] for e in events]
    late, early = 850, 130
    predictions[late] = break_seed(predictions[late])
    predictions[early] = break_seed(predictions[early])
    with pytest.raises(ValueError) as serial_err:
        score_membership(predictions, events)
    with pytest.raises(ValueError) as par_err:
        P.parallel_score_membership(
            score_membership, predictions, events, force=True, workers=4, chunks_per_worker=4
        )
    assert str(serial_err.value) == str(par_err.value)
    assert ids[early] in str(par_err.value)  # earliest-in-event-order failure, matching serial


def test_parallel_module_is_a_private_copy_and_leaves_shared_module_untouched():
    import bgbench.forecast_retrospective_scoring as S

    original_fn = S.score_membership
    private = P.parallel_scoring_module(S, force=True, workers=3, chunks_per_worker=2)
    try:
        assert private is not S
        assert getattr(private, P.MARK) is True
        assert private.__dict__[P.UNDERLYING] is original_fn
        assert getattr(S, P.MARK, False) is False  # shared module NOT mutated
        assert S.score_membership is original_fn  # shared module's function unchanged
        predictions, events, rules = build_mixed(400)
        assert deep_eq(
            S.score_membership(predictions, events, rules),
            private.score_membership(predictions, events, rules),
        )
        # idempotent
        assert P.parallel_scoring_module(private) is private
    finally:
        assert S.score_membership is original_fn


def test_pinned_scoring_source_unchanged():
    """The adapter relies on the pinned file; its sha must still match D-A39's pin."""
    import bgbench.forecast_retrospective_scoring as S

    assert hashlib.sha256(Path(S.__file__).read_bytes()).hexdigest() == F32.SCORING_SHA


def test_duplicate_event_rows_are_accepted_and_equal():
    c = [1, 2, 3, 4]
    seeds = [1, 2]
    row = {
        "event_id": "d",
        "candidate_asns": c,
        "seed_asns": seeds,
        "predicted_asns": [1, 2, 3],
        "threshold": 0.5,
        "probabilities": [1.0, 1.0, 0.7, 0.2],
    }
    events = [
        {
            "event_id": "d",
            "asn": np.array(c),
            "seed_asns": np.array(seeds),
            "target_asns": np.array([1, 2, 3]),
        },
        {
            "event_id": "d",
            "asn": np.array(c),
            "seed_asns": np.array(seeds),
            "target_asns": np.array([1, 2, 3]),
        },
    ]
    serial = score_membership([row], events)
    assert len(serial) == 2 and deep_eq(serial[0], serial[1])  # original accepts duplicate events
    par = P.parallel_score_membership(
        score_membership, [row], events, force=True, workers=3, chunks_per_worker=2
    )
    assert deep_eq(serial, par) and [r["event_id"] for r in par] == ["d", "d"]


def test_duplicate_prediction_ids_are_refused_with_same_message():
    predictions, events, _ = build_mixed(60)
    predictions = predictions + [dict(predictions[0])]  # duplicate event_id in predictions
    with pytest.raises(ValueError) as ser:
        score_membership(predictions, events)
    with pytest.raises(ValueError) as par:
        P.parallel_score_membership(score_membership, predictions, events, force=True, workers=4)
    assert str(par.value) == str(ser.value) == "Prediction/target event IDs differ or duplicate"


def test_mismatched_global_threshold_error_matches_serial():
    predictions, events, rules = build_mixed(300)
    bad = {**rules, "global_threshold": 0.9}  # differs from every row threshold
    with pytest.raises(ValueError) as ser:
        score_membership(predictions, events, bad)
    with pytest.raises(ValueError) as par:
        P.parallel_score_membership(
            score_membership, predictions, events, bad, force=True, workers=4, chunks_per_worker=3
        )
    assert (
        str(par.value) == str(ser.value) == "Decision rules belong to a different global threshold"
    )


def test_native_history_union_baseline_matches_serial():
    preds, events = [], []
    for i in range(40):
        c = [100 * i + k for k in range(8)]
        seeds = c[:2]
        preds.append(
            {
                "event_id": f"n{i:03d}",
                "candidate_asns": list(reversed(c)),
                "seed_asns": seeds,
                "predicted_asns": sorted(set(seeds) | set(c[2:5])),
                "ranking_scores": list(range(8, 0, -1)),
                "baseline": "history-knn-mean",
                "candidate_protocol": "native_history_union",
            }
        )
        events.append(
            {
                "event_id": f"n{i:03d}",
                "asn": np.array(c),
                "seed_asns": np.array(seeds),
                "target_asns": np.array(c[:4]),
            }
        )
    serial = score_membership(preds, events)
    assert serial and all(r["baseline"] == "history-knn-mean" for r in serial)
    for workers in (2, 4):
        assert deep_eq(
            serial,
            P.parallel_score_membership(
                score_membership, preds, events, force=True, workers=workers, chunks_per_worker=3
            ),
        )


def test_ranking_ties_are_reproduced():
    preds, events = [], []
    for i in range(30):
        c = [10 * i + k for k in range(6)]
        preds.append(
            {
                "event_id": f"t{i:03d}",
                "candidate_asns": c,
                "seed_asns": c[:2],
                "predicted_asns": c,
                "threshold": 0.5,
                "probabilities": [0.5] * 6,
            }
        )
        events.append(
            {
                "event_id": f"t{i:03d}",
                "asn": np.array(c),
                "seed_asns": np.array(c[:2]),
                "target_asns": np.array(c[:3]),
            }
        )
    serial = score_membership(preds, events)
    assert all(
        r["average_precision"] is not None for r in serial
    )  # ties give an expected AP, not a crash
    assert deep_eq(
        serial, P.parallel_score_membership(score_membership, preds, events, force=True, workers=4)
    )


def test_worker_count_is_hard_capped_at_eight():
    assert P._resolve_workers(64, P.MAX_WORKERS, 5000) == 8
    assert P._resolve_workers(None, P.MAX_WORKERS, 5000) <= 8
    budget = P._cpu_budget()
    expected = min(P.MAX_WORKERS, budget)  # review round-2 regression: the CONSTANT cap binds too
    assert P._resolve_workers(64, 64, 500) == expected       # oversized workers AND max_workers together
    assert P._resolve_workers(64, 1000, 10_000) == expected
    assert P._resolve_workers(1000, P.MAX_WORKERS, 10_000) == expected
    original_budget = P._cpu_budget
    try:
        P._cpu_budget = lambda: 3                            # a smaller affinity/allocation lowers it further
        assert P._resolve_workers(64, 64, 10_000) == 3
        assert P._resolve_workers(None, P.MAX_WORKERS, 10_000) == 3
    finally:
        P._cpu_budget = original_budget
    assert P._resolve_workers(64, 64, 2) == 2                # row-count cap still binds

    def pid_fn(prediction_list, events, rules=None):
        return [{"event_id": e["event_id"], "pid": os.getpid()} for e in events]

    n = 8000
    preds = [
        {"event_id": f"p{i}", "candidate_asns": [], "seed_asns": [], "predicted_asns": []}
        for i in range(n)
    ]
    evs = [
        {
            "event_id": f"p{i}",
            "asn": np.zeros(0, int),
            "seed_asns": np.zeros(0, int),
            "target_asns": np.zeros(0, int),
        }
        for i in range(n)
    ]
    out = P.parallel_score_membership(pid_fn, preds, evs, None, force=True, workers=64)
    distinct = {r["pid"] for r in out}
    assert 1 < len(distinct) <= 8  # hard cap honoured in practice


def _gc_probe(start, stop):  # module level: resolved by name in the forked children
    import gc as _gc
    return [(start, _gc.isenabled())]


def _boom_probe(start, stop):
    raise RuntimeError(f"probe failure at {start}")


def test_gc_disabled_around_pool_children_never_scan_and_parent_state_restored():
    gc.enable()  # scenario: parent had automatic GC enabled before the call
    out = P._execute_parallel(_gc_probe, [(0, 1), (1, 2), (2, 3)], 2)
    assert [enabled for _, enabled in out] == [False, False, False]  # no child scans the inherited graph
    assert gc.isenabled() is True                                     # prior enabled state restored after drain

    gc.disable()  # scenario: parent had it disabled already — stay disabled, do not force-enable
    try:
        out = P._execute_parallel(_gc_probe, [(0, 1), (1, 2)], 2)
        assert all(not enabled for _, enabled in out)
        assert gc.isenabled() is False
    finally:
        gc.enable()

    gc.enable()  # pool work fails: the finally restores the prior state anyway
    with pytest.raises(RuntimeError):
        P._execute_parallel(_boom_probe, [(0, 1), (1, 2)], 2)
    assert gc.isenabled() is True
