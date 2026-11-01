# Review packet: class (b) host run of the frozen verifier-r2 (LOCAL; nothing submitted)

- Author: claude-opus-5-5, session <SESSION_ID> (`/root/opus_implementation`).
- It runs verifier-r2 (CODEPASS 46c72360, pins 2a861eb0) as reviewed. No verifier byte changes.
- The code comes from the classd-host transport (`B/r1-posteval-classd-v1/code/verifier-r2`, pins bffe254e, under
  review).
- This is the execution that the verifier CODEPASS left separate: "after K1/K2/K2c, inputs bound by sha, in place on
  the host, memory from the K1 census, shared venv numpy 2.5.2, --sample-sum numpy_pairwise, once".
- **Not done:** no ssh, no job, no host read, no report, per-event or result content. The R1 eval (317830) is
  untouched.

## `vrun.py`

| Phase | What it does |
|---|---|
| `script` (local) | Prints the exact job script and its sha. |
| `submit` (once) | `ssh <SUBMIT_HOST> 'sbatch --parsable'`, with the script on stdin. |
| `queue-check` (read only) | `squeue -h -j ID -o "%i %T %r"` and `sacct -n -P -X -j ID -o JobID,State,ExitCode,Elapsed,MaxRSS,NodeList`. |
| `fetch-request` (once) | Only when sacct shows `COMPLETED\|0:0`: one `ssh <BATCH_HOST> sha256sum OUT`, recorded, then the f19 request for `OUT` at that sha. |

**`script`:**
- It is a pure function of two executed captures:
  - `--complete-sha256` is the sha of `complete.json` raw from the K2a capture, after `requests.complete` accepts
    it (passed, spec 95ee898d, retry false, exact report path);
  - `--mem` comes from the K1 census.
- An absent capture, a non-terminal census or a non-regular per-event entry refuses. With no captures, the real CLI
  answers `ValueError: K1 census and K2a capture must exist (approved, executed) first`.

**`submit`:**
- No `--export` is passed: `--export=ALL,VAR=` over ssh triggers Slurm user-env retrieval and holds the job.
- It needs:
  - the exact approval;
  - a successful classd-host transport record (`classd-host/transport-records/stage-result.json`, rc 0);
  - no earlier submit intent.
- It records intent and result exclusively and never resubmits.

**`queue-check`** is what root uses about 30 s after submit, to read the pending **reason**, not just the state. It
contains no scancel, sbatch or scontrol.

**The approval gate checks:**
- an independent reviewer;
- scope `r1-posteval-verifier-run-v1`;
- `tool_sha256`;
- **`job_script_sha256` exact**;
- the exact `inputs` and `out`;
- `attempt_limit` 1 and retry false;
- `per_event_in_place_read_authorized` true and `result_fetch_authorized` true;
- labels, predictions, `n_or_2026` and `manuscript_use` all false.

**Why the approval binds the exact script:**
- The script depends on the K2a complete sha and the K1 bytes, so it exists only after K1/K2a.
- Sequence:
  1. root runs K1/K2a;
  2. the author runs `vrun.py script` and publishes the script and its sha;
  3. the reviewer checks them and issues the exact approval;
  4. root runs `submit` once.
- The reviewer's work at step 3 is mechanical: diff against the template below plus the two values.

## Job script template (the only free values are the K2a sha and the GiB)

```bash
#!/bin/bash
#SBATCH --job-name=r1-verify-r2
#SBATCH --partition=cpu
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=<GiB>G
#SBATCH --time=12:00:00
#SBATCH --no-requeue
#SBATCH --output=B/r1-posteval-classd-v1/out/verify-r1-slurm-%j.out
set -euo pipefail
export PATH=/usr/bin:/bin
test ! -e B/r1-posteval-classd-v1/out/verify-r1.json
cd B/r1-posteval-classd-v1/code/verifier-r2
sha256sum --strict --check - <<'SHAS'
2a861eb0…  pins.json
36ab00c5…  run_verify.py
5ed5229f…  verify_r1.py
SHAS
exec <RESULTS_ROOT>/work/<PROJECT>/venv/bin/python -I -B run_verify.py \
  --complete ROOT/complete.json --report ROOT/results/report.json --per-event-dir ROOT/results/per_event \
  --spec B/r1-release-assembly-v7-20261022/control-v1/prepared/spec.json \
  --seal B/occurrence-final-v1/custody/r1-access/r1-seal-17f81575….json \
  --ledger B/r1-release-assembly-v7-20261022/control-v1/prepared/evaluation/ledger.json \
  --manifest-d30 B/occurrence-final-v1/manifests/retrospective-2025-v6-d30.json \
  --manifest-d60 B/occurrence-final-v1/manifests/retrospective-2025-v6-d60.json \
  --slice-rules B/occurrence-final-v1/slice-rules/issue-time-slice-rule-v6b.json \
  --arm-spec B/r1-analysis-arm-binding-v1-20261020/arm-spec.json \
  --complete-sha256 <K2a> --sample-sum numpy_pairwise --out B/r1-posteval-classd-v1/out/verify-r1.json
```

Paths are written in full in the real script (`B` = `<FORECAST_ROOT>`,
`ROOT` = `B/r1-release-assembly-v7-20261022/evaluation-control-v1`).

`run_verify.py` itself checks every input against its external anchor before parsing:
- spec 17f81575, seal 6412d726, ledger ec445b8d;
- manifests 45865cdf and f885a805;
- slice rules 0291d789, arm spec 9a6d36e8;
- complete.json against the K2a sha, then the report against the sha complete.json binds;
- per-event entries are opened `O_NOFOLLOW` and must be regular files.

**Resources (derived, not guessed):**
- `--mem` = ceil((10 × (per-event bytes + report bytes) + 4 GiB) / GiB).
  - Parsed JSON rows take about 10× their bytes, as proposed in verifier round 1.
  - Above 480 GiB it refuses and resources are re-proposed.
- 4 CPUs. The verifier uses no BLAS, so the thread count cannot change any number.
- 12 h wall, partition `cpu`, no `--nodelist`, far inside the 5000-CPU cap.
- `--no-requeue`, so Slurm itself never reruns it.

**What it reads, where it writes:**
- It reads report and per-event files in place (class b).
- No labels, predictions or tensors (class d, separate).
- Writes: only `out/verify-r1.json` (opened exclusively by run_verify) and the Slurm log, both in the fresh classd
  directory.
- The output holds findings only: the summary counts and the failed checks. **No manuscript use** until the result is
  independently assessed.

## Exact steps (each once; no retry; stop and report on any refusal)

**Preconditions:**
- the R1 eval is a terminal success;
- K1 and K2a have been executed;
- classd-host T1 (transport) has succeeded.

K2b and K2c are not inputs to the job; the verifier reads report and slice rules in place by sha. They are only
needed to read the result locally.

| Step | Who | Command (from `.agents/operations/r1-posteval-verification-20261022`) |
|---|---|---|
| S | author | `…/.venv/bin/python -I -B vrun-host/vrun.py script > vrun-host/job-script.json`, then publish its sha |
| A | reviewer | exact approval `reviews/<…>-vrun-approval.json` binding `job_script_sha256` |
| R | root | `vrun-host/vrun.py submit --approval <A> --approval-sha256 <sha>` |
| Q | root | `vrun-host/vrun.py queue-check` about 30 s after R, then on its existing watch; read the reason |
| F | root | `vrun-host/vrun.py fetch-request --approval <A> --approval-sha256 <sha> > vrun-host/request-fetch.json`, then f19 from `.agents/operations` to `r1-posteval-verification-20261022/vrun-host/evidence-verify.json.gz` |

**If the job ends in any state other than COMPLETED 0:0:**
- F refuses;
- nothing is resubmitted;
- the sacct line is the reported outcome;
- reading the Slurm log needs a separate f19 approval.

## Tests

| Suite | Result |
|---|---|
| `test_vrun.py` | 28 passed |
| `ruff check` | pass |

**Inputs:**
- they come only from the captures, and absence refuses;
- a non-regular per-event entry refuses;
- memory arithmetic: 35 GiB for 3 GiB + 1000 B, 5 GiB minimum; the ceiling and zero both refuse.

**Cross-packet consistency:**
- seal, ledger, spec, report, manifests, DEST and venv equal classd-host's;
- slice rules equal the K2c request path;
- the arm spec is the staged arm-binding root;
- the code shas equal the verifier-r2 files.

**Job script:**
- it carries every anchor and has no nodelist, `--export` or srun;
- it is deterministic;
- its exec line parses under the frozen `run_verify` argparse to exactly the INPUTS, the complete sha,
  numpy_pairwise and OUT;
- **it runs under real bash in a sandbox** with a stub interpreter:
  - the stub is reached only after the hash check;
  - it is not reached with changed code, missing code, or an already existing output.

**Approval refusals (10):** author, author worker, script sha, tool, inputs, per-event false, labels, manuscript,
attempts, retry.

**Submit:**
- one sbatch on <SUBMIT_HOST> with the script on stdin;
- a second refuses without ssh;
- the transport must have succeeded;
- a failed sbatch is recorded and never repeated.

**Queue-check:** needs a job, and its command is read-only with the reason field.

**Fetch:**
- RUNNING and FAILED refuse without the sha ssh;
- COMPLETED 0:0 gives the request at the host sha;
- a second fetch refuses.

**Main:** no ssh without an approval (submit and fetch); a wrong anchor refuses; submit sends exactly the approved
script.

**`mutation_controls.py`:** 10/10 detected.

| Mutation | Targeted tests |
|---|---|
| job code hash check dropped | 1 failed |
| existing output not refused | 1 failed |
| memory not from the measured bytes | 1 failed |
| memory ceiling dropped | 1 failed |
| non-regular per-event entries accepted | 1 failed |
| approval not bound to the job script | 1 failed |
| approval independence dropped | 1 failed |
| submission repeatable | 2 failed |
| transport precondition dropped | 1 failed |
| fetch before COMPLETED 0:0 | 1 failed |

**Not authorized by any of this:** labels, predictions, tensors, N or protected-2026 data, the D2 rescore, resubmission,
installs or venv writes, and manuscript use of any number.
