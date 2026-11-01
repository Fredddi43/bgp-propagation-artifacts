# Independent review of q41 E5 port (read-only; tests re-run locally)

VERDICT: CHANGES (no BLOCKER in the port's mechanics; two blockers are the author's F1/F2 unproduced inputs, confirmed; three RISKs below)

## (1) Re-diff vs pinned check_e5.py (sha acb3bbef... confirmed; port sha ded150dd... confirmed)
Hunks of `diff -u pinned port` (port line numbers):
- :6 import adds `os` - PATH (needed by env layout hook).
- :11-12 FREEZE/DONE constants -> `FREEZE=DONE=None` - PATH. Unset layout cannot pass: path equality at pinned :40 fails.
- :30-50 new `layout()` + env hook - PATH. Not vacuous.
- :76-90 (pinned :51-55) done.json block REWRITTEN - NOT purely path. Classified below.
- :118 adds `layout` key, :123 adds `completion_record`/`publication_files` to output - additive output only.
All other lines (controls, 40+10 grid, All56, complete400, reviewer model, E1-E4 ordering, require_e5, assemble_after_e5, ten-name set, namespace line 58, constants/regexes) byte-identical. No constant/regex relaxed.

Semantic changes in the rewritten block (pinned :51-55) - these are the real weakenings:
- RISK (check_e5_v2_compat.py ~:75-82) `done.passed`, `done.result.passed`, `result.passed` are now tautologies (`kind=='g1_freeze_anchor'` compared to itself). Assertion kept in form, empty in content.
- RISK `automatic_retry_authorized/gate_issued/predictions_computed is False` now read from the acceptance packet (reviewer attestation), not from the finalizer's own record. `predictions_executed` is derived `not freeze.all_retained_outputs_absent_at_freeze` - a missing key yields True -> fails closed (good).
- RISK `done.plan == finalize_plan` and `done.approval == finalize_approval` replaced by `review.draft_sha256==finalize_plan.sha256` and `finalize_approval==disposition_review`: finalize_approval is now forced equal to disposition_review, so the "approval" check no longer says anything independent. `operation=='finalize'` has no counterpart. Author disclosed all of this (REPORT F2-F4); I agree with the disclosure and the classification. Cheap fix in g1/freeze_run.py:119: write kernel result's `automatic_retry_authorized:false, predictions_executed:false` into the anchor, and read them from it.

## (2) Path mapping vs new procedure
Confirmed against freeze_run.py:112-123 and retention.py:159-177: anchor = {kind, freeze, files, anchored_utc}; publish() returns files for every non-primary group + freeze.json, written into one fresh root. Mapping table in REPORT s2 matches. Confirmed NOT produced: done.json (no runner), g1_actual_acceptance (BLOCKER, only a reviewer can author; make_e5_acceptance.py PENDING packet is the right mechanism; the port correctly refuses rather than skips), finalize_plan (analogue = draft.json, bound by sha via signed review), finalize_approval (merged). Author flagged all of these. Anchor does not record retry/gate flags (see fix above).

## (3) Tests
Ran: `cd /tmp; PYTHONPATH=src .venv/bin/python -B -I -m unittest discover -p 'test_e5*.py' -s q41-e5-port` -> Ran 30, OK (11 s).
Read test_e5_v2_compat.py:122-188: wrong freeze sha asserts "Exact bounded input bytes"; missing review has 3 subcases incl. the caller subprocess refusing; 399 roles asserts "Complete400 required" after resealing the namespace (so the reason is isolated, not an earlier mismatch); primary failure asserts "All56 primary executable" with reseal; extra file asserts "All ten original publications". Each uses assertRaisesRegex on the specific message: right reason. NIT: acceptance packet in the positive fixture is synthetic (disclosed), and positive world is the rehearsal with synthetic origin/timing arms.

## (4) fill_e5_admission.py
OK: receipt kind/layout/exact six bindings (:70-88); receipt freeze path == --freeze-ref and sha == bytes read now (:99-113); missing group docs -> fail (:117-120); learned hash recomputed with pinned selector (:136-146); contract_evidence keys exactly E1..E5, E1-E4 passed, E5 pending/passed, re-verified after flip (:171-179, :236-245); flip only when `fails` empty.
- RISK :237-248 With no `--e5-review`, draft becomes passed=true, all_five_admitted=true, E5="passed" (verdict string only says PENDING_ROOT_SIGNATURE). Pinned require_e5 demands an independent E5 binding review before E5 counts. "Cannot flip E5 without a passing receipt" holds; "cannot flip without independent review" does not. Fix: leave E5 pending and passed=false unless --e5-review validates.
- RISK :117-120 group docs checked for existence only; their bytes are not compared with anchor files shas inside fill (runner does this in harness_extras, but fill ignores receipt.harness_extras, and `--no-group-doc-check` in e5_check_run.py lets a receipt skip it). Fix: fill should require harness_extras.anchor_publication_bytes_all_match and recompute vs anchor.
- RISK `--no-recheck` flag (:67): permits E5 flip with only receipt-hash checks. Remove or make it force passed=false.
- NIT :142 broad `except Exception` converts to a fail (fail-closed, acceptable).

## (5) Vacuity
No empty-loop passes found: learned must be exactly 50 with 40 updated; ten-name set exact; per-arm loop runs over a non-empty enforced list. Layout hook fails closed when unset. Exceptions in check_bytes propagate; caller prints failure and exits 1. Only tautology is the anchor-kind items in (1).

Not verified: real cluster freeze (none exists), make_e5_acceptance.py internals, RUN-ON-REAL-FREEZE.md commands.
