# vrun fix: verifier job 52473761 failed in integrity() on 22 retro_finals_v1 cells

Diagnostic (approval a1fbb93e; k2-v1/vrun-failure-diagnostic.txt ae38706c):
- the code re-hash and every input anchor passed;
- then `verify_r1.integrity()` line 623 raised `KeyError: 'population_sha256'` on `cells[cell_id]`;
- DEST/out holds only plan.json from D0 and the job log; no verify-r1.json was written.

Cause, from local metadata only:
- 22 of the 1066 committed seal cells, in families chronos-adapted-test-v6b and tsfm-zeroshot-test-v6b (format
  retro_finals_v1, payload curve_npz), carry no `population_sha256`. The reviewed custody seals them with
  `population_events = R1_EVENTS = 3543`, because the evaluator requires full-cohort finals commitments
  (src/bgbench/forecast_retrospective_custody.py:815 and :854).
- Their population is the sealed R1 population, stored once as `seal['r1_event_ids_sha256']` = f5f212ba =
  run_verify `R1_POPULATION_SHA256`.
- The v9/v10 seals have the same 112 schema-variant cells. The reviewed verifier never ran on a report containing them.

Fix (`build_vrun_fix.py` from packet 955199fe; full delta in `vrun_fix.diff`):
- `run_verify.py` only: `r1_population_cells(seal)` asserts the seal's R1 population equals `R1_POPULATION_SHA256`
  and maps exactly the committed retro_finals_v1 cells with population_events 3543 and no population_sha256. Any other
  committed cell without one refuses.
- The kernel's B4 population check then runs on their rows, and wrong rows give a named failed finding. The mapped
  ids are written to the output.
- `verify_r1.py` and `test_verify.py` are byte-identical.
- New verifier-only DEST2 `r1-posteval-vrun-v11-r2-20261024`. The classd DEST stays as written for D1/D2.
- `stage_vrun.py` is stage_code.py with DEST2, the 3 verifier files, scope r1-posteval-vrun-code-transport-r2 and
  PACKET = this directory.
- `vrun_r2.py` is vrun.py with DEST2, the new run_verify/pins shas, scope r1-posteval-verifier-run-r2 and its own
  transport record. The job script, memory, partition and walltime are unchanged.

Tests: 12 pass (`test_vrun_fix.py`):
- the reviewed kernel reproduces the KeyError;
- the mapped check passes on correct rows and fails as a finding on wrong rows;
- other formats, partial cohorts and wrong or missing seal populations refuse;
- the actual seal maps exactly the 22 cells and leaves every other cell untouched;
- transport, vrun and job script bind DEST2 and the fixed code;
- the author is refused and the reviewer accepted.
