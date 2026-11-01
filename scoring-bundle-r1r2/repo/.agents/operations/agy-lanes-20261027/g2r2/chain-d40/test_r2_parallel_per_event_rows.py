"""Exact-equivalence tests for parallel_per_event_rows against the REAL forecast_custodian_eval.

Synthetic only — no labels are opened, no cluster, no driver. per_event_rows runs the full label-free
checks AND the per-event scoring inside each child (the adapter never weakens or repeats them in the
parent); parallel output must equal serial output exactly, in reference order, for matched/neural and
native-baseline arms, censored/abstention rows, issue-time slice rules, shuffled predictions and
duplicate manifest rows — and every failure must cross the IPC boundary unchanged.

Run: .venv/bin/python -m pytest scratch/experiment-finish-20261030/performance/test_r2_parallel_per_event_rows.py -q
"""

import hashlib
import os
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "src" / "bgbench").is_dir())  # repo root, from performance/ or chain-d39-v2/
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

import bgbench.forecast_custodian_eval as CE  # noqa: E402
import r2_parallel_scoring as P  # noqa: E402

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")
COVERAGE_MSG = "Committed predictions do not cover the reference population exactly"


def fingerprint(value):
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
        elif isinstance(v, np.generic):
            walk(v.item())
        elif isinstance(v, (int, float, str, bool)) or v is None:
            h.update(f"{type(v).__name__}:{v!r}".encode())
        else:
            raise TypeError(type(v).__name__)

    walk(value)
    return h.hexdigest()


def build_per_case(
    n,
    *,
    baseline=False,
    candidates="matched",
    slice_on=False,
    censored_every=None,
    abstain_every=None,
    ties=False,
    seed=20261030,
):
    """A coherent (predictions, manifest_rows, labels, inputs, issue_time, slice_rule) fixture."""
    rng = np.random.default_rng(seed)
    predictions, manifest, labels, inputs, issue_time = [], [], {}, {}, {}
    slice_rule = {"variable": "seeds_at_issue", "cut": 2} if slice_on else None
    for i in range(n):
        eid = f"e{i:05d}"
        cands = [1000 * i + k for k in range(6)]
        seeds = cands[:2]
        abstain = abstain_every is not None and i % abstain_every == 0
        if abstain:
            status = [
                "unavailable_no_input",
                "source_failure",
                "parser_failure",
                "inference_failure",
                "technical_failure",
            ][i % 5]
            predictions.append(
                {"event_id": eid, "seed_asns": seeds, "candidate_asns": [], "predicted_asns": []}
            )
            manifest.append({"event_id": eid, "input_status": status})
        elif baseline:
            scores = [5.0] * 6 if ties else list(range(6, 0, -1))
            predicted = seeds + cands[2:5]
            predictions.append(
                {
                    "event_id": eid,
                    "seed_asns": seeds,
                    "candidate_asns": cands,
                    "predicted_asns": predicted,
                    "ranking_scores": scores,
                }
            )
            manifest.append({"event_id": eid})
        else:
            probs = [0.5] * 6 if ties else [1.0, 1.0] + [float(x) for x in rng.random(4)]
            predicted = sorted(set(seeds) | {c for c, p in zip(cands, probs) if p >= 0.5})
            row = {
                "event_id": eid,
                "seed_asns": seeds,
                "candidate_asns": cands,
                "predicted_asns": predicted,
                "probabilities": probs,
            }
            if slice_on:
                row["slice_predicted_asns"] = seeds + [cands[2]]
            predictions.append(row)
            manifest.append({"event_id": eid})
        target = [cands[0], cands[1]] + [c for c in cands if c % 2 == 0][:2]
        censored = censored_every is not None and i % censored_every == 0
        labels[eid] = {
            "target_status": "censored" if censored else "scorable",
            "target_asns": target,
        }
        if manifest[-1].get("input_status", "available") == "available":
            asn = cands if candidates == "matched" else list(dict.fromkeys(seeds + cands))
            inputs[eid] = {"event_id": eid, "asn": asn, "seed_asns": seeds}
        issue_time[eid] = {"early_growth": 3, "seeds_at_issue": 2}
    return {
        "predictions": predictions,
        "manifest_rows": manifest,
        "labels": labels,
        "inputs": inputs,
        "issue_time": issue_time if slice_on else None,
        "slice_rule": slice_rule,
        "baseline": baseline,
        "candidates": candidates,
    }


def run_serial(case):
    return CE.per_event_rows(
        case["predictions"],
        case["manifest_rows"],
        case["labels"],
        baseline=case["baseline"],
        inputs=case["inputs"],
        candidates=case["candidates"],
        issue_time=case["issue_time"],
        slice_rule=case["slice_rule"],
    )


def run_parallel(case, workers, chunks=3, force=True):
    return P.parallel_per_event_rows(
        CE.per_event_rows,
        case["predictions"],
        case["manifest_rows"],
        case["labels"],
        baseline=case["baseline"],
        inputs=case["inputs"],
        candidates=case["candidates"],
        issue_time=case["issue_time"],
        slice_rule=case["slice_rule"],
        force=force,
        workers=workers,
        chunks_per_worker=chunks,
    )


def test_exact_serial_vs_parallel_matched_neural_and_native_baseline():
    for tag, case in [
        ("neural", build_per_case(300)),
        ("neural-ties", build_per_case(220, ties=True)),
        ("native-baseline", build_per_case(260, baseline=True, candidates="native")),
        (
            "native-baseline-ties",
            build_per_case(200, baseline=True, candidates="native", ties=True),
        ),
    ]:
        serial = run_serial(case)
        assert serial, tag
        for workers in (2, 4):
            assert run_parallel(case, workers) == serial, f"{tag} at workers={workers}"


def test_censored_and_abstention_rows_match_serial():
    case = build_per_case(280, censored_every=5, abstain_every=7)
    serial = run_serial(case)
    assert any(
        r["ranking_status"] in ("no_input", "technical_failure") for r in serial
    )  # abstentions present
    assert all(
        r["event_id"]
        not in {e for e, v in case["labels"].items() if v["target_status"] == "censored"}
        for r in serial
    )  # censored skipped
    for workers in (2, 4):
        assert run_parallel(case, workers) == serial


def test_native_baseline_with_censored_and_abstention():
    case = build_per_case(
        240, baseline=True, candidates="native", censored_every=4, abstain_every=9
    )
    serial = run_serial(case)
    assert run_parallel(case, 4) == serial


def test_issue_time_slice_rules_two_threshold_and_membership_flags():
    case = build_per_case(260, slice_on=True)
    serial = run_serial(case)
    assert any("two_threshold_jaccard" in r and "in_issue_time_slice" in r for r in serial)
    for workers in (2, 4):
        assert run_parallel(case, workers) == serial


def test_shuffled_prediction_order_preserves_output_and_order():
    case = build_per_case(300)
    rng = np.random.default_rng(1)
    shuffled = list(case["predictions"])
    rng.shuffle(shuffled)
    case_shuffled = {**case, "predictions": shuffled}
    serial = run_serial(case_shuffled)
    par = run_parallel(case_shuffled, 4)
    assert par == serial
    assert [r["event_id"] for r in par] == [
        m["event_id"]
        for m in case["manifest_rows"]
        if case["labels"][m["event_id"]]["target_status"] == "scorable"
    ]


def test_duplicate_manifest_rows_are_allowed_and_equal():
    case = build_per_case(140)
    manifest = case["manifest_rows"]
    manifest = (
        manifest[:40] + [manifest[5], manifest[30]] + manifest[40:]
    )  # repeats crossing chunk edges
    case_dup = {**case, "manifest_rows": manifest}
    serial = run_serial(case_dup)
    assert len(serial) == len(run_serial(case)) + sum(
        case["labels"][m["event_id"]]["target_status"] == "scorable"
        for m in (manifest[40], manifest[41])
    )
    assert run_parallel(case_dup, 4, chunks=3) == serial


def test_worker_error_propagates_with_original_type_and_message():
    case = build_per_case(200)
    case["manifest_rows"][150] = {**case["manifest_rows"][150], "input_status": "available"}
    case["inputs"][case["manifest_rows"][150]["event_id"]] = {
        "event_id": case["manifest_rows"][150]["event_id"],
        "asn": [999999],
        "seed_asns": [],
    }  # committed-input mismatch
    with pytest.raises(ValueError) as ser:
        run_serial(case)
    with pytest.raises(ValueError) as par:
        run_parallel(case, 4, chunks=4)
    assert str(par.value) == str(ser.value)


@pytest.mark.parametrize(
    "mutate", ["missing_prediction", "extra_prediction", "duplicate_prediction"]
)
def test_coverage_and_duplicate_prediction_refused_with_same_message(mutate):
    case = build_per_case(160)
    preds, manifest, labels = case["predictions"], case["manifest_rows"], case["labels"]
    if mutate == "missing_prediction":
        preds = preds[:-1]
    elif mutate == "extra_prediction":
        preds = preds + [
            {"event_id": "zzz", "seed_asns": [], "candidate_asns": [], "predicted_asns": []}
        ]
    else:
        preds = preds + [dict(preds[0])]  # duplicate event_id
    for run in (
        lambda: CE.per_event_rows(preds, manifest, labels, baseline=False, inputs=case["inputs"]),
        lambda: P.parallel_per_event_rows(
            CE.per_event_rows,
            preds,
            manifest,
            labels,
            baseline=False,
            inputs=case["inputs"],
            force=True,
            workers=4,
        ),
    ):
        with pytest.raises(ValueError, match="do not cover the reference population"):
            run()


def test_first_error_in_reference_order_names_the_earliest_bad_event():
    # Same failure phase on both events (validation): first-error reproduction is exact here.
    case = build_per_case(300)
    manifest = case["manifest_rows"]

    def poison(idx):
        eid = manifest[idx]["event_id"]
        case["inputs"][eid] = {"event_id": eid, "asn": [-7], "seed_asns": []}

    ids = [m["event_id"] for m in manifest]
    poison(250)
    poison(60)
    with pytest.raises(ValueError) as ser:
        run_serial(case)
    with pytest.raises(ValueError) as par:
        run_parallel(case, 4, chunks=4)
    assert str(par.value) == str(ser.value)
    assert ids[60] in str(par.value)


def test_mixed_failure_phases_both_reject():
    """Review round-2 contract: per_event_rows validates ALL rows label-free, THEN scores; chunks
    interleave the phases, so with independent invalid failures in both phases the surfaced original
    error MAY differ (serial names the later row's validation error; the adapter names the earlier
    chunk's scoring error). What must never differ: both paths refuse the entire call with an original
    error — no invalid input can yield a successful family. Accepted by the owner and reviewer."""
    case = build_per_case(300)
    early = case["manifest_rows"][5]["event_id"]     # chunk 0 failure: scoring-phase (invalid label status)
    late = case["manifest_rows"][200]["event_id"]    # later chunk failure: validation-phase (committed seed mismatch)
    case["labels"][early] = {"target_status": "undeclared_status", "target_asns": []}
    case["inputs"][late] = {**case["inputs"][late], "seed_asns": [987654321]}
    with pytest.raises(ValueError) as ser:
        run_serial(case)
    with pytest.raises(ValueError) as par:
        run_parallel(case, 4, chunks=4)
    assert f"{late}: committed seeds differ from the custodian input" == str(ser.value)  # original phase order
    assert f"Undeclared target status for {early}" == str(par.value)                      # earliest chunk's original error
    assert str(par.value) != str(ser.value)                                               # the accepted, documented difference


def test_input_objects_are_not_mutated():
    case = build_per_case(240, slice_on=True)
    before = {k: fingerprint(v) for k, v in case.items() if isinstance(v, (list, dict))}
    run_serial(case)
    run_parallel(case, 4)
    after = {k: fingerprint(v) for k, v in case.items() if isinstance(v, (list, dict))}
    assert before == after


def test_private_original_copy_leaves_shared_module_untouched():
    original_fn = CE.per_event_rows
    private = P.parallel_original_module(CE, force=True, workers=3, chunks_per_worker=2)
    try:
        assert private is not CE
        assert getattr(private, P.MARK) is True
        assert private.__dict__[P.UNDERLYING] is original_fn
        assert getattr(CE, P.MARK, False) is False
        assert CE.per_event_rows is original_fn  # shared module not mutated
        case = build_per_case(220)
        assert private.per_event_rows(
            case["predictions"],
            case["manifest_rows"],
            case["labels"],
            baseline=False,
            inputs=case["inputs"],
        ) == run_serial(case)
        assert P.parallel_original_module(private) is private  # idempotent
    finally:
        assert CE.per_event_rows is original_fn


def test_parallel_really_runs_across_processes_and_caps_at_eight():
    assert P._resolve_workers(64, P.MAX_WORKERS, 5000) == 8
    assert P._resolve_workers(None, P.MAX_WORKERS, 5000) <= 8

    def pid_fn(predictions, manifest_rows, labels, **kw):
        return [{"event_id": m["event_id"], "pid": os.getpid()} for m in manifest_rows]

    case = build_per_case(500)
    out = P.parallel_per_event_rows(
        pid_fn,
        case["predictions"],
        case["manifest_rows"],
        case["labels"],
        baseline=False,
        inputs=case["inputs"],
        force=True,
        workers=64,
    )
    distinct = {r["pid"] for r in out}
    assert 1 < len(distinct) <= 8  # hard cap honoured in practice
