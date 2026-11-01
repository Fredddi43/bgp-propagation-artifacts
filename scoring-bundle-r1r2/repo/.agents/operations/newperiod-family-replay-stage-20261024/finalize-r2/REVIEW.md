# Replay finalize r2: narrow prev_origins fix + fresh finalization root (author f4d75bb1)

Basis: the replay diagnostic actual (5e013ca8) and reviewer 4ba6111c's assessment (F1-F3). Code and spec only:
nothing staged, submitted or run. The failed finalize-0000, its records, the 32 merges, the symlinks and the
eventset in `newperiod-origin-replay-v2` are preserved and are only READ by r2.

## F1: kernel/replay.py:194 (the only scientific change)
- Before: `pl.col('prev_origins').cast(pl.String).str.extract(...)`
- After: `pl.col('prev_origins').cast(pl.List(pl.String)).list.join(',').str.extract(...)`
  This rebuilds the original on-disk form (identifier2.py:352) before the original extraction
  (rpki_validity_events.py:45).
- `prev_origins` occurs exactly once in the operational payload. The only other occurrence,
  kernel/identify.py:56, is a schema-name check.

## F2: tests (`test_finalize_r2.py`, 8 passed, local polars 2.0.0)
- The fixed line, evaluated from the file text, equals the original join-then-extract pipeline on a List[UInt32]
  fixture with multi-origin, empty, single and null lists: `[7, null, 64512, null]`.
- The pre-fix line raises InvalidOperationError on the same fixture (negative control).
- Cluster runtime confirmation: `synthetic_check_cluster.py` ran under the placement venv (polars 1.44.1, the plan's
  pinned version) on synthetic data only. It gave fixed == original == [7, null, 64512, null], and the old line raises
  polars.exceptions.InvalidOperationError (`synthetic-check-cluster.json`).
- Payload delta: only run.py, kernel/replay.py and phases/finalize/{plan.json, job.sh} differ, and the v1
  resource-admission.json is dropped. task-0.json and all 102 source/kernel files are byte-identical.
- The plan differs only in root, stage, the two file pins, the tasks[0] path and resource_admission
  (PENDING_ROOT_ADMISSION).
- Transport delta: exactly 4 lines. The build is reproducible.

## F3: fresh finalization root `.../data-custodian/newperiod-origin-replay-v2-finalize-r2`
- `build.py` -> `payload/` (plan da8c6fae, pending the admission sha):
  - run.py ROOT is the new root. shape() binds plan root and stage = ROOT/control.
  - task-0 still references the 32 preserved v2 merge done/plan files, the candidate and the 47 ROA days, by exact
    sha. They are reused read-only, never moved or replaced.
- `build_transport.py` -> `client_r2.py` (13404d67): the r4 client (7c14c230) with exactly these deltas:
  - both root strings are the new root;
  - the fresh-root branch admits `finalize` (r4 created a fresh root only for `extract`);
  - the existing-root branch excludes extract and finalize.
  Staging, readback, held submission and the held-state check are unchanged. It does not release.
- `packet.py <root admission> <out>`: once root issues the resource admission (it must bind
  `binding(plan)` = 71b26d65), this pins its sha into the plan, re-pins job.sh and writes the v1-shaped stage
  request (106 files).
- `resource-admission.DRAFT.json`: resources identical to v1 (same work, same population); passed=false. Root
  fills in the fresh df, the concurrent reservations and the identity.

## Still needed, in order
1. Your source+spec review.
2. The root resource admission, then the `packet.py` packet and the request sha.
3. Independent stage/held approval and a one-shot transport run.
4. Held-readback review, root release authority and a release successor (release.py with the new JOB/ROOT/PLAN).
5. Outcome capture.
- The later origin `stage` phase must bind the r2 final_done, not v2.
