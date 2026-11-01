# cleanup-five-v2: prune the five 2025 prefix groups that cleanup-seven left untouched (author Opus 4ba6111c)

Author: claude-opus-5-5, worker /root/opus_review, session <SESSION_ID>. The required independent reviewer is f4d75bb1
(/root/opus_implementation). The author cannot approve this. Local code and metadata only: no host calls, no
execution, no authority.

## Why
cleanup-seven (root one-shot 554abaec, now consumed) pruned rrc00-2025 and rrc01-2025, each with an exact proof. It
then refused rrc12-2025 at prune25.py:59, before any unlink: one admission covered a three-group batch, but the
pruner requires its admission to be <= 600 s old when EACH group starts. My assessment of that run is 78a1d32f.

## What changes (`executable/`, against the reviewed prune25-v1 = the executed cleanup-seven sources)
- `consumer_probe.py`: byte-identical (c392b0f9).
- `prune.py` 8a5cf894: two literals plus a docstring note, nothing else (a test proves this).
  * `CONTROL` becomes `storage-prefix25-prune-five-v2-20261024`. The old control root holds the exhausted request and
    authorization, and its files are read-only and were created exclusively.
  * The admission name range grows from 0-3 to 0-4, to allow five single-group admissions.
  * Every check, the journal, the HF re-verification, the source re-hash and the proof are unchanged. That includes
    the 600 s freshness window.
- `execute.py` 43982ec1: the reviewed executor with these deltas.
  * The request must be exactly the five remaining single-group batches, in order rrc12, rrc15, rrc25, route-views3,
    route-views.linx. rrc00/rrc01 are refused explicitly.
  * The request binds the cleanup-seven batch0 execution stdout dba27251. The executor requires it to show exactly
    rrc00 rc0, rrc01 rc0 and rrc12 rc1.
  * Both hosts are probed fresh, and a fresh mechanical admission is written, immediately before EACH group (the
    existing per-batch loop, now one group per batch).
  * New: the admission must be <= 480 s old when sent (`SEND_WINDOW`). Otherwise the executor refuses before that
    group's prune, leaving at least 120 s of the pruner's unchanged 600 s window for the remote start.
  * The per-group prune subprocess timeout rises from 480 s to 1500 s, with the ssh timeout at 1600 s. rrc25 is
    11.96 GB, and the cleanup-seven batch0 took about 13 min for rrc00 + rrc01 (16.7 GB), about 48 s/GB. A kill
    mid-unlink would leave a partial journal, so the limit must clear the largest group, with margin.
  * The new control root goes into the STAGE/BATCH programs; admission indices are 0-4.
  * Unchanged: the scheduler check (both backup arrays terminal, selected tasks COMPLETED 0:0), the active-input
    disjointness proof v2 (157dff1d), the consumer/receipt checks, the exact per-group proof match, and stop on the
    first failure with no retry.

## Request (`executable/request.json` 4459f71f, rebuilt by `build_request.py`)
- It is derived from the reviewed seven-group request dff50923, minus rrc00/rrc01 and their restore drill. The
  verification documents and shas, the archive sources, the recipe, the disjointness reference and the exception
  list are copied unchanged.
- build_request asserts the predecessor evidence: rrc00/rrc01 proofs equal the old request, and rrc12 shows the
  freshness refusal with empty stdout.
- 7,300 files and 35,627,288,316 B logical. That is the seven-group 10,220 / 52,291,526,472 minus the pruned 2,920 /
  16,664,238,156.

## Tests: 25 passed (`test_execute.py` 15, `test_prune.py` 10)
- Every group gets its own fresh admission, even when each prune takes 700 s: 10 probes, 5 admissions. The fake
  pruner asserts the 600 s rule when each group starts.
- An admission too old to send is refused before that group's prune.
- A failing prune stops the run: no later group runs, and failed.json is written.
- Refused requests: one naming rrc00 or rrc01, multi-group batches, four groups, or the wrong order.
- Predecessor evidence must be exact, and changed evidence refuses.
- The generated STAGE/BATCH accept admission index 4 and refuse 5.
- Source deltas are exactly as declared, and the frozen request is reproducible.
- The pruner suite runs the reviewed prune25-v1 cases under the new root, plus index 4 accepted and 5 refused with
  all sources kept.
- Negative controls, run once in a temporary copy that was then deleted:
  * `SEND_WINDOW=600` makes the too-old test fail;
  * reusing the first group's probes for later groups makes the slow-groups test fail with "Consumer evidence
    expired".

## Before any authority (not done here)
1. Independent review by f4d75bb1.
2. A fresh K4 recheck (cleanup-seven-v1/root-ready/k4_recheck.py) and a fresh both-host baseline of unreadable owned
   processes. The request carries the cleanup-seven exception list; its non-sshd entries are pid-specific.
   - If any pid changed, the executor refuses before deleting anything. That is safe, but it wastes the authority.
   - So rebuild `unreadable_process_exceptions` from the fresh baseline, and have the request delta re-reviewed.
3. A root exact one-shot authority binding the final request sha (the executor requires reviewer_worker /root),
   then one invocation as in cleanup-seven INVOCATION.md, with the new paths.
4. Credit only a measured fresh df delta (K3). rrc00/rrc01 are never repeated.
