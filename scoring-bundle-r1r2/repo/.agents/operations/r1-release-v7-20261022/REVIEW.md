# R1 v7: calibration-binding recovery, source/resource candidate (review packet, stage 1)

- Author: claude-opus-5-5, session `<SESSION_ID>`, role `/root/opus_implementation`.
  The frozen legacy author `f1d352ff` is unchanged in every v6 artifact. Both are refused as reviewers.
- Status: built and tested locally. Nothing staged, launched or remotely written; no approval exists. Exact pins:
  `pins.json`.
- Planned remote root (absent): `B/r1-release-assembly-v7-20261022`, where
  `B=<FORECAST_ROOT>`.

## What changes

- **The failure:** v6 terminated rc 1 at `verify_batch:1859` → `checked_decision_rules:1615` (evidence in
  `../r1-preparation-failure-v6-20261021`, pins d898567c).
- **The fix:** custody a0dba7aa → **409e1171**, the only source change. `adapt_h1` names the OOD fit ledger as
  `{path, sha256}`.
  - Independent CODEPASS: `reviews/opus-v6fix-round1-verdict.json` d8b9a3a3.
  - The metadata preflight r3 (result c55dfe58, independent assessment c406014c) predicted 102/102 candidate cells
    PASS and the 60 old-shape cells FAIL. That is a **prediction only**; the fresh full run must verify.
- **Source:** the staged v6 overlay (candidate dc17cbdd) verbatim. The 372 other source files are byte-identical,
  and so are driver 4573658e and prepare c42e78ac.
- **Draft:** only the 3 scorer paths (v6 → v7 root, same SHAs) and `release_resources.contract` (new path and sha)
  change. Science keys are byte-equal.
- **Resources:** limits are unchanged. Only `input_identity_sha256`, the runtime/label bindings and
  `output_filesystem_root` change. `runtime.implementation_files` appends the v7 source set; history is kept.

## Exact subjects

| Item | sha256 |
|---|---|
| source candidate `source-candidate-v1/candidate.json` (kind `r1_reviewed_source_overlay_v7`, 375 files, 373 source) | 29a733a90388c41ebc97fc7ef55d4ab9a8231712b4b46d18afe588086c6cc397 |
| source manifest (root `B/r1-release-assembly-v7-20261022/source`) | 7f35bd2258ef67ef6e8dfb1548d0c7ab0d5f84d347321ee612aa6f8255007823 |
| base draft, pending bindings | 737685e8979ab60d48ee4dc0aa3ae1e3774df97cf1ac435e08727152098e5761 |
| resource candidate `resource-candidate-v1/candidate.json` | d77a5a32b360d317781e0b3223634c2a32bd2c1905e6811ab735a0ec2d9fb275 |
| input identity | d03ee0b20c26f3dc22e0d019415756801d6d9bae7a772be865f04cd92ae3d7af |
| review archive `archive/r1-v7-candidates.tar` (380 members, deterministic) | f7f7cd206a1768332174225f6afe1da7a0de7f4ae1c59a2d387ef2682342dc47 |

## Failed-v6 predecessor evidence (actual, not reconstructed)

- `evidence/v6-start-records-capture.json`: ONE bounded read-only read of v6 `control-v1/execution-started.json`
  (307 B, 9047f8ff) and `launched.json` (105 B, 4558d726), with raw bytes and the program that read them.
  - `launched.json` = {pid 193917, spec ce9e6bfc}, matching `../r1-release-v6-20261021/coordination/launched.json`.
- The terminal capture is already held: launch.err 5797a627, execution-exit aa202f17 (rc 1, no retry), capture
  3d33a0f6.

## Tooling: the reviewed v6 tools, changed only as declared (`diff-*.diff`)

- `build_source_resource.py`: v6 base/root, custody a0dba7aa → 409e1171, fix pins/CODEPASS/preflight bindings,
  kind `_v7`, the current author session.
- `archive_candidate.py`: v7 candidate digests and archive name.
- `stage.py`:
  - the remote program is identical to v6 except the root path (a test asserts this)
  - kind `_v7`, scope `r1-source-only-staging-v7`
  - every author session refused
  - intent/result records go to `staging/` (in v6 they sat beside the candidate and broke the frozen
    reproducibility test)
- `test_source.py`: 15 passed (reproducibility, single custody change, draft/resource deltas, recorded fix and
  prediction, actual start records, stager identity and equivalence, archive members, untouched v6/failure
  packets). Ruff clean.

## Still PENDING (nothing here grants or claims them)

1. Independent source/resource review and the exact staging approval (contract in `coordination/source-review-ready.json`).
2. One source stage, with readback.
3. Local control binding.
4. New retention and preparation reviews bound to the actual v7 draft, custody 409e1171, driver and prepare.
5. Final package, then execution review and approval.
6. One control stage and launch.
