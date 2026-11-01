# v8 preparation staging/control candidate (LOCAL; nothing staged, provisioned, approved or run)

- Author: claude-opus-5-5, session <SESSION_ID>.
- **What it is:** the reviewed v7 preparation tools, re-pinned to the O1-bound v8 assembly:
  - `v8-1-assembly-candidate`, CODEPASS;
  - driver 33011eed, source candidate fded6806, manifest 6a9a325f, resource candidate 32bbd21d.
- **Single pass:** preparation stays the reviewed `prepare_r1_metadata.py` c42e78ac, one `verify_batch`, as in v7.
  There is no separate freeze/seal/plan pass.
- **Nothing is executed remotely by anything here.**
  - Staging the fresh v8 root, building the package and launching each need their own exact phase approval.
  - Scientific preparation, retry or relaunch is not authorized.

## How it is built (`build_prep.py` → `tools/`, `diff-*.diff`, `planned.json`)

- Every input is a sha-bound v7 file: stage 503ee102, readback b98255ff, bind_controls e8f4ff82, build_execution
  78037ece, execute bfe1d495, launch 6ea224eb, supervise d955fbc2, run.sh 7aa47cc3.
- Every change is an exact `(old → new, count)` edit in `EDITS`, tagged with one of four kinds.
- `test_prep.py` proves the tools regenerate byte-identically and that every changed diff line comes from a declared
  edit.

| Kind | What changes |
|---|---|
| root | `r1-release-assembly-v7-20261022` → `-v8-` in every tool. The only v7 path left is the predecessor's `evaluation-control-v1`. |
| bind | O1 driver; v8 source/resource candidates and manifest; kind `r1_reviewed_source_overlay_v8_1`; scopes `r1-source-only-staging-v8` and `r1-single-pass-metadata-execution-v8`; `build_execution` OPS path (tools/ sits two levels down) |
| pred | review A3 (replace, not add): `execute.py` `failed_v6` → **`failed_v7`**; `launch.py` STATIC uses `failed-v7-evidence.json`; `build_execution` binds `a3-result/failed-v7-evidence.json` **e425007e** and sets `predecessor_spec_sha256` to the v7 evaluation spec 95ee898d |
| calib | the calibration approval binds the driver, so `bind_controls` takes the reviewer's **re-issue** as an argument (`calibration_bound`). It requires driver 33011eed, decision d359941f, scoring 740bf610, `test_outcomes_used` false and an independent reviewer, then fills only the draft's pending approval sha. This replaces v7's fixed v3 calibration file. |

**`failed_v7` (host-side, in the v8 preparation `execute.py`) checks, in order:**
1. The evidence kind and root; success, results, labels and retry are all false; the spec equals
   `predecessor_spec_sha256`.
2. The path is not a symlink and does not escape.
3. The staged package equals the evidence, file by file, and `stage-complete.json` equals it too.
4. The six control records match byte for byte; `launch.err` matches by size and sha256.
5. The exit equals the evidence: non-zero, retry false.
6. There is no `results/` and no `complete.json`.
7. The gate record's presence is unchanged (absent for v7).
8. `closed()` refuses any `r1-unblinding*`, before and after.

**Approval keys** (reviewer decides; changed by the `pred` edits):
- `calibration_binding_recovery_authorized` → `o1_driver_adopted`;
- `failed_v6_supersession_authorized` / `failed_v6_accepted_as_pass` → the `failed_v7_*` pair.

Every other key and the FORBIDDEN list are unchanged.

**Unchanged and inherited:**
- resources 1536 GiB AS / 4 CPUs / 12 h (the measured v7 preparation took about 3.9 h);
- the audit hook (output plus the one canonical seal);
- the custody CODEPASS check (409e1171);
- launch/stage transport checks and caps (≤ 32 MiB package, ≤ 16 MiB per file);
- `failed_v6_evidence()` and the V6 constants stay in `build_execution` as unreferenced reviewed lineage.

## Planned placement (`planned.json`)

**Source root** `.../r1-release-assembly-v8-20261022`:
- 375 candidate-listed files (373 source + manifest + base draft), 5,071,463 bytes, plus `candidate.json` itself;
- within the stage caps (≤ 400 files, ≤ 16 MiB, ≥ 64 MiB free);
- `stage.py` REMOTE creates the root once and refuses if it exists;
- files are written `xb` with mode 0444 and fsynced;
- readback with `readback_program.py`: per-file sha, symlinks, modes, owners, top listing.

**Control root** `.../control-v1`:
- 12 static + 5 dynamic files.

**Unresolved reviewer records** (arguments at bind/build time; nothing is faked):
- the resource review (binds contract d5798bee, runtime, label);
- the calibration re-issue;
- the retention review (the final draft plus `check_transition_v8`);
- the preparation review (prepare c42e78ac, driver 33011eed, A3 e425007e);
- the execution approval and review.

## Verification

- `test_prep.py`: **34 passed**. It covers:
  - regeneration, diff purity, and root/bindings;
  - `failed_v7` accepting a synthetic root built from the **real** v7 package-v1 bytes and the **actual** captured six
    records (launch.err synthetic, identity form);
  - 8 later-change refusals and 6 evidence-field refusals;
  - approval shape (6 cases);
  - `build_execution` binding the real A3 evidence and custody CODEPASS;
  - calibration re-issue: fills only the sha, plus 6 refusals and a double-bind refusal;
  - stage caps.
- `mutation_controls.py` → `evidence/mutation-controls.json`: the unmutated control passes. **7/7 mutants are
  detected:**
  - results/complete not checked;
  - staged package not checked;
  - launch.err sha not compared;
  - evidence flags not checked;
  - O1 adoption not required;
  - calibration driver not bound;
  - rebinding an already-bound draft.
- ruff: clean. The inherited `readback_program.py` I001 is v7's.

## Order (review-r2 routing)

1. v7 terminal, then K1 — done.
2. A3 capture and identity read — done.
3. Newperiod host attempt3 — in progress.
4. v8 phase approvals: stage the source, bind the controls (reviewer records), build the package, preparation approval,
   launch.
