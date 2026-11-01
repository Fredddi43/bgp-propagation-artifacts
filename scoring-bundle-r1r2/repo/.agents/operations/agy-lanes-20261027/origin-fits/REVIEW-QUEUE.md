# REVIEW-QUEUE: origin-fits

## Packet 1: Origin Disclosure Counts (P7)
- **Review file**: `<REPO>/.agents/operations/agy-lanes-20261027/origin-fits/REVIEW-ORIGIN-DISCLOSURE-COUNTS-P7.json`
- **Packet path**: `<REPO>/.agents/operations/agy-lanes-20261027/origin-fits/ORIGIN-DISCLOSURE-COUNTS.json`
- **Summary**: Exact event-id projection and ROA snapshot availability counts computed for development [2025-01-01, 2026-09-01) and prospective [2026-09-01, 2026-10-16). Replaces `\pending{...}` in `paper/sections/10-disclosures.tex`. Dev: 42827 events (42764 same-day, 63 fallback 1-7d, 0 no_roa, 90 cross-midnight). New period: 223308 events (all same-day, 0 fallback, 0 no_roa, 3018 cross-midnight).
- **Changes vs predecessor**: Resolves pending template `REVIEWER-sol-g1a-ORIGIN-DISCLOSURE-COUNTS-V1-PASS.json` with actual computed aggregates directly from pinned source tables.
- **Tests/output**: Executed on <BATCH_HOST> using venv python against pinned parquet tables matching projection v3r3 sha256 sums. All 6 tables verified intact.
- **Risks**: None. Metadata-only aggregates, no labels or predictions decoded, no downstream dependencies broken.
- **Flip command**: `<REPO>/.agents/operations/agy-lanes-20261027/signoff.sh <REPO>/.agents/operations/agy-lanes-20261027/origin-fits/REVIEW-ORIGIN-DISCLOSURE-COUNTS-P7.json`

## 2026-10-27T10:55Z qwen-driver: BLOCKER ALERT-FIT40-CUSTODY-DEV.md (needs pinned remote.py 1-line fix)
- Both fit40 arrays die at entry.py on the GPU node: remote.py:55 OF_R04 compares custody-log st_dev captured on <BATCH_HOST> (=80) vs node (=87); same inode 5636854 — cross-node unsatisfiable (evidence dbg jobs 52589386/52589438/52589716).
- Earlier cause already fixed by me (non-pinned prepare.py ulimit -f 1GiB->2GiB, tests 31 OK).
- Fix = Option A in the alert (inode-only compare) -> then I relaunch both fit drivers within a minute.

## 2026-10-27T14:52Z qwen-driver: BATCH — 20 completed-fit review drafts (valid family) origin-fits/g1-fit-reviews/origin_change_valid-*.completed-fit-review.json — PENDING_ROOT, reviewer claude-sonnet-5-5. Attest per-cell fit completion (array 52591957, 20/20 COMPLETED 0:0; leaf sha256 verified on cluster: CAPTURE-VERIFY-valid.json; receipt<->manifest cross-check in ALERT-SIGN-ORIGIN.md §A). Flip: for f in g1-fit-reviews/origin_change_valid-*.json; do ../signoff.sh "$f"; done. Details: ALERT-SIGN-ORIGIN.md.

## S0 origin test-window stage (qwen origin S0 lane) — 2026-10-27
- Packet: <FORECAST_ROOT>/data-custodian/origin-s0-staging-v1-20261027/staging-receipt.json (stage doc for the S1 family_source_plan; kernel.source_plan field set incl. protected_test/source_scope/history digests/projection+sampling-rule refs).
- 5-line summary: 149,092 unique projection test events (14,004 invalid + 135,088 valid, d30==d60 asserted) link-staged byte-identically from reviewed finalize-r2 job 52510900 (hardlinks, same st_dev); 60 reviewed components pinned in control/s0-control.json (eventset/2026 tables, 47 daily ROAs, AS-ROV series, cones/as-rel for 202609+202610 incl. fresh CAIDA 20261001 cone); per-event verified (summary.onset==projection.onset, coverage panel=10, completeness recorded never gated); s0-manifest.json = sha256+bytes of every output + data_root_digest (sorted-path-sha rule); per-shard markers x512 (array 52600483, 0 FAILED).
- vs predecessor: replaces the missing S0 (q27 BLOCKER-1); no re-replay was needed — replay staging already existed (finalize-r2). Bench: 20-event re-merge reproduced anomalous/coverage/summary byte-identical, membership row-order/float-ulp only.
- Tests: smoke shard 0 + group 7 on <BATCH_HOST> (rc=0, idempotent rerun); sacct +60s checks; assemble re-hashes and cross-checks all shard markers, refuses foreign bytes.
- Risks/changes needing your OK: ALERT-S0-1 (AS-ROV series reuse 2021-12-24..2026-10-09 = leak-chain bytes; ROVista unpublished after 10-09; fresh CAIDA cone sha 1475e722).
- Flip command (after reading): <REPO>/.agents/operations/agy-lanes-20261027/signoff.sh <review file> after binding staging-receipt.json sha256 064ad2d8a7ff56e59648fdee49340e74eb53fa467c9737054f4322776fe21dcb + s0-manifest.json 60b405f9a10df6f99c274aeec268af9734cc59cc97c268fcae0f300b7da8fc67

## 2026-10-27T18:37Z qwen-driver: BATCH EXTENDED — all 40 completed-fit review drafts now exist (invalid 20 added: array 52591966, 20/20 COMPLETED exit 0:0, 132-183m; leaves sha256-verified CAPTURE-VERIFY-invalid.json). Flip all: for f in g1-fit-reviews/*.json; do ../signoff.sh "$f"; done. Nothing else signable in this lane until the q27 export chain lands (ALERT-SIGN-ORIGIN.md FINAL).
