# Redactions

The bundle is an anonymized copy. Identity markers were replaced by neutral placeholders in copies of the files; the originals were not changed. The literal patterns are kept with the private build tool and are not released, because they would themselves identify the authors. The rules below are applied one after another, in this order, so that the more specific rule (a full path, an e-mail address) is applied before the more general one (a name inside it).

## Rules

| Rule | What it replaces | Placeholder | Replacements |
|---|---|---|---|
| P01 | cluster path: forecasting root of the project storage | `<FORECAST_ROOT>` | 22,909,615 |
| P02 | cluster path: model storage root | `<MODELS_ROOT>` | 890,376 |
| P03 | cluster path: results storage root | `<RESULTS_ROOT>` | 17,419,694 |
| P04 | cluster path: NFS export of the storage | `<CLUSTER_EXPORT>` | 3 |
| P05 | cluster path: other storage mount, and its truncated fragments in interleaved log lines | `<CLUSTER_STORAGE>` | 6,436 |
| P06 | storage/project directory name, and its fragments in interleaved log lines | `<PROJECT_STORAGE>` | 6,435 |
| P07 | workstation path: repository checkout | `<REPO>` | 6,693 |
| P08 | home directory path | `<HOME>` | 38 |
| P09 | AI agent session scratch directory | `<AGENT_SCRATCH>` | 0 |
| P10 | AI agent temporary directory | `<AGENT_TMP>` | 11 |
| P11 | private project/repository name (it also names a public dataset of the author), and its fragments | `<PROJECT>` | 1,007,986 |
| E01 | e-mail address | `<EMAIL>` | 0 |
| N01 | cluster user name | `<USER>` | 18,475,280 |
| N02 | personal account name | `<USER>` | 2 |
| N03 | author name | `<AUTHOR>` | 0 |
| N04 | co-author name | `<COAUTHOR>` | 0 |
| N05 | author first name / workstation user name | `<AUTHOR>` | 25 |
| I01 | institution host name | `<INSTITUTION_HOST>` | 8 |
| I02 | institution domain | `<INSTITUTION_DOMAIN>` | 0 |
| I03 | institution gateway host | `<GATEWAY_HOST>` | 1 |
| I04 | institution name | `<INSTITUTION>` | 0 |
| I05 | institution city/region | `<LOCATION>` | 0 |
| H01 | cluster batch host name | `<BATCH_HOST>` | 845,861 |
| H02 | cluster submit host name | `<SUBMIT_HOST>` | 107 |
| H03 | personal workstation host name | `<WORKSTATION>` | 35 |
| H04 | cluster compute node name | `<COMPUTE_NODE>` | 17,629,756 |
| H05 | private network host name | `<TAILNET_HOST>` | 0 |
| H06 | cluster unix group | `<CLUSTER_GROUP>` | 1 |
| H07 | cluster gateway host (bare name) | `<GATEWAY_HOST>` | 1 |
| A01 | AI agent session identifier (UUID) | `<SESSION_ID>` | 492 |
| A02 | AI agent pane identifier | `<AGENT_PANE>` | 3 |
| A03 | AI agent tooling name | `<AGENT_TOOL>` | 5 |
| A04 | AI agent short session identifier | `<SESSION_ID>` | 129 |

Rule A04 keeps the word before the identifier (for example `session `) and replaces only the identifier.

## Binary files

4 pickles contained storage-root paths inside string values: `cluster/data-custodian/single-R2-v1/arms/000/rescore-secondary-D-A39/families/counts.pkl.part0000`, `cluster/data-custodian/single-R2-v1/arms/000/rescore-secondary-D-A39/families/membership-ordinary.pkl.part0000`, `cluster/data-custodian/single-R2-v1/arms/000/rescore-secondary-D-A39/families/stable.pkl.part0000`, `cluster/data-custodian/single-R2-v1/arms/000/rescore-stable-D-A40/stable-result-raw.pkl.part0000`. Only rules P01 to P03 and P11 were applied to them, as same-length byte replacements (the placeholder is padded with underscores to the original length), so each pickle still loads and every other byte is unchanged. The other 23 binary files hold no marker and are byte-identical to the originals.

## Effect on recorded hashes

Many records cite the SHA-256 of other files (seal, freeze, marker, receipts, family manifests, the R1 report's per-event digests, the deviation ledger). Those citations refer to the original bytes. Wherever redaction changed a file, `MANIFEST.json` keeps the original hash as `pre_redaction_sha256` (and `pre_redaction_bytes`) next to the hash of the released bytes, and its `hash_checks` show that the original bytes matched the cluster-side `sha256sum` and every recorded citation before redaction. The citations inside the records were left as written: a citation is verified against `pre_redaction_sha256`, not against the released bytes. Files without an entry for `pre_redaction_sha256` are byte-identical to the originals.

## Replacements per file

958 files changed. Counts per rule:

| File | Replacements by rule |
|---|---|
| `cluster/d-a39-lane-extract-20261101/out/extract-full.json` | P01 77, P03 5 |
| `cluster/d-a39-lane-extract-20261101/out/extract.log` | P01 1 |
| `cluster/d-a39-lane-extract-20261101/out/sha256-secondary-json.txt` | P01 1 |
| `cluster/d-a39-lane-extract-20261101/out/sha256-small.txt` | P01 23 |
| `cluster/d-a39-lane-extract-20261101/out/stable-narrow-v2.json` | P01 1 |
| `cluster/d-a39-lane-extract-20261101/out/stat.txt` | P01 28 |
| `cluster/d-a39-lane-extract-20261101/out/validate-explore.err` | P01 2 |
| `cluster/d-a39-lane-extract-20261101/out/validate-explore.jsonl` | P01 21 |
| `cluster/d-a39-lane-extract-20261101/out/validate-require-complete.err` | P01 2 |
| `cluster/d-a39-lane-extract-20261101/out/validate-require-complete.jsonl` | P01 21 |
| `cluster/d-a39-lane-extract-20261101/scripts/build_lanes.py` | H01 1, P01 3 |
| `cluster/d-a39-lane-extract-20261101/scripts/extract_lanes.py` | P01 1 |
| `cluster/d-a39-lane-extract-20261101/scripts/hash_families.sh` | P01 2 |
| `cluster/d-a39-lane-extract-20261101/scripts/probe_structure.py` | P01 1 |
| `cluster/d-a39-lane-extract-20261101/scripts/run_validator.sh` | P01 2 |
| `cluster/d-a39-lane-extract-20261101/scripts/stable_narrow.py` | P01 1 |
| `cluster/d-a39-lane-extract-20261101/scripts/validate_final_data.py` | P01 17, P03 1, P05 1 |
| `cluster/d-a40-lane-extract-20261101/out/completion.json` | P01 2 |
| `cluster/d-a40-lane-extract-20261101/out/extract-full.json` | P01 77, P03 5 |
| `cluster/d-a40-lane-extract-20261101/out/extract-stable-d40.json` | P01 15 |
| `cluster/d-a40-lane-extract-20261101/out/extract-stable-d40.log` | P01 1 |
| `cluster/d-a40-lane-extract-20261101/out/newperiod-lanes.json` | P01 14 |
| `cluster/d-a40-lane-extract-20261101/out/newperiod-lanes.tex` | P01 1 |
| `cluster/d-a40-lane-extract-20261101/out/r2-d-a39-v2-52728251.out` | P01 39 |
| `cluster/d-a40-lane-extract-20261101/out/sha256-small.txt` | P01 23 |
| `cluster/d-a40-lane-extract-20261101/out/stable-narrow-v2.json` | P01 1 |
| `cluster/d-a40-lane-extract-20261101/out/stat.txt` | P01 28 |
| `cluster/d-a40-lane-extract-20261101/out/validate-explore.jsonl` | P01 21 |
| `cluster/d-a40-lane-extract-20261101/out/validate-require-complete.jsonl` | P01 21 |
| `cluster/d-a40-lane-extract-20261101/scripts/build_lanes.py` | H01 1, P01 3 |
| `cluster/d-a40-lane-extract-20261101/scripts/extract_lanes.py` | P01 1 |
| `cluster/d-a40-lane-extract-20261101/scripts/extract_stable_d40.py` | P01 1 |
| `cluster/d-a40-lane-extract-20261101/scripts/stable_narrow.py` | P01 1 |
| `cluster/data-custodian/complete-label-preparation-v3-retained/arms/000/attempt/output/labels.g4-receipt.json` | P01 1 |
| `cluster/data-custodian/complete-label-preparation-v3-retained/arms/000/attempt/output/labels.json` | P01 606,710 |
| `cluster/data-custodian/g1-freeze-20261028T184148Z/freeze.json` | H01 80, P01 5,376, P03 13, P07 1,266 |
| `cluster/data-custodian/newperiod-identification-v1/access-log.jsonl` | H01 845,357, H04 17,629,711, N01 18,475,067, P01 21,916,078, P02 890,322, P03 17,419,498, P05 6,355, P06 6,424, P07 8, P08 22, P11 1,007,812 |
| `cluster/data-custodian/single-R2-v1/arms/000/attempt/intent.json` | P01 2 |
| `cluster/data-custodian/single-R2-v1/arms/000/attempt/primary-scores.json` | P01 6 |
| `cluster/data-custodian/single-R2-v1/arms/000/attempt/primary.json` | P01 1 |
| `cluster/data-custodian/single-R2-v1/arms/000/rescore-secondary-D-A39/completion.json` | P01 2 |
| `cluster/data-custodian/single-R2-v1/arms/000/rescore-secondary-D-A39/families/counts.pkl.part0000` | P01 34 |
| `cluster/data-custodian/single-R2-v1/arms/000/rescore-secondary-D-A39/families/membership-ordinary.pkl.part0000` | P01 40 |
| `cluster/data-custodian/single-R2-v1/arms/000/rescore-secondary-D-A39/families/stable.pkl.part0000` | P01 2, P03 5 |
| `cluster/data-custodian/single-R2-v1/arms/000/rescore-secondary-D-A39/intent.json` | P01 5 |
| `cluster/data-custodian/single-R2-v1/arms/000/rescore-secondary-D-A39/primary-recomputed-D-A39.json` | P01 1 |
| `cluster/data-custodian/single-R2-v1/arms/000/rescore-secondary-D-A39/primary-scores.json` | P01 6 |
| `cluster/data-custodian/single-R2-v1/arms/000/rescore-secondary-D-A39/second-label-read-D-A39.json` | P01 2 |
| `cluster/data-custodian/single-R2-v1/arms/000/rescore-stable-D-A40/completion.json` | P01 2 |
| `cluster/data-custodian/single-R2-v1/arms/000/rescore-stable-D-A40/done.json` | P01 3 |
| `cluster/data-custodian/single-R2-v1/arms/000/rescore-stable-D-A40/intent.json` | P01 7 |
| `cluster/data-custodian/single-R2-v1/arms/000/rescore-stable-D-A40/primary-recomputed-D-A40.json` | P01 1 |
| `cluster/data-custodian/single-R2-v1/arms/000/rescore-stable-D-A40/primary-scores.json` | P01 6 |
| `cluster/data-custodian/single-R2-v1/arms/000/rescore-stable-D-A40/stable-result-raw.pkl.part0000` | P01 1 |
| `cluster/data-custodian/single-R2-v1/arms/000/rescore-stable-D-A40/stable-result.json` | P01 49, P03 1 |
| `cluster/data-custodian/single-R2-v1/arms/000/rescore-stable-D-A40/third-label-read-D-A40.json` | P01 2 |
| `cluster/newperiod-g2-inference-v1-20261027/amend/amended-freeze.json` | H01 80, P01 5,370, P03 13, P07 1,265 |
| `cluster/newperiod-g2-inference-v1-20261027/amend/unblinded-8ede1a58a437559ea1fb5259edd60141e1a8312ae286a978e7e4554e19a6014f.json` | P01 2 |
| `cluster/newperiod-g2-inference-v1-20261027/g3-seal-sharded-20261029T013648Z/seal.json` | P01 1 |
| `cluster/newperiod-g2-inference-v1-20261027/g3-seal-sharded-20261029T013648Z/seal.receipt.json` | P01 2 |
| `cluster/newperiod-g2-inference-v1-20261027/r2-evidence-20261030T0440Z/evidence-baseline.json` | P01 6 |
| `cluster/newperiod-g2-inference-v1-20261027/r2-evidence-20261030T0440Z/evidence-h1.json` | P01 6 |
| `cluster/newperiod-g2-inference-v1-20261027/r2-evidence-20261030T0440Z/evidence-h3.json` | P01 6 |
| `cluster/newperiod-g2-inference-v1-20261027/r2-evidence-20261030T0440Z/evidence-history.json` | P01 6 |
| `cluster/newperiod-g2-inference-v1-20261027/r2-evidence-20261030T0440Z/evidence-ordinary.json` | P01 6 |
| `cluster/newperiod-g2-inference-v1-20261027/r2-evidence-20261030T0440Z/evidence-origin.json` | P01 7 |
| `cluster/newperiod-g2-inference-v1-20261027/r2-evidence-20261030T0440Z/evidence-stable.json` | P01 5 |
| `cluster/newperiod-g2-inference-v1-20261027/r2-evidence-20261030T0440Z/evidence-timing.json` | P01 6 |
| `cluster/newperiod-g2-inference-v1-20261027/r2-evidence-20261030T0440Z/full-retention-review.DRAFT.json` | P01 19 |
| `cluster/newperiod-g2-inference-v1-20261027/r2-evidence-20261030T0440Z/full-retention-review.SIGNED-PACKET.json` | P01 19 |
| `cluster/newperiod-g2-inference-v1-20261027/r2-evidence-20261030T0440Z/full-retention-review.json` | P01 19 |
| `cluster/newperiod-g2-inference-v1-20261027/r2-rescore-D-A39-approval/APPROVAL-D-A39.json` | A01 1, N05 2, P01 2 |
| `cluster/newperiod-g2-inference-v1-20261027/r2-rescore-D-A39-dry-run-52725204/records-dry-run/done.json` | P01 1 |
| `cluster/newperiod-g2-inference-v1-20261027/r2-rescore-D-A39-dry-run-52725204/records-dry-run/intent.json` | P01 4 |
| `cluster/newperiod-g2-inference-v1-20261027/r2-rescore-D-A39-dry-run-52725204/records-dry-run/ready.json` | H04 1, P01 83, P03 14 |
| `cluster/newperiod-g2-inference-v1-20261027/r2-rescore-D-A39-logs/r2-d-a39-v2-52725204.out` | P01 43 |
| `cluster/newperiod-g2-inference-v1-20261027/r2-rescore-D-A39-logs/r2-d-a39-v2-52728251.err` | P01 3, P03 13 |
| `cluster/newperiod-g2-inference-v1-20261027/r2-rescore-D-A39-logs/r2-d-a39-v2-52728251.out` | P01 39 |
| `cluster/newperiod-g2-inference-v1-20261027/r2-rescore-D-A40-approval/APPROVAL-D-A40.json` | A01 1, N05 2, P01 2 |
| `cluster/newperiod-g2-inference-v1-20261027/r2-rescore-D-A40-dry-run-52748137/records-dry-run/done.json` | P01 1 |
| `cluster/newperiod-g2-inference-v1-20261027/r2-rescore-D-A40-dry-run-52748137/records-dry-run/intent.json` | P01 6 |
| `cluster/newperiod-g2-inference-v1-20261027/r2-rescore-D-A40-dry-run-52748137/records-dry-run/ready.json` | H04 1, P01 82, P03 17 |
| `cluster/newperiod-g2-inference-v1-20261027/r2-rescore-D-A40-logs/r2-d-a40-52748137.out` | P01 40 |
| `cluster/newperiod-g2-inference-v1-20261027/r2-rescore-D-A40-logs/r2-d-a40-52750274.out` | P01 42 |
| `cluster/newperiod-g2-inference-v1-20261027/r2-run-20261030-a17/r2-exec-spec.json` | P01 328,857, P03 23, P11 1 |
| `cluster/occurrence-final-v1/custody/r1-access/r1-access.log` | P01 1 |
| `cluster/occurrence-final-v1/custody/r1-access/r1-seal-134d74fb72dd8d4940adb52bb0bdc11d0f7948cfad0560324275d711a219f887.json` | H01 24, P01 6,163 |
| `cluster/occurrence-final-v1/custody/r1-access/r1-unblinding.json` | P01 1 |
| `cluster/occurrence-final-v1/manifests/training-integration-v6b-both.json` | H01 1, P01 19,322, P02 19, P03 1, P11 20 |
| `cluster/occurrence-final-v1/source-audit-v5/source-audit.json` | P01 34 |
| `cluster/r1-rank-sidecar-20261101/README.md` | H02 1 |
| `cluster/r1-rank-sidecar-20261101/build/build_sidecar-d3b2fdbe.py` | P01 1 |
| `cluster/r1-rank-sidecar-20261101/build/build_sidecar.py` | P01 1 |
| `cluster/r1-rank-sidecar-20261101/build/compare_runs.py` | P01 1 |
| `cluster/r1-rank-sidecar-20261101/build/inventory.py` | P01 2 |
| `cluster/r1-rank-sidecar-20261101/build/merge.sbatch` | P01 2, P03 1, P11 1 |
| `cluster/r1-rank-sidecar-20261101/build/replay.sbatch` | P01 2, P03 1, P11 1 |
| `cluster/r1-rank-sidecar-20261101/sidecar/MANIFEST.json` | P01 1 |
| `cluster/r1-release-parallel-v11-20261024/control-v1/complete.json` | P01 1 |
| `cluster/r1-release-parallel-v11-20261024/control-v1/derived/evaluation/ledger.json` | P01 3,200 |
| `cluster/r1-release-parallel-v11-20261024/control-v1/derived/evaluation/r1-authorization.json` | P01 9 |
| `cluster/r1-release-parallel-v11-20261024/control-v1/release-native-v2/publication-approval.json` | A01 2, P01 1, P07 2 |
| `cluster/r1-release-parallel-v11-20261024/control-v1/release-native-v2/r1-release.json` | P01 13, P07 6 |
| `cluster/r1-release-parallel-v11-20261024/control-v1/source-manifest.json` | P01 1 |
| `repo/.agents/operations/agy-lanes-20261027/REVIEW-QUEUE.md` | H01 4, P01 1, P03 1, P08 1, P11 1 |
| `repo/.agents/operations/agy-lanes-20261027/g1/REVIEW-QUEUE.md` | P07 4 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/G2-DESIGN.md` | H01 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/R2-RUNBOOK.md` | H01 3, H02 3, P10 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/REVIEW-h1-runner-successor.json` | P07 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/ROOT-GO-G2.txt` | P01 2, P02 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/ROOT-GO-R2.txt` | P01 2 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/chain-d39-v2/build_r2_template.py` | P01 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/chain-d39-v2/common.py` | P01 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/chain-d39-v2/g3_seal_parallel.py` | H01 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/chain-d39-v2/g4_labels.py` | P01 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/chain-d39-v2/r2_float32_offline.sbatch` | P01 3, P03 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/chain-d39-v2/r2_plan.py` | P01 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/chain-d39-v2/r2_rescore_secondary.py` | N05 1, P01 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/chain-d39-v2/r2_rescore_secondary.sbatch` | P01 3, P03 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/chain-d39-v2/seal_array.sbatch.generated` | P01 4, P03 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/chain-d39-v2/test_r2_rescore_binding.py` | P05 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/chain-d39-v2/test_r2_rescore_secondary.py` | P05 5, P10 2 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/chain-d40/README.md` | N05 1, P01 4, P03 3, P07 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/chain-d40/build_r2_template.py` | P01 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/chain-d40/common.py` | P01 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/chain-d40/g3_seal_parallel.py` | H01 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/chain-d40/g4_labels.py` | P01 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/chain-d40/r2_float32_offline.sbatch` | P01 3, P03 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/chain-d40/r2_plan.py` | P01 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/chain-d40/r2_rescore_stable.py` | N05 1, P01 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/chain-d40/r2_rescore_stable.sbatch` | P01 3, P03 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/chain-d40/r2_stable_not_scorable.py` | N05 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/chain-d40/seal_array.sbatch.generated` | P01 4, P03 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/chain-d40/test_r2_rescore_stable.py` | P05 5 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/chain-d40/test_r2_rescore_stable_binding.py` | P05 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/chain/build_r2_template.py` | P01 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/chain/common.py` | P01 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/chain/g3_seal_parallel.py` | H01 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/chain/g4_labels.py` | P01 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/chain/r2_float32_offline.sbatch` | P01 3, P03 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/chain/r2_plan.py` | P01 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/chain/r2_rescore_secondary.py` | N05 1, P01 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/chain/r2_rescore_secondary.sbatch` | P01 3, P03 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/chain/seal_array.sbatch.generated` | P01 4, P03 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/g2/check_e5_g2.py` | H01 2, P05 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/g2/fill_e5_admission.py` | H01 2, P01 1, P05 1, P07 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/g2/freeze_day_chain.sh` | H01 1, P01 1, P05 1, P07 1, P10 2 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/g2/g2_submit.py` | H01 1, H02 1, P10 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/g2/monitor_g2.sh` | H01 2, P01 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/g2/precheck_cluster.py` | H01 4, P01 1, P05 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/g2/precheck_h1_v2.py` | H01 2 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/g2/prestage_g2.sh` | H01 4, P01 1, P02 1, P05 2, P07 1, P10 1, P11 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/g2/stage_source.py` | H01 1 |
| `repo/.agents/operations/agy-lanes-20261027/g2r2/g2/submit_all_g2.sh` | H01 2, H02 3, P01 1, P05 1, P07 1, P10 2 |
| `repo/.agents/operations/agy-lanes-20261027/h3p-mixed7/REVIEW-QUEUE.md` | H01 1, P01 1 |
| `repo/.agents/operations/agy-lanes-20261027/origin-fits/REVIEW-ORIGIN-DISCLOSURE-COUNTS-P7.json` | P07 1 |
| `repo/.agents/operations/agy-lanes-20261027/origin-fits/REVIEW-QUEUE.md` | H01 3, P01 1, P07 5 |
| `repo/.agents/operations/agy-lanes-20261027/qwen/q11-deviations/DEVIATIONS-LEDGER.md` | A02 2, H01 9, H02 1, H04 5, N05 8, P02 1, P03 1, P05 1, P10 2, P11 2 |
| `repo/.agents/operations/agy-lanes-20261027/qwen/q27-origin-export/stage/v2/root-signed-v2-review.json` | P01 7, P07 16 |
| `repo/.agents/operations/agy-lanes-20261027/qwen/q29-tr2-v6/review-probe.DRAFT.PENDING_ROOT.json` | A01 1, P07 6 |
| `repo/.agents/operations/agy-lanes-20261027/qwen/q36-prestage/REVIEW-VERDICT.md` | H01 1, P05 1, P08 1 |
| `repo/.agents/operations/agy-lanes-20261027/qwen/q36-prestage/root-files/ROOT-GO-G2.txt.template` | H01 1, P01 2, P02 1 |
| `repo/.agents/operations/agy-lanes-20261027/qwen/q36-prestage/root-files/ROOT-GO-R2.txt.template` | P01 2, P05 1, P08 1 |
| `repo/.agents/operations/agy-lanes-20261027/qwen/q37-equiv-gate/REVIEW-VERDICT.md` | H01 1 |
| `repo/.agents/operations/agy-lanes-20261027/qwen/q38-parallel-assemble/REVIEW-VERDICT.md` | H01 1, P05 1 |
| `repo/.agents/operations/agy-lanes-20261027/qwen/q43-storage-exec/ROOT-GO-STORAGE-1.txt` | N05 2, P11 1 |
| `repo/.agents/operations/agy-lanes-20261027/qwen/q43-storage-exec/ROOT-GO-STORAGE-2.txt` | H02 1, N05 1 |
| `repo/.agents/operations/agy-lanes-20261027/qwen/q52-capture-fill/REVIEW-QUEUE.md` | H01 1, P03 1, P11 1 |
| `repo/.agents/operations/agy-lanes-20261027/qwen/q54-post-g2-driver/REVIEW-QUEUE.md` | H01 1 |
| `repo/.agents/operations/agy-lanes-20261027/qwen/q54-post-g2-driver/ROOT-GO-R2.PREFILL-q54.md` | H01 1, P05 2, P11 1 |
| `repo/.agents/operations/agy-lanes-20261027/storage/ROOT-GO-DELETE.txt` | N05 1, P02 1, P11 1 |
| `repo/.agents/operations/agy-lanes-20261027/t-d300/REVIEW-QUEUE.md` | H04 2, P02 1, P07 21 |
| `repo/.agents/operations/agy-lanes-20261027/t-d300/REVIEWER-storage-d300-wave1-v4-flock-resolved.json` | H04 6, I01 1, P02 1, P04 1, P07 3 |
| `repo/.agents/operations/agy-lanes-20261027/t-d300/reviews/REVIEW-assemble-allocation_premise.json` | P01 1, P07 1 |
| `repo/.agents/operations/agy-lanes-20261027/t-d300/reviews/REVIEW-assemble-stage_science.json` | P01 1, P07 1 |
| `repo/.agents/operations/agy-lanes-20261027/t-d300/reviews/REVIEW-audit-allocation_premise.json` | P01 1, P07 1 |
| `repo/.agents/operations/agy-lanes-20261027/t-d300/reviews/REVIEW-audit-stage_science.json` | P01 1, P07 1 |
| `repo/.agents/operations/agy-lanes-20261027/t-d300/reviews/REVIEW-continuation_wave1-allocation_premise.json` | P01 1, P07 1 |
| `repo/.agents/operations/agy-lanes-20261027/t-d300/reviews/REVIEW-continuation_wave1-stage_science.json` | P01 1, P07 1 |
| `repo/.agents/operations/agy-lanes-20261027/t-d300/reviews/REVIEW-continuation_wave2-allocation_premise.json` | P01 1, P07 1 |
| `repo/.agents/operations/agy-lanes-20261027/t-d300/reviews/REVIEW-continuation_wave2-stage_science.json` | P01 1, P07 1 |
| `repo/.agents/operations/agy-lanes-20261027/t-d300/reviews/REVIEW-d300final-allocation_premise.json` | P01 1, P07 1 |
| `repo/.agents/operations/agy-lanes-20261027/t-d300/reviews/REVIEW-d300final-stage_science.json` | P01 1, P07 1 |
| `repo/.agents/operations/agy-lanes-20261027/t-d900/reviews/REVIEW-d900assemble-allocation_premise.json` | P01 1, P07 1 |
| `repo/.agents/operations/agy-lanes-20261027/t-d900/reviews/REVIEW-d900assemble-stage_science.json` | P01 1, P07 1 |
| `repo/.agents/operations/agy-lanes-20261027/t-d900/reviews/REVIEW-d900audit-allocation_premise.json` | P01 1, P07 1 |
| `repo/.agents/operations/agy-lanes-20261027/t-d900/reviews/REVIEW-d900audit-stage_science.json` | P01 1, P07 1 |
| `repo/.agents/operations/agy-lanes-20261027/t-d900/reviews/REVIEW-d900build-allocation_premise.json` | P01 1, P07 1 |
| `repo/.agents/operations/agy-lanes-20261027/t-d900/reviews/REVIEW-d900build-stage_science.json` | P01 1, P07 1 |
| `repo/.agents/operations/agy-lanes-20261027/t-d900/reviews/REVIEW-d900final-allocation_premise.json` | P01 1, P07 1 |
| `repo/.agents/operations/agy-lanes-20261027/t-d900/reviews/REVIEW-d900final-stage_science.json` | P01 1, P07 1 |
| `repo/.agents/operations/newperiod-complete-label-execution-r3-astra-20261025/review-ready.json` | P07 2 |
| `repo/.agents/operations/newperiod-complete-retention-execution-r2-astra-20261025/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-core-calibration-consumer-binding-astra-v1-20261025/review-ready.json` | A01 1, P07 1 |
| `repo/.agents/operations/newperiod-core-calibration-execution-r3-20261025/review-ready.json` | A01 1 |
| `repo/.agents/operations/newperiod-core-calibration-execution-r4-20261025/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-core-calibration-phaseB-operator-v1-20261025/REVIEW.md` | N01 1 |
| `repo/.agents/operations/newperiod-core-calibration-preload-capture-astra-v1-v36-20261025/review-ready.json` | P07 6 |
| `repo/.agents/operations/newperiod-core-calibration-preload-source-astra-v1-20261025/review-request.json` | A01 1, P07 8 |
| `repo/.agents/operations/newperiod-core-campaign-membership-local-once-astra-v1-20261026/review-ready.json` | A01 1, P07 9 |
| `repo/.agents/operations/newperiod-core-chain/v3/review-request.json` | P07 1 |
| `repo/.agents/operations/newperiod-core-e5-freeze-check-astra-v1-20261025/REVIEW.md` | P01 1 |
| `repo/.agents/operations/newperiod-core-immediate-launch-20261024/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-core-immediate-launch-20261024/review-request.json` | P01 12, P03 1, P07 5, P11 1 |
| `repo/.agents/operations/newperiod-core-label-preconditions-v3-20261025/REVIEW.json` | P07 5 |
| `repo/.agents/operations/newperiod-core-label-preconditions-v4-20261025/REVIEW.json` | P07 5 |
| `repo/.agents/operations/newperiod-core-local-metadata-once-astra-v1-20261026/review-ready.json` | P07 8 |
| `repo/.agents/operations/newperiod-core-output-size-probe-20261024/root-remaining-wave2-storage-review.json` | P07 1 |
| `repo/.agents/operations/newperiod-core-remote-metadata-binding-astra-v1-v36-20261026/review-ready.json` | P07 19 |
| `repo/.agents/operations/newperiod-core-remote-metadata-binding-astra-v2-v36-20261026/review-ready.json` | P07 23 |
| `repo/.agents/operations/newperiod-core-remote-metadata-once-astra-v1-20261026/REVIEW.md` | H01 1 |
| `repo/.agents/operations/newperiod-core-remote-metadata-once-astra-v1-20261026/review-ready.json` | P07 18 |
| `repo/.agents/operations/newperiod-core-remote-metadata-once-astra-v3-20261026/review-ready.json` | A01 1, P07 21 |
| `repo/.agents/operations/newperiod-core-remote49-execution-astra-v3-20261026/review-ready.json` | P07 6 |
| `repo/.agents/operations/newperiod-core-typed-local-once-astra-v1-20261026/REVIEW.md` | A01 1 |
| `repo/.agents/operations/newperiod-core-typed-local-once-astra-v1-20261026/review-ready.json` | P07 10 |
| `repo/.agents/operations/newperiod-core-typed-local-projection-astra-v1-20261026/review-ready.json` | P07 4 |
| `repo/.agents/operations/newperiod-core-typed-local-projection-astra-v1-20261026/review-request.json` | P07 2 |
| `repo/.agents/operations/newperiod-count-native-bridge-20261024/root-code-actual-review.json` | A01 1 |
| `repo/.agents/operations/newperiod-count-native-metadata-20261021/REVIEW.md` | P02 1, P11 1 |
| `repo/.agents/operations/newperiod-count-native-metadata-20261021/revision-v1/REVIEW.md` | P02 1, P11 1 |
| `repo/.agents/operations/newperiod-count-window-recovery-plan-20261024/review-readiness.json` | A01 1, H01 1, P07 1 |
| `repo/.agents/operations/newperiod-counts-chronos-20261020/review-request.json` | P07 3 |
| `repo/.agents/operations/newperiod-current-day-equivalence-20261023/REVIEW.md` | H04 1 |
| `repo/.agents/operations/newperiod-current-day-equivalence-20261023/outcome-v1/REVIEW.md` | A03 1, H02 1 |
| `repo/.agents/operations/newperiod-custodian-count-truth-20261023/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-dev-chain-tools-20261025/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-development-scratch-fix-20261023/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-family-history-stage-r2-binding-20261024/review-ready.json` | A01 1 |
| `repo/.agents/operations/newperiod-family-history-stage-r2-launch-20261024/review-ready.json` | A01 1 |
| `repo/.agents/operations/newperiod-family-history-stage-r3-20261024/review-ready.json` | A01 1 |
| `repo/.agents/operations/newperiod-family-history-stage-r3-20261024/root-review-response.json` | P07 2 |
| `repo/.agents/operations/newperiod-family-history-stage-r3-binding-20261024/review-ready.json` | A01 1 |
| `repo/.agents/operations/newperiod-family-history-stage-r3-launch-20261024/receipt-audit-v1/review-ready.json` | A01 1 |
| `repo/.agents/operations/newperiod-family-history-stage-r3-launch-20261024/receipt-reader-v1/review-ready.json` | H01 1 |
| `repo/.agents/operations/newperiod-family-history-stage-r3-launch-20261024/review-ready.json` | A01 1 |
| `repo/.agents/operations/newperiod-family-inference-transport-20261023/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-family-replay-stage-20261024/actual-finalize-v1/diagnostic-v1/review-ready.json` | A01 1, H01 1 |
| `repo/.agents/operations/newperiod-family-replay-stage-20261024/actual-finalize-v1/diagnostic-v2-schema/review-ready.json` | A01 1, H01 1, P01 1 |
| `repo/.agents/operations/newperiod-family-replay-stage-20261024/actual-finalize-v1/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-family-replay-stage-20261024/finalize-r2/review-ready-successor.json` | A01 1, H01 1 |
| `repo/.agents/operations/newperiod-family-replay-stage-20261024/finalize-r2/review-ready.json` | A01 1 |
| `repo/.agents/operations/newperiod-family-resource-probe-20261023/REVIEW.md` | H01 1 |
| `repo/.agents/operations/newperiod-family-source-probe-20261023/REVIEW.md` | H01 1 |
| `repo/.agents/operations/newperiod-feature7-rexact-recovery-20261024/core-c1/placement-manifest-capture-v1/review-ready.json` | H01 1 |
| `repo/.agents/operations/newperiod-feature7-rexact-recovery-20261024/review-ready.json` | A01 1 |
| `repo/.agents/operations/newperiod-feature7-rexact-recovery-20261024/rexact-v2/review-ready-terminal-and-diagnostic.json` | H01 2, I01 1 |
| `repo/.agents/operations/newperiod-feature7-rexact-recovery-20261024/rexact-v2/review-ready-tools.json` | A01 1 |
| `repo/.agents/operations/newperiod-feature7-rexact-recovery-20261024/rexact-v2/review-ready-trace-diagnostic-v2.json` | H01 1, I01 1 |
| `repo/.agents/operations/newperiod-feature7-rexact-recovery-20261024/rexact-v2/review-ready.json` | A01 1, P07 1 |
| `repo/.agents/operations/newperiod-feature7-rexact-recovery-20261024/rexact-v3/gate-phase-core-v2/review-ready.json` | P07 2 |
| `repo/.agents/operations/newperiod-feature7-rexact-recovery-20261024/rexact-v3/gate-phase-core/core-gate/review-ready.json` | A02 1, A04 1, H01 2, P07 1 |
| `repo/.agents/operations/newperiod-feature7-rexact-recovery-20261024/rexact-v3/gate-phase-temporal-execution-v1/t2-fetch-candidate-v1/review-ready.json` | H01 1, P07 1 |
| `repo/.agents/operations/newperiod-feature7-rexact-recovery-20261024/rexact-v3/gate-phase-temporal/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-feature7-rexact-recovery-20261024/rexact-v3/review-ready-binder-b-v3-r2.json` | H01 1, I01 1 |
| `repo/.agents/operations/newperiod-feature7-rexact-recovery-20261024/temporal-v2/postimage-diagnostic-v1/review-ready.json` | A01 1, H01 1, P05 2 |
| `repo/.agents/operations/newperiod-feature7-rexact-recovery-20261024/temporal-v2/postimage-diagnostic-v2-symlinks/review-ready.json` | A01 1, H01 1 |
| `repo/.agents/operations/newperiod-feature7-source-diagnosis-20261024/comparison-candidate-v1/review-ready.json` | P07 3 |
| `repo/.agents/operations/newperiod-feature7-source-diagnosis-20261024/comparison-exact-v2/review-ready.json` | P07 4 |
| `repo/.agents/operations/newperiod-final-chain-preparation-astra-g1a-v1-20261026/REVIEW.md` | A01 1 |
| `repo/.agents/operations/newperiod-final-chain-preparation-astra-g1a-v1-20261026/review-ready.json` | A01 1, P07 1 |
| `repo/.agents/operations/newperiod-final-parsed-owner-rules-v1-20261026/review-ready.json` | P07 4 |
| `repo/.agents/operations/newperiod-g1-count34-evidence-staging-sonnet-v1-20261027/REVIEW.md` | H01 2, P05 1, P08 1 |
| `repo/.agents/operations/newperiod-g1-count34-opus-science-v1-20261026/review-schema.UNSIGNED.json` | P07 2 |
| `repo/.agents/operations/newperiod-g1-custody-bindings-sonnet-v2-20261027/REVIEW.md` | P05 1 |
| `repo/.agents/operations/newperiod-g1-custody-bindings-sonnet-v3-20261027/REVIEW.md` | P05 1 |
| `repo/.agents/operations/newperiod-g1-ordinary12-fit-provenance-sonnet-v2-20261027/REVIEW.md` | P03 1 |
| `repo/.agents/operations/newperiod-g1-ordinary12-fit-provenance-sonnet-v3-20261027/REVIEW.md` | P03 1 |
| `repo/.agents/operations/newperiod-g1-ordinary12-fit-provenance-sonnet-v4-20261027/REVIEW.md` | P03 1, P11 1 |
| `repo/.agents/operations/newperiod-g1a-certification-execution-successors-v1-20261026/REVIEW.md` | P05 1 |
| `repo/.agents/operations/newperiod-g1a-certification-execution-successors-v1-20261026/review-ready.json` | P07 40 |
| `repo/.agents/operations/newperiod-g1a-parsed-a2-owner-response-v1-20261026/review-ready.json` | P07 4 |
| `repo/.agents/operations/newperiod-g1b-count-stage-v1-20261026/REVIEW.md` | H01 1, P05 1 |
| `repo/.agents/operations/newperiod-g1b-count-stage-v1-20261026/review-ready.json` | P05 1, P07 10 |
| `repo/.agents/operations/newperiod-g1b-count-stage-v1-20261026/review-schema.UNSIGNED.json` | P07 2 |
| `repo/.agents/operations/newperiod-g1b-family-packets-v1-20261026/review-ready.json` | P07 12 |
| `repo/.agents/operations/newperiod-g1b-next-steps-v1-20261026/review-ready.json` | P07 14 |
| `repo/.agents/operations/newperiod-g4-four-scope-preparation-astra-v1-20261026/review-ready.json` | P07 10 |
| `repo/.agents/operations/newperiod-gate-host-readiness-20261022/REVIEW.md` | A04 1, H01 5, N01 3, P03 7, P04 2, P11 6 |
| `repo/.agents/operations/newperiod-gate-host-readiness-20261022/attempt3-diagnosis-r2/REVIEW.md` | A04 1 |
| `repo/.agents/operations/newperiod-gate-host-readiness-20261022/attempt3-diagnosis/coordination/review-ready.json` | A01 1 |
| `repo/.agents/operations/newperiod-gate-host-readiness-20261022/attempt3-probe-r2/REVIEW.md` | A04 1, H01 1, P03 2, P05 2, P06 1, P11 1 |
| `repo/.agents/operations/newperiod-gate-host-readiness-20261022/attempt3-probe-r2/coordination/review-ready.json` | P03 1, P11 1 |
| `repo/.agents/operations/newperiod-gate-host-readiness-20261022/attempt3-probe-r3/REVIEW.md` | A04 1 |
| `repo/.agents/operations/newperiod-gate-host-readiness-20261022/attempt3-probe-r3/coordination/review-ready.json` | P03 1, P11 1 |
| `repo/.agents/operations/newperiod-gate-host-readiness-20261022/attempt3-probe-r4/REVIEW.md` | A04 1, H06 1, P03 1, P05 1, P11 1 |
| `repo/.agents/operations/newperiod-gate-host-readiness-20261022/attempt3-probe-r4/coordination/review-ready.json` | P03 1, P11 1 |
| `repo/.agents/operations/newperiod-gate-host-readiness-20261022/attempt3-probe/REVIEW.md` | A04 1 |
| `repo/.agents/operations/newperiod-gate-host-readiness-20261022/attempt4-candidate-r2/REVIEW-READY.json` | A01 2 |
| `repo/.agents/operations/newperiod-gate-host-readiness-20261022/attempt4-candidate-r2/REVIEW.md` | A04 1, H01 1, P05 1 |
| `repo/.agents/operations/newperiod-gate-host-readiness-20261022/attempt4-candidate/REVIEW-READY.json` | A01 2, H01 1 |
| `repo/.agents/operations/newperiod-gate-host-readiness-20261022/attempt4-candidate/REVIEW.md` | A04 1, H01 1, P05 1 |
| `repo/.agents/operations/newperiod-gate-host-readiness-20261022/coordination/review-ready.json` | A01 2 |
| `repo/.agents/operations/newperiod-gate-host-readiness-20261022/revision-v2/REVIEW.md` | A04 1, P01 1, P03 3, P11 4 |
| `repo/.agents/operations/newperiod-gate-host-readiness-20261022/revision-v2/coordination/review-ready.json` | A01 2 |
| `repo/.agents/operations/newperiod-gate-host-readiness-20261022/revision-v3-round2/REVIEW.md` | A04 1 |
| `repo/.agents/operations/newperiod-gate-host-readiness-20261022/revision-v3-round2/coordination/review-ready.json` | A01 1 |
| `repo/.agents/operations/newperiod-gate-host-readiness-20261022/revision-v3/REVIEW.md` | A04 1, P03 2, P11 2 |
| `repo/.agents/operations/newperiod-gate-host-readiness-20261022/revision-v3/coordination/review-ready.json` | A01 1 |
| `repo/.agents/operations/newperiod-gate-host-readiness-20261022/runtime-capture-v1/REVIEW.md` | A04 1, H01 1, N01 1, P03 2, P07 1, P11 1 |
| `repo/.agents/operations/newperiod-gate-host-readiness-20261022/runtime-capture-v1/coordination/review-ready.json` | A01 1 |
| `repo/.agents/operations/newperiod-gate-isolated-runtime-20261023/REVIEW.md` | P03 1, P11 1 |
| `repo/.agents/operations/newperiod-gate-isolated-runtime-20261023/execution-v1/payload/newperiod-gate-private-v1/repo/.agents/operations/newperiod-input-gate-20261021/revision-v5/REVIEW-READY.json` | A01 2 |
| `repo/.agents/operations/newperiod-gate-isolated-runtime-20261023/execution-v1/payload/newperiod-gate-private-v1/repo/.agents/operations/newperiod-input-gate-20261021/revision-v5/REVIEW.md` | A04 1 |
| `repo/.agents/operations/newperiod-gate-launch-20261022/REVIEW.md` | A04 1, H01 1, N01 1 |
| `repo/.agents/operations/newperiod-gate-launch-20261022/coordination/review-ready.json` | A01 2 |
| `repo/.agents/operations/newperiod-gate-launch-20261022/revision-v2/REVIEW.md` | A04 1 |
| `repo/.agents/operations/newperiod-gate-launch-20261022/revision-v2/coordination/review-ready.json` | A01 2 |
| `repo/.agents/operations/newperiod-gate-private-launch-20261023/actual-witness-v1/outcome-v1/root-code-review.json` | A01 1, P07 1 |
| `repo/.agents/operations/newperiod-gate-private-launch-20261023/actual-witness-v1/root-resource-review.json` | A01 1, P07 2 |
| `repo/.agents/operations/newperiod-gate-private-launch-20261023/actual-witness-v1/waiter-v1/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-gate-private-launch-20261023/actual-witness-v1/waiter-v1/root-code-review.json` | A01 1, P07 1 |
| `repo/.agents/operations/newperiod-gbdt-client-r5-20261024/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-gbdt-completion-capture-20261024/REVIEW.md` | H01 1 |
| `repo/.agents/operations/newperiod-gbdt-immediate-launch-20261024/pooled-r5/review-request.json` | P01 9, P07 11 |
| `repo/.agents/operations/newperiod-h1-audit-only-v4-20261025/review-ready.json` | H01 1, P07 2 |
| `repo/.agents/operations/newperiod-h1-audit-only-v4-g3-20261025/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-h1-audit-only-v4-release-20261025/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-h1-construction-binding-20261024/review-ready.json` | A01 1 |
| `repo/.agents/operations/newperiod-h1-d30-manifest-outcome-capture-v1-v36-20261026/REVIEW.md` | H01 1 |
| `repo/.agents/operations/newperiod-h1-d60-development-v5-20261025/review-ready.json` | P07 2 |
| `repo/.agents/operations/newperiod-h1-d60-v5-tools-20261025/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-h1-development-budget-r2-20261024/review-ready-v1.json` | P07 1 |
| `repo/.agents/operations/newperiod-h1-development-budget-r2-20261024/wave0-waiter-v1/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-h1-development-budget-r2-20261024/wave2-failure-diagnostic-v1/review-ready.json` | A01 1, H01 1 |
| `repo/.agents/operations/newperiod-h1-development-budget-r3-20261025/audit-failure-diagnostic-v1/review-ready.json` | H01 1, P07 1 |
| `repo/.agents/operations/newperiod-h1-development-budget-r3-20261025/audit-failure-diagnostic-v2/review-ready.json` | H01 1, P07 1 |
| `repo/.agents/operations/newperiod-h1-development-budget-r3-20261025/audit-failure-diagnostic-v3/review-ready.json` | H01 1, P07 1 |
| `repo/.agents/operations/newperiod-h1-development-budget-r3-20261025/base-graph-ref-diagnostic-v1/review-ready.json` | H01 1, P06 2, P07 1, P11 1 |
| `repo/.agents/operations/newperiod-h1-development-budget-r3-20261025/review-ready-held-and-waiters.json` | P07 1 |
| `repo/.agents/operations/newperiod-h1-development-budget-r3-20261025/review-ready-v2.json` | A01 1 |
| `repo/.agents/operations/newperiod-h1-development-budget-r3-20261025/review-ready.json` | A01 1 |
| `repo/.agents/operations/newperiod-h1-development-launch-20261024/stage-proposal-v1/root-actual-held-review.json` | A01 1 |
| `repo/.agents/operations/newperiod-h1-development-launch-20261024/wave0-waiter-v1/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-h1-development-launch-20261024/wave0-waiter-v1/root-review.json` | A01 1 |
| `repo/.agents/operations/newperiod-h1-first-manifest-release-v1-v36-20261026/REVIEW.md` | H01 2, H02 3 |
| `repo/.agents/operations/newperiod-h1-first-manifest-release-v2-v36-20261026/REVIEW.md` | H01 2, H02 3 |
| `repo/.agents/operations/newperiod-h1-g1-binding-sonnet-v1-20261026/REVIEW.md` | H01 1 |
| `repo/.agents/operations/newperiod-h1-g1-packet-A-refs-sonnet-v2-20261026/REVIEW.md` | H07 1 |
| `repo/.agents/operations/newperiod-h1-metadata-execution-20261024/actual-binding-v1/failure-capture-v1/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-h1-metadata-execution-20261024/actual-binding-v1/stage-v1/root-stage-held-review.json` | H02 1, P01 1 |
| `repo/.agents/operations/newperiod-h1-metadata-execution-20261024/actual-binding-v1/waiter-v1/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-h1-metadata-execution-r2-20261024/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-h1-protected-allocation-stability-v1-v36-20261026/REVIEW.md` | H01 1 |
| `repo/.agents/operations/newperiod-h1-protected-allocation-stability-v2-v36-20261026/REVIEW.md` | H01 1 |
| `repo/.agents/operations/newperiod-h1-protected-execution-v2-v36-20261025/REVIEW.md` | H01 1, H02 2 |
| `repo/.agents/operations/newperiod-h1-protected-held-readback-v1-v36-20261025/REVIEW.md` | H02 1 |
| `repo/.agents/operations/newperiod-h3-assembly-acceptance-v1-20261025/review-ready.json` | P07 3 |
| `repo/.agents/operations/newperiod-h3-audit-only-v4-20261025/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-h3-audit-only-v5-20261025/review-ready.json` | A04 1, P07 13 |
| `repo/.agents/operations/newperiod-h3-audit-scratch-correction-v1-20261025/review-ready.json` | P07 12 |
| `repo/.agents/operations/newperiod-h3-audit-successor-prefreeze-v1-20261025/review-ready.json` | P07 2 |
| `repo/.agents/operations/newperiod-h3-audit-v5-final-request-builder-v1-20261026/review-ready.json` | A04 2, P07 10 |
| `repo/.agents/operations/newperiod-h3-audit-v5-first-capture-final-v1-v36-20261026/review-ready.json` | A04 2, P07 13 |
| `repo/.agents/operations/newperiod-h3-audit-v5-first-capture-preparation-v1-v36-20261026/review-ready.json` | A04 1, P07 13 |
| `repo/.agents/operations/newperiod-h3-audit-v5-group-release-v1-20261025/review-ready.json` | P07 22 |
| `repo/.agents/operations/newperiod-h3-audit-v5-group-release-v2-20261025/review-ready.json` | A04 1, P07 20 |
| `repo/.agents/operations/newperiod-h3-audit-v5-group-release-v3-v36-20261026/review-ready.json` | A04 1, P07 28 |
| `repo/.agents/operations/newperiod-h3-audit-v5-group-release-v4-v37-pending-20261026/review-ready.json` | A04 1, P07 27 |
| `repo/.agents/operations/newperiod-h3-audit-v5-group-release-v5-v37-final-pending-20261026/review-ready.json` | A04 2, P07 25 |
| `repo/.agents/operations/newperiod-h3-audit-v5-group-release-v6-v37-credits-pending-20261026/review-ready.json` | A04 2, P07 25 |
| `repo/.agents/operations/newperiod-h3-audit-v5-outcome-capture-v2-20261025/review-ready.json` | P07 19 |
| `repo/.agents/operations/newperiod-h3-audit-v5-outcome-capture-v3-v36-20261026/review-ready.json` | P07 21 |
| `repo/.agents/operations/newperiod-h3-audit-v5-outcome-capture-v4-v37-pending-20261026/review-ready.json` | A04 1, P07 20 |
| `repo/.agents/operations/newperiod-h3-audit-v5-outcome-capture-v5-v37-final-pending-20261026/review-ready.json` | A04 2, P07 17 |
| `repo/.agents/operations/newperiod-h3-audit-v5-outcome-capture-v6-v37-credits-pending-20261026/review-ready.json` | A04 2, P07 17 |
| `repo/.agents/operations/newperiod-h3-audit-v5-stage-held-final-request-v1-20261025/review-ready.json` | A04 4, P07 13 |
| `repo/.agents/operations/newperiod-h3-audit-v5-stage-held-operator-v1-20261025/review-ready.json` | A04 2, P07 17 |
| `repo/.agents/operations/newperiod-h3-audit-v5-stage-held-v35-binding-v1-20261025/review-ready.json` | P07 14 |
| `repo/.agents/operations/newperiod-h3-c3-admissions-proposal-astra-v1-20261025/review-request.json` | P07 6 |
| `repo/.agents/operations/newperiod-h3-chain-20261025/review-ready-v2.json` | P07 1 |
| `repo/.agents/operations/newperiod-h3-chain-20261025/review-ready-v3.json` | P07 1 |
| `repo/.agents/operations/newperiod-h3-chain-20261025/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-h3-chain-v4-20261025/REVIEW.md` | A03 1, A04 1 |
| `repo/.agents/operations/newperiod-h3-chain-v4-20261025/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-h3-coverage-c2-astra-v1-20261025/review-ready.json` | P07 16 |
| `repo/.agents/operations/newperiod-h3-coverage-c2-astra-v2-20261025/review-ready.json` | P07 22 |
| `repo/.agents/operations/newperiod-h3-coverage-c3-astra-v1-20261025/review-ready.json` | P07 16 |
| `repo/.agents/operations/newperiod-h3-coverage-c3-astra-v2-20261025/review-ready.json` | P07 18 |
| `repo/.agents/operations/newperiod-h3-coverage-c3-binding-preparation-astra-v1-20261025/review-ready.json` | P07 18 |
| `repo/.agents/operations/newperiod-h3-coverage-c3-final-astra-v1-v36-20261025/review-ready.json` | P07 18 |
| `repo/.agents/operations/newperiod-h3-coverage-capture-operator-v1-20261025/REVIEW.md` | N01 1 |
| `repo/.agents/operations/newperiod-h3-coverage-diagnostic-once-astra-v1-20261025/review-ready.json` | H01 1, P07 11 |
| `repo/.agents/operations/newperiod-h3-coverage-gap-astra-final-v1-20261025/review-ready.json` | P07 7 |
| `repo/.agents/operations/newperiod-h3-coverage-logged-wrapper-v1-20261025/REVIEW.md` | H02 1, N01 1 |
| `repo/.agents/operations/newperiod-h3-coverage-logged-wrapper-v1-20261025/review-ready.json` | P07 3 |
| `repo/.agents/operations/newperiod-h3-coverage-reconciliation-20261024/r2/review-ready.json` | A01 1 |
| `repo/.agents/operations/newperiod-h3-coverage-reconciliation-20261024/r3/review-ready.json` | A01 1 |
| `repo/.agents/operations/newperiod-h3-coverage-reconciliation-20261024/r4/review-ready.json` | A01 1 |
| `repo/.agents/operations/newperiod-h3-coverage-reconciliation-20261024/review-ready.json` | A01 1, P07 2 |
| `repo/.agents/operations/newperiod-h3-coverage-reconciliation-20261024/review-request-h3-coverage-kernel.json` | A01 2, P07 2 |
| `repo/.agents/operations/newperiod-h3-coverage-reconciliation-20261024/review-request-h3-coverage-r2-supplement.json` | A01 2, P07 2 |
| `repo/.agents/operations/newperiod-h3-coverage-reconciliation-20261024/review-request-h3-coverage-r4-B1.json` | A01 2, P07 3 |
| `repo/.agents/operations/newperiod-h3-coverage-release-operator-v1-20261025/REVIEW.md` | N01 1 |
| `repo/.agents/operations/newperiod-h3-coverage-stage-operator-v1-20261025/review-ready.json` | P07 7 |
| `repo/.agents/operations/newperiod-h3-development-budget-r2-20261024/REVIEW.md` | A04 1 |
| `repo/.agents/operations/newperiod-h3-development-budget-r2-20261024/review-ready-r4.json` | A01 1, P07 1 |
| `repo/.agents/operations/newperiod-h3-development-budget-r2-20261024/review-ready.json` | A01 1 |
| `repo/.agents/operations/newperiod-h3-development-budget-r2-20261024/review-request-for-f4d75bb1.json` | A01 1, P07 3 |
| `repo/.agents/operations/newperiod-h3-development-launch-20261024/review-ready.json` | A01 1 |
| `repo/.agents/operations/newperiod-h3-development-launch-20261024/review-request-h3-development-launch.json` | A01 2, P07 2 |
| `repo/.agents/operations/newperiod-h3-first-manifest-input-gate-v1-20261026/review-ready.json` | A01 1, P07 13 |
| `repo/.agents/operations/newperiod-h3-first-manifest-input-gate-v2-20261027/REVIEW-REQUEST.txt` | P05 1, P07 1 |
| `repo/.agents/operations/newperiod-h3-first-manifest-input-gate-v2-20261027/REVIEW.md` | H01 3, H02 1, H03 1, N01 2, P05 1, P11 1 |
| `repo/.agents/operations/newperiod-h3-first-manifest-input-gate-v3-20261027/REVIEW-REQUEST.txt` | P07 1 |
| `repo/.agents/operations/newperiod-h3-first-manifest-input-gate-v3-20261027/REVIEW.md` | H01 1, N01 1, P05 1, P11 2 |
| `repo/.agents/operations/newperiod-h3-first-manifest-input-gate-v4-20261027/REVIEW-REQUEST.txt` | P07 1 |
| `repo/.agents/operations/newperiod-h3-forty-refits-calibration-preparation-v1-20261026/review-ready.json` | P07 6 |
| `repo/.agents/operations/newperiod-h3-forty-refits-calibration-preparation-v2-20261026/review-ready.json` | P07 6 |
| `repo/.agents/operations/newperiod-h3-integration-gate-opus-h3-v1-20261026/REVIEW.md` | H01 1 |
| `repo/.agents/operations/newperiod-h3-manifest-growth-proof-astra-v1-20261026/review-ready.json` | P07 6 |
| `repo/.agents/operations/newperiod-h3-metadata-execution-20261024/REVIEW.md` | A04 1 |
| `repo/.agents/operations/newperiod-h3-metadata-execution-20261024/actual-binding-v1/review-request-h3-draft-actual-and-publication.json` | A01 2, P01 1, P07 5 |
| `repo/.agents/operations/newperiod-h3-metadata-execution-20261024/actual-binding-v1/review-request-h3-draft-waiter-and-capture.json` | A01 2, P07 1 |
| `repo/.agents/operations/newperiod-h3-metadata-execution-20261024/actual-binding-v1/review-request-h3-finalize-approval.json` | A01 2, P07 2 |
| `repo/.agents/operations/newperiod-h3-metadata-execution-20261024/actual-binding-v1/review-request-h3-finalize-package.json` | A01 2, P01 2, P07 2 |
| `repo/.agents/operations/newperiod-h3-metadata-execution-20261024/actual-binding-v1/review-request-h3-finalize-waiter-and-capture.json` | H01 2, H02 2, P07 1 |
| `repo/.agents/operations/newperiod-h3-metadata-execution-20261024/review-ready.json` | A01 1 |
| `repo/.agents/operations/newperiod-h3-metadata-execution-20261024/review-request-h3-draft-approval-finalize.json` | A01 2, P07 2 |
| `repo/.agents/operations/newperiod-h3-metadata-execution-20261024/review-request-h3-execution-and-draft-binding.json` | A01 2, P07 3 |
| `repo/.agents/operations/newperiod-h3-metadata-publication-20261024/review-ready.json` | A01 1 |
| `repo/.agents/operations/newperiod-h3-metadata-publication-20261024/review-request-h3-coverage-r3-and-kernel-update.json` | A01 2, P07 2 |
| `repo/.agents/operations/newperiod-h3-metadata-publication-20261024/review-request-h3-publication-kernel.json` | A01 2, P07 2 |
| `repo/.agents/operations/newperiod-h3-protected-c3-binding-astra-v1-20261025/review-ready.json` | P07 138 |
| `repo/.agents/operations/newperiod-h3-protected-coverage-constructor-astra-v1-20261025/review-ready.json` | P07 8 |
| `repo/.agents/operations/newperiod-h3-protected-coverage-probe-v1-20261025/REVIEW.md` | P01 1 |
| `repo/.agents/operations/newperiod-h3-protected-coverage-probe-v1-20261025/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-h3-protected-custody-budget-storage2-v1-20261026/review-ready.json` | P07 4 |
| `repo/.agents/operations/newperiod-h3-protected-execution-astra-v1-20261025/REVIEW.md` | A01 1 |
| `repo/.agents/operations/newperiod-h3-protected-execution-astra-v1-20261025/review-ready.json` | A01 1, P07 196 |
| `repo/.agents/operations/newperiod-h3-protected-execution-astra-v2-20261025/REVIEW.md` | A01 1 |
| `repo/.agents/operations/newperiod-h3-protected-execution-astra-v2-20261025/review-ready.json` | A01 1, P07 201 |
| `repo/.agents/operations/newperiod-h3-protected-launch-packet-storage2-v1-20261026/review-ready.json` | A01 1, P07 10 |
| `repo/.agents/operations/newperiod-h3-protected-launch-packet-storage2-v2-20261026/review-ready.json` | P07 10 |
| `repo/.agents/operations/newperiod-h3-protected-launch-packet-storage2-v3-20261026/review-ready.json` | P07 8 |
| `repo/.agents/operations/newperiod-h3-protected-operating-evidence-astra-v1-20261026/review-ready.json` | P07 2 |
| `repo/.agents/operations/newperiod-h3-protected-stage-storage2-v3-20261026/REVIEW.md` | A01 1 |
| `repo/.agents/operations/newperiod-h3-protected-stage-storage2-v3-20261026/review-ready.json` | A01 1, P07 206 |
| `repo/.agents/operations/newperiod-h3-protected-stage-storage2-v3-v43-20261026/review-ready.json` | P07 198 |
| `repo/.agents/operations/newperiod-h3-protected-stage-storage2-v4-20261026/review-ready.json` | A01 1, P07 197 |
| `repo/.agents/operations/newperiod-h3-protected-stage-storage2-v5-20261026/review-ready.json` | P07 154 |
| `repo/.agents/operations/newperiod-h3-protected-stage-storage2-v6-20261026/review-ready.json` | P07 151 |
| `repo/.agents/operations/newperiod-h3-protected-wave-00-capture-sonnet-v1-20261027/REVIEW-REQUEST.txt` | P07 1 |
| `repo/.agents/operations/newperiod-h3-protected-wave-00-capture-sonnet-v1-20261027/REVIEW.md` | H01 1, H02 2, H04 1 |
| `repo/.agents/operations/newperiod-h3-refit40-admit-actual-release-review-astra-final-20261027/review-release.json` | A01 2, P07 13 |
| `repo/.agents/operations/newperiod-h3-refit40-adoption004-stage-review-astra-final-20261026/review-stage.json` | A01 2, P07 10 |
| `repo/.agents/operations/newperiod-h3-refit40-capture-adoption006-review-astra-final-20261027/review-capture.json` | A01 2, P07 13 |
| `repo/.agents/operations/newperiod-h3-refit40-capture-review-astra-final-v1-20261027/review-capture.NOT-AUTHORIZED.json` | A01 2, P07 12 |
| `repo/.agents/operations/newperiod-h3-refit40-execution-sonnet-v1-20261026/REVIEW.md` | H01 2 |
| `repo/.agents/operations/newperiod-h3-refit40-execution-sonnet-v1-20261026/templates/review-admit.FALSE.json` | A01 1, P07 7 |
| `repo/.agents/operations/newperiod-h3-refit40-execution-sonnet-v1-20261026/templates/review-capture.FALSE.json` | A01 1, P07 7 |
| `repo/.agents/operations/newperiod-h3-refit40-execution-sonnet-v1-20261026/templates/review-release.FALSE.json` | A01 1, P07 7 |
| `repo/.agents/operations/newperiod-h3-refit40-execution-sonnet-v1-20261026/templates/review-stage.FALSE.json` | A01 1, P07 7 |
| `repo/.agents/operations/newperiod-h3-refit40-execution-sonnet-v1-20261026/templates/review-submit_held.FALSE.json` | A01 1, P07 7 |
| `repo/.agents/operations/newperiod-h3-refit40-execution-sonnet-v2-20261026/REVIEW.md` | H01 2 |
| `repo/.agents/operations/newperiod-h3-refit40-execution-sonnet-v2-20261026/templates/review-admit.FALSE.json` | A01 1, P07 7 |
| `repo/.agents/operations/newperiod-h3-refit40-execution-sonnet-v2-20261026/templates/review-capture.FALSE.json` | A01 1, P07 7 |
| `repo/.agents/operations/newperiod-h3-refit40-execution-sonnet-v2-20261026/templates/review-release.FALSE.json` | A01 1, P07 7 |
| `repo/.agents/operations/newperiod-h3-refit40-execution-sonnet-v2-20261026/templates/review-stage.FALSE.json` | A01 1, P07 7 |
| `repo/.agents/operations/newperiod-h3-refit40-execution-sonnet-v2-20261026/templates/review-submit_held.FALSE.json` | A01 1, P07 7 |
| `repo/.agents/operations/newperiod-h3-refit40-root-driver-sonnet-v1-20261026/REVIEW.md` | A04 1 |
| `repo/.agents/operations/newperiod-h3-refit40-stage-actual-submit-review-astra-final-20261026/review-submit_held.json` | A01 2, P07 10 |
| `repo/.agents/operations/newperiod-h3-refit40-submit-actual-admit-review-astra-final-20261026/review-admit.json` | A01 2, H02 1, N01 1, P07 10 |
| `repo/.agents/operations/newperiod-h3-release-v26-20261025/REVIEW.md` | A04 1 |
| `repo/.agents/operations/newperiod-h3-release-v26-20261025/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-h3-root-evidence-storage2-v1-20261026/review-ready.json` | P07 11 |
| `repo/.agents/operations/newperiod-h3-timing-protected-execution-v1-20261025/REVIEW.md` | N01 1 |
| `repo/.agents/operations/newperiod-h3-timing-protected-execution-v2-20261025/REVIEW.md` | N01 1 |
| `repo/.agents/operations/newperiod-h3-timing-protected-execution-v2-20261025/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-h3-timing-protected-execution-v3-20261025/review-ready.json` | P07 249 |
| `repo/.agents/operations/newperiod-h3-v35-retirement-proposal-20261025/review-ready.json` | P07 3 |
| `repo/.agents/operations/newperiod-h3-v37-operating-evidence-v1-20261026/review-ready.json` | A04 2, P07 11 |
| `repo/.agents/operations/newperiod-h3-v37-operating-evidence-v2-credits-pending-20261026/review-ready.json` | A04 2, P07 6 |
| `repo/.agents/operations/newperiod-h3t-binary192-a2-owner-confirmation-v1-20261026/review-ready.json` | P07 2 |
| `repo/.agents/operations/newperiod-h3t-parsed-consumer-deltas-v2-20261026/review-ready.json` | P07 6 |
| `repo/.agents/operations/newperiod-h3t-parsed-d4-admission-inputs-v1-20261026/review-ready.json` | P07 8 |
| `repo/.agents/operations/newperiod-h3t-parsed-owner-holds-v1-20261026/review-ready.json` | P07 9 |
| `repo/.agents/operations/newperiod-h3t-withdrawal-binary-owner-delta-v1-20261026/review-ready.json` | P07 10 |
| `repo/.agents/operations/newperiod-inference-packets-astra-20261025/review-ready.json` | A01 1, N05 1, P07 9 |
| `repo/.agents/operations/newperiod-input-gate-20261021/REVIEW.md` | A04 1 |
| `repo/.agents/operations/newperiod-input-gate-20261021/revision-v2/REVIEW-READY.json` | A01 2 |
| `repo/.agents/operations/newperiod-input-gate-20261021/revision-v2/REVIEW.md` | A04 1, H01 1 |
| `repo/.agents/operations/newperiod-input-gate-20261021/revision-v3/REVIEW-READY.json` | A01 2 |
| `repo/.agents/operations/newperiod-input-gate-20261021/revision-v4/REVIEW-READY.json` | A01 2 |
| `repo/.agents/operations/newperiod-input-gate-20261021/revision-v4/REVIEW.md` | A04 1 |
| `repo/.agents/operations/newperiod-input-gate-20261021/revision-v5/REVIEW-READY.json` | A01 2 |
| `repo/.agents/operations/newperiod-input-gate-20261021/revision-v5/REVIEW.md` | A04 1 |
| `repo/.agents/operations/newperiod-input-gate-plan-bindings-20261024/rexact-v1/review-ready.json` | A01 1, P07 6 |
| `repo/.agents/operations/newperiod-input-gate-plan-bindings-20261024/rexact-v3-frozen-r3/review-ready-r3.json` | P07 2 |
| `repo/.agents/operations/newperiod-input-gate-plan-bindings-20261024/root-code-review.json` | A01 1 |
| `repo/.agents/operations/newperiod-joint-v37-composition-draft-v1-20261025/review-ready.json` | P07 6 |
| `repo/.agents/operations/newperiod-joint-v37-composition-draft-v2-20261025/review-ready.json` | P07 3 |
| `repo/.agents/operations/newperiod-joint-v37-composition-draft-v3-20261025/review-ready.json` | P07 3 |
| `repo/.agents/operations/newperiod-joint-v37-composition-draft-v4-20261025/review-ready.json` | P07 3 |
| `repo/.agents/operations/newperiod-joint-v37-final-template-v1-20261026/review-ready.json` | P07 6 |
| `repo/.agents/operations/newperiod-joint-v37-final-template-v2-20261026/review-ready.json` | A01 1, P07 7 |
| `repo/.agents/operations/newperiod-joint-v48-origin-mv-sonnet-v1-20261027/REVIEW.md` | H01 1 |
| `repo/.agents/operations/newperiod-ledger-metadata-20261023/REVIEW.md` | N01 1 |
| `repo/.agents/operations/newperiod-october-timestamp-census-20261023/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-october-timestamp-census-r2-20261023/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-ordinary-transport-20261023/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-origin-construction-sonnet-v1-20261026/REVIEW.md` | P05 1 |
| `repo/.agents/operations/newperiod-origin-construction-sonnet-v1-20261026/templates/root-meta_review-meta.FALSE.json` | P07 7 |
| `repo/.agents/operations/newperiod-origin-construction-sonnet-v1-20261026/templates/root-review_install-invalid.FALSE.json` | P07 7 |
| `repo/.agents/operations/newperiod-origin-construction-sonnet-v1-20261026/templates/root-review_install-valid.FALSE.json` | P07 7 |
| `repo/.agents/operations/newperiod-origin-construction-sonnet-v2-20261026/templates/root-meta_review-meta.FALSE.json` | P07 7 |
| `repo/.agents/operations/newperiod-origin-construction-sonnet-v2-20261026/templates/root-review_install-invalid.FALSE.json` | P07 7 |
| `repo/.agents/operations/newperiod-origin-construction-sonnet-v2-20261026/templates/root-review_install-valid.FALSE.json` | P07 7 |
| `repo/.agents/operations/newperiod-origin-construction-sonnet-v3-20261026/templates/root-meta_review-meta.FALSE.json` | P07 7 |
| `repo/.agents/operations/newperiod-origin-construction-sonnet-v3-20261026/templates/root-review_install-invalid.FALSE.json` | P07 7 |
| `repo/.agents/operations/newperiod-origin-construction-sonnet-v3-20261026/templates/root-review_install-valid.FALSE.json` | P07 7 |
| `repo/.agents/operations/newperiod-origin-construction-sonnet-v4-20261026/templates/root-meta_review-meta.FALSE.json` | P07 7 |
| `repo/.agents/operations/newperiod-origin-construction-sonnet-v4-20261026/templates/root-review_install-invalid.FALSE.json` | P07 7 |
| `repo/.agents/operations/newperiod-origin-construction-sonnet-v4-20261026/templates/root-review_install-valid.FALSE.json` | P07 7 |
| `repo/.agents/operations/newperiod-origin-construction-sonnet-v5-20261027/templates/root-meta_review-meta.FALSE.json` | P07 7 |
| `repo/.agents/operations/newperiod-origin-construction-sonnet-v5-20261027/templates/root-review_install-invalid.FALSE.json` | P07 7 |
| `repo/.agents/operations/newperiod-origin-construction-sonnet-v5-20261027/templates/root-review_install-valid.FALSE.json` | P07 7 |
| `repo/.agents/operations/newperiod-origin-construction-sonnet-v6-20261027/REVIEW.md` | H01 1 |
| `repo/.agents/operations/newperiod-origin-construction-sonnet-v6-20261027/templates/root-meta_review-meta.FALSE.json` | P07 7 |
| `repo/.agents/operations/newperiod-origin-construction-sonnet-v6-20261027/templates/root-review_install-invalid.FALSE.json` | P07 7 |
| `repo/.agents/operations/newperiod-origin-construction-sonnet-v6-20261027/templates/root-review_install-valid.FALSE.json` | P07 7 |
| `repo/.agents/operations/newperiod-origin-construction-sonnet-v7-20261027/REVIEW-V6.md` | H01 1 |
| `repo/.agents/operations/newperiod-origin-construction-sonnet-v7-20261027/templates/root-meta_review-meta.FALSE.json` | P07 7 |
| `repo/.agents/operations/newperiod-origin-construction-sonnet-v7-20261027/templates/root-review_install-invalid.FALSE.json` | P07 7 |
| `repo/.agents/operations/newperiod-origin-construction-sonnet-v7-20261027/templates/root-review_install-valid.FALSE.json` | P07 7 |
| `repo/.agents/operations/newperiod-origin-construction-sonnet-v8-20261027/templates/root-meta_review-meta.FALSE.json` | P07 7 |
| `repo/.agents/operations/newperiod-origin-construction-sonnet-v8-20261027/templates/root-review_install-invalid.FALSE.json` | P07 7 |
| `repo/.agents/operations/newperiod-origin-construction-sonnet-v8-20261027/templates/root-review_install-valid.FALSE.json` | P07 7 |
| `repo/.agents/operations/newperiod-origin-construction-sonnet-v9-20261027/templates/root-meta_review-meta.FALSE.json` | P07 7 |
| `repo/.agents/operations/newperiod-origin-construction-sonnet-v9-20261027/templates/root-review_install-invalid.FALSE.json` | P07 7 |
| `repo/.agents/operations/newperiod-origin-construction-sonnet-v9-20261027/templates/root-review_install-valid.FALSE.json` | P07 7 |
| `repo/.agents/operations/newperiod-origin-fit-bindings-astra-g1b-v1-20261026/REVIEW.md` | A01 1 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v1-20261026/REVIEW.md` | A01 1 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v1-20261026/templates/review-invalid-capture.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v1-20261026/templates/review-invalid-release.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v1-20261026/templates/review-invalid-stage.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v1-20261026/templates/review-invalid-submit_held.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v1-20261026/templates/review-valid-capture.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v1-20261026/templates/review-valid-release.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v1-20261026/templates/review-valid-stage.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v1-20261026/templates/review-valid-submit_held.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v2-20261026/REVIEW.md` | A01 1 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v2-20261026/templates/review-invalid-capture.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v2-20261026/templates/review-invalid-release.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v2-20261026/templates/review-invalid-stage.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v2-20261026/templates/review-invalid-submit_held.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v2-20261026/templates/review-valid-capture.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v2-20261026/templates/review-valid-release.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v2-20261026/templates/review-valid-stage.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v2-20261026/templates/review-valid-submit_held.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v3-20261026/REVIEW.md` | H01 1, P05 5 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v3-20261026/templates/review-invalid-capture.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v3-20261026/templates/review-invalid-release.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v3-20261026/templates/review-invalid-stage.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v3-20261026/templates/review-invalid-submit_held.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v3-20261026/templates/review-valid-capture.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v3-20261026/templates/review-valid-release.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v3-20261026/templates/review-valid-stage.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v3-20261026/templates/review-valid-submit_held.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v4-20261027/REVIEW.md` | H01 1, P05 5 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v4-20261027/templates/review-invalid-capture.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v4-20261027/templates/review-invalid-release.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v4-20261027/templates/review-invalid-stage.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v4-20261027/templates/review-invalid-submit_held.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v4-20261027/templates/review-valid-capture.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v4-20261027/templates/review-valid-release.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v4-20261027/templates/review-valid-stage.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v4-20261027/templates/review-valid-submit_held.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v5-20261027/REVIEW.md` | H01 1, P05 5 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v5-20261027/templates/review-invalid-capture.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v5-20261027/templates/review-invalid-release.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v5-20261027/templates/review-invalid-stage.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v5-20261027/templates/review-invalid-submit_held.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v5-20261027/templates/review-valid-capture.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v5-20261027/templates/review-valid-release.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v5-20261027/templates/review-valid-stage.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v5-20261027/templates/review-valid-submit_held.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v6-20261027/REVIEW.md` | H01 1, P05 5 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v6-20261027/templates/review-invalid-capture.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v6-20261027/templates/review-invalid-release.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v6-20261027/templates/review-invalid-stage.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v6-20261027/templates/review-invalid-submit_held.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v6-20261027/templates/review-valid-capture.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v6-20261027/templates/review-valid-release.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v6-20261027/templates/review-valid-stage.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-fit40-operator-sonnet-v6-20261027/templates/review-valid-submit_held.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-origin-inference-r2-retain-20261027/REVIEW-DRAFT.json` | H01 1, P07 1 |
| `repo/.agents/operations/newperiod-origin-meta-actual-v8-review-sol-g1a-20261027/review-v8.json` | A01 1, P07 12 |
| `repo/.agents/operations/newperiod-origin-projection-once-opus-science-v1-20261026/REVIEW.md` | H01 1 |
| `repo/.agents/operations/newperiod-origin-projection-once-opus-science-v2-20261026/REVIEW.md` | H01 1 |
| `repo/.agents/operations/newperiod-origin-projection-reader-adapter-v2-20261026/REVIEW.md` | H01 1 |
| `repo/.agents/operations/newperiod-origin-s3-boundary-source-v2-20261026/REVIEW.md` | H01 1 |
| `repo/.agents/operations/newperiod-origin-s3-once-v2-20261026/REVIEW.md` | H01 1 |
| `repo/.agents/operations/newperiod-origin-s3-once-v4-20261026/REVIEW.md` | H01 1 |
| `repo/.agents/operations/newperiod-origin-s3-root-fill-sonnet-v1-20261026/REVIEW.md` | P02 1 |
| `repo/.agents/operations/newperiod-origin-s3-workspace-v2-20261026/REVIEW.md` | H01 1 |
| `repo/.agents/operations/newperiod-origin-source-aug31-20261024/review-ready.json` | A01 1 |
| `repo/.agents/operations/newperiod-origin-stable-lineage-astra-g1a-v1-20261026/REVIEW.md` | P05 1 |
| `repo/.agents/operations/newperiod-origin-stable-lineage-astra-g1a-v1-20261026/review-ready.json` | P07 10 |
| `repo/.agents/operations/newperiod-origin-stable-metadata-once-astra-g1a-v1-20261026/review-ready.json` | P07 18 |
| `repo/.agents/operations/newperiod-origin-stable-scientific-audit-astra-g1a-v1-20261026/review-ready.json` | P07 23 |
| `repo/.agents/operations/newperiod-origin-stable-scientific-audit-astra-g1a-v2-20261026/review-ready.json` | P07 24 |
| `repo/.agents/operations/newperiod-origin-stable-scientific-audit-astra-g1a-v3-20261026/review-ready.json` | P07 24 |
| `repo/.agents/operations/newperiod-own-origin-stage-admission-delta-astra-g1a-v1-20261026/review-ready.json` | P07 3 |
| `repo/.agents/operations/newperiod-p24-retained-launcher-astra-v1-20261026/review-ready.json` | A01 1, P07 6 |
| `repo/.agents/operations/newperiod-parsed-consumer-deltas-astra-final-v2-20261025/review-ready.json` | P07 3 |
| `repo/.agents/operations/newperiod-parsed-consumer-deltas-astra-v28-v1-20261025/review-ready.json` | P07 3 |
| `repo/.agents/operations/newperiod-parsed-consumer-deltas-astra-v28-v2-20261025/review-ready.json` | P07 4 |
| `repo/.agents/operations/newperiod-parsed-p07-operational-delta-astra-v1-20261025/review-ready.json` | P07 2 |
| `repo/.agents/operations/newperiod-placement-venv-incident-20261024/review-ready-consumer-proof.json` | A01 1, H01 1, I01 1, P01 1 |
| `repo/.agents/operations/newperiod-placement-venv-incident-20261024/review-ready-restore-v2.json` | A01 1, H01 1, H02 1, I01 1, N01 1, P11 1 |
| `repo/.agents/operations/newperiod-placement-venv-incident-20261024/review-ready-restore.json` | A01 1, H01 1 |
| `repo/.agents/operations/newperiod-placement-venv-incident-20261024/review-ready.json` | A01 1, H01 1, I01 1 |
| `repo/.agents/operations/newperiod-primary-construction-four-waves-20261024/remaining-outcomes-v1/root-final67-actual-review.json` | P01 67 |
| `repo/.agents/operations/newperiod-primary-construction-four-waves-20261024/wave1-waiter-v1/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-primary-construction-four-waves-20261024/wave1-waiter-v1/root-conditional-review.json` | P07 1 |
| `repo/.agents/operations/newperiod-primary-construction-waves-20261024/review-ready-v1.json` | P07 1 |
| `repo/.agents/operations/newperiod-primary-construction-waves-20261024/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-primary-export-chain-r3-20261024/review-ready.json` | P07 2 |
| `repo/.agents/operations/newperiod-primary-export-waves-20261024/bind-outcome-v1/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-primary-export-waves-20261024/bind-waiter-v1/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-primary-export-waves-20261024/export0-waiter-v1/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-primary-export-waves-20261024/export1-waiter-v1/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-primary-export-waves-20261024/export2-waiter-v1/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-primary-export-waves-20261024/export3-waiter-v1/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-primary-export-waves-20261024/master-waiter-v1/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-primary-export-waves-20261024/review-ready.json` | P07 2 |
| `repo/.agents/operations/newperiod-primary-export-waves-20261024/root-code-review.json` | P07 3 |
| `repo/.agents/operations/newperiod-primary-export-waves-20261024/witness-plans-capture-v1/root-code-review.json` | A01 1 |
| `repo/.agents/operations/newperiod-protected-variant-resources-r2-20261023/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-shard27-allocation-probe-v1-20261025/review-ready.json` | A01 1, A04 1, P07 14 |
| `repo/.agents/operations/newperiod-shard27-allocation-probe-v2-20261025/review-ready.json` | A01 1, P07 14 |
| `repo/.agents/operations/newperiod-shard27-allocation-probe-v3-20261025/review-ready.json` | A01 1, P07 13 |
| `repo/.agents/operations/newperiod-shard27-residue-cleanup-v3-binding-v1-20261025/REVIEW.md` | A01 1 |
| `repo/.agents/operations/newperiod-shard27-residue-cleanup-v3-binding-v1-20261025/review-ready.json` | A01 2, A04 1, P07 10 |
| `repo/.agents/operations/newperiod-shard27-residue-cleanup-v3-v36-20261025/review-ready.json` | A01 3, A04 1, P07 17 |
| `repo/.agents/operations/newperiod-shard27-stat-completion-v1-20261025/review-ready.json` | A01 1, P07 11 |
| `repo/.agents/operations/newperiod-shard27-v2-empty-residue-cleanup-v1-20261025/REVIEW.txt` | N01 1 |
| `repo/.agents/operations/newperiod-shard27-v2-empty-residue-cleanup-v1-20261025/review-ready.json` | A01 1, P07 18 |
| `repo/.agents/operations/newperiod-shard27-v2-empty-residue-cleanup-v2-20261025/review-ready.json` | A01 1, P07 19 |
| `repo/.agents/operations/newperiod-single-r2-persistence-20261024/bootstrap.py` | P01 1 |
| `repo/.agents/operations/newperiod-single-r2-persistence-20261024/client.py` | H01 1, H02 2, N01 2, P01 1, P03 1 |
| `repo/.agents/operations/newperiod-single-r2-persistence-20261024/reviewed_transport.py` | H01 1, H02 1, N01 2, P01 1, P03 1 |
| `repo/.agents/operations/newperiod-single-r2-persistence-20261024/runner.py` | P01 1 |
| `repo/.agents/operations/newperiod-single-r2-persistence-20261024/test_transport.py` | N01 1 |
| `repo/.agents/operations/newperiod-stable-assembly-mixed32-sonnet-v1-20261026/REVIEW.md` | A01 1 |
| `repo/.agents/operations/newperiod-stable-assembly-mixed32-sonnet-v1-20261026/draft/control/review-assemble.json` | P01 1 |
| `repo/.agents/operations/newperiod-stable-assembly-mixed32-sonnet-v2-20261026/REVIEW.md` | A01 1, A04 1, H02 2 |
| `repo/.agents/operations/newperiod-stable-assembly-mixed32-sonnet-v2-20261026/draft/control/review-assemble.json` | P01 1 |
| `repo/.agents/operations/newperiod-stable-assembly-mixed32-sonnet-v3-20261026/REVIEW.md` | A01 1, A04 1 |
| `repo/.agents/operations/newperiod-stable-assembly-mixed32-sonnet-v3-20261026/draft/control/review-assemble.json` | P01 1 |
| `repo/.agents/operations/newperiod-stable-history-provenance-opus-science-v1-20261026/witness/REVIEW.md` | H01 1, P02 1, P11 1 |
| `repo/.agents/operations/newperiod-stable-rerun4-launch-sonnet-v1-20261026/REVIEW.md` | H01 2, H02 2, P07 2 |
| `repo/.agents/operations/newperiod-stable-scientific-audit-astra-g1a-v4-20261026/review-ready.json` | A01 1, P07 18 |
| `repo/.agents/operations/newperiod-stable-stage32-operator-opus-science-v1-20261026/REVIEW.md` | H01 2, H02 1, N01 2 |
| `repo/.agents/operations/newperiod-stable-stage32-rerun4-sonnet-v2-20261026/REVIEW.md` | A01 1, A04 1 |
| `repo/.agents/operations/newperiod-stable-stage32-transport-opus-science-v1-20261026/REVIEW.md` | P05 3 |
| `repo/.agents/operations/newperiod-stable-stage32-transport-opus-science-v2-20261026/REVIEW-V1-DRAFT.md` | P05 3 |
| `repo/.agents/operations/newperiod-stable-v6-v44-launch-root-v2-20261026/REVIEW.md` | H01 1, H02 1, N01 1, P07 1 |
| `repo/.agents/operations/newperiod-stable-v6-v44-launch-sonnet-v1-20261026/REVIEW.md` | H01 1, H02 1, N01 1, P07 1 |
| `repo/.agents/operations/newperiod-storage-prefix25-backup-20261024/review-ready-backup-code-v1.json` | N02 1, P11 1 |
| `repo/.agents/operations/newperiod-storage-prefix25-backup-20261024/review-ready.json` | N02 1, P11 1 |
| `repo/.agents/operations/newperiod-storage-prefix25-terminal-20261024/REVIEW.md` | H01 1, H02 1 |
| `repo/.agents/operations/newperiod-storage-prefix25-terminal-20261024/cleanup-five-v2/REVIEW.md` | A04 1 |
| `repo/.agents/operations/newperiod-storage-prefix25-terminal-20261024/cleanup-five-v2/review-ready.json` | A01 1, P07 2 |
| `repo/.agents/operations/newperiod-storage-prefix25-terminal-20261024/cleanup-five-v2/review-request-for-f4d75bb1.json` | A01 1, P07 3 |
| `repo/.agents/operations/newperiod-storage-prefix25-terminal-20261024/drill-v1/review-ready.json` | A01 1 |
| `repo/.agents/operations/newperiod-storage-prefix25-terminal-20261024/prune25-v1/review-ready.json` | A01 1 |
| `repo/.agents/operations/newperiod-storage-prefix25-terminal-20261024/recovery-r3/REVIEW.md` | A04 1 |
| `repo/.agents/operations/newperiod-storage-prefix25-terminal-20261024/recovery-r3/review-ready.json` | A01 1 |
| `repo/.agents/operations/newperiod-storage-prefix25-terminal-20261024/recovery-r3a/review-ready.json` | A01 1 |
| `repo/.agents/operations/newperiod-storage-prefix25-terminal-20261024/restore/review-ready.json` | A01 1 |
| `repo/.agents/operations/newperiod-storage-prefix25-terminal-20261024/review-ready.json` | A01 1 |
| `repo/.agents/operations/newperiod-storage-prefix25-terminal-20261024/review-request-prefix25-r3-recovery.json` | A01 2, P07 5 |
| `repo/.agents/operations/newperiod-storage-prefix25-terminal-20261024/review-request-prefix25-r3a.json` | A01 2, P07 3 |
| `repo/.agents/operations/newperiod-storage-prefix25-terminal-20261024/review-request-prefix25-terminal-capture.json` | A01 2, P07 2 |
| `repo/.agents/operations/newperiod-storage-prefix25-terminal-20261024/review-request-prune25-code.json` | A01 2, P07 2 |
| `repo/.agents/operations/newperiod-storage-prefix25-terminal-20261024/review-request-r3a-executed-and-waiter.json` | A01 2, P02 1, P07 1, P11 1 |
| `repo/.agents/operations/newperiod-storage-prefix25-terminal-20261024/review-request-r3a-terminal-capture.json` | A01 2, P07 2 |
| `repo/.agents/operations/newperiod-storage-prefix25-terminal-20261024/review-request-restore-drill.json` | A01 2, P07 2 |
| `repo/.agents/operations/newperiod-storage-prefix25-terminal-20261024/review-request-restore-recipe.json` | A01 2, P07 2 |
| `repo/.agents/operations/newperiod-storage-prefix25-terminal-20261024/review-request-waiter-relaunch.json` | A01 2, P07 1 |
| `repo/.agents/operations/newperiod-storage-prefix25-terminal-20261024/terminal-r3a/review-ready.json` | A01 1 |
| `repo/.agents/operations/newperiod-storage-prefix25-terminal-20261024/waiter-r3a/review-ready.json` | A01 1, H02 2 |
| `repo/.agents/operations/newperiod-storage-recovery-20261023/REVIEW.md` | N05 1 |
| `repo/.agents/operations/newperiod-storage-recovery-20261023/prune-r3/REVIEW.md` | H01 1 |
| `repo/.agents/operations/newperiod-temporal-20261020/review-request.json` | P07 2 |
| `repo/.agents/operations/newperiod-temporal-completion-capture-20261024/REVIEW.md` | H01 1 |
| `repo/.agents/operations/newperiod-temporal-immediate-launch-20261024/fit-actual-v1/waiter-v1/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-temporal-immediate-launch-20261024/input-audit-actual-v1/review-request.json` | P01 3, P07 6 |
| `repo/.agents/operations/newperiod-temporal-immediate-launch-20261024/input-audit-actual-v1/waiter-v1/root-review.json` | A01 1 |
| `repo/.agents/operations/newperiod-temporal-input-audit-20261020/REVIEW-PACKET.md` | P01 1 |
| `repo/.agents/operations/newperiod-temporal-input-audit-20261020/review-request.json` | P07 2 |
| `repo/.agents/operations/newperiod-temporal-input-completion-capture-20261024/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-temporal-source-audit-20261020/review-request.json` | P07 2 |
| `repo/.agents/operations/newperiod-temporal-source-transport-20261024/REVIEW.md` | N01 1 |
| `repo/.agents/operations/newperiod-temporal-source-transport-20261024/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-temporal-witness-bindings-r2-20261024/actual-witness-v1/root-launch-actual-review.json` | A01 1 |
| `repo/.agents/operations/newperiod-temporal-witness-bindings-r2-20261024/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-temporal-witness-bindings-r2-20261024/root-code-review.json` | A01 1 |
| `repo/.agents/operations/newperiod-temporal-witness-bindings-r2-20261024/witness-plans-capture-v1/review-ready.json` | P07 2 |
| `repo/.agents/operations/newperiod-timing-adoption-evidence-sonnet-v1-20261026/REVIEW.md` | H01 8, H02 1, H03 3, H04 1, N01 1, P07 1, P11 1 |
| `repo/.agents/operations/newperiod-timing-adoption-evidence-sonnet-v10-20261026/REVIEW.md` | H01 11, H02 6, H03 3, H04 3, N01 19, P02 1, P03 1, P06 1, P07 1, P08 2, P11 9 |
| `repo/.agents/operations/newperiod-timing-adoption-evidence-sonnet-v11-20261026/REVIEW.md` | H01 11, H02 6, H03 3, H04 3, N01 19, P02 1, P03 1, P06 1, P07 1, P08 2, P11 9 |
| `repo/.agents/operations/newperiod-timing-adoption-evidence-sonnet-v2-20261026/REVIEW.md` | H01 10, H02 3, H03 3, H04 1, N01 4, P07 1, P11 2 |
| `repo/.agents/operations/newperiod-timing-adoption-evidence-sonnet-v3-20261026/REVIEW.md` | H01 10, H02 5, H03 3, H04 1, N01 11, P02 1, P03 1, P07 1, P11 4 |
| `repo/.agents/operations/newperiod-timing-adoption-evidence-sonnet-v4-20261026/REVIEW.md` | H01 10, H02 5, H03 3, H04 1, N01 14, P02 1, P03 1, P07 1, P11 4 |
| `repo/.agents/operations/newperiod-timing-adoption-evidence-sonnet-v5-20261026/REVIEW.md` | H01 11, H02 6, H03 3, H04 1, N01 18, P02 1, P03 1, P06 1, P07 1, P11 6 |
| `repo/.agents/operations/newperiod-timing-adoption-evidence-sonnet-v6-20261026/REVIEW.md` | H01 11, H02 6, H03 3, H04 3, N01 19, P02 1, P03 1, P06 1, P07 1, P08 2, P11 9 |
| `repo/.agents/operations/newperiod-timing-adoption-evidence-sonnet-v7-20261026/REVIEW.md` | H01 11, H02 6, H03 3, H04 3, N01 19, P02 1, P03 1, P06 1, P07 1, P08 2, P11 9 |
| `repo/.agents/operations/newperiod-timing-adoption-evidence-sonnet-v8-20261026/REVIEW.md` | H01 11, H02 6, H03 3, H04 3, N01 19, P02 1, P03 1, P06 1, P07 1, P08 2, P11 9 |
| `repo/.agents/operations/newperiod-timing-adoption-evidence-sonnet-v9-20261026/REVIEW.md` | H01 11, H02 6, H03 3, H04 3, N01 19, P02 1, P03 1, P06 1, P07 1, P08 2, P11 9 |
| `repo/.agents/operations/newperiod-timing-chain-20261025/REVIEW.md` | A03 1, A04 1 |
| `repo/.agents/operations/newperiod-timing-chain-20261025/review-ready.json` | P07 2 |
| `repo/.agents/operations/newperiod-timing-chain-astra-execution-20261025/review-placement-intent.json` | P01 1, P07 1 |
| `repo/.agents/operations/newperiod-timing-chain-v2-20261025/REVIEW.md` | A03 1, A04 1 |
| `repo/.agents/operations/newperiod-timing-chain-v2-20261025/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-timing-client-r2-20261024/root-code-review.json` | A01 1 |
| `repo/.agents/operations/newperiod-timing-cohort-diagnostic-v1-20261025/REVIEW.md` | N01 1 |
| `repo/.agents/operations/newperiod-timing-cohort-diagnostic-v1-20261025/review-ready.json` | P07 8 |
| `repo/.agents/operations/newperiod-timing-cohort-operator-r2-20261025/REVIEW.md` | N01 1 |
| `repo/.agents/operations/newperiod-timing-cohort-operator-r2-20261025/review-ready.json` | P07 3 |
| `repo/.agents/operations/newperiod-timing-cohort-operator-r3-20261025/review-ready.json` | P07 3 |
| `repo/.agents/operations/newperiod-timing-cohort-operator-r4-20261025/review-ready.json` | P07 8 |
| `repo/.agents/operations/newperiod-timing-d10-capture-once-opus-science-v1-20261026/REVIEW.md` | H01 1 |
| `repo/.agents/operations/newperiod-timing-d300-operator-astra-v28-v1-20261026/REVIEW.md` | H01 1, H02 1 |
| `repo/.agents/operations/newperiod-timing-d300-operator-astra-v28-v4-20261027/REVIEW.md` | N01 1 |
| `repo/.agents/operations/newperiod-timing-d300-operator-astra-v28-v6-20261027/REVIEW.md` | H02 1, N01 1 |
| `repo/.agents/operations/newperiod-timing-d300-successor-astra-v7-20261027/REVIEW.md` | N01 2 |
| `repo/.agents/operations/newperiod-timing-development-budget-r2-20261024/review-ready-stage.json` | P07 1 |
| `repo/.agents/operations/newperiod-timing-development-budget-r2-20261024/review-ready.json` | A01 2 |
| `repo/.agents/operations/newperiod-timing-development-launch-20261024/first-wave-release-v1/review-request.json` | P01 1, P07 4 |
| `repo/.agents/operations/newperiod-timing-development-launch-20261024/first-wave-release-v1/waiter-v1/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-timing-development-launch-20261024/root-actual-stage-held-review.json` | P07 3 |
| `repo/.agents/operations/newperiod-timing-development-launch-20261024/root-code-review.json` | A01 1 |
| `repo/.agents/operations/newperiod-timing-development-r2-20261024/root-code-review.json` | A01 1 |
| `repo/.agents/operations/newperiod-timing-metadata-execution-20261024/review-ready.json` | P07 1 |
| `repo/.agents/operations/newperiod-timing-s2-once-astra-v2-20261026/REVIEW.md` | H01 1, I01 1, I03 1 |
| `repo/.agents/operations/newperiod-timing-shard27-cgroup-review-sol-h3t-v1-20261025/review-v2.json` | A01 3, P07 13 |
| `repo/.agents/operations/newperiod-timing-tn4-gate-memory-qualification-sonnet-v1-20261027/REVIEW.md` | A04 1 |
| `repo/.agents/operations/newperiod-timing-tn4-operator-sonnet-v1-20261026/REVIEW.md` | A04 1 |
| `repo/.agents/operations/newperiod-timing-tn4-operator-sonnet-v2-20261026/REVIEW.md` | A04 1, H02 1 |
| `repo/.agents/operations/newperiod-timing-tn4-operator-sonnet-v3-20261026/REVIEW.md` | A04 1, H01 1, H02 1 |
| `repo/.agents/operations/newperiod-timing-tn4-operator-sonnet-v4-20261026/REVIEW.md` | A04 3 |
| `repo/.agents/operations/newperiod-timing-tn4-operator-sonnet-v5-20261027/REVIEW.md` | A04 1, H01 1 |
| `repo/.agents/operations/newperiod-timing-tn4-operator-sonnet-v6-20261027/REVIEW.md` | A04 1 |
| `repo/.agents/operations/newperiod-timing-tn4-operator-v2-review-sol-final-20261027/tmp-author/test_native_gate_once_end_to_e0/ROOT-GO.json` | P07 17 |
| `repo/.agents/operations/newperiod-timing-tn4-operator-v2-review-sol-final-20261027/tmp-author/test_native_gate_refuses_wrong0/ROOT-GO.json` | P07 17 |
| `repo/.agents/operations/newperiod-timing-tn4-operator-v2-review-sol-final-20261027/tmp-author/test_native_gate_stage_accepts0/ROOT-GO.json` | P07 17 |
| `repo/.agents/operations/newperiod-timing-tn4-operator-v2-review-sol-final-20261027/tmp-author/test_native_release_gate_then_0/ROOT-GO.json` | P07 19 |
| `repo/.agents/operations/newperiod-timing-tn4-sonnet-v1-20261026/REVIEW.md` | A04 1 |
| `repo/.agents/operations/newperiod-timing-tn4-sonnet-v2-20261026/REVIEW.md` | H01 1 |
| `repo/.agents/operations/newperiod-timing-tn4-sonnet-v4-20261026/REVIEW.md` | A04 1 |
| `repo/.agents/operations/newperiod-timing-tr2-sonnet-v1-20261026/REVIEW.md` | A04 1 |
| `repo/.agents/operations/newperiod-timing-tr2-sonnet-v4-20261026/REVIEW.md` | H01 1 |
| `repo/.agents/operations/newperiod-timing-tr2-sonnet-v5-20261026/REVIEW.md` | H01 1, P05 1 |
| `repo/.agents/operations/newperiod-timing-tr2-sonnet-v6-20261027/REVIEW.md` | H01 1, P05 1 |
| `repo/.agents/operations/newperiod-timing-ts4-v1-review-sol-final-20261026/SYNTHETIC-authority-fixture/root-self-execution-review.json` | A01 1, P07 3 |
| `repo/.agents/operations/newperiod-timing-ts4-v1-review-sol-final-20261026/SYNTHETIC-authority-fixture/root-self-review-authority.json` | P07 4 |
| `repo/.agents/operations/newperiod-timing40-operator-astra-v28-v1-20261026/templates/review-capture.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-timing40-operator-astra-v28-v1-20261026/templates/review-release.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-timing40-operator-astra-v28-v1-20261026/templates/review-stage.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-timing40-operator-astra-v28-v1-20261026/templates/review-submit_held.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-timing40-operator-sonnet-v2-20261027/templates/review-capture.FALSE.json` | A01 3, P07 9 |
| `repo/.agents/operations/newperiod-timing40-operator-sonnet-v2-20261027/templates/review-release.FALSE.json` | A01 3, P07 9 |
| `repo/.agents/operations/newperiod-timing40-operator-sonnet-v2-20261027/templates/review-replace_held.FALSE.json` | A01 3, P01 4, P07 9 |
| `repo/.agents/operations/newperiod-timing40-operator-sonnet-v3-20261027/templates/review-capture.FALSE.json` | A01 3, P07 9 |
| `repo/.agents/operations/newperiod-timing40-operator-sonnet-v3-20261027/templates/review-release.FALSE.json` | A01 3, P07 9 |
| `repo/.agents/operations/newperiod-timing40-operator-sonnet-v3-20261027/templates/review-replace_held.FALSE.json` | A01 3, P01 4, P07 9 |
| `repo/.agents/operations/newperiod-timing40-operator-sonnet-v4-20261027/templates/review-capture.FALSE.json` | A01 3, P07 8 |
| `repo/.agents/operations/newperiod-timing40-operator-sonnet-v4-20261027/templates/review-release.FALSE.json` | A01 3, P07 11 |
| `repo/.agents/operations/newperiod-timing40-v3-root-prep-sonnet-20261027/review-replace_held.TEMPLATE.json` | P01 4, P07 11 |
| `repo/.agents/operations/newperiod-validation-calibration-20261022/coordination/review-ready.json` | A01 2 |
| `repo/.agents/operations/newperiod-validation-calibration-20261022/revision-v2/REVIEW.md` | A04 1 |
| `repo/.agents/operations/newperiod-validation-calibration-20261022/revision-v2/coordination/review-ready.json` | A01 2 |
| `repo/.agents/operations/newperiod-variant-source-metadata-capture-20261024/REVIEW.md` | A03 1, H01 1 |
| `repo/.agents/operations/newperiod-variant-source-metadata-capture-20261024/root-actual-capture-review.json` | P01 3, P07 3 |
| `repo/.agents/operations/paper-f1-protocol-timeline-r2-20261022/REVIEW-READY.json` | A01 1 |
| `repo/.agents/operations/paper-f1-protocol-timeline-r2-20261022/REVIEW.md` | A04 1 |
| `repo/.agents/operations/paper-related-work-gate-status-r2-20261022/REVIEW-READY.json` | A01 1 |
| `repo/.agents/operations/paper-related-work-gate-status-r2-20261022/REVIEW.md` | A04 1 |
| `repo/.agents/operations/paper-status-cleanup-r2-20261022/REVIEW.md` | A04 1 |
| `repo/.agents/operations/r1-arm-spec-20261020/REVIEW-PACKET.md` | H01 1 |
| `repo/.agents/operations/r1-critical-path-speedup-20261022/a3-predecessor-capture/REVIEW.md` | A04 1 |
| `repo/.agents/operations/r1-critical-path-speedup-20261022/a3-predecessor-capture/coordination/review-ready.json` | A01 1 |
| `repo/.agents/operations/r1-critical-path-speedup-20261022/budget-r3/REVIEW.md` | A04 1 |
| `repo/.agents/operations/r1-critical-path-speedup-20261022/budget-r3/coordination/review-ready.json` | A01 1 |
| `repo/.agents/operations/r1-critical-path-speedup-20261022/budget-r4/REVIEW.md` | A04 1 |
| `repo/.agents/operations/r1-critical-path-speedup-20261022/budget-r4/coordination/review-ready.json` | A01 1 |
| `repo/.agents/operations/r1-critical-path-speedup-20261022/driver-v8-1-o1/REVIEW.md` | A04 1 |
| `repo/.agents/operations/r1-critical-path-speedup-20261022/driver-v8-1-o1/coordination/review-ready.json` | A01 1 |
| `repo/.agents/operations/r1-critical-path-speedup-20261022/driver-v8/REVIEW.md` | A04 1 |
| `repo/.agents/operations/r1-critical-path-speedup-20261022/final-inventory/REVIEW.md` | A04 1 |
| `repo/.agents/operations/r1-critical-path-speedup-20261022/final-inventory/coordination/review-ready.json` | A01 1 |
| `repo/.agents/operations/r1-critical-path-speedup-20261022/h3-stable-timing/REVIEW.md` | A04 1 |
| `repo/.agents/operations/r1-critical-path-speedup-20261022/recovery-serial-d1-r2/coordination/review-ready.json` | A01 1 |
| `repo/.agents/operations/r1-critical-path-speedup-20261022/recovery-serial-d1/coordination/review-ready.json` | A01 1 |
| `repo/.agents/operations/r1-critical-path-speedup-20261022/s0-host-timing/REVIEW.md` | A04 1, H01 3, N01 1, P03 1, P11 1 |
| `repo/.agents/operations/r1-critical-path-speedup-20261022/s0-host-timing/coordination/review-ready.json` | A01 1 |
| `repo/.agents/operations/r1-critical-path-speedup-20261022/s0b-host-timing/REVIEW.md` | A04 1, H01 2, N01 1 |
| `repo/.agents/operations/r1-critical-path-speedup-20261022/s0b-host-timing/coordination/review-ready.json` | A01 1 |
| `repo/.agents/operations/r1-critical-path-speedup-20261022/s0b-result/REVIEW.md` | H01 1 |
| `repo/.agents/operations/r1-critical-path-speedup-20261022/v8-1-assembly-candidate/REVIEW.md` | A04 1 |
| `repo/.agents/operations/r1-critical-path-speedup-20261022/v8-1-assembly-candidate/coordination/review-ready.json` | A01 1 |
| `repo/.agents/operations/r1-critical-path-speedup-20261022/v8-assembly-candidate/REVIEW.md` | A04 1 |
| `repo/.agents/operations/r1-critical-path-speedup-20261022/v8-assembly-candidate/coordination/review-ready.json` | A01 1 |
| `repo/.agents/operations/r1-critical-path-speedup-20261022/v8-assembly-r2/REVIEW.md` | A04 1 |
| `repo/.agents/operations/r1-critical-path-speedup-20261022/v8-assembly-r2/coordination/review-ready.json` | A01 1 |
| `repo/.agents/operations/r1-critical-path-speedup-20261022/v8-assembly-r3/REVIEW.md` | A04 1, H01 1, N01 1 |
| `repo/.agents/operations/r1-critical-path-speedup-20261022/v8-assembly-r3/coordination/review-ready.json` | A01 1 |
| `repo/.agents/operations/r1-critical-path-speedup-20261022/v8-postprep-candidate/REVIEW.md` | A04 1 |
| `repo/.agents/operations/r1-critical-path-speedup-20261022/v8-postprep-candidate/coordination/review-ready.json` | A01 1 |
| `repo/.agents/operations/r1-critical-path-speedup-20261022/v8-postprep-candidate/tools/evaluation/review-pins.json` | A01 1 |
| `repo/.agents/operations/r1-critical-path-speedup-20261022/v8-postprep-resolved/REVIEW-READY.json` | A01 2 |
| `repo/.agents/operations/r1-critical-path-speedup-20261022/v8-postprep-resolved/REVIEW.md` | A04 1 |
| `repo/.agents/operations/r1-critical-path-speedup-20261022/v8-postprep-resolved/tools/evaluation/review-pins.json` | A01 1 |
| `repo/.agents/operations/r1-critical-path-speedup-20261022/v8-preparation-candidate/REVIEW.md` | A04 1 |
| `repo/.agents/operations/r1-critical-path-speedup-20261022/v8-preparation-candidate/coordination/review-ready.json` | A01 1 |
| `repo/.agents/operations/r1-evaluation-v6-20261021/REVIEW.md` | A01 3 |
| `repo/.agents/operations/r1-evaluation-v6-20261021/review-pins.json` | A01 1 |
| `repo/.agents/operations/r1-evaluation-v7-20261022/REVIEW.md` | A01 1, A04 1 |
| `repo/.agents/operations/r1-evaluation-v7-20261022/coordination/review-ready.json` | A01 2 |
| `repo/.agents/operations/r1-evaluation-v7-20261022/review-pins.json` | A01 1 |
| `repo/.agents/operations/r1-full-custody-preflight-20261020/REVIEW-PACKET.md` | H01 2, N01 1, P01 1 |
| `repo/.agents/operations/r1-full-custody-preflight-20261020/code-review-state/REVIEW-PACKET.md` | H01 1, N01 1, P01 1 |
| `repo/.agents/operations/r1-paper-integration-20261024/review-ready.json` | P07 1 |
| `repo/.agents/operations/r1-paper-integration-20261024/revision-v2/review-ready.json` | P07 1 |
| `repo/.agents/operations/r1-parquet-schema-20261020/REVIEW-PACKET.md` | H01 1 |
| `repo/.agents/operations/r1-posteval-verification-20261022/REVIEW.md` | A04 1, H01 1, N01 1 |
| `repo/.agents/operations/r1-posteval-verification-20261022/adapter-r2/REVIEW.md` | A04 1 |
| `repo/.agents/operations/r1-posteval-verification-20261022/adapter-r2/coordination/review-ready.json` | A01 1 |
| `repo/.agents/operations/r1-posteval-verification-20261022/adapter/REVIEW.md` | A04 1, P03 1, P11 1 |
| `repo/.agents/operations/r1-posteval-verification-20261022/adapter/coordination/review-ready.json` | A01 1 |
| `repo/.agents/operations/r1-posteval-verification-20261022/classd-host/REVIEW.md` | A04 1, H01 1, N01 1 |
| `repo/.agents/operations/r1-posteval-verification-20261022/classd-host/coordination/review-ready.json` | A01 1 |
| `repo/.agents/operations/r1-posteval-verification-20261022/d2-host-r2/REVIEW.md` | A04 1 |
| `repo/.agents/operations/r1-posteval-verification-20261022/d2-host-r2/coordination/review-ready.json` | A01 1 |
| `repo/.agents/operations/r1-posteval-verification-20261022/d2-host/REVIEW.md` | A04 1, H02 1 |
| `repo/.agents/operations/r1-posteval-verification-20261022/d2-host/coordination/review-ready.json` | A01 1 |
| `repo/.agents/operations/r1-posteval-verification-20261022/k2c/REVIEW.md` | A04 1, P01 1, P07 1 |
| `repo/.agents/operations/r1-posteval-verification-20261022/verifier-r2/REVIEW.md` | A04 1 |
| `repo/.agents/operations/r1-posteval-verification-20261022/verifier-r2/coordination/review-ready.json` | A01 1 |
| `repo/.agents/operations/r1-posteval-verification-20261022/verifier/REVIEW.md` | A04 1, P03 1, P11 1 |
| `repo/.agents/operations/r1-posteval-verification-20261022/vrun-host/REVIEW.md` | A04 1, H01 1, H02 2, P01 1, P03 1, P11 1 |
| `repo/.agents/operations/r1-posteval-verification-20261022/vrun-host/coordination/review-ready.json` | A01 1 |
| `repo/.agents/operations/r1-posteval-verification-v10-20261023/REVIEW.md` | H01 1 |
| `repo/.agents/operations/r1-posteval-verification-v8-20261022/REVIEW.md` | A04 1 |
| `repo/.agents/operations/r1-posteval-verification-v8-20261022/coordination/review-ready.json` | A01 1, P07 1 |
| `repo/.agents/operations/r1-posteval-verification-v8-resolution-20261022/REVIEW-READY.json` | A01 1 |
| `repo/.agents/operations/r1-posteval-verification-v8-resolution-20261022/REVIEW.md` | A04 1 |
| `repo/.agents/operations/r1-preparation-failure-v5-20261021/tier1-capture/REVIEW.md` | H01 3, N01 1 |
| `repo/.agents/operations/r1-preparation-failure-v6-20261021/census/REVIEW.md` | A01 1 |
| `repo/.agents/operations/r1-preparation-failure-v6-20261021/preflight-r2/REVIEW.md` | A01 1, H01 1 |
| `repo/.agents/operations/r1-preparation-failure-v6-20261021/preflight-r3/REVIEW.md` | A01 1 |
| `repo/.agents/operations/r1-preparation-failure-v6-20261021/preflight/REVIEW.md` | A01 1, H01 2, N01 1 |
| `repo/.agents/operations/r1-preparation-transaction-20261020/execution-v1/REVIEW-CODE.md` | H01 1, N01 1, P01 1 |
| `repo/.agents/operations/r1-recovery-assembly-20261021/REVIEW-CONTROLS.md` | P01 1 |
| `repo/.agents/operations/r1-recovery-assembly-20261021/REVIEW-SOURCE-RESOURCE.md` | P01 1 |
| `repo/.agents/operations/r1-release-assembly-20261020/REVIEW-RESOURCE-V2.md` | P01 1, P06 1 |
| `repo/.agents/operations/r1-release-assembly-20261020/REVIEW-SOURCE-V2.md` | N01 1, P01 1 |
| `repo/.agents/operations/r1-release-assembly-20261020/reviews/source-v2-round1/REVIEW-SOURCE-V2.md` | N01 1, P01 1 |
| `repo/.agents/operations/r1-release-v5-20261021/REVIEW.md` | A01 3, P01 1 |
| `repo/.agents/operations/r1-release-v6-20261021/REVIEW.md` | A01 1, P01 1 |
| `repo/.agents/operations/r1-release-v6-20261021/builder-b1/REVIEW.md` | N01 1 |
| `repo/.agents/operations/r1-release-v7-20261022/REVIEW.md` | A01 1, P01 1 |
| `repo/.agents/operations/r1-release-v7-transition-20261022/REVIEW.md` | A04 1, H01 1 |
| `repo/.agents/operations/r1-release-v7-transition-20261022/coordination/review-ready.json` | A01 2 |
| `repo/.agents/operations/r1-resource-inventory-20261020/review-request.json` | P07 2 |
| `repo/.agents/operations/r1-synthetic-runtime-parity-20261023/REVIEW.md` | H01 7 |
| `repo/.agents/operations/r1-synthetic-runtime-parity-20261023/review-ready.json` | H01 3 |
| `repo/.agents/operations/r1-v10-waiting-array-cleanup-20261024/REVIEW.md` | N01 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/d0d1-fix-v1/review-ready.json` | A01 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/d2-fix-v1/review-ready.json` | A01 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/d2-fix-v2/REVIEW.md` | H01 1, P02 1, P11 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/d2-fix-v2/review-ready.json` | A01 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/d2-fix-v2/root-current-review-response.json` | P07 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/d2-fix-v3/review-ready.json` | A01 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/d2-fix-v4/review-ready.json` | A01 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/d2-fix-v5/review-ready.json` | A01 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/evidence/released/report.json` | P01 2 |
| `repo/.agents/operations/r1-v11-posteval-20261024/evidence/released/retrospective-2025-v6-d30.json` | P01 8,415 |
| `repo/.agents/operations/r1-v11-posteval-20261024/evidence/released/retrospective-2025-v6-d60.json` | P01 8,415 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/d0d1-actual-assessment.txt` | A04 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/d0d1-capture-and-transport-assessment.txt` | A04 1, N01 1, P01 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/d0d1-fix-and-vrun-diagnostic-review.txt` | A04 1, H04 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/d2-actual-assessment-v1.json` | A01 1, P01 2, P07 2 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/d2-actual-assessment.txt` | A04 1, H04 2 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/d2-fix-v2-link-census-review.txt` | A04 1, H01 1, N01 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/d2-fix-v3-review.txt` | A04 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/d2-oom-and-d2-fix-v4-review.txt` | A04 1, H04 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/k1-census-assessment.txt` | A04 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/k2a-transport-assessment-and-k2b.txt` | A04 1, N01 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/k2b-assessment.txt` | A04 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/link-census-actual-assessment.txt` | A04 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/next-step-review.txt` | A04 1, P05 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/opus-classd-transport-approval-v11.json` | A01 2, P01 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/opus-d0-d1-approval-v11.json` | A01 2, P01 8, P11 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/opus-d0-readback-d1-approval-v11-r2.json` | A01 2, P01 8 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/opus-d0d1-fetch-approval-v11-r2.json` | A01 2, P01 2, P07 3 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/opus-d0d1-fetch-approval-v11.json` | A01 2, P01 2, P07 2 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/opus-d2-link-census-approval-v11.json` | A01 2, H01 1, P01 1, P03 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/opus-d2-run-approval-v11-r5.json` | A01 2, P01 6 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/opus-d2-run-approval-v11.json` | A01 2, P01 6 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/opus-k1-census-approval-v11.json` | A01 2, P01 7 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/opus-k2a-capture-approval-v11-r2.json` | A01 2, P01 2, P07 4 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/opus-k2a-capture-approval-v11.json` | A01 2, P01 2, P07 3 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/opus-k2b-capture-approval-v11.json` | A01 2, P01 3, P07 3 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/opus-r1-receipt-publication-approval-v1.json` | A01 2, P01 1, P07 2 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/opus-vrun-approval-v11.json` | A01 2, P01 11 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/opus-vrun-diagnostic-approval-v11.json` | A01 2, H01 1, P01 1, P07 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/opus-vrun-r2-approval-v11.json` | A01 2, P01 11 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/opus-vrun-r2-transport-approval-v11.json` | A01 2, P01 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/r1-publication-actual-assessment.txt` | A04 1, P05 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/r1-receipt-final-review.txt` | A04 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/release-draft-v1-review.txt` | A04 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/release-native-v2-review.txt` | A04 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/release-publication-code-review.txt` | A04 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/review.txt` | A01 2 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/reviewer-response-d0d1-vrun-stage.json` | A01 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/reviewer-response-d1-vrun.json` | A01 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/reviewer-response-fix-diag.json` | A01 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/reviewer-response-k2a-r2.json` | A01 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/reviewer-response-release-k2b.json` | A01 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/reviewer-response-vrun-r2-d1.json` | A01 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/reviewer-response-vrunfix.json` | A01 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/verdict.json` | A01 2 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/vrun-failure-finding.txt` | A04 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/vrun-fix-d2-fix-review.txt` | A04 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/independent-opus-review-v1/vrun-r2-actual-assessment.txt` | A04 1, H04 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/release-actual-v1/r1-retrospective-release.json` | P01 13, P07 6 |
| `repo/.agents/operations/r1-v11-posteval-20261024/release-draft-v1/review-ready.json` | A01 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/release-native-v2/REVIEW.md` | A01 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/release-native-v2/publication/REVIEW.md` | H01 1 |
| `repo/.agents/operations/r1-v11-posteval-20261024/review-ready.json` | A01 2 |
| `repo/.agents/operations/r1-v11-posteval-20261024/vrun-fix-v1/review-ready.json` | A01 1 |
| `repo/docs/paper/forecasting-improvement-20261017/ALL-RECIPES-FREEZE-RECEIPT-20261019.json` | P01 21 |
| `repo/docs/paper/forecasting-improvement-20261017/EXPOSURE-LEDGER-DRAFT.json` | H01 1, H03 1, P11 1 |
| `repo/docs/paper/newperiod-final-20261030/facts/facts.json` | P01 1 |
| `repo/docs/paper/r2-report-20261030/primary.json` | P01 1 |
| `repo/paper/generated/allowlist_by_year.json` | P03 14, P11 14 |
| `repo/paper/generated/newperiod-lanes.json` | P01 14 |
| `repo/paper/generated/roa_anchor_check.json` | H01 2, P01 35, P02 9, P11 9 |
| `repo/scratch/experiment-finish-20261030/audit/validate_final_data.py` | P01 17, P03 1, P05 1 |
| `repo/scratch/experiment-finish-20261030/code-backup/docs/experiment-completion-20261030/deviation-D-A39.md` | N05 1 |
| `repo/scratch/experiment-finish-20261030/code-backup/docs/experiment-completion-20261030/runner-review.md` | H02 1, P03 1 |
| `repo/scratch/experiment-finish-20261030/code-backup/docs/experiment-completion-20261030/scientific-closure.json` | P01 91 |
| `repo/scratch/experiment-finish-20261030/review-combined-final.md` | H02 1, P03 1 |
| `repo/scratch/experiment-finish-20261030/review-validator-snapshot-rev4.py` | P01 17, P03 1, P05 1 |
| `repo/scratch/experiment-finish-20261030/review-validator-snapshot-rev5.py` | P01 17, P03 1, P05 1 |
| `repo/scratch/experiment-finish-20261030/review-validator-snapshot-v2.py` | P01 17, P03 1, P05 1 |
| `repo/scratch/experiment-finish-20261030/review-validator-snapshot.py` | H01 1, P01 1, P03 1, P05 1 |
| `repo/scripts/paper_allowlist_by_year.py` | H01 2, P02 2, P03 2, P11 4 |
| `repo/scripts/paper_month_boundary.py` | P05 2 |
| `repo/scripts/paper_roa_anchor_check.py` | H01 1, P01 1, P02 1, P03 1, P11 2 |
| `repo/src/bgbench/config.py` | H01 1, P02 1, P03 2, P11 3 |
| `repo/src/bgbench/forecast_retrospective_custody.py` | P01 1 |
| `repo/src/bgbench/parse.py` | P03 1, P11 1 |
| `repo/src/bgbench/ranking.py` | N05 1 |
