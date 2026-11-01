# REVIEW-VERDICT-QUICK: origin parallel master/export/audit

Verdict: CHANGES (BLOCKER for promoting any group's export until a gate exists and the equivalence run has passed).
Recommendation: add the RESULTS.json gate to the chain, keep the parallel driver, and do not capture/promote any group until equiv shows master/export/audit equal=true.

## (1) Is equiv_test.py a sound proof?
Partly. What it compares (equiv_test.py L267-L296, L318-L368):
- sha256 of every file in the output tree of seq vs par, for master (parse/, status/, custodian-master.json, source-inventory.json), export (all .pt and input_manifest.json), and audit (original-audit.json, with only generated_utc normalized). It is not a subset of files.
- Reference: the pinned single-pass `adapter.master/audit` and `original.export` called directly, in the same process, on a derived fixture.
- Sample: about 500 test events, stride-sampled from the 135,088 valid cohort, built from a derived data root (equiv_test.py L108-L152) that drops error-null rows lacking replay dirs.
- Export and audit are both run on the SEQ master/export, so a par-master defect would not propagate to them; each phase is tested in isolation only.

Gaps a 500-event sample or this harness would miss:
- Not the production path. The test calls the phases directly. It does not go through `kernel.run_phase`, the `bounded_save` budget wrapper, or the real `run_step_origin_par.py` (L68-L72). The seal wrapper is re-implemented in the test (L304-L320), so a divergence from kernel.py L101-109 would go unnoticed. The access-log append is never compared.
- Custody append. `_log_pending` (parallel_phases.py L71-L86) writes the JSON record straight to `original.LOG` when that attribute exists, bypassing `original.log_read`. If log_read adds locking, chaining or an fsync, the parallel append differs from single-pass. The record also carries the driver's pid and script. The audit log is protected custody, and no test covers it.
- Cohort-dependent paths. Failure paths (non-empty `failures`, ties/true_exposures, omitted_part_ids, an error status event) are hit only if the sample happens to contain them. The test records `audit_passed` but never asserts the sample was non-trivial.
- Scale. Not tested: `chunksize` heuristics at n=135k vs 500 (ordering is guaranteed by `pool.map`, so low risk); the 128 to 192 worker memory footprint (the fork-inherited `_S`, the ledger, the cones memo per worker); `Counter` insertion order across rare keys; and the `float(s.median())`/`quantile` summary over all ages (computed in the driver from the concatenated list, so likely fine).
- The cohort-level digests (library digest, `reference_population_sha256`, the history library) are computed once in the driver, not sharded, so the sharding risk there is low.

## (2) Does group_phases_job.sh gate on the equivalence result?
No. There is no reference to RESULTS.json or equiv anywhere in chain/ (the only hit is the read-only report in check1.sh L18-L22).
`group_phases_job.sh` L32-L40 runs the parallel master, export and audit as soon as the builds and assemble are done. `run_step_origin_par.py` L66-L72 installs the parallel driver unconditionally. The invalid groups also run on the parallel driver with no gate.
Where the gate must go:
- A. group_phases_job.sh, before L32. Require `$EQ/RESULTS.json` to exist and contain master.equal, export.equal and audit.equal all true. Otherwise exit 1 with `EQUIV-GATE-MISSING`.
- B. run_step_origin_par.py, before L68. Refuse to `pp.install` unless the same file passes and the sha of parallel_phases.py matches the one equiv ran against. Record that sha in RESULTS.json (today it is not recorded).
- C. Whatever captures or promotes the group exports (capture_origin.py) must also require the gate.

## (3) Live state of the equivalence run (read at 05:35Z)
Not finished, not passed yet. No RESULTS.json exists. PID 2678465 is alive (39:56 elapsed, `--reuse`, workers 112). equiv.out (last written 04:57Z) ends with `FIXTURE events=500 manifest_sha256=6ea8b123...`, so the run is past fixture creation and has not yet printed MASTER/EXPORT/AUDIT lines. The earlier crash (`_split_root` missing signature digest at equiv_test.py L296) is in the older part of the log from the pre-patch process; the current process has not repeated it so far. History in the same log: two REFUSED build-shard failures, and a full build that took 8,207 s. The fixture manifest sha changed between runs (3d2dac5e, e998856b, 6ea8b123), which is why `--reuse` can refuse; check that graphs/ was actually rebuilt against 6ea8b123 (graphs/ was re-created 04:15Z, before this manifest).
q27 STATUS also mentions a full-rebuild Slurm job 52620439. Its output was not checked; only one of the two runs needs to pass.
Conclusion: the proof is pending. Treat it as NOT passed until RESULTS.json shows master/export/audit equal=true.

## (4) Top risks
1. No gate, so the unproven driver can write all four groups' outputs: group_phases_job.sh L32-L40; run_step_origin_par.py L66-L72.
2. The harness does not exercise the production path (kernel.run_phase, budget wrapper, access-log append), and the custody append bypasses `log_read`: equiv_test.py L267-L296, L304-L320; parallel_phases.py L71-L86.
3. Phases are tested in isolation on a derived fixture of 500 events. This misses failure/tie/error-status branches and scale/memory effects at 135k events with 192 workers, and nothing in RESULTS.json pins the parallel_phases.py sha or the fixture's coverage: equiv_test.py L108-L152, L355-L368.

## Suggested minimum fix before any capture
- Add the gate (A+B+C) and have equiv_test.py write the parallel_phases.py sha, and the counts of events by status and of failures/ties exercised, into RESULTS.json.
- Compare the access-log delta (record keys excluding time_utc/pid/script) between seq and par.
- Run one cheap end-to-end check on a real invalid group (smaller cohort, 14,004 events) through `run_step_origin_par.py` and the single-pass `run_step_origin.py`, and compare the output trees. The invalid d30 outputs are the natural candidate.
