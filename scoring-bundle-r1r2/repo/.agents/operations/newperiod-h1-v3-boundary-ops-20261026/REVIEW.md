# H1 protected v3: generic boundary release + capture onces (ordinals 0, 1, 2)

Successor transport for the v3 namespace (stage/held once ran rc0 01:41Z, jobs 52539237.. in submission).
Same reviewed shapes as the v2-era operators (ordinal1 v2 release was consumed+accepted; ordinal2/wave-capture PASSed),
generalized by ordinal so one review covers manifest (0), build wave0 (1), build wave1 (2).

- common3.py: pins (v3 stage_once, v3 preflight, v3 package partial_dispatch/boundary_binding/controller, reviewed held_check,
  allocation_policy loaded with __file__ so its pinned resume_support path resolves), v3 stage records reader,
  SCHEDULE = partial_dispatch.schedule()[0:3], rows_for(): manifest = envelope_rows('manifest', padding 14GiB) (as the v2
  first manifest), builds = the 82GiB rows.
- bind_request3.py: derives history (accepted capture entries, real partial.checked_history), boundary request
  (envelope rows checked by the real partial_dispatch), operation request into a fresh sibling dir (ordinalN-<phase>/).
- operate3.py: once per ordinal. Preflight (newest phase floors, staged sources, custody headroom >=512MiB) -> exact
  controller held_job check of every unsplit, not-completed job (d30 build dependency on the completed manifest
  normalized as in the accepted manifest capture) + squeue -r layout (completed predecessors absent, everything else
  JobHeldUser) -> remote binder writes records/boundaries/NN (00 creates boundaries/) after running the STAGED
  boundary_binding.check for every target index -> recheck -> scontrol release of exactly the targets -> readback.
- capture3.py + capture_remote3.py: once per ordinal after the targets are terminal: sacct (all targets COMPLETED 0:0 r0),
  held layout (everything not yet released still held), remote finite capture (two stat passes >=310s apart, only
  intent/worker-intent/done JSON read, manifest construction.json digest-only vs done.result), reconcile (floors, custody
  identity, physical model 2L+1MiB*N within the boundary rows, real retained_prefix + assess_history A2/A3 over all own
  waves, wave0 stats unchanged at wave1), actual + history-entry pending independent acceptance.

test_e2e3.py (test-e2e3.out): full simulated chain 0 -> capture0 -> 1 -> capture1 -> 2 -> capture2 with real
current_phase, partial_dispatch, boundary_binding, controller.held_job (fed real v2 readback lines re-identified), remote
binder and capture_remote3 code on temp trees; synthetic authorities only in a throwaway copy.

Real now: ordinal0-v39/ (manifest 52539237 request on issued v39). Read-only live check: exact held_job passes for all 12
v3 jobs and squeue -r shows all 74 rows JobHeldUser.

Reviewer outputs per ordinal: physical-profile (phase, rows_for(n), joint_phase = request phase, fixed_writer_transfer_accepted),
independent-review (scope h1-protected-partial-boundary-v1, operation_scope h1-v3-boundary-release-once-v1, request_sha256,
physical_profile_sha256, operation_request, operator_sha256, joint_phase), capture review (scope h1-v3-capture-v1) and
capture acceptance (scope h1-v3-capture-actual-v1, actual, ordinal, a2_a3_accepted for builds). ROOT once kinds:
h1_protected_boundary_once_v1 (records from the operation request) and h1_v3_capture_once_v1.
Note: before the first manifest the v2 chain also had a separate >=300s allocation-stability once; here the manifest capture
does the >=300s stat pair after the manifest. Reviewer decides if a pre-manifest stability once is still required.
If v40 is issued before a release once runs, re-derive that ordinal's request into a fresh sibling (one command).
