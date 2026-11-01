# H3 R3/R4 preparation: wave waiter + stage/held proposal (author Opus 4ba6111c; reviewer f4d75bb1)

Follows f4d75bb1's CODE/SOURCE PASS b05532ba of the H3 package (plan e32b00eb), conditions R1-R4. This is code and
metadata only: no host calls, no stage, no submission, no release, no approval signed.

## `wave-waiter-v1/wait.py` (R4): port of the reviewed H1 wave-waiter-v2 (wait.py 2768195a, approval 3f84585b)
- The build array id is no longer a constant. `build_job()` takes it from the exact sha-bound held submission
  record, and requires all of:
  * kind `newperiod_development_held_submission_v1`;
  * plan equal to the H3 plan ref e32b00eb at the H3 controls root;
  * exactly the four groups x four phases in controller order;
  * 16 distinct numeric ids;
  * request.job_id equal to the named group's build job.
  `remote_command`, `terminal_state` and the wake text all use that id.
- `terminal_state(text, wave, job)`: the per-row rules are unchanged. A test proves the result is identical to the
  reviewed H1 v2 function for its own job on 5 scheduler texts. Waves 0-3 are allowed; H1 v2 allowed 1-3 because wave
  0 had its own waiter.
- Unchanged: the coordinator identity check (codex pane/cwd/session), one durable intent before the single prompt,
  the deadline, and the 24 h expiry.
- One live H3 wave at a time and the group order stay a root-authority policy (R1). The waiter watches exactly one
  group/wave.
- Tests: 10 passed (`wave-waiter-v1/test_wait.py`).

## `build_stage_proposal.py` -> `stage-proposal-v1/request.json` (R3 preparation)
- Mirrors H1 r2 stage-proposal-v1:
  * exact local package actual-v1/package, plan e32b00eb and controller 027b7a68 (every file re-hashed);
  * f4d75bb1's review b05532ba as the review.txt to stage;
  * 3,521,594 B total against the controller's 32 MiB stage cap;
  * the controller CLI invocations for stage / submit-held / read-held, with every required argument.
- `approval_template` holds exactly the fields `controller.authority()` checks, with placeholder reviewer identity.
  Tests: the template passes authority() only once a root identity is filled in; the unsigned template is refused;
  changing submit/release flags, scope or admitted groups is refused. Every jobs/*.sh in the plan equals the
  controller's `job_script()` (approval-independent).
- R3 is preserved, because the controller itself fails closed if the controls root or any group claim already
  exists (STAGE_REMOTE root.mkdir, CLAIM_REMOTE claims/<key> mkdir). The held-readback review must still confirm the
  fresh root and the claims.
- Tests: 3 passed (`test_stage_proposal.py`).

## Not included (later steps, each needs its own review / authority)
- The root-signed stage/submit approval.
- The held-readback review.
- The initial binding and admission (from the actual held submission, `newperiod_h3_initial_wave_admission_v1`,
  phase reservation 132 GiB).
- The root joint storage phase (R2).
- The wave-0 root authority.
- The waiter request (pane/session/deadline, from the actual submission).
