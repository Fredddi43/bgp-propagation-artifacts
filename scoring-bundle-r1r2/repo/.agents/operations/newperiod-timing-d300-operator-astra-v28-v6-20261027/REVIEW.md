# d300 operator v6 (no --export=NONE; fresh astra-v6 namespace; stage_hold + install_release)

No execution authority; v3-v5 and their actuals are untouched. Root cause (root canaries, FINDINGS.md): `sbatch --export=NONE` jobs are cancelled by uid 0 at start; /dev/null outputs and ulimits are fine.

Changes vs v5/v4:
- `held_argv` no longer contains `--export=NONE` (job name now `n-timing-d300-v6`); `check_held` compares SubmitLine to `held_argv`, so an old-style SubmitLine with `--export=NONE` is refused (tested). Dependence check: `job.sh` needs only SLURM_* injected by slurmd, `/usr/bin` tools, and `env -i` for the successor; with default export the batch shell inherits the submitter's environment but the successor still runs under `env -i` with the same fixed variables, and the `SLURM_ARRAY_*` guard still runs. Nothing else in operate/prepare/remote reads export state. Residual: the job.sh bash itself now sees the submit environment (ssh non-interactive on <SUBMIT_HOST>).
- `prepare.py` SOURCE/PINNED point at successor v6 (successor f398f172..., plan 857c8b77..., template f4f6efa4...); keeps the v5 NumNodes `1`/`1-1` rule.
- `operate.py` = v4 (stage_hold + install_release with the ordinary `actual-stage_hold/result.json` path) plus v5's `parse_scontrol` (mid-line SubmitLine fix). The v5 recovery-from-consumed-stage path is not needed and is absent.
- `remote.py` = v4 with `FRESH` -> astra-v6; `recovery/` now exists as a plain <USER> 2700 dir, so stage takes the existing-parent branch (tested: not recreated, `recovery_created` null); the create-once branch is retained and still tested.
- Fresh actual dirs `actual-stage_hold` and `actual-install_release` (none exist). Templates regenerated (phase V48 913754c6, plan path/sha v6). `scontrol-52573670.real.txt` is a real v5-era line used, re-targeted textually to v6 flags/namespace/new job id, as the readback fixture.

Tests (`python3 -I -B` from /tmp): test_operate 13, test_prepare 10, test_reason_codes 3 pass, including `no '--export=NONE'` regression on the submit argv, real-line readback+check_held, absent/existing parent, and v3 vs v4 reproduction. Both FALSE root templates refuse `--check-only` at the issued-root gate.
