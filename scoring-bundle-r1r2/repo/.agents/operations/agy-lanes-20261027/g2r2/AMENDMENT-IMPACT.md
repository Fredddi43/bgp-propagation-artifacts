# Reviewer amendment (claude-sonnet-5-5) vs the final path (g2r2 audit, 2026-10-27)
Commit 6bebfc7c changed 25 files (one-line reviewer regex/tuple edits, no scientific edit). Method: grep of old SHA-256 values (amendment/AMENDMENT.md) across active packages + grep of reviewer checks in every final-path runner.

## Consumers that accept any truthy reviewer_model (no change needed)
Family inference runners (ordinary/history/stable/origin/timing/h1/h3/baseline/learned): `reviewer_model` only has to be non-empty. Single-R2 persistence runner (authority + resource admission + full-retention review): same. retention.py (G1 draft/finalize reviews): same. forecast_custody, forecast_custodian_eval (G3 seal, R2): no reviewer check. Bundle (G4): fixed authority dict, no reviewer.

## Pins the amendment broke (old hash still pinned, repo file now new)
Six amended files are hash-pinned in packages on the final path: `src/bgbench/forecast_recipes.py` (04691c48..) and `src/bgbench/forecast_retrospective_custody.py` (818497e4..) in newperiod-single-r2-persistence pins.json, newperiod-pre-r2-binding source-closure/pre_R2_implementation_binding, newperiod-complete-retention-execution(-r2) package-manifest, inference-packets prepare.py (`add()` asserts REPO file == pin) and every family inference pins.json; `scripts/forecast_campaign.py` (baseline/history/stable inference + inference packets), `scripts/forecast_newperiod_campaign.py` (frozen/learned inference), `scripts/forecast_h1_calibration.py` (h1 inference), `scripts/forecast_count_commitments.py` (count, not executable).
Effect: staging a source root from the CURRENT working tree fails every one of those pin checks. The already-built `revision-v2/*/source-package/source/**` trees still hold the OLD bytes and stay self-consistent.
Fix (no science change, keeps every pin and review valid): stage the pre-amendment blobs for these 6 paths: `git show baa869d9:<path>` (recipes, retrospective_custody) and the parent of 6bebfc7c for the four scripts. The only difference is the reviewer regex; none of those modules checks a reviewer on the G2/R2 path (recipe/retrospective review receipts are already frozen). Do NOT re-run inference-packets prepare.py from the working tree.

## Hard `codex` pin the amendment did NOT cover
`newperiod-complete-retention-execution-r2-astra-20261025/construction/common.py:46` and `newperiod-complete-label-execution-r4-retained-20261026/construction/common.py:46` (identical bytes, pinned 265179ef.. in their runner/job.py): `validate_authority` requires `reviewer_model=='codex'`. This blocks the G1 execution wrapper (draft/finalize) and the G4 r4 runner for a claude-sonnet-5-5 approval. Not fixable without breaking the pin. Bypass used here: G1 freeze runs retention.py draft/finalize directly (kernel unchanged), G4 runs bundle.py directly (chain/g4_labels.py). If root wants the wrappers, amend line 46 and re-pin COMMON_SHA in job.py plus runner PINS.
## Irrelevant leftovers
h1/h3 `reviewed_fit.py`/`reviewed_h3_fit.py` MODELS tuples (refits finished earlier), count `original_counts.py` REVIEWER regex (count34 not executable), tests/*.py still name old reviewers (not on the path).

## Update 09:30Z
Root reverted the amendment on the six pinned files (b9bc5467): pins hold again on the working tree; the codex pin in construction/common.py:46 is unchanged. R2 persistence runner accepts any non-empty reviewer_model (checked: runner.py authority + readiness + review).
