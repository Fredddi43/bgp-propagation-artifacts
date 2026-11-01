# L6 receipt capture for the completed history-r3 job 52474707 (COMPLETED 0:0, 51m05s)

The paths are the exact emitter paths; there is no listing.
- `records/history-0000/intent.json`, from run.py.
- `records/history-0000/done.json`, from run.py on success: the parsed ORIGIN_REPLAY_COMPLETE line.
- `records/history-0000/output/staging-receipt.json`, from history_stage.stage into run.py's `records/'output'`.
  done.json `result.staging` names its path and sha.

Two steps, both with the reviewed f19 capture tool (f19d1066). It reads the listed .json files only, caps each at
16 MiB and 256 MiB in total, asserts shas and claims its output exclusively. Neither step makes a host write.

1. step1: request-step1.json, the two records (sha unknown).
2. step2: `receipt_capture.py step2 --capture-1 <c1>` checks:
   - intent and completion bind plan bd697b0d, index 0 and passed;
   - phase history and no retry;
   - the completion names exactly the emitter receipt path.

   It then requests that receipt at the named sha. If the receipt is over 16 MiB, f19 refuses and the step stays a
   failure.

`check` then binds the receipt bytes to the named sha and its passed / training_authorized false /
forecast_outcomes_computed false flags. The routed result is the L6 audit input.

No membership, parquet, source payload or labels are read. 7 tests pass.
