# Stable v6 stage32 launch against V44 (author: sonnet, claude-sonnet-5-5; not authority)

## Re-pin: NOT needed
The signed request (ce391b74) and its plan bind V43 (`storage_phase`). `operate_stage32.Operator.current_phase` calls
`phase_compat.accept(authority.joint_resource_admission, ...)` (phase_compat v2, b84be518) and lifts the floors to the newest
issued phase: `models_minimum = request.minimum_free + newest.models - V43.models`. Run against the real files: V44 (e5fab44a)
supersedes V43 directly, `stable_source*` own-lane rows are identical, results floor is unchanged, so V44 is accepted.
The authority therefore keeps `joint_resource_admission = V43`; the constructor demands `request.storage_phase == that`.
Nothing frozen is changed, no successor request exists. Residual: stage.sh's in-job `free >= minimum_free` is V43-based (weaker
than the operator gate); the operator gate runs V44 floors + 20GiB before stage, submit and release.

## What the generic operator does NOT enforce (added in fill.py)
V44 rows `retained_failed_stable_v5b_stage >= root-supplied accepted bound` (current row 468713472), `retained_failed_stable_v4_stage
>= 16MiB`, `stable_source_stage >= 20GiB`. Enforced at fill-adoption and at --check from the newest accepted phase doc. Bound kind is
recorded as `accepted_actual_allocation` or `conservative_upper_bound_from_logical_sizes` (root1029); never relabelled as measured.

## Files
`fill.py` (probe / fill-adoption / fill-once / check), `pins.json` (operator 30ab0c54, request ce391b74, draft v8-final adoption,
once template, phase_compat, V43, V44), `facts.FALSE-TEMPLATE.json`, `test_fill.py`, `tests.txt`, `verification.json`.
fill.py only: reads pinned files, runs the operator's own `ssh_argv` (pinned known_hosts) for one stat/df/rlimit query on
<BATCH_HOST> (the log is lstat-ed, never opened), `squeue -u <USER>` and one `getrlimit(FSIZE)` python call on <SUBMIT_HOST>
(the one exchange beyond the v28 pattern; failure is a reported warning), and writes NEW files with `xb` outside this directory.
The adoption is the pinned DRAFT-v8-final with exactly the 11 flags flipped plus an added `root_fill` record (facts ref, V44 ref,
observation, preflight); `Operator.load_adoption` (real code) is run on the bytes before they are written.
--check runs the real `Operator(authority, consume=False)` then V44 retention, newest phase == pinned V44, and the gate
arithmetic on a fresh observation (floors incl. +20GiB, same dev/inode/no shrink, EOF+256MiB < 2GiB-64MiB, growth + 84529704 <= 160MiB,
inherited hard FSIZE >= EOF+256MiB). It never calls gate() (needs records dir) and never consumes.

## sol-h3t must check
1. pins.json hashes match the bound inputs (operator 30ab0c54..., request ce391b74..., V44 e5fab44a..., draft adoption fb56f414...).
2. The no-re-pin reasoning above, by running `phase_compat.accept` yourself, and that no V45 exists (fill refuses when newest != pinned V44).
3. `retention()` and `preflight()` match `Operator.gate` arithmetic and the root1029 clarification; flag/scheduler handling in `fill_adoption`.
4. Independence: the facts, writer inventory, operation review and snapshot are root/reviewer-supplied; the helper invents none.
5. Tests: 22 pass, synthetic only, incl. an end-to-end real-constructor `consume=False` pass.
Review of the actual root adoption (current all-host writer reconciliation) is still required before fill-once.

## Root commands (all with `cd /tmp`; H=<REPO>/.agents/operations/newperiod-stable-v6-v44-launch-sonnet-v1-20261026; R=<fresh root dir outside H>)
1. `python3 -I -B $H/fill.py --probe > $R/probe.json`   (check is_pinned_v44 true; note scheduler_sha256)
2. Root writes `$R/facts.json` from facts.FALSE-TEMPLATE.json (writer inventory, v5b bound + acceptance, 11 flags true, scheduler_sha256).
3. `python3 -I -B $H/fill.py --fill-adoption $R/facts.json --out $R/root-operating-adoption.json`
4. Give the adoption to sol-h3t for independent exact acceptance, and obtain the operation review for operator 30ab0c54 + request ce391b74.
5. Root writes control snapshot (six scan dirs) and adds `independent_operation_review`, `control_post_snapshot`, `scan_dirs`, fresh `utc` to facts.
6. `python3 -I -B $H/fill.py --fill-once $R/facts.json --adoption $R/root-operating-adoption.json:<sha256> --out $R/root-once.json`
7. `python3 -I -B $H/fill.py --check $R/root-once.json`   (must print passed true; re-run immediately before launch)
8. Immediately re-scan ROOT/REVIEWER posts, then launch once: `python3 -I -B $PWD_OF_OPERATOR/operate_stage32.py operate --authority $R/root-once.json`
   (operator = newperiod-stable-stage32-successor-astra-v6-20261026/operate_stage32.py). No retry; keep failures.
