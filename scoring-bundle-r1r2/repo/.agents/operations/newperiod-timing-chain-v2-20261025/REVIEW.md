# Timing chained runner + generic dev audit-chain capture

Author 4ba6111c (timing author per ROOT-ASSIGNMENTS-V2). Reviewer review2 7f4c18c0. Local only; nothing executed.

- `chain_timing.py`: generated from chain_h3.py by asserted edits, so the gates G1-G3 and assessments A1-A4 are the
  same.
  * Transport: timing waves.py 78e81655 (f4d PASS), including its post-64 'audit-chain' release (assemble + audit +
    finalize). Timing audits read only their own assembled graphs (review2 05:24 static check).
  * Growth G-T: no H1 proxy exists for timing, so each group's wave 0 is a measurement wave. For k >= 1, the mean
    per-shard apparent AND allocated bytes must stay <= 1.50 x wave 0's, else stop. The 6 GiB / 8 GiB / 512 MiB stops
    are unchanged.
  * A group's audit chain overlaps the next group's build waves; its row must be in the joint sum. At the end every
    chain is awaited (assemble, audit[0-31], finalize) and captured once with the generic capture; final.json has a
    per-group PASS/NOT PASSED. No retry.
  * The submission is bound through the authority (submit-held has not run yet). Scan dirs come from the authority.
- `build_binding_timing.py`: port of the H3 build_binding.py, parametric in first_group, the root minimum and the
  actual submission (path + sha).
- `../newperiod-dev-chain-tools-20261025/chain_capture.py`: the H1 r3 chain_capture read discipline, generic over a
  FIXED family table (timing budget-r2; H3 audit-only v4). The summary is projected by type: bools, ints, floats, the
  kind, 64-hex strings, refs reduced to their sha, and lists reduced to their length. No free text, rows or event ids;
  the tests plant event ids to check this. 8 tests.
- Tests: test_chain_timing.py (simulator; the binding builder feeds the chain); see test-run.txt for the count (v2: 16 passed). Mutations in mutation-proof.txt (M1-M13).
- Timing stage + submit-held + read-held already ran once and were ACCEPTED by review2 (05:45:08Z; submission 2608e3bc).
  Not executable until a joint phase with timing rows (timing_live_build_wave 128 GiB + timing_audit_chain 34 GiB, v27
  proposal) is issued and a root chain authority is signed from chain-authority.TEMPLATE.json.

## T2 (review2) / H3 chain F1-F2 lessons built in
- execute() catches BaseException and writes STOPPED.json {reason, exception_type, step}; transient read-only poll
  failures while waiting are recorded (<step>-wait/transient.jsonl) and polling continues to the deadline.
- Refusal tests for every mechanical stop: earlier shard changed, shard > 6 GiB, file > 512 MiB, census symlinks,
  results df, authority chain sha, growth vs wave 0, failed task, failed audit chain, STOP post, low models df.
  Timeout probes too. 15 tests; mutations M1-M12 caught.
- Template now binds the ACTUAL timing submission 2608e3bc (stage/held accepted by review2 05:45:08Z) and its 16 job
  ids; notify.session is the <AGENT_TOOL>-reported <SESSION_ID>; minimum and joint admission come from the v27 phase (root fills).

## v2 (new immutable dir; v1 = newperiod-timing-chain-20261025 aed5fb06)
- T-R1: before releasing a group's audit chain, every previously released timing audit chain is awaited to terminal and captured (finish_chain), so at most ONE timing audit chain is live (v27 P2, timing_audit_chain 34 GiB). Build waves still overlap the live chain. Ordering test + mutation M13.
- T-R2: the REVIEW statements on test count and stage/held status are corrected (above).
