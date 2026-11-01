"""D-A39 follow-up: optional, exact-equivalent parallel adapters for the pure custodian scorers.

Two pinned pure scorers loop independently per event (no RNG, no I/O, no aggregate reduction — the
loop only appends to a result list in reference order), and each is the last serial cost of an
otherwise-parallel re-score:

  * ``bgbench.forecast_retrospective_scoring.score_membership(prediction_list, events, rules=None)``
    scores membership/curve/extent/slice metrics per event;
  * ``bgbench.forecast_custodian_eval.per_event_rows(predictions, manifest_rows, labels, *, baseline,
    inputs, candidates="matched", issue_time=None, slice_rule=None)`` scores ranking AP/P@k, Jaccard
    and slice Jaccard per reference event. ``m.score_cell`` runs this BEFORE ``score_membership``, so
    it is the earlier serial origin tail; it recomputes the ranking twice per event (label-free with an
    empty target, then with the truth) — the adapters preserve that, they do not weaken any check.

Exact-equivalence contract (the whole point, not best-effort):
  * The adapter reuses the caller's EXACT selected function per contiguous chunk; no arithmetic, tie
    handling, metric schema, decision, failure, ordering or input object is changed here.
  * A child calls the ORIGINAL function on a matching slice with the FULL read-only inputs/labels/
    kwargs inherited by fork, so every per-event original check still executes; ordered concatenation
    of the chunks equals one serial call.
  * The parent runs ONLY the original's global coverage / duplicate-prediction precondition (same
    error text) before any fork; it does not run the per-event checks (that would repeat work). A worker
    failure is propagated with its original type and message, choosing the earliest-in-reference-order
    failure. For ``score_membership`` (no whole-batch pre-scoring phase) that reproduces the serial
    loop's first error exactly. ``per_event_rows`` validates ALL rows label-free and only then scores
    them, while chunks interleave the two phases: with several independent invalid failures the original
    can refuse on a later row's validation error where the adapter refuses on an earlier row's scoring
    error. Both always refuse the whole call with an original error (never a partial success on invalid
    data), but WHICH error surfaces can differ — accepted by the owner and reviewer as scientific
    scoping; proven by ``test_mixed_failure_phases_both_reject``. The exact-equality contract is
    therefore: on valid (admitted) data the parallel output equals the serial output exactly; any
    invalid input fails closed on both paths.
  * Duplicate reference rows, which both originals accept (they dedup predictions by id and emit a
    row per reference occurrence), are supported by de-duplicating each chunk's prediction list while
    leaving the reference rows intact. Duplicate prediction ids are refused by the original precondition.

It is deliberately INERT: nothing is wired into a driver, and it mutates no shared module.
``parallel_scoring_module`` / ``parallel_original_module`` return PRIVATE module copies (the
r2_float32_scoring.patched_scoring pattern) so a caller can point one secondary consumer's
``scoring`` / ``original`` at the wrapped function without touching the shared bgbench module, the
primary evaluator, or any checkpoint key. Serial fallback is honored for small payloads / force=False.

Fork (copy-on-write) means the huge read-only inputs are INHERITED, not pickled across IPC — a worker
receives only a ``(start, stop)`` index pair. Python 3.14 defaults Linux to "forkserver"; "fork" is
pinned so behaviour matches the 3.12 venv and the node. Not reentrant / not thread-safe: one parallel
job at a time (the scorers are single-threaded). No labels are read; no cluster work is launched.
"""

from __future__ import annotations

import gc
import os
import types
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing as _mp

MARK = "_r2_parallel_scoring"  # idempotence marker on a private module copy
UNDERLYING = "_r2_parallel_underlying"  # the score function a parallel copy wraps
MAX_WORKERS = 8  # agreed hard cap (64-CPU allocation on the 1.95 TB node)

_CTX = _mp.get_context("fork")

# Inherited read-only job state, set by the parent immediately before forking, cleared once drained.
# score_membership job.
_SCORE_FN = _EVENTS = _PRED_BY_ID = _RULES = None
# per_event_rows job.
_PER_FN = _MANIFEST = _PER_PRED_BY_ID = _LABELS = _PER_KWARGS = None


# -------------------------------------------------------------------------------------- chunk plumbing
def _bounds(n, chunks):
    """Contiguous index ranges covering [0, n): the first ``rem`` chunks get one extra row.

    No gaps, no overlaps, order preserved -> concatenating per-chunk results in index order is the
    full reference sequence.
    """
    chunks = max(1, min(chunks, n))
    base, rem = divmod(n, chunks)
    bounds, start = [], 0
    for i in range(chunks):
        size = base + (1 if i < rem else 0)
        bounds.append((start, start + size))
        start += size
    return bounds


def _cpu_budget():
    """CPUs this process may use: the affinity mask (Slurm/cgroup allocation) when available."""
    try:
        return len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        return os.cpu_count() or 1


def _resolve_workers(workers, max_workers, n):
    """Worker count for one call: the smaller of the explicit ``workers`` (when given), ``max_workers``,
    the constant ``MAX_WORKERS`` hard cap and the CPU budget — an oversized ``max_workers`` AND oversized
    ``workers`` together can never exceed 8; only a smaller host/allocation or row count lowers it."""
    cap = max(1, min(MAX_WORKERS, max_workers, _cpu_budget()))
    chosen = cap if workers is None else max(1, min(workers, cap))
    return max(1, min(chosen, n))


def _child_init():
    """Worker initializer: automatic cyclic GC stays OFF in every child. Children inherit the already
    disabled state from the parent (disabled before the fork) — this re-disables explicitly so a worker
    library that enables GC during startup cannot re-expose the inherited ~1 TB of tracked objects."""
    gc.disable()


def _execute_parallel(task_fn, bounds, worker_count):
    """Run ``task_fn(start, stop)`` over every bound across a fork pool; return ordered results.

    Automatic cyclic GC is disabled in the parent BEFORE the pool is created/forks and kept disabled by
    each child's initializer (Python's documented fork/GC interaction: a child's collection can scan and
    mark inherited shared objects and page them through copy-on-write). No ``gc.collect()`` and no
    ``gc.freeze()`` pass anywhere: scanning or freezing the ~1 TB prepared graph is exactly the cost this
    avoids, and these bounded pure scoring calls create no cycles. The parent's PRIOR enabled/disabled
    state is restored in ``finally`` after all workers have drained, including pool-startup and scoring
    failures. Reference counting stays active everywhere.

    Waits for all workers, then raises the earliest-in-reference-order failure; otherwise concatenates
    the per-chunk lists in reference order.
    """
    gc_was_enabled = gc.isenabled()
    gc.disable()
    try:
        with ProcessPoolExecutor(max_workers=worker_count, mp_context=_CTX, initializer=_child_init) as pool:
            futures = {pool.submit(task_fn, start, stop): i for i, (start, stop) in enumerate(bounds)}
            results, errors = {}, {}
            for future in as_completed(futures):
                index = futures[future]
                try:
                    results[index] = future.result()
                except BaseException as error:  # propagate worker failures (incl. SystemExit)
                    errors[index] = error
    finally:
        if gc_was_enabled:
            gc.enable()
    if errors:
        raise errors[min(errors)]
    out = []
    for index in range(len(bounds)):
        out.extend(results[index])
    return out


# ----------------------------------------------------------------------------------- score_membership
def _validate_membership_ids(prediction_list, events):
    """Mirror forecast_retrospective_scoring.score_membership lines 64-66 EXACTLY (same message).

    The parent owns the global ID check so a prediction id missing from events (would be silently
    dropped when chunking) or an event id with no prediction (would raise the wrong error) fails with
    the original message, before any fork. Duplicate prediction ids are refused; duplicate event ids
    are accepted by the original and handled in _score_chunk.
    """
    predictions = {r["event_id"]: r for r in prediction_list}
    if len(predictions) != len(prediction_list) or set(predictions) != {
        e["event_id"] for e in events
    }:
        raise ValueError("Prediction/target event IDs differ or duplicate")
    return predictions


def _score_chunk(start, stop):
    """Worker: run the inherited score function on one contiguous event slice."""
    events_chunk = _EVENTS[start:stop]
    seen, pred_chunk = set(), []
    for i in range(start, stop):
        event_id = _EVENTS[i]["event_id"]
        if event_id not in seen:
            seen.add(event_id)
            pred_chunk.append(_PRED_BY_ID[event_id])
    return _SCORE_FN(pred_chunk, events_chunk, _RULES)


def parallel_score_membership(
    score_fn,
    prediction_list,
    events,
    rules=None,
    *,
    min_parallel_rows=8192,
    max_workers=MAX_WORKERS,
    workers=None,
    force=None,
    chunks_per_worker=4,
):
    """Score with ``score_fn`` (the caller's already-selected score_membership), parallel when large.

    Serial is used when ``force is False``, when ``force is None`` and ``len(events) <
    min_parallel_rows``, for an empty list, or when only one worker would run. Returns exactly what
    ``score_fn`` would. ``max_workers`` defaults to the hard cap 8, further capped by the CPU budget.
    """
    n = len(events)
    if n == 0 or force is False or (force is None and n < min_parallel_rows):
        return score_fn(prediction_list, events, rules)

    global _SCORE_FN, _EVENTS, _PRED_BY_ID, _RULES
    _validate_membership_ids(prediction_list, events)  # exact global failure semantics
    worker_count = _resolve_workers(workers, max_workers, n)
    if worker_count == 1:
        return score_fn(prediction_list, events, rules)
    total_chunks = min(n, max(worker_count, worker_count * max(1, chunks_per_worker)))
    bounds = _bounds(n, total_chunks)
    _SCORE_FN, _EVENTS, _RULES = score_fn, events, rules  # set before forking -> inherited
    _PRED_BY_ID = {r["event_id"]: r for r in prediction_list}
    try:
        return _execute_parallel(_score_chunk, bounds, worker_count)
    finally:
        _SCORE_FN = _EVENTS = _PRED_BY_ID = _RULES = None


# ------------------------------------------------------------------------------------- per_event_rows
def _validate_row_coverage(predictions, manifest_rows):
    """Mirror forecast_custodian_eval.check_rows_label_free lines 445-447 EXACTLY (same message).

    The ONLY parent-side check: reference-population coverage and the duplicate-prediction refusal.
    Duplicate manifest rows are allowed by the original (the manifest id set is de-duplicated); the
    per-event label-free checks run in the children, never here (the parent must not repeat work).
    """
    by_id = {r["event_id"]: r for r in predictions}
    if len(by_id) != len(predictions) or set(by_id) != {m["event_id"] for m in manifest_rows}:
        raise ValueError("Committed predictions do not cover the reference population exactly")
    return by_id


def _per_chunk(start, stop):
    """Worker: run the ORIGINAL per_event_rows on one contiguous manifest slice, full inputs/labels.

    The matching prediction list is de-duplicated by id so a manifest slice that repeats an id (or
    whose repeat lands in another chunk) still satisfies the child's own coverage precondition; the
    child re-runs every per-event check on the FULL inherited inputs/labels/kwargs, so the per-event
    semantics — censored skips, abstentions, matched/native inputs, issue-time slice — are unchanged.
    """
    manifest_chunk = _MANIFEST[start:stop]
    seen, pred_chunk = set(), []
    for i in range(start, stop):
        event_id = _MANIFEST[i]["event_id"]
        if event_id not in seen:
            seen.add(event_id)
            pred_chunk.append(_PER_PRED_BY_ID[event_id])
    kw = _PER_KWARGS
    return _PER_FN(
        pred_chunk,
        manifest_chunk,
        _LABELS,
        baseline=kw["baseline"],
        inputs=kw["inputs"],
        candidates=kw["candidates"],
        issue_time=kw["issue_time"],
        slice_rule=kw["slice_rule"],
    )


def parallel_per_event_rows(
    score_fn,
    predictions,
    manifest_rows,
    labels,
    *,
    baseline,
    inputs,
    candidates="matched",
    issue_time=None,
    slice_rule=None,
    min_parallel_rows=8192,
    max_workers=MAX_WORKERS,
    workers=None,
    force=None,
    chunks_per_worker=4,
):
    """Score with ``score_fn`` (the original per_event_rows), parallel over contiguous manifest chunks.

    ``score_fn`` is passed unchanged so every per-event check runs in the child; the child receives
    the FULL inputs/labels/kwargs. Serial is used when ``force is False``, when ``force is None`` and
    ``len(manifest_rows) < min_parallel_rows``, for an empty list, or when only one worker runs.
    On valid data, returns exactly what a serial ``score_fn`` call returns; on invalid input both paths
    refuse with an original error, though which one surfaces can differ (module contract above).
    """
    n = len(manifest_rows)
    if n == 0 or force is False or (force is None and n < min_parallel_rows):
        return score_fn(
            predictions,
            manifest_rows,
            labels,
            baseline=baseline,
            inputs=inputs,
            candidates=candidates,
            issue_time=issue_time,
            slice_rule=slice_rule,
        )

    global _PER_FN, _MANIFEST, _PER_PRED_BY_ID, _LABELS, _PER_KWARGS
    _validate_row_coverage(predictions, manifest_rows)  # exact global failure semantics
    worker_count = _resolve_workers(workers, max_workers, n)
    if worker_count == 1:
        return score_fn(
            predictions,
            manifest_rows,
            labels,
            baseline=baseline,
            inputs=inputs,
            candidates=candidates,
            issue_time=issue_time,
            slice_rule=slice_rule,
        )
    total_chunks = min(n, max(worker_count, worker_count * max(1, chunks_per_worker)))
    bounds = _bounds(n, total_chunks)
    _PER_FN, _MANIFEST, _LABELS = score_fn, manifest_rows, labels  # set before forking -> inherited
    _PER_KWARGS = {
        "baseline": baseline,
        "inputs": inputs,
        "candidates": candidates,
        "issue_time": issue_time,
        "slice_rule": slice_rule,
    }
    _PER_PRED_BY_ID = {r["event_id"]: r for r in predictions}
    try:
        return _execute_parallel(_per_chunk, bounds, worker_count)
    finally:
        _PER_FN = _MANIFEST = _PER_PRED_BY_ID = _LABELS = _PER_KWARGS = None


# -------------------------------------------------------------------------------- private module copies
def _private_copy(module, attribute, wrapper_factory):
    """A private module copy with ONE attribute replaced; the shared module is never mutated."""
    if getattr(module, MARK, False):
        return module
    original = getattr(module, attribute)
    private = types.ModuleType(module.__name__ + "_parallel")
    private.__dict__.update(module.__dict__)
    private.__dict__[attribute] = wrapper_factory(original)
    private.__dict__[UNDERLYING] = original
    private.__dict__[MARK] = True
    return private


def parallel_scoring_module(scoring, **options):
    """Private copy of a scoring module whose ``score_membership`` is the parallel adapter.

    Closes over the module's own selected score_membership (float32-patched or float64), preserving
    its marker and underlying function. Attaches to a consumer's ``scoring``; never the primary
    evaluator. Idempotent.
    """
    return _private_copy(
        scoring,
        "score_membership",
        lambda original: (
            lambda prediction_list, events, rules=None: parallel_score_membership(
                original, prediction_list, events, rules, **options
            )
        ),
    )


def parallel_original_module(original, **options):
    """Private copy of a custodian-eval-style module whose ``per_event_rows`` is the parallel adapter.

    For a secondary consumer's ``m.original`` only; never the primary evaluator's original module.
    Idempotent.
    """

    def wrap(fn):
        def per_event_rows(predictions, manifest_rows, labels, **kwargs):
            return parallel_per_event_rows(
                fn, predictions, manifest_rows, labels, **kwargs, **options
            )

        return per_event_rows

    return _private_copy(original, "per_event_rows", wrap)
