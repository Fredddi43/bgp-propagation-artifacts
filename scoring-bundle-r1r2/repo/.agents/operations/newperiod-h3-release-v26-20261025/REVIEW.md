# H3 release packet #1: v26 storage rows, waves_v2 (assemble-only post-64), initial-wave binding builder

Author: claude-opus-5-5, session <SESSION_ID> (h3_author). Required reviewer: review2 7f4c18c0. Local only; nothing executed.
Root direction ROOT-H3-DIRECTION (05:06:57Z): builds+assemble via waves.py, H3 audit-only bound_base successor,
H3 rows for a v26 joint phase. H3 stays held until v26 is reviewed and issued (v25 C2).

## Why
- F1: H3's frozen audits fail deterministically, like H1 r3. The audit-templates bind base_manifest
  sealed-core-v1 74ff724e (d30) and 1dad255b (d60). D2 (55ef) proved 74ff724e's 14,787 base graph refs are leaf
  links. h3_audit.read():17 and source_io.raw():14 require path.resolve()==path, and audit_event reads base_row
  graph_path through them.
- The frozen waves.py has a single post-64 phase, 'audit-chain', which releases assemble + audit + finalize together.
  It can therefore never be used.
- F2 (the H1 v4 controller rejecting afterok:X_*) does NOT affect H3: waves.held() accepts those forms. The test
  runs all 16 ACTUAL read-held captures through held() and every one passes.

## Files
- `v26-h3-rows-proposal.json`: three new rows.
  * h3_live_build_wave 128 GiB: a hard cap, 16 x writer 8 GiB enforced by job.py:74-76/104, with control in the
    existing 4 GiB row.
  * h3_assembly 1 GiB.
  * h3_audit_v4_chain 35 GiB per live group.
  * Planning upper proxy: H1 d30 actuals (same builder/job/base).
  * Feasibility: NOT feasible while the h1_d60_v5_build row is live. Feasible after it retires, which R1 requires anyway.
  * Proposed conditions H3-C1..C5.
- `build_waves_v2.py` -> `waves_v2.py` bdaf8e14: five closed edits to waves.py 5301e876 (diff in the test).
  * Post-64 phase 'assemble' only, with reservation = control + assembly_bytes.
  * audit/finalize are still held()- and script-checked, but never released.
  * 'audit-chain' no longer exists.
- `test_waves_v2.py`: the reviewed H3 waves tests ported, plus v2 tests, the actual captures, and a fulfilled-(null)
  dependency test.
- `build_binding.py`: wave-0 binding over the actual submission 351c6afb.
  * Parametric in first_group and root's v26 minimum_free_bytes.
  * Emits the admission (controller encoding), outcome requests for 4 groups x 4 waves, and release-approval and
    wave-0 authority templates.
- `test_binding.py`: the filled templates pass controller.authority(release=True) and waves_v2.authority().
  * End to end: waves_v2.release() wave 0 against the ACTUAL held captures releases exactly <build>_0..15 for each
    group, and nothing else.
  * A space shortfall releases nothing.
- `test-run.txt`: 34 passed. `mutation-proof.txt`: 3/3 caught.

## Not in this packet (next)
- The H3 audit-only v4 package (`newperiod-h3-audit-only-v4-20261025/build_audit_v4.py`, drafted; it freezes after the
  four assemblies) and its per-group dispatcher, waiter and capture.
- The root v26 issuance, the wave authorities and the actual binding values.
