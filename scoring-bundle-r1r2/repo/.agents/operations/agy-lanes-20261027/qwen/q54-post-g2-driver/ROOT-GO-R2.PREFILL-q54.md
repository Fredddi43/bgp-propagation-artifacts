# ROOT-GO-R2 pre-fill values available TODAY (q54, 2026-10-28T21:3xZ — values read FROM ARTIFACTS, root re-verifies at write time)

| field | value | source |
|---|---|---|
| freeze.json sha256 (ORIGINAL) | `0164b1da3462affe180f900faa7a27f37b31da4d4af40b46f6b895be5b511127` | sha256sum on <BATCH_HOST> 21:2xZ |
| AMENDED freeze sha256 | `921fc9bb06888e39b2399735cd2bc673506116375b5be84ce16dfee59b33beaa` | `$R/amend/amended-freeze.json` — 345 executable arms, frozen_2025-sage-history-on-d30-s0 moved to retained_failures (q53 amend driver, evidence-backed); q28's sharded seal is pinned to THIS; root must choose which freeze ROOT-GO-R2 cites |
| G4 plan sha256 | `432f5381306ef71c7a8aff7b668a7b6a3c5d26a4c1f28fccbeb2233a02521d4f` | kernel-plan.json in `…/g4-four-scope-preparation-20261028/write-20261028T210542Z/` |
| G4 plan output path | `<CLUSTER_STORAGE>/…/data-custodian/complete-label-preparation-v3-retained/arms/000/attempt/output/labels.json` | plan.base.ordinary.output; file confirmed ABSENT (dir exists, labels.json does not) |
| extension decision | confirmed on cluster: sha `3f5bb81128769cb815ced7be05d83fba23be527d78f3f646696688d831d57dd7` (re-hashed byte-exact at refs step; extend=false end=2026-10-16) | `$L/occurrence-final-v1/sizing-binding-v6b/extension-decision.json` |
| R2 rehearsal passed at | Tier A complete: A1 fixture-eval PASS 7/7 (`$R0/logs/tierA1-fixture-eval-PASS-*.log`, sandbox `$R0/sb-fxA`), A3 evaluate-fixture PASS 5/5 on pinned bytes cf90e07d, stub-prepare PASS 1685 files; R0=`<CLUSTER_STORAGE>/…/<PROJECT>/q54-rehearsal-r0-20261028` | lane STATUS.md 20:4xZ entry |
| h3 reference availability ledgers | `$R/h3-reference-derived/availability-d30.json` sha `b034138bc4c1d7144f213c2a272efcc8bb83f7720713f9946e02a3b3c0cd03ab` (+ availability-d60.json) — 1289 rows, all input_seed_asns; derived by q28 h3ref.py | shape-verified vs build_r2_evidence |
| seal sha / arms, timing equivalence, arm-spec sha, signed review, R2 template sha, inventory files, spec path, access log, timestamps | NOT AVAILABLE YET — rows 14/16/17/20/21 | — |

## FINAL field values (2026-10-29T07:3xZ) — everything rows 14-16 produced
| field | value |
|---|---|
| seal.json sha256 | `8ede1a58a437559ea1fb5259edd60141e1a8312ae286a978e7e4554e19a6014f` |
| seal.receipt.json sha256 | `3c657bcefe012db5f4f4db1874ddc167cc2c768552e8e0f4e78d9f85e096871a` (arms 345) |
| seal path | `$R/g3-seal-sharded-20261029T013648Z/seal.json` |
| evidence bundle | `$R/r2-evidence-20261029T0525Z/` (8 family docs) |
| timing-label-equivalence | `d1a90c926aee49dcfa35119da00ec8c19cf8f96a7f642f61f2c08beca6e9ab8e` — equivalent TRUE (1124 events) |
| full-retention-review SIGNED-PACKET | `51087174367e4b0d7b1cb7a5a4ed7dcc2767cc0d3097ccea71f4e2a8d14ac761` |
| signed review | `fe36f5980c84be03e33d8d7d9d14d100f0ed66f006e38bdb457573334be51bbe` |
| h3 reference ledgers | d30 `b034138b…` (above), d60 `0c5c05d61eb285fe3405d2bf0f70c786d2bacf65cb208de2399ca990a481018f` |
| labels (row 19 pending) | output path per plan.base.ordinary.output; authority `approved:false` — root flip + ROOT-GO-R2 both required |
