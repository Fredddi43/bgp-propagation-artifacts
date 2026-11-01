# REVIEW-VERDICT q36-prestage (independent final review, read-only)

VERDICT: CHANGES. Templates, runner pin and consumer schemas are mostly correct and the rehearsal is
sandboxed; the checklist has defects on real input shapes and one class of false-GO. Not fixed here.

## BLOCKER

B1. prestage_check.py crashes on the real spec shape. make_templates.py:243 emits `"kernel": None`; the
    checker does `(a.get("kernel") or {}).get("path")` (prestage_check.py:353) -> None in the `todo` set ->
    `sorted()` at :357 raises TypeError. Reproduced with a local fixture (config remote=local, 2 arms,
    kernel null): `TypeError: '<' not supported between 'NoneType' and 'str'`. After freeze, every
    `--gate g2/g3/...` run dies, so the live proof (evidence/live-gate-all, pre-freeze) never exercised it.
    With kernel set to a path the g2 phase runs.
B2. False-GO when the link degrades. `Remote._ssh` returns "" and only sets `R.degraded` (:104-109).
    Absence checks then read "absent" = GO: EV-05 (:440), R2-08 (:506), R2-09 (:509, `R.ls` -> []),
    R2-10 (:512, squeue -> []), G4-03 (:464). `gate_ok`/exit code ignore `R.degraded` (:575-578), so exit 0
    is possible with a WARNING line only. The ssh stall on <BATCH_HOST> is documented in this very lane.
    A one-shot guard (R2-08/R2-09) must fail closed: degraded => NOGO and exit 1.
B3. Gate rows accept weaker evidence than they name.
    - G2-03/G4-01 (:319-324, :445-451): any non-empty text without PENDING/SYNTHETIC/"{{" is GO. Reproduced:
      an 8-byte "approved" file gave `[GO] G2-03`. The consumers (g2_exec.py:76, r2_exec.py:46,
      g4_labels.py:26) also check only non-empty, so a half-edited or unedited-but-marker-stripped file
      authorizes a one-shot. The checker never compares the file to freeze sha/anchor.
    - T-04 (:542-545) says "accepted complete-result.json" but GO = file exists; no acceptance, no
      "approved result read scope" (FINAL-RESULTS-PLAN.md:76,80), no independent-review check.
    - G4-03 is `"GO" if F else "GO"` (:464): both branches GO, including "one-shot already consumed".

## RISK

R1. G3-01 can never be GO: `all(c["id"] == "G2-08" and ... for c in checks if c["phase"]=="g2")` (:403)
    requires every g2 row to be G2-08. Reproduced (all arms result-1.json present -> G3 stays PEND).
    G2-07 also emits no row when the 3 sampled parents exist but later parents are missing
    (:358-363, unsampled counted missing, no GO/NOGO row added).
R2. GO-file location. g2 specs carry the CLUSTER path `<G2_ROOT>/ROOT-GO-G2.txt` (make_templates.py:233) and
    g2_exec runs in the job (g2_exec.py:75-76). Template, action sheet row 9 and G2-03 only handle the local
    `g2r2/ROOT-GO-G2.txt`; no copy-to-cluster step and no remote probe of the file. Likewise
    r2-exec-spec.PENDING-ROOT.json pre-fills `go_file` with a <HOME> path that a compute node lacks
    (R2-04 would catch it late; the template should say cluster path).
R3. The rehearsal does not prove what runbook step 11 asked for (evaluate() on freeze+seal copy with a
    synthetic all-censored table). Tier A stops at `refused at single_evaluation` by construction; Tier B
    uses a stub runner. evidence rows are "REHEARSAL-PASS" though evaluate() never ran on pinned bytes.
    Also the row "real one-shot namespace untouched" is `(lambda: True)()` (r2_rehearsal_eval.py:194): a
    vacuous pass counted in the "8/8". REPORT states the limit honestly; the pass wording overstates it.
R4. Doc claims not true of code.
    - R2-REHEARSAL-PLAN.md: "`prestage_check.py --gate r2` (R2-06) refuses a spec whose job-name is not
      r2-rehearsal". R2-06 is the access-log size check; no job-name check exists.
    - prestage_check.py docstring :18 cites `run_test_prestage.sh`; it does not exist, so the script has
      no self-tests at all (I found none to run).
    - ROOT-GO-G2 template says origin 8 cpus / 900,000 MiB; g2templates.SUBMIT["origin"] is 32 / 900000
      (g2templates.py:247); the checker imports 32 and prints it, the authority text says 8 (q33 REPORT:82).
      Root would approve one shape and the submit would use another.
R5. Ordering: build_evidence.py:60 reads the G4 plan (controls "g4_plan"), but ROOT-ACTION-SHEET puts evidence
    (row 15) before G4 plan assemble (row 17); the template's g4_plan field is PENDING at row 15.
R6. EV-02 scans only top-level string values (:423), so `{{PENDING_ROOT}}` left inside `groups` or
    `h3_availability` passes (build then fails, no one-shot burned, but the row reads GO).
R7. Inventory probe hashes `--labels` bytes if the file exists (r2_inventory_probe.py:67). Plan says "future ok";
    state explicitly: never pass the real label artifact after G4, pass a nonexistent path.

## NIT
- pre_R2_implementation_binding sha is known now (a5de3e6a... on the repo file) but left PENDING in the
  controls template; ROOT-GO-G2 draft/arm counts 346 sum correct (20+80+40+20+12+6+56+48+24+40).
- FZ-03 for/else-style logic is convoluted; G2-02 `fsha[:12]` would crash if sha is None.
- ROOT-GO templates carry a PENDING_ROOT marker line; good, but consumer-side refusal would be safer.

## Checked and correct (evidence)
- Pinned runner sha cf90e07d... == sha256sum of newperiod-single-r2-persistence-20261024/runner.py; ROOT literal at
  runner.py:8; records.parent must exist and records must not (runner.py:297), so row 22b is a real finding.
- Output names (complete-result, primary-scores, done.json at runner.py:335), reviewer `go-file-`+sha[:16]
  (r2_exec.py:57-ish), 164 GiB / 64 GiB floors, evidence-controls keys vs build_r2_evidence.py docstring,
  GO_FILE default g2r2/ROOT-GO-R2.txt (common.py:19), array shapes for h1/h3/timing/history/stable vs SUBMIT.
- No template pre-sets PASS or invents a sha; the extension-decision sha is the only pre-filled value.
- Rehearsal: all writes inside a fresh --sandbox, refuses paths containing single-R2-v1, synthetic go-file,
  placeholder label never opened, job-name r2-rehearsal. Cannot open real labels in Tier A; Tier B real
  controls replace `labels` (inventory may still follow other refs, same as production).

## SERIALIZABLE-WAITS.md
Estimates plausible (400 GB seal at 0.3-0.5 GB/s ~ 15-25 min up to 2 h NFS contention). Missing from the
table though present in the action sheet or FINAL-RESULTS-PLAN: G2 execution wall (origin 6.6/15.6 h, the
dominant wait), evidence build + root signing of full-retention-review (10-30 + 15-30 min), G4 plan
assemble + labels, R2 execution wall itself, "approved result read scope" and independent review of
facts/tables before integration (FINAL-RESULTS-PLAN.md:76-81,99).

## Could not verify
No cluster access used (live rows, <CLUSTER_STORAGE> paths, 03/04 equivalence, squeue count); did not re-run the
rehearsal modes or run_offline_evidence.sh; g2_submit path with real specs; whether q13 dryrun specs carry
`kernel`. Real-scale walk/seal timings are author estimates.
