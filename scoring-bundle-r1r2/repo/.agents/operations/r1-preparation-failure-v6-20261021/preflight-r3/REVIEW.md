# Remaining-guard preflight, revision 3: limits from the reviewed size census (NOT RUN, NOT APPROVED)

- Author: claude-opus-5-5, session `<SESSION_ID>`.
- Answers `../coordination/revision-request-1.json` e9a7d0ab (R1-R3).
- Base: the CODEPASS v1 files in `../preflight/` (pins e496e976). They are untouched, and so is attempt 1
  (`../coordination/preflight-result.json` f530f19e, TERMINAL_REFUSED).
- `../preflight-r2/` is superseded and never runs.

## R1, the measured census

`../coordination/census-result.json` 008b5cd5: one approved stat-only run, approval c5635c1d, review 9605fa9f.

| Class | Files | Total | Largest |
|---|---|---|---|
| exact refs (rule files, fit ledgers, H1 evidence) | 70 | 0.7 MiB | 0.51 MiB (H1 audit) |
| fit completions | 42 | < 0.01 MiB | < 0.01 MiB |
| fit receipts | 42 | 313.0 MiB | 7.45 MiB |

- All 154 paths are regular files, not symlinks, with realpath == path. No problems were found.
- The 40 H1 audit-derived files are not measured, because the audit is not held.

## R2, the limits

Measured + 25% margin, rounded up to MiB:
- **Per file: 10 MiB** (7.45 MiB × 1.25). This is narrower than the 32 MiB approved earlier. It also bounds the 40
  unmeasured H1 files: a larger one refuses fail-closed, and the refusal now reports its size (counts and sizes
  only, no content).
- **Total: 579 MiB**, equal to the census proposal (313.8 MiB measured + 20 H1 receipts budgeted at 7.45 MiB, ×1.25).
  The 20 H1 completions are budgeted as negligible, like the measured ones.
- **Address space: 8 GiB** (`resource.setrlimit(RLIMIT_AS)`). Retained raw bytes are ≤ 579 MiB; JSON parse
  objects of a 7.45 MiB receipt are transient. Exhaustion fails closed as `PreflightFailed MemoryError`.

**What the large receipts are, by field name only**, from the producing source `forecast_train.py`:403-433 and
`forecast_baseline.py`:86-104 (details in `../census/REVIEW.md`):
- The bulk is `train_inputs` / `validation_inputs`, per-event input provenance with `event_id`, `path`, `sha256`,
  `forecast_contract`, and `history_provenance` for training events.
- They hold no prediction values and no labels. The custody reads only `checkpoint_sha256`, `test_inputs_opened`,
  `threshold_calibration_split` and `threshold` from a receipt. None of these reach the output (A4).

## R3, everything else identical (`revision.diff`)

- The payload is byte-identical, 74140aed: 70 exact refs, 4 held documents, 122 cells, the same AST-extracted
  expressions and the same candidate custody 409e1171.
- Policy, register(), the held documents, the snapshot views, the unperformed digests, sanitized output and attempt
  semantics are unchanged.
- **Driver changes:**
  - scope `r1-v6-remaining-guard-preflight-v3`
  - result `../coordination/preflight-r3-result.json` (write-once)
  - output validation: per file ≤ 10 MiB, total ≤ 579 MiB
- Fresh program bytes 66467bc6. Tests: 53 v1 tests (one size bound adjusted to the new limit) plus 2 new = 55
  passed. Ruff clean.
