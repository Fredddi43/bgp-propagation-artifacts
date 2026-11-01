# Review packet: R1 post-evaluation capture (K1 census → K2 content → K3 projection). LOCAL; nothing read.

- Author: claude-opus-5-5, session <SESSION_ID> (`/root/opus_implementation`).
- Governing documents:
  - reviewer contract 48238fc3 and addendum-1 7c161f63 (V0 and V2 resolved, V1 adopted, V3 required);
  - root adopted-rules (`coordination-numerical-verification-decisions/adopted-rules.json`).
- **Not done:** no results listing, content, manifest, label or prediction read. No remote action.
- The R1 final evaluation (supervisor 317830, spec 95ee898d) is running. Its operational terminal watch is root's,
  and that scope is already approved.
- This packet covers authorization classes (a), (b) and (c) of addendum §6. Class (d), the labels and predictions
  for re-scoring, is a later, separate request.

## Steps (each once, each under its own exact independent approval; no retry)

| Step | What | Tool | Reads |
|---|---|---|---|
| K1 | census | `census.py` (new, stat-only) | stat of the control root, `results/**` (depth ≤ 2, cap 5000 entries), the 2 manifests and the 3 registry markers; content only of the ≤ 4 KiB `execution-exit.json` (already-approved scope); `/proc/*/cmdline` for the exact control-root script paths |
| K2a | `complete.json` + `execution-exit.json` | f19d1066 unchanged, request from `requests.py k2a` | 2 small JSON files |
| K2b | `report.json` at the sha `complete.json` binds; the d30/d60 cohort manifests at 45865cdf / f885a805 | f19d1066 unchanged, request from `requests.py k2b` | 3 JSON files, label-free except the released report (R1 released-output class) |
| K3 | lossless facts projection | `scripts/forecast_released_report_facts.py` 72bb5d9f + `forecast_release_facts.py` 442f3cbc, unchanged | local only; `numerical_verification_performed` stays false |

**Terminal success** is `census.judge`, from stat and the exit record only. Every one of these must hold:
- the exit has the integer returncode 0;
- supervisor 317830 is gone;
- no process has `execute.py`, `run.sh` or `supervise.py` of the control root as an exact argv element (the
  worker pid is not recorded anywhere, so it is found this way);
- `complete.json` and `results/report.json` are regular files;
- the registry has `r1-unblinding.complete.json` and no `r1-unblinding.failure.json`;
- the listing is not truncated.

Anything else stops at K1. On rc != 0, a failure packet is opened instead.

**Sizes decide the reads, not guesses.**
- `requests.py` refuses K2 unless K1 measured every size. Each must be within f19's caps: 16 MiB per file and
  256 MiB in total.
- A measured size over a cap refuses with the message "needs a separately reviewed read limit", never a workaround.
- The per-event directory is censused by name and size only, giving the count, total bytes and maximum file. That
  sizes a later in-place host verifier. Per-event content is NOT read in this packet.

**Bindings:**
- K2b's report sha comes from the captured `complete.json`. That file must say `passed`, carry the final spec
  95ee898d, have no retry, and name exactly `…/results/report.json`. The capture's exit record must have
  returncode 0.
- The manifests come at their seal-bound shas (addendum §2).
- `extract` re-checks every sha. It writes `report.json` and the manifests exclusively, and names the unchanged K3
  command with `--expected-report-sha256` from `complete.json`.

**Census remote:**
- It runs the base interpreter with `-I -S -B` as <USER> on <BATCH_HOST>, not in Slurm.
- The control root must be canonical and not a symlink.
- The marker paths come through stdin, so the census's own argv cannot match them.
- No writes.

## Tests

| Suite | Result |
|---|---|
| `test_capture.py` | 34 passed |
| `ruff check` | pass |

- **Census on synthetic trees:** the results files are mode 000, which proves no content is read.
  - A successful run is judged terminal and gives exact per-event counts and sizes.
  - 7 non-successes are judged false, each on its own key: rc 1, no `complete.json`, no report, the failure marker,
    the supervisor alive, a marker process, a truncated listing.
  - The marker match is exact (`execute.py.bak` is not a hit).
  - A symlinked root refuses.
  - An oversize report is judged not to fit f19.
- **Census approval:** 7 refusals, and no ssh without an independent approval.
- **Requests:**
  - K2a and K2b are exact, with the manifest shas pinned.
  - Refusals without a measured fit: not terminal, oversize, a missing size, a missing manifest. Exactly at the cap
    is accepted.
  - K2b refuses a `complete.json` that is not passed, has another spec, another report path, a malformed sha or
    retry, and an exit with rc 1.
  - `extract` refuses unbound report or manifest bytes and writes nothing; it writes once.
  - The projection entrypoint, the facts module and f19 are the reviewed bytes.

**`mutation_controls.py`:** all 8 detected:

| Mutation | Targeted tests |
|---|---|
| exit returncode not judged | 1 failed |
| supervisor liveness not judged | 1 failed |
| marker match by substring | 1 failed |
| registry failure marker ignored | 1 failed |
| census approval independence removed | 2 failed, 1 passed |
| f19 per-file cap unchecked | 1 failed |
| complete.json passed unchecked | 1 failed |
| report not bound to complete.json | 1 failed |

## Requested approvals (each separate, exact, once; none claimed)

1. **K1 census.**
   - Command: `census.py census --approval <A1> --approval-sha256 <sha>`
   - The approval must bind: `scope` `r1-posteval-census-v1`, `tool_sha256` (`census.py`), `payload` (equal to
     `census.payload()`), `attempt_limit` 1, no retry, and content, label, prediction and host-write all false.
2. **K2a + K2b + K3.**
   - Commands, from `.agents/operations`:
     `…/.venv/bin/python -I -B r1-prerequisite-evidence-20261021/capture_metadata.py <request> <output.json.gz>`,
     once per request. The request files come from `requests.py k2a` and `requests.py k2b`.
   - Then `requests.py extract` and the K3 command it prints.
   - Released R1 output (the report) plus label-free metadata (the manifests). No per-event, label or prediction
     content.

## Not in this packet

- The verifier: the `verifier/` subpacket, reviewed separately.
- In-place host reads of the per-event files, predictions and labels (class d), and any host job.
- Any manuscript number. Results stay out of the paper until the numerical check passes.
