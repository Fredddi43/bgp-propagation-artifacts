# H3 development construction metadata publication kernel (author Opus f4d75bb1; H3 owner since root takeover 08:30Z)

**Status.** A prospective kernel. No host read, job, coverage or gate was produced; no execution is authorized.

**Composition.** Every module other than publish.py is byte-identical to its reviewed source:

| File | sha | Source |
|---|---|---|
| h3.py | b578690b | variant-construction-binding (root CODE_ONLY 5ba5ea7d) |
| history.py | 7c946614 | same |
| source_io.py | 5c61a00e | same |
| bound_selector.py | f2985250 | same |
| core_metadata.py | cc45d828 | same |
| coverage.py | 0ea072cc | h3-coverage-reconciliation r4 (handoff kernel + eventset.py:72 onset fallback + two input panels + exact original check() six-status port; under review) |
| original_guard.py | 7d2b8e3d | timing publisher (pins the original forecast_manifest/forecast_release via H3 core_metadata) |

**publish.py** is a sibling of the reviewed timing publisher with the same draft/publish authority shape.

`draft(plan, read, hash_file, log)`:
1. For both core horizons: original metadata validation, the exact five R1 release artifacts, and the unchanged
   original core_fit authorize (original_guard).
2. Common release/recipe/staging/source audit across horizons.
3. `coverage.reconcile` over the legacy receipt 3aa8b404. The documented daily arithmetic must reproduce exactly.
   Each core event's staged `events_replay_leak/<id>/summary.json` is read through the staging receipt's exact
   file links (source_io Sources/EventSource; a7ed6ae8 binds 14,823 summary.json files individually).
   Bounds: explicit per-file bytes, closure bytes and population.
4. The receipt is encoded once (coverage.encode) and served from memory at its future publication path.
5. `h3.prepare` for ris7/mixed7 x 30/60 over it: panel-specific CompletedEventLibrary digests from the original
   from_eventsets bytecode, historical population equality, and coverage onset equality.

Logging: every staged source read is logged (resolved path + staged alias) before its bytes are opened. A Sources
subclass is injected at the h3 module seam (`h3.Sources`) and restored afterwards. No reviewed byte changes.

`publish(plan, expected, review, ...)` publishes only after these checks:
- the draft is recomputed and equals the reviewed draft;
- there is a separate exact publication review: scope, draft sha, root, inputs, release evidence and coverage
  receipt ref, approved_operations [supervised_graph_build], gate_publication_authorized; the reviewer is
  independent (`/root/opus_implementation` and `/root/deadline_audit` are refused); fit, prediction, label and retry
  are all false;
- the unchanged original `authorize(supervised_graph_build)` passes for all four groups before any byte is written.

It then writes 17 files exclusively, 0444, fsynced, gates last:
- the full coverage receipt;
- 4 per-group `h3_panel_coverage_extract` documents (the dev-construction `coverage` refs);
- 4 passed source audits;
- 4 sealed construction manifests;
- 4 passed gates.

No graph tensors, labels, predictions, scores or fits.

**Tests** (`.venv/bin/python -m pytest -q test_publish.py`, isolated subprocesses): 5 passed.
- Genuine pooled core world from the reviewed test_h3 fixture, both horizons, with a legacy receipt in the original
  format. The draft logs summary reads, and publish writes 17 files.
- For each of the 4 groups, the extract kind/horizon is checked, then original authorize, then a real original
  `build_graphs` whose history digest equals the published manifest. A second publish is refused.
- Refusals at their intended checks: legacy parity mismatch, missing summary admission, author as reviewer, changed
  draft.
- Fixture note: real sealed rows carry `actor` (captured d30/d60 construction manifests). The shared fixture omits it,
  so the test adds it at fixture creation, before any seal or gate is derived.

**Not here.**
- Supervised execution: a specialization of the reviewed timing/H1 metadata-execution runner (finite read inventory,
  access log, Budget/FileLimits, memory/wall). Next packet.
- Actual plan values: sealed core refs, collector binding, limits from captured sizes (data ~1.46 GB encoded,
  history ~86.7 MB, max source 59.83 MB).
- Independent execution, draft and publication reviews, and root resource admission.

**Actual local partial dry run** (`actual-local-v1/prepare.py`; local captures only, no host calls).
- Both real core horizons pass original validated_base and the original core_fit guard.
- coverage.reconcile ran over all 14,787 real core events and the real legacy receipt 3aa8b404, with **stub** summaries
  (core onset; explicitly not staged evidence).
- Parity holds on 473,678 rows, and exactly 116 adopted onsets changed (matches root reconciliation a9186cfd).
- The receipt is 115,198,115 B (cap 134,217,728), and the four extracts are 16.2-16.8 MB each.
- It ran in 31 s with 1.8 GB RSS.
- This run found the r2 refusal on real data (reference10 is in ip.H3_PANELS but is not an input panel). r3 fixes it.
- It also emitted the real kernel-plan.json and the N-h3 collector inventory (reviewed composer) for the host draft.
