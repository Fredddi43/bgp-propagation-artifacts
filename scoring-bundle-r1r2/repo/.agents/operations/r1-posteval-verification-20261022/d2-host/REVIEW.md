# Review packet: class (d) D2 host run of adapter-r2 rescore (LOCAL; synthetic only; nothing submitted)

- Author: claude-opus-5-5, session <SESSION_ID> (`/root/opus_implementation`).
- It runs the frozen adapter-r2 (pins 5eb25c10, CODEPASS 251b5e05) with verifier-r2 (2a861eb0). The code is already
  placed by the classd-host transport (bffe254e, approval a701734b) at `B/r1-posteval-classd-v1/code`.
- This is the D2 step that classd-host REVIEW.md left as a proposal.
- **Not done:**
  - no ssh, no job;
  - no label, prediction, tensor, per-event or report content;
  - the R1 eval (317830) is untouched;
  - real inputs exist only after K1/K2a and classd D0/D1/F.

## `d2.py` (tool sha 15d6ee26)

Phases follow vrun-host exactly: `script` (local), `submit` (once), `queue-check` (read only), `fetch-request` (once).

**`script` is a pure function of executed, recorded evidence:**
- **The f19 capture `classd-host/evidence-d0d1.json.gz`** must be exactly `{out/plan.json, out/census.json}`.
  - Their shas must equal the classd phase records `d0-result.json` and `d1-result.json`.
  - The census must be of that plan and have no missing or non-regular entries.
- **The K1 census** must be a terminal success.
- **K2a:** the report sha must equal what `complete.json` binds, and the plan must bind that report.
- **Fixed membership:** the plan's cells must be exactly adapter-r2 `fixed_cells` over the held seal, ledger and spec
  captures. That is the 66 protocol cells; locally it returns 66.
- An absent capture refuses. With no captures, the real CLI answers
  `ValueError: census.json must exist (approved, executed) first`.

**Why exactly two array tasks (`--array=0-1`, one per horizon):**
- `rescore` decodes the whole target partition of a horizon once.
- Per-cell arithmetic is about 0.6 s (measured), so any finer split only adds whole-partition decodes.
- Each task runs `run_adapter.py rescore --cells-file <that horizon's fixed cells>`. Its cells JSON is embedded in
  the script (so bound by the script sha) and written to node-local `mktemp -d /tmp/...`, removed on exit.
- Outputs: `out/rescore-d30.json`, `out/rescore-d60.json`.
- Math, membership and outputs are unchanged. The union of the two outputs is the run.

**Resources, from the D1 census:**
- Per horizon: `mem` = 2 × (Σ stored tensor bytes of that horizon's allowlist) + 2 × (largest prediction file of its
  cells) + 4 GiB.
- The array takes the maximum of the two. Above 480 GiB it refuses and resources are re-proposed.
- 1 CPU per task, since the code is single-threaded. 4 h wall, partition `cpu`, no `--nodelist`, `--no-requeue`.
- No `--export`: user-env retrieval holds jobs.
- Two CPUs in total, far inside the 5000-CPU user cap.

**In the job:**
- `set -euo pipefail` and `PATH=/usr/bin:/bin`;
- `sha256sum --strict --check` of adapter.py, run_adapter.py, verify_r1.py and verifier pins before anything runs;
- `test ! -e $OUT`;
- the venv python runs with `-I -B`;
- all other inputs are re-anchored by run_adapter itself: plan sha (A2), report sha (A1), source manifest 7f35bd22
  with the import closure (A3), and every prediction, per-event, rules and tensor sha from the plan.

**The approval gate (scope `r1-posteval-classd-d2-v1`) checks:**
- an independent reviewer;
- `tool_sha256`;
- **`job_script_sha256` exact**;
- the exact `inputs` and `outs`;
- `attempt_limit` 1 and retry false;
- label, prediction, per-event and result-fetch **true** (D2 is class d);
- `n_or_2026`, `manuscript_use` and `other_cells` **false**.

**`submit`** additionally needs the transport stage record (rc 0) and the D0/D1 records. It records intent and result
exclusively and never resubmits.

**`fetch-request`** proceeds only if sacct shows both `<id>_0` and `<id>_1` as `COMPLETED|0:0`. It then takes one host
`sha256sum` of both outputs and builds the f19 request.

## Exact steps (each once; stop and report on any refusal)

Preconditions:
- K1 and K2a executed;
- classd T1/T2 and D0/D1/F executed (F produces `classd-host/evidence-d0d1.json.gz`);
- the author publishes the D1 census figures.

| Step | Who | Command (from `.agents/operations/r1-posteval-verification-20261022`) |
|---|---|---|
| S | author | `…/.venv/bin/python -I -B d2-host/d2.py script > d2-host/job-script.json`, then publish its sha and the resources |
| A | reviewer | exact approval binding `job_script_sha256` |
| R | root | `d2-host/d2.py submit --approval <A> --approval-sha256 <sha>` |
| Q | root | `d2-host/d2.py queue-check` about 30 s after R; read the pending reason |
| F | root | `d2-host/d2.py fetch-request --approval <A> --approval-sha256 <sha> > d2-host/request-fetch.json`, then f19 to `d2-host/evidence-rescore.json.gz` |

## Tests (`test_d2.py`): 46 passed; `ruff` clean

**Inputs** (fixtures use the real 66 fixed cell ids from held metadata, with synthetic plan, census and captures):
- positive;
- an absent capture refuses;
- 8 refusals:
  - plan record sha;
  - census record sha, with plan and census still mutually consistent;
  - report;
  - census of another plan;
  - non-regular entry;
  - a dropped fixed cell;
  - an added non-fixed cell;
  - a missing horizon allowlist.

**Resources:**
- per-horizon arithmetic is exact (15 GiB and 25 GiB in the fixture); the array takes the maximum;
- the ceiling refuses.

**Membership:** each horizon gets exactly its 33 fixed cells.

**Script:**
- every anchor present: array, cpu, 1 CPU, mem, report sha, code shas;
- no nodelist, `--export` or srun;
- deterministic;
- code shas equal the reviewed files;
- both tasks parse under the frozen `run_adapter` argparse to exactly the expected arguments;
- **under real bash** with a stub interpreter:
  - each task runs its own horizon's out path and its exact cells file, only after the hash check;
  - the stub is never reached with changed code, a missing verifier, an existing output, no task id, or task id 2.

**Approval refusals (12):** author, author worker, script, tool, inputs, outs, labels false, other cells, N/2026,
manuscript, attempts, retry.

**Submit:**
- once on <SUBMIT_HOST> with the script on stdin;
- the transport and the D1 record must be present;
- a failed sbatch is recorded and never repeated.

**Queue-check:** read-only, with the reason field.

**Fetch:**
- refuses for one task RUNNING, one FAILED, or one task missing, with no sha ssh;
- with both complete, gives the request for both shas once.

**Main:** no ssh without an approval; a wrong anchor refuses; submit sends exactly the approved script.

**`mutation_controls.py`:** 14/14 detected.

| Mutation | Targeted tests |
|---|---|
| job code hash check dropped | 1 failed |
| existing output not refused | 1 failed |
| horizon tasks swapped | 2 failed |
| fixed membership dropped | 2 failed |
| capture not bound to phase records | 1 failed |
| report binding dropped | 1 failed |
| memory not from the census | 1 failed |
| memory ceiling dropped | 1 failed |
| approval not bound to the job script | 1 failed |
| approval independence dropped | 1 failed |
| other cells may be approved | 1 failed |
| submission repeatable | 2 failed |
| phase records not required | 1 failed |
| fetch after one task | 3 failed |

"Capture not bound to phase records" was undetected at first: the plan-record case also broke the census-to-plan link.
The census-record case was added for it.

**Note.** D2 needs the eval's report and per-event files. Per `../../r1-critical-path-speedup-20261022/diagnosis/`, the
current eval is not expected to produce them. This packet is ready for whichever reviewed run does.
