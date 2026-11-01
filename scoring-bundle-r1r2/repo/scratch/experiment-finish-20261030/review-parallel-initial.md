# Independent initial parallel-scoring review

Status: the per-event chunking design is suitable for the pinned pure scorer, subject to final tests, a hard worker cap, and review of the integrated driver. This is not label-opening approval.

Reviewed adapter: `performance/r2_parallel_scoring.py`, SHA-256 `19cd091f8a6eea2b0327319251ba4e72915a93f88b55e94e16a1ed216635a399` (relative to this report's directory).

The pinned `score_membership` validates global IDs and then computes each event independently, with no aggregate numerical reduction, RNG or I/O. The adapter reproduces global ID validation in the parent, passes the exact selected score function to fork-inherited state, scores contiguous event slices and concatenates them in original event order. Prediction ordering is preserved semantically by its ID map. Duplicate event rows, which the original function accepts, are supported by deduplicating each chunk's prediction list while leaving event rows intact. Earliest chunk failure is propagated in event order. No scientific arithmetic is changed.

Independent local probe with `.venv/bin/python -B` and the real pinned scorer: exact JSON output equality for 31 valid neural rows with independently reversed prediction order; equality with duplicate event rows crossing chunks; identical exception type/message for extra, missing and duplicate prediction IDs. Adapter source was inspected read-only and no experiment artifact was read.

Required before integration:

1. `_resolve_workers` at line 102 does not enforce `max_workers` for explicit `workers`: `_resolve_workers(64, 8, 500)` returns 64. Enforce the agreed maximum eight workers for every call, also respecting available CPUs/allocation. The current draft test exercises 64 rather than proving the cap.
2. Complete the real-scorer equivalence tests. The current test draft has invalid fixtures: candidate/probability lengths differ; mixed events receive rules despite missing history signatures; the float32-edge prediction omits the edge candidate that float32 selects. Fix those fixtures before claiming an equivalence pass. Include both scorer variants, ties, empty/no-growth rows, baseline/native candidates, curves, history rules, mismatched global IDs, duplicate predictions, accepted duplicate events, ordering, input immutability and first-error ordering.
3. Include the adapter's source hash and exact execution options in the replacement dry-run ready record and open-mode verification. Keep the checkpoint code/fingerprints unchanged because this adapter affects post-preparation scoring only.

Correct private attachment points inside the existing D-A39 `install_layer`:

- In its composition-components wrapper, after `r2_float32_scoring.patch(modules['membership'])`, replace only `modules['membership'].scoring` with the adapter's private copy of that already-patched scoring module. Preserve its float32 marker and underlying selected function.
- In the same wrapper, replace only `modules['stable'].m.scoring` with a private parallel copy of its existing float64 scoring module.
- In the outer components wrapper, replace only `loaded['origin'].m.scoring` and `loaded['baseline'].m.scoring` with private parallel copies of their existing float64 scoring modules.
- Apply to every newly constructed component module; component loaders create fresh objects. Preserve isolation wrappers. Never assign into the shared `bgbench.forecast_retrospective_scoring` module or into any consumer's `m.original`, and never patch the primary evaluator.

Performance limitation: every membership-style `m.score_cell` first executes `m.original.per_event_rows`, which serially recomputes ranking metrics for every event. This adapter accelerates the subsequent `m.scoring.score_membership` pass only. It can reduce the tail but does not remove that earlier serial pass. Confirm runtime expectations accordingly; any additional optimization requires its own scope and equivalence review.
