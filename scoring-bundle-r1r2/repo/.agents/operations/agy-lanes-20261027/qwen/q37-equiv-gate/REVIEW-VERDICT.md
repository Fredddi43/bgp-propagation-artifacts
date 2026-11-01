# q37-equiv-gate independent quick review

Verdict: CHANGES (1 BLOCKER, 4 RISK, 3 NIT). Read-only review; gate fixtures run in a scratch dir, no cluster access, no protected data read.

## (1) gate_check.py: fixtures run locally
Fixture runs, each ending with `gate_check.py --eq X --controls c1 c2 --quiet` and its exit code:
- all-equal, matching sha, v2 kind: rc 0 (correct)
- audit.equal=false, audit.equal="yes" (string): rc 1; master/export equal but audit not: refused (E2 needs `is True`)
- RESULTS.json absent: rc 1 EQUIV-GATE-MISSING; unparsable JSON: rc 3
- recorded sha missing: rc 2; controls pp bytes drifted from plan pin or between the two controls: rc 1
- RESULTS.json is a JSON list: uncaught AttributeError traceback, exit 1 (non-zero, so safe, but not the designed path). NIT gate_check.py:211-224 (catch AttributeError/TypeError too).
No path found to exit 0 with missing/stale/partial results or a different parallel_phases sha, for the explicit-controls case.
- RISK gate_check.py:80-82: controls dirs without plan.json/parallel_phases.py are silently dropped. With the default two-variant list, one variant's controls missing means the gate passes on the other. Capture passes one explicit dir so is unaffected; the standalone CLI and fill_export_fields (live re-check, `--groups` only) can be. Fix: require both variants when `--controls` is not given.
- RISK gate_check.py:36 plus 112-122: `coverage` is recorded but never checked. The OPEN-1 fork-pool hang means a run that used workers=1 (inline pool) would still pass. Fix: require coverage to show the fork pool was exercised, and non-trivial status/tie coverage.
- RISK gate_check.py:77-79: ORIGIN_EQ and ORIGIN_B (env) redirect the result dir. Anyone able to set env plus write a RESULTS.json can pass the gate. Same class as (2).

## (2) Patched capture/promotion
- capture_origin.py.diff: the gate call (L54-67 of the patch) sits right after variant selection and before the plan read, `done()` reads and `write_new`, so no side effect precedes it for a given group. Only ImportError and GateFail are caught, and any other exception propagates (non-zero), so none is swallowed.
- RISK capture_origin.py:55 `ORIGIN_GATE_DIR` env override: it loads and executes an arbitrary `gate_check.py` from the named dir. That is a bypass path (a stub `evaluate` returning a fake receipt). Remove the env override and use `CH/'controls'` only.
- NIT: multi-group argv runs the gate per group inside the loop, so group 1 can write before group 2 is refused. Evaluate all groups up front.
- RISK family_expectations.py.diff (check/draft): it only verifies a local receipt file and the sha string in the fragment. Nothing re-runs the gate or hashes the receipt against the capture dir. A hand-written receipt passes promotion drafting. Bind the receipt sha256 and re-run the gate.
- fill_export_fields.py.diff: the live re-check is `gate_check.py --groups g --quiet` rc!=0 refusal, which is good (rc 0 only). The `... .stdout or sys.exit(...)` idiom works but is fragile.

## (3) real_data_compare
- BLOCKER real_data_compare.sh:95,99,130: `$RK_TOOLS` is never defined and `set -eu` is on. The remote `prep`, `iso` and `verify` modes abort with "unbound variable", so the documented cluster flow (prep, iso, verify) does not run without LOCAL=1. Define `RK_TOOLS="${Q37_RK_TOOLS:?}"` and pass the directory (the tools dir as seen on <BATCH_HOST>). `compare` uses `$S/tools` and is OK.
- Isolation is sound by construction (run_step_origin_scratch_*.py patches): state root and `CUSTODIAN_ACCESS_LOG` are redirected to `$S`, the wrapper refuses state inside the real chain root, refuses a log equal to the real log, and plan.json stays byte-identical. The real access log is only opened for reading by phase_compare.py:~285. Jobs run under `env -i` with an explicit env (job script `$ENVI`). `isolation_check.py` snapshot/verify hashes the real access log in full. Running it cannot write real state as far as the code shows. NIT: the `iso` snapshot is a manual step; `submit` does not stage it, so the compare job fails if it was skipped. Remind the driver or make `submit` refuse without the snapshot.
- Byte-compare covers master, export, audit trees via `phase_compare.py` (only top-level generated_utc plus provable hash-cascade normalized, tamper tests in test_local.py). The primary comparison is par vs seq inside scratch, and both run the scratch wrappers. So the primary compare does not exercise the deployed driver bytes or deployed parallel_phases (6fddec14, which REPORT says is broken for audit); it exercises the fixed copy and hotfix wiring. The deployed-vs-single-pass compare is "NOT-AVAILABLE" until real trees exist. State this plainly in the gate docs.
- RISK phase_compare.py:~256-258: access-log comparison is ordered list equality on `(path, files, purpose, actor, user)` filtered by the `script` field. Parallel workers may append in a different order or different counts, which gives a false FAIL (tolerable, fails closed). Time/host/pid fields are excluded, so raw append lines are not byte-compared. This is documented in REPORT §6 and the brief asked for append lines; use a sorted multiset compare.
- sbatch lines: `--export=NIL`, 64 CPU, 1000000M, 1 day, `--no-requeue`, afterok chain are correct and unquoted words are safe (no spaces). NIT: time 1-00:00:00 is not clearly the partition max, and RESOURCE-POLICY asks for wall at the maximum.

## (4) Doc claims vs code
- REPORT §1 "gate exits 2 when no recorded sha" matches the code (gate_check.py:119-132).
- REPORT §6 says "ISOLATION ... cannot write the real group dir". True for the wrappers, but it needs `iso` run first (see NIT).
- Gate docstring E4 says the pins prove the phase "ran with exactly those bytes". True only for the deployed driver, which source()-pins at load; the scratch driver is not that. OK as written, but the report should not read as evidence about deployed bytes before the plan re-issue.
- Everything else checked matches the code.
