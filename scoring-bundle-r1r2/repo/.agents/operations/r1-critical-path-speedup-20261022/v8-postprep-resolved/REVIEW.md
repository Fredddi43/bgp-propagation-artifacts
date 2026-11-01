# v8 post-preparation RESOLVED tree (LOCAL; nothing staged or run)

Author: claude-opus-5-5, session <SESSION_ID>. Built 2026-10-22 under the reviewer's step 5a
(`v8-captures-u2-u3-results.txt` 46c9ad9a). It needs the reviewer's resolved-tree delta check before any B8 transport
approval.

## How it was built (once)

    cd v8-postprep-candidate && .venv/bin/python -I -B build_post.py --resolve \
        <review>/v8-postprep-resolution.json ../v8-postprep-resolved/tools

- The resolution is the reviewer's `v8-postprep-resolution.json` **3de7a2e7**, with all 10 markers. No value was
  chosen by the author.
- The candidate is pins 67414ab7.
- The build gave rc 0 with empty stdout and stderr (`evidence/resolve.*`). No `__V8_` text remains anywhere in `tools/`.
- `tools/` sits at the same depth as the candidate's, so `OPS = HERE.parents[3]` still names `.agents/operations`.

## Delta against the candidate's tools (`diff-candidate-resolved.diff`)

- **Marker text only, in 3 files:**
  - `transition.py`: EVAL_VERDICT;
  - `stage_b8.py`: the two B8 shas and ACTUAL spec/seal/ledger;
  - `final_build.py`: the 4 BOUND shas and the 2 B8 shas.
- The other 13 generated files are byte-identical to the candidate's.

## Copied byte-exact (step 5a list only)

| Resolved path | sha256 | Source |
|---|---|---|
| transition/evidence/capture-a.json.gz | 23f5e760 | candidate (capture A1) |
| transition/evidence/capture-b.json.gz | 45921015 | candidate (capture B1) |
| transition/filled-v1/execution-spec-FILLED.json | fdb12162 | candidate (F1) |
| transition/filled-v1/r1-authorization-DRAFT.json | 518a1d79 | candidate (F1) |
| transition/filled-v1/transition-summary.json | 1f5aa28a | candidate (F1) |
| transition/capture-request-b.json | ccee9252 | candidate (A2) |
| transition/reviews/opus-b8-sources-assessment.json | 92637539 | reviewer run dir |
| transition/reviews/opus-b8-fits-assessment.json | 989bd795 | reviewer run dir |

The other capture-step records (terminal status, rc/stdout/stderr, capture-request-a, source-fit-bridge) stay in the
committed candidate (d440641) and are not copied. No resolved tool reads them.

## Local check (read-only; `evidence/local-check.txt`)

From the resolved tree:
- `stage_b8.checked_files(local_files())` accepts both B8 JSONs.
- `final_build.bound` accepts all 4 BOUND inputs.
- `final_build.codepass()` accepts the eval v8 files against review-pins c250dda7.
- `final_build.b8_bytes()` names the two files under `r1-b8-evidence-v8-20261022`.

No suite or benchmark was re-run.

## Not authorized

B8 transport (stage_b8 stage/readback), the R1 receipt, `final_build spec/package`, evaluation staging or launch,
labels and scoring. Each needs its own exact approval and root routing. The caps are unchanged: 113 h wall, 452 h
CPU, supervisor 407,100 s.
