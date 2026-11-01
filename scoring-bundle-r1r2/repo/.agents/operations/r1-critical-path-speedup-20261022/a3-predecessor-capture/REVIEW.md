# A3 predecessor capture proposal (LOCAL; nothing captured, nothing run)

- Author: claude-opus-5-5, session <SESSION_ID>.
- Purpose: the minimal exact reads that let the v8 preparation bind the v7 attempt (review A3) after a v7 terminal
  failure, with no widening of read scope.
- Tooling is reused frozen and unchanged: `v8-assembly-r2/failed_v7.py`, checked against r2 pins d589b310.
- **No A3 capture runs until v7 is terminal and an exact, scoped review approval exists.**

## Sequence (each step once, no retry; each stops its branch on failure)

1. **v7 terminal.** The root's watch shows `evaluation-control-v1/execution-exit.json` with an integer returncode.
2. **K1, unchanged.** `census.py` e4696da7 under approval bdf45c60: stat-only, plus the ≤ 4 KiB exit record. Already
   approved for exactly one run. Output `r1-posteval-verification-20261022/evidence/census.json`.
   - If `terminal_success` is true, this failure branch stops. The existing K2 conditional chain applies only under its
     own exact conditions.
3. **Derive the request (local).** `propose.py request --census <census.json>` writes `requests/a3-request.json` (open
   `x`, never overwritten) and prints the exact command. It refuses unless the census:
   - is the approved K1 output (tool and approval sha);
   - shows v7 non-success: supervisor 317830 gone, no control process, a non-zero or exception exit with retry false;
   - shows no `results/`, no `complete.json` and no result entries;
   - shows none of the three `r1-unblinding*` markers;
   - lists all six control records.
4. **One f19d1066 capture** (needs the new approval), local output `evidence/a3-capture.json.gz` (exclusive):
   ```
   cd <repo> && .venv/bin/python -I -B .agents/operations/r1-prerequisite-evidence-20261021/capture_metadata.py \
     .agents/operations/r1-critical-path-speedup-20261022/a3-predecessor-capture/requests/a3-request.json \
     .agents/operations/r1-critical-path-speedup-20261022/a3-predecessor-capture/evidence/a3-capture.json.gz
   ```
   - It reads exactly these files under the v7 control root:
     - `stage-complete.json`;
     - `launch-started.json`;
     - `launched.json`;
     - `supervision-started.json`;
     - `execution-started.json`;
     - `execution-exit.json`;
     - and `results.resources-before-label.json`, only if the census listed it.
   - All are small, label-free control records (sizes are measured by K1 before the capture).
   - Tool caps: `.json`/`.py` only, under the forecasting root, 16 MiB per file, 256 MiB total. No listing, no write.
5. **Build and check (local).** `failed_v7.py build`, then the host-side `check_failed_v7` in the v8 preparation
   launcher (r2).

## Decision for the reviewer: `launch.err`

The f19 tool cannot read it (not `.json`). This proposal **does not capture it** and adds no read scope.

| Option | What it means |
|---|---|
| **A** (author's recommendation) | Not required. The exit record (rc/exception) plus K1's stat size of `launch.err` bind the failure. The predecessor rule needs failure + nothing published + no labels, all of which are covered. The frozen `failed_v7.build_evidence` currently *requires* a launch.err item, so A needs a narrow follow-up revision of `failed_v7.py` (size-only binding; the host check compares size). Not done here: r2 is frozen under review. |
| B | Required as bytes, via the already-reviewed `eval_status.sh` tail. Exact only if K1 measures ≤ 65,536 bytes. No new tool, but it uses that script's operational scope once more, which the reviewer must approve explicitly. |

No other logs are proposed (`launch.out` and `supervise` output are not read).

## Tests (`test_a3.py`: 13 passed; ruff clean)

- The request is exactly the 6 or 7 v7 JSON records, never `launch.err`.
- The command string is exact; one attempt; exclusive output.
- Refusals:
  - not the K1 tool or not the K1 approval;
  - v7 success; live supervisor; a marker; published results;
  - exit 0; a missing record.
- Refuses changed f19 or `failed_v7` bytes.
- One request file, a second write refused.
- No remote call anywhere.
