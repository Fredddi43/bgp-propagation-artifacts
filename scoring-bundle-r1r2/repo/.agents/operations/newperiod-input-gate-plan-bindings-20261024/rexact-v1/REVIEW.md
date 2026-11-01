# R-exact A→B successor binder + core B gate-phase spec builder (CK3 0532cf59 M1–M3)

Author: claude-opus-5-5 f4d75bb1 (/root/opus_implementation). Code only. Nothing executed, nothing staged.
The original `../bind.py` (f5d05feb, root PASS dfb26e58) and `../test_bind.py` are byte-unchanged (a test checks this).

## M1: `rexact-v1/bind.py`

Deltas from `../bind.py`:
- Keys `core-rexact` / `temporal-rexact`. Roots are `BASE/newperiod-input-gate-{private,temporal}-rexact-v1`.
- Request kind `primary_gate_metadata_binding_rexact_v1`, so the two binders' requests never cross.
- Source manifest is `<root>/source-manifest.json`, with the sha pinned per key: core c68c9727, temporal 3e7f8aff
  (the exact members of the staged source tars 7f236cc8 / 2eb4d7d1). The manifest must also say
  kind `newperiod_temporal_gate_source_v1` and `root == <root>/source`.
- New check: the plan code must name the revision-v1 package `audit_witness.py` and no `/revision-v5/` file. The
  revision-v1 B (input_gate.py:267) needs its own package's audit_witness as the trace entry.
- The emitted plan keeps the scientific `input_profile` `core`/`temporal`, and the export path `exports/{profile}`.
- Output is `<root>/gate-plan-bindings-v1/plan-input-gate.json`. Gate out is
  `<root>/gate-control-v1/outputs/input-gate.json`.
- Unchanged: every other ancestry check, the custody-log-first order (the log record kind now ends `_rexact`), the
  9-read/6-stat finite set, and the bounds.

## M2: tests, `rexact-v1/test_bind.py` (23 pass)

- The real pins: c68c9727 / 3e7f8aff extracted from the real tars name their own roots, and they cover every code
  pin of the real R-exact plans (core-v1 / temporal-v2, d30/d60).
- Positive: core-rexact and temporal-rexact plans pass the revision-v1 `checked_inputs` (AST-extracted).
- Refusals:
  - an R-exact witness against the d3e3c20a placement manifest (request level), and against an old-verifier
    manifest (content level);
  - plan-code pins checked even when all recorded modules agree;
  - a source manifest naming another kind or root;
  - original roots under an rexact key;
  - rexact roots under original keys (both binders), and core↔temporal swapped;
  - an original request kind;
  - a revision-v5 audit_witness in the plan code;
  - 9 ancestry mutations, including an export path naming the other profile.
- The finite logged invocation: log first, exactly 10 opens, no tensor path, exclusive output (a second invoke
  refuses).
- Mutation check: removing each of 6 key checks (source-manifest pin, manifest kind/root, plan-code pins, package
  check, request kind, export profile) makes at least one test fail.

## M3: `newperiod-feature7-rexact-recovery-20261024/core-c1/core-v1/gate-phase-v1/build_gate.py` (16 tests pass)

- `request` builds the successor-binder request from the ACTUAL core A outcome capture (the reviewed capture.py
  51737170 shape). It refuses unless all of these hold:
  - launched/started name spec 8dbe98d5;
  - exit `{returncode 0, no retry}`;
  - result `{passed true, rc 0}`;
  - both stage results rc 0 with empty stderr and `audit_passed true`;
  - every record path is under the R-exact core witness root.
- Inventory and assembly refs come from the root-accepted primary-export master outcome (root-actual-assessment /
  its request).
- `spec` builds the gate-phase spec:
  - phase `gate`, scope `newperiod-input-gate-issue-execution-v1`, root `.../private-rexact-v1/gate-control-v1`;
  - stage plan = the binder's actual output sha (staged as `plan-gate.json`);
  - `witness_exit` = the captured execution-exit reference; `witness_spec` = 8dbe98d5;
  - placement / stage / source manifests, files, tracer and python are copied from the launched witness spec.
- Resources are the earlier reviewed core B draft's: 8 GiB AS, 3600 s CPU, 256 MiB FSIZE, 2 threads, 1800 s wall.
  **Reviewer: confirm these or set others.**
- The gate authority stays `pending` (sha null) until root issues it. `gate_execute.checked_spec` refuses a pending
  spec, and accepts the built spec once a sha is supplied (tested).
- Refuses the real failed temporal capture (rc 1, d30 postimage, foreign root).

## Not done / blocked

- **Core A has not run.** It is held because R-exact temporal still failed at `postimage` with a passing report
  (diagnostic result routed separately). M3 therefore cannot be exercised on real records yet.
- B execution needs, in order:
  1. a successful core A capture;
  2. this binder run once (exact request approval);
  3. a gate-phase transport (not built: same pattern as the witness transport);
  4. independent B approval;
  5. a separate root gate-issuance authority.
- M4 respected: label_handoff, predict.py, forecast_inputs and the runtime verifiers are untouched.
