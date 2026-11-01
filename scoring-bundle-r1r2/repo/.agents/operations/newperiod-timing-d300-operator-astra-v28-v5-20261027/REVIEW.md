# d300 operator v5 (readback fix + install-only recovery of held job 52573670)

No execution authority. v3 and v4 (including v4's consumed actual-stage_hold) are untouched; `remote.py` is byte-identical to v4. Diffs: `prepare-delta.patch`, `operate-delta.patch` (both against v4).

Real cause of the v4 readback stop (read-only `scontrol show job -o 52573670`, saved as `scontrol-52573670.real.txt`): two defects, not one.
1. NumNodes prints `1-1`. `check_held` now accepts `('1','1-1')` only.
2. Slurm prints SubmitLine in the MIDDLE of the line, followed by WorkDir/StdErr/StdIn/StdOut/TresPerTask. The old `readback` took everything after `SubmitLine=` as SubmitLine, so WorkDir/StdOut/StdErr were never parsed and the exact-SubmitLine check could not match either. New `parse_scontrol` ends SubmitLine at the last ` WorkDir=`. All other checked fields match the real line (field-by-field diff run).

Recovery path (install_release only; `stage_hold` is refused and operate.py contains no sbatch/`held_argv`):
- Authority carries `recovery_stage` = {dir, intent, stage, pre_submit, submitted, stopped} (path+sha of the consumed v4 records). `recovery_job` requires the exact v4 dir, no `result.json`, STOPPED step `readback` and consumed, passed stage and pre_submit, and `submitted.json` equal to exactly `{job_id: 52573670, retry_authorized: false}`. Any other job id refuses. `stage_actual` must be null.
- Authority also carries `held_record` (ref to the parsed scontrol record; candidate at `candidate/held-record.json`) and `held_acceptance` (independent typed record: passed, job_id, `held_record_sha256`, plan, phase, reviewer_worker/session, plus `recovery_stage` and `held_record` equal to the authority's). `bind` checks it exactly as before.
- Operation review must carry the same `recovery_stage`, `held_record`, `held_acceptance` and the binding sha. Gate-after-consumption re-reads them and the recovery records.
- Install still re-reads live scontrol (`check_held`) before install, before release and refuses any change; then install, preflight, `scontrol release` as in v4. Fresh `actual-install_release` (does not exist).
- The v4 stage records carry no phase/pins; the install is bound to the current latest phase (V48) and v5 pins instead. Stated limitation.

Tests (`python3 -I -B` from /tmp): test_operate 14, test_prepare 9, test_reason_codes 3, pass. New: real scontrol fixture through `readback` + `check_held`; NumNodes 1-1 accepted and 2/1-2/2-2/empty/0 refused; wrong job id refused; recovery records exact/variants/tamper/result.json present; the real consumed v4 records bind only 52573670; stage_hold refused. FALSE templates refuse `--check-only`.

Re-review: concurrences (timing_science, allocation_premise) re-bind to v5 `prepare.py` (bbdce1e1...); install_release operation review re-binds to v5 pins and the recovery fields; held_acceptance is new; adoption-007 unaffected (phase+plan only); stage_hold review/once no longer applicable.
