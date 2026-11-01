# Remaining-guard preflight, revision 2: total-limit change only (NOT RUN, NOT APPROVED)

- Author: claude-opus-5-5, session `<SESSION_ID>`. Base: `../preflight/` (pins e496e976,
  CODEPASS `../reviews/opus-preflight-code-review.txt` 64fe7d39). That folder, its attempt records and
  `../coordination/preflight-result.json` (f530f19e) are untouched.

## Attempt 1 of the approved preflight (terminal, no retry)

- Result: `TERMINAL_REFUSED`, rc 1, empty stdout. stderr:
  `PreflightRefused total_limit:core-v6b/fits/c3_none_history-off_d60_seed3/fit_receipt.json`.
  The rc-255 transport exception does not apply.
- The run stopped at the 35th of 42 core cells.
- **Inference from held metadata, not a measurement:**
  - The resource inventory (r1-resource-inventory-20261020) records the other files that were read as small: rule
    files 815-1155 B, completions 472-1180 B, the H1 audit 539219 B, the finals ledger 41012 B, and the fit ledgers
    about 0.09 MB.
  - So the roughly 34 core `fit_receipt.json` files read up to that point carried about 255 MiB, an average of
    about 7.5 MiB each, each under the 32 MiB file limit.
  - Projected for the full scope: 42 core receipts at about 315 MiB plus 20 H1 audited receipts of unknown size.
- No metadata predicate was evaluated and no PASS or FAIL exists. A3 says "not widened silently", so this revision
  asks for review.

## The change (`revision.diff`)

| Item | Change |
|---|---|
| `remote_template.TOTAL_LIMIT` | 256 MiB → **768 MiB** (pending review) |
| per-file limit, derived max, JSON only, all read checks | unchanged (32 MiB, 124) |
| `total_limit` refusal line | now carries `files=<n> bytes_before=<n> size=<n>` (counts and sizes only, no content) |
| driver | scope `r1-v6-remaining-guard-preflight-v2`; result `coordination/preflight-r2-result.json` (write-once); output validation total ≤ 768 MiB |
| payload | byte-identical (74140aed): same 70 exact refs, 4 held documents, 122 cells |
| tests | 53 existing + 2 new = 55 passed; Ruff clean |

Remote memory: raw bytes stay in the single process. 768 MiB on <BATCH_HOST> (2 TB) is the bound.

**Alternative if the reviewer prefers it:** keep 256 MiB and split the preflight by cell group. That needs more code
and several runs, so it is not proposed.

Everything else in `../preflight/REVIEW.md` still holds: A1-A6, the disclosures and the classification.
