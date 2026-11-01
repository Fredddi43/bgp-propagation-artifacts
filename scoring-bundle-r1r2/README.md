# R1/R2 scoring bundle

This directory is the anonymized scoring bundle of the retrospective (R1) and new-period (R2) forecast evaluations.

- `MANIFEST.json`: every file with its size, SHA-256, component, role and source; for redacted files also the SHA-256 of
  the original bytes; the hash checks made at assembly; the list of excluded items.
- `REDACTIONS.md`: the anonymization rules and the number of replacements per rule and per file.
- `LICENSE`: MIT licence of the code.
- `cluster/`: files of the evaluation's data store. The directory mirrors the store's forecasting root, which the records
  call `<FORECAST_ROOT>`: a path `<FORECAST_ROOT>/x` in any record is the file `cluster/x` here.
- `repo/`: files of the source repository at their repository paths (code, records, paper outputs). A path `<REPO>/x` in
  a record is `repo/x` here.
- `leak-audit-data/`: the store inputs of the leak audit (`paper_leak_audit.py --data`): `leak_events/`, `triples/` and
  `labels/`. A path `<data>/x` in `leak_audit.json` is `leak-audit-data/x` here.

**Size:** 3,288 files, 36,538,293,157 bytes (36.5 GB), including the four top-level documents
(`README.md`, `MANIFEST.json`, `REDACTIONS.md`, `LICENSE`), which `MANIFEST.json` does not list.

## What is included

| Component | Contents | Files | Bytes |
|---|---|---|---|
| `r2_results` | R2 primary result of attempt 12, its per-event scores and intent; local copies of `primary.json` and the facts projection | 5 | 54,313,721 |
| `r2_secondary` | D-A39 re-scoring records and the nine family files with their manifests; D-A40 stable-lane records | 35 | 6,203,266,755 |
| `r2_lanes` | the paper's lane table and its JSON | 3 | 107,693 |
| `lane_extraction` | D-A39 and D-A40 lane extractions: scripts, inputs and outputs, validator rev5 runs | 47 | 1,321,930 |
| `r2_labels` | R2 label table and G4 receipt | 2 | 611,351,309 |
| `access_log` | custodian access log | 1 | 10,651,188,863 |
| `ledgers` | freezes, seal, arm spec, marker, execution spec, evidence build, deviation ledger, R1 ledgers | 28 | 464,920,103 |
| `approvals` | D-A39 and D-A40 approvals, dry-run records, run logs; R1 authorization and publication approval | 19 | 164,631 |
| `r1_results` | R1 report, cohort manifests, release records, arm spec, completion record | 7 | 24,782,903 |
| `r1_forecasts` | R1 per-event score tables (1,066) and the R1 prediction ledger | 1,067 | 18,181,354,582 |
| `r1_rank_sidecar` | R1 ranking file (121 MB): per R1 cell and event, the tie groups holding new members, plus target and input-seen sets; `scripts/r1_rank_sidecar_check.py` recomputes AP, P@k, recall@k and coverage and matches every released value (1,008 of 1,032 ranking cells; the forecasts of 24 history-baseline cells of the delay/withholding sensitivity no longer exist) | 18 | 121,554,537 |
| `r1_labels` | R1 seal and label-access records | 4 | 2,894,205 |
| `evaluator` | R2 runner, chain code (attempt 12, D-A39, D-A40), G2 tools, validator, completion records, 90 closure sources | 243 | 2,806,050 |
| `wrappers` | in-process wrappers of the evaluator | 23 | 124,243 |
| `review_records` | review and approval records of the R1 and R2 steps | 1,689 | 6,568,490 |
| `analysis_over_bundle` | paper analyses that read the bundle, and their outputs | 54 | 20,166,561 |
| `leak_audit_data` | leak-audit store inputs: leak-event and new-triple tables (pipeline-derived), Cloudflare Radar route-leak labels (CC BY-NC 4.0) | 24 | 188,924,927 |
| `paper_sections` | paper section source (`paper/sections/*.tex`) and `paper/refs.bib` at the repository's current commit | 15 | 307,548 |

In detail:

- **R2 primary result** (`cluster/data-custodian/single-R2-v1/arms/000/attempt/`): `primary.json` of attempt 12 (the
  confirmatory primary report), `primary-scores.json` (per-event primary scores: AP, Jaccard, seed ASes; no forecast
  sets) and the attempt's `intent.json`.
- **R2 secondary lanes, D-A39 re-scoring** (`.../rescore-secondary-D-A39/`): `completion.json`, `intent.json`,
  `second-label-read-D-A39.json` (the one approved second label read), `primary-recomputed-D-A39.json` and the recomputed
  `primary-scores.json`, the nine family files `families/<family>.pkl.part0000` with their `families/<family>.manifest.json`,
  and the manifest of the raw secondary pickle. The lane extraction that the paper's lane table is built from is in
  `cluster/d-a39-lane-extract-20261101/` (scripts, outputs and the two validator runs) and
  `repo/paper/generated/newperiod-lanes.{json,tex}`.
- **R2 stable lane, D-A40 re-scoring** (`cluster/data-custodian/single-R2-v1/arms/000/rescore-stable-D-A40/`): the
  disclosed re-scoring of the stable-peer lane after its D-A39 failure, with one approved third label read:
  `completion.json` (passed), `done.json`, `intent.json`, `third-label-read-D-A40.json`, `primary-recomputed-D-A40.json`,
  the recomputed `primary-scores.json`, `stable-result.json`, the raw stable pickle with its manifest, and
  `families/stable.{manifest.json,pkl.part0000}`. The lane extraction of both re-scorings is in
  `cluster/d-a40-lane-extract-20261101/`; its `build_lanes.py` supersedes the copy in `d-a39-lane-extract-20261101/`.
- **R2 labels**: `cluster/data-custodian/complete-label-preparation-v3-retained/arms/000/attempt/output/labels.json`
  (the G4 label table, derived from public archives) and its G4 receipt.
- **Ledgers**: the G1 freeze as published, the amended freeze, the G3 seal and its receipt, the R2 arm specification,
  the one-opening marker of attempt 12, the R2 execution spec, the R2 evidence build (`r2-evidence-20261030T0440Z/`), the
  deviation ledger (`repo/.agents/operations/agy-lanes-20261027/qwen/q11-deviations/DEVIATIONS-LEDGER.md`, entries D-A1 to
  D-A39), the custodian freeze of 17 October, the recipe freeze receipt, the exposure ledger draft, and the R1 ledgers
  (retained-arm ledger, source audit, training integration gate, code source manifest).
- **Approvals**: the D-A39 approval, the records of the label-free dry run 52725204 (`ready.json`, `done.json`,
  `intent.json`), the logs of the dry run and of the one label-opening run 52728251; the same for D-A40 (approval,
  dry run 52748137, label-opening run 52750274); and the R1 authorization and publication approval.
- **Access log**: `cluster/data-custodian/newperiod-identification-v1/access-log.jsonl`, the custodian access log, complete
  as of the end of D-A39 (2026-10-31T21:43Z). About 19 % of its lines are interleaved or truncated writes; they are kept
  as written.
- **R1 results and scores**: the R1 report, the two cohort manifests, the release record, the arm specification, the R1
  completion record, and the 1,066 per-event score tables
  (`cluster/r1-release-parallel-v11-20261024/control-v1/results/per_event/`, one file per retained cell; each matches the
  digest in the report's `per_event_sha256`). Also the R1 prediction ledger and the R1 seal, which bind the excluded R1
  forecasts by hash (the seal also binds the label files of the count cells and the stable-peer target tables), and
  the R1 label-access records.
- **Evaluator and wrappers** (`repo/`): the pinned one-shot R2 runner, the R2 chain of attempt 12
  (`.agents/operations/agy-lanes-20261027/g2r2/chain/`), the reviewed D-A39 successor chain (`.../chain-d39-v2/`) with
  the in-process wrappers, the reviewed D-A40 chain (`.../chain-d40/`, driver `r2_rescore_stable.py` with
  `r2_stable_not_scorable.py` and `r2_rescore_stable.sbatch`), the G2 tools, the runbook and design records, the final data validator (rev5), the D-A39
  code-backup completion records, and all 90 source files of the evaluator's scientific closure (`repo/src/bgbench/`),
  each original matching the hash in `scientific-closure.json` (a few carry redactions in comments; see
  `pre_redaction_sha256`).
- **Review records**: the review and approval records of the R1 and R2 steps (`REVIEW*`, `ROOT-GO*`,
  `ROOT-SIGNATURE*`, `review-*.json`), the independent review of the R1 release, and the reviews of the D-A39 code and
  of the data validator.
- **R1 ranking file** (`cluster/r1-rank-sidecar-20261101/`): `sidecar/{cells,events,sets}.parquet` with its
  `MANIFEST.json`, the README, the build scripts and the checker results; the checker is
  `repo/scripts/r1_rank_sidecar_check.py`. It replaces the raw R1 forecasts for the ranking metrics.
- **Paper analyses over the bundle**: every revision analysis, with its script under `repo/scripts/` and its outputs
  under `repo/paper/generated/` (table below), plus the generated facts two of them read (`propagation-facts.json`,
  `frontier_facts.json`) and `paper_propagation_tables.py`, which the onset analyses import.
- **Leak-audit inputs** (`leak-audit-data/`): the month leak-event tables of the identifier (`leak_events/`), the month
  new-triple tables (`triples/`), both derived by the pipeline, and the Cloudflare Radar route-leak labels with the replay
  selection (`labels/`; Cloudflare Radar, CC BY-NC 4.0). Each file that `leak_audit.json` cites matches its recorded hash.
- **Paper sections**: `repo/paper/sections/*.tex` and `repo/paper/refs.bib` at the repository's current commit.

## What is excluded, and why

| Item | Size | Why | Bound by (included) |
|---|---|---|---|
| R1 raw forecasts (per-candidate probabilities and committed sets) | 432,123,440,381 bytes | Not released; the R1 ranking file replaces them for the ranking metrics. The forecasts of 24 cells no longer exist. | R1 prediction ledger (`.../derived/evaluation/ledger.json`, SHA-256 `5575ebb3ad13b117ce02de2f342da321c3fa4c7b836b04be3df39766960e70c6`) and the R1 seal (per-cell `commitment_sha256`, `predictions_sha256`) |
| R1 label inputs (retained per-cell label files) | not measured | Custody-store files, not assembled as one table; the per-event score tables and cohort manifests are included. Available on request. | R1 seal (`labels` of the count cells, `stable_target_table` of the stable-peer cells) and R1 spec (SHA-256 `134d74fb72dd8d4940adb52bb0bdc11d0f7948cfad0560324275d711a219f887`) |
| R2 sealed forecasts, `predictions.json` of the 345 sealed arms | 425,467,553,865 bytes | Not released; the per-event primary scores (`primary-scores.json`) and the secondary family results are included. | `seal.json`, `predictions_sha256` per arm |
| R2 sealed forecasts, `commitment.json` of the 345 sealed arms | 5,085,299,491 bytes | Not released. | `seal.json`, `commitment_sha256` per arm |
| D-A39 `secondary-result.json` | 13,811,479,924 bytes, SHA-256 `47479a9f8a337109ecc4dbb383d16da90fdbc749cf96459d022e1101db9e0d9e` | Size: the bundle exceeds about 20 GB even without it, so the nine per-family files with their manifests and the compact lane extraction are released instead; they carry the same family results. | `completion.json` (`secondary_result`) |
| D-A39 `secondary-result-raw.pkl.part0000` | 6,027,451,047 bytes, SHA-256 `af5113d3193f7040c4c44b497e50d7c43684e7fb2a8da01097baaa6629ee968f` | Holds the same families as the included per-family pickles. | `secondary-result-raw.manifest.json`, `completion.json` (`raw_result`) |
| Run specifications and read inventories of attempt 12, the D-A39 and the D-A40 runs (`r2-inventory.json`, `spec.json`, `read-inventory.json`, `template.json`, `work/`) | the large ones about 120 to 130 MB each | Run plumbing; the pinned R2 execution spec is included. Available on request. | `ready.json`, run records |
| CAIDA AS-to-organisation files `20250901`, `20251001`, `20251101`, `20251201` `.as-org2info.txt.gz` (input of `paper_leak_audit.py --as2org`) | not redistributed | CAIDA Acceptable Use Agreement. Obtain them from <https://publicdata.caida.org/datasets/as-organizations/>; SHA-256 below. | `repo/paper/generated/leak_audit.json` (`inputs_sha256`) |
| CAIDA AS-relationship files `YYYYMM01.as-rel.v6-stable.txt.bz2`, 202508 to 202601 (input of `paper_leak_audit.py --asrel-v6`) | not redistributed | CAIDA Acceptable Use Agreement. Obtain them from <https://publicdata.caida.org/datasets/as-relationships/serial-1/>; SHA-256 below. | `repo/paper/generated/leak_audit.json` (`inputs_sha256`) |
| CAIDA-derived relationship tables `graphs/YYYYMM01.rel.parquet`, 202508 to 202601 (the `graphs/` part of `paper_leak_audit.py --data`) | not redistributed | Built from CAIDA serial-1 AS-relationship files (<https://publicdata.caida.org/datasets/as-relationships/serial-1/>) with `bgbench.leakcheck.relationship_table`; CAIDA Acceptable Use Agreement. SHA-256 below. | `leak_audit.json` (`inputs_sha256`) |
| RIPEstat BGPlay downloads of `paper_leak_audit.py --ris` (207 files and their `MANIFEST.json`, about 913 MB) | not included | Public and re-fetchable: `--ris <dir> --ris-fetch` downloads them again; their `MANIFEST.json` records URL, fetch time and SHA-256 of each file. | `leak_audit.json` (`inputs_sha256`), `<ris>/MANIFEST.json` SHA-256 `2dcad61825c8bc7f504cc1fca928bc46f8e6a9a8f990848b2c72f37077a62213` |
| Eight synthetic `ROOT-GO.json` test fixtures in pytest temporary directories of two review runs | small | Test output, not review records. | none |

Also not included: raw MRT archives, model checkpoints, credentials and the private repository history. The public data
products of the 16 October package are not repeated here; several analyses read its `data/` tree (below).

## Restoring the files

In the published copy, every file larger than 7,000,000 bytes is stored compressed with xz and, where still larger,
split into numbered parts (`<path>.xz` or `<path>.xz.part0000`, `.part0001`, ...). `PUBLISHED.json` lists every
published file with its size and SHA-256, and `shards.json` lists each compressed file with its parts. Run

```bash
python3 restore_bundle.py
```

from any directory (Python 3.8 or later, standard library only). It checks every published file, joins and decompresses
the parts, checks each restored file against `MANIFEST.json`, and writes it at the path that `MANIFEST.json` names. The
restored files need about 36 GB of free disk space.

## Anonymization and hashes

Identity markers (names, user and host names, institution, storage and home paths, the private project name, e-mail
addresses, AI agent session identifiers and tooling names) were replaced by placeholders such as `<FORECAST_ROOT>`, `<USER>` or `<SESSION_ID>`,
in copies. `REDACTIONS.md` lists the rules and every replacement count. Event identifiers, AS numbers, prefixes,
timestamps, job numbers and hashes are unchanged. In the access log, the interleaved lines also hold truncated pieces of
paths; pieces long enough to recognize were replaced as well, shorter ones (a few letters) were left.

The records cite each other by SHA-256 (the seal binds the freeze, the marker binds the seal and the labels, receipts
bind outputs, the R1 report binds the per-event tables). Those citations refer to the **original** bytes. When redaction
changed a file, `MANIFEST.json` gives both `sha256` (the released bytes) and `pre_redaction_sha256` (the original
bytes, the value the citations use). Every file taken from the store was checked against the store's own `sha256sum` at
fetch time, and every original, from the store or the repository, against each hash recorded for it in another record
(the R1 report's per-event digests, the evaluator's closure list, the family manifests, the validator's pins, the
release records); the results are in `hash_checks`, and all passed. Repository files that no record cites have no check
beyond their hash. A file without `pre_redaction_sha256` is
byte-identical to the original.

Some pickles (listed in `REDACTIONS.md`, section "Binary files") held storage paths inside string values. They were
redacted with same-length placeholders padded with underscores (for example `<FORECAST_ROOT______...>`), so they still
load and every other byte is unchanged; their manifests still name the original hash.

Scripts that embed store paths now carry placeholders. To run one against this bundle, re-root the placeholder in a copy,
for example:

```bash
sed "s#<FORECAST_ROOT>#$PWD/cluster#g" cluster/d-a39-lane-extract-20261101/scripts/extract_lanes.py > /tmp/extract_lanes.py
```

## Reproducing the paper's tables from the included scores

Python 3.12 or later. The R2 table scripts and `build_lanes.py` use the standard library only. Re-deriving the lane
extraction and the revision analyses need `numpy`; the analyses that read `--r1-events` or `--eventset-root` also need
`polars`. The pinned versions are in `requirements.txt` of the 16 October package.
Run from the bundle root unless noted; `$B` is the absolute path of the bundle root.

### R2 primary table (`tab:r2`, `paper/generated/newperiod-table.tex`)

```bash
cd "$B/repo"
python3 -B .agents/operations/agy-lanes-20261027/g2r2/chain/r2_primary_facts.py \
    "$B/cluster/data-custodian/single-R2-v1/arms/000/attempt/primary.json" /tmp/r2-facts \
    --expected-report-sha256 4e2a8739705fc7a1a2416b72813b5c1f704c0f1df406f11b1311d397742ad697
python3 -B scripts/paper_r2_table.py /tmp/r2-facts/facts.json --out-dir /tmp/r2-tables
diff /tmp/r2-tables/newperiod-table.tex paper/generated/newperiod-table.tex
```

`r2_primary_facts.py` projects the confirmatory primary report with the reviewed projection
(`src/bgbench/forecast_release_facts.py`, `forecast_full_report_facts.py`, with the d60-only patches of `d60_only.py`);
it computes nothing new. `--expected-report-sha256` takes the hash of the released `primary.json` (above); the original
bytes have `849e064518d1aa7e0b1c61c4c5836acd75864de12dce0278dab75918493e9ac1`. Use a fresh `--out-dir`:
`paper_r2_table.py` deletes `newperiod-lanes.tex` in its output directory when the facts hold no lane section, which is
the case for the primary-only facts. Checked when the bundle was assembled: the regenerated `newperiod-table.tex` is byte-identical to `repo/paper/generated/newperiod-table.tex`.

### R2 lane table (`tab:r2-lanes`, `paper/generated/newperiod-lanes.tex`)

The lane table copies recorded values from the D-A39 family files and the D-A40 stable record; no metric is recomputed.
The extraction directory holds every input of the builder (`extract-full.json`, `extract-stable-d40.json`,
`stable-narrow-v2.json`, `sha256-small.txt`, `stat.txt`, `manifests/`, the D-A39 `completion.json`, the D-A39 run log and
the two validator runs):

```bash
X="$B/cluster/d-a40-lane-extract-20261101"
python3 -I "$X/scripts/build_lanes.py" "$X/out" /tmp/newperiod-lanes.json /tmp/newperiod-lanes.tex
diff /tmp/newperiod-lanes.tex "$B/repo/paper/generated/newperiod-lanes.tex"
```

Checked when the bundle was assembled: the regenerated `newperiod-lanes.tex` is byte-identical to `repo/paper/generated/newperiod-lanes.tex`, and the regenerated JSON equals `repo/paper/generated/newperiod-lanes.json` except for `generated_utc`.

To re-derive `extract-full.json` (D-A39 families), `stable-narrow-v2.json` and `extract-stable-d40.json` (D-A40 stable
lane) from the pickles, re-root `extract_lanes.py`, `stable_narrow.py` (in `d-a39-lane-extract-20261101/scripts/`) and
`extract_stable_d40.py` as shown above and run them with `numpy` and `repo/src` on `PYTHONPATH`
(`python -I -B <script> <out.json>`). They verify each pickle against its family manifest, which binds the original
bytes, so for a redacted pickle the check fails by design; compare it with `pre_redaction_sha256` in `MANIFEST.json`
instead.

### R1 ranking metrics from the R1 ranking file

```bash
cd "$B/repo"
python3 -I -B scripts/r1_rank_sidecar_check.py --sidecar "$B/cluster/r1-rank-sidecar-20261101/sidecar" \
    --per-event "$B/cluster/r1-release-parallel-v11-20261024/control-v1/results/per_event" \
    --report .agents/operations/r1-v11-posteval-20261024/evidence/released/report.json --mode groups --out /tmp/r1-rank-check.json
```

It needs `numpy` and `polars`. `--mode entry` calls the evaluator's per-event metric function itself and is about ten
times slower. The 24 cells whose forecasts no longer exist are reported as gaps, so the result reads `passed: true`,
`complete: false`. Checked on this bundle's own files when it was assembled: `--mode groups` compared 32,193,080 fields of the 1,008 ranking cells with 0 mismatches, matched all 1,066 per-event files to the report's digests, and reported the 24 gap cells (282 s with 8 workers). Its result records the hash of the released, redacted report, not the original `049c7a9c...`.

### Revision analyses (`repo/scripts/`, outputs in `repo/paper/generated/`)

Common inputs, with `R1=cluster/r1-release-parallel-v11-20261024/control-v1` and run from `repo/`:

- `--r1-report .agents/operations/r1-v11-posteval-20261024/evidence/released/report.json`
- `--r1-per-event $B/$R1/results/per_event`
- `--r1-arm-spec .agents/operations/r1-arm-spec-20261020/arm-spec.json`
- `--r1-manifest-30 .agents/operations/r1-v11-posteval-20261024/evidence/released/retrospective-2025-v6-d30.json`
- `--r1-manifest-60 .agents/operations/r1-v11-posteval-20261024/evidence/released/retrospective-2025-v6-d60.json`
- `--r2-scores $B/cluster/data-custodian/single-R2-v1/arms/000/attempt/primary-scores.json`
- `--r2-report docs/paper/r2-report-20261030/primary.json`
- `--r1-events data/eventset/2025_leak/events.parquet` **from the 16 October package** (not repeated here)

| Script | Inputs beyond the common ones | Outputs |
|---|---|---|
| `paper_set_errors.py` | none (no `--r1-events`) | `set_errors.{json,tex}` |
| `paper_set_errors_r2.py` | `--set-errors-json paper/generated/set_errors.json` (no `--r1-events`) | `set_errors_r2.{json,tex}` |
| `paper_actor_bootstrap.py` | `--r1-events` | `actor_bootstrap.{json,tex}` |
| `paper_month_boundary.py` | `--r1-events` | `month_boundary.{json,tex}` |
| `paper_month_boundary_actor.py` | `--r1-events`, `--month-boundary-json paper/generated/month_boundary.json`, `--actor-bootstrap-json paper/generated/actor_bootstrap.json` | `month_boundary_actor.{json,tex}` |
| `paper_leaker_split.py` | `--r1-events`, `--eventset-root <16 October package>/data/eventset` | `leaker_split.{json,tex}` |
| `paper_slice_vs_persistence.py` | none (no `--r1-events`) | `slice_vs_persistence.{json,tex}` |
| `paper_native_vs_shared.py` | none (no `--r1-events`); writes only `--out-json` | `native_vs_shared.json` |
| `paper_recovery_dayblock.py` | only the 16 October package's `data/` directory (positional) | `recovery_dayblock.{json,tex}` |
| `paper_measurement_checks.py` | only the 16 October `data/` directory and the output directory (positional); reads `propagation-facts.json` and `frontier_facts.json` | `measurement-checks-facts.json`, `recovery_gap.tex`, `recovery_summary_rows.tex`, `floor_bins.tex`, `frontier_diff.tex`, `floor_dayblock.tex` |
| `paper_onset_sensitivity.py`, `paper_onset_sensitivity_ci.py` | only the 16 October `data/` directory and the output directory (positional); read `propagation-facts.json` | `onset_sensitivity.json`, `onset_sensitivity_ci.json` |
| `paper_allowlist_by_year.py` | `--cache <dir>`: a read-only collection of identifier outputs from the store; **not included** (store intermediates) | `allowlist_by_year.json` |
| `paper_roa_anchor_check.py` | `collect` over the 16 October `data/` tree and the new-period finalize output (a store intermediate, **not included**), then `ripe-check`, which downloads RIPE NCC RPKI archive files (third party) | `roa_anchor_check.json` |
| `paper_r1_arm_levels.py` | only `--report` (the R1 report) and `--comparisons paper/generated/r1-comparisons.json` | `r1-arm-levels.{json,tex}` |
| `paper_leak_audit.py` | `--events` (the same 16 October `events.parquet`), `--data "$B/leak-audit-data"` after adding the CAIDA-derived `graphs/` there (command below); `--as2org` and `--asrel-v6` with the CAIDA files below, `--ris <dir>` (with `--ris-fetch`) for the RIPEstat BGPlay files; no `--r2-scores`, `--r2-report` | `leak_audit.{json,tex}`, `leak_audit_sample.csv` (`leak_audit_novolume.json` with `--novolume-only`) |

The reader-obtained inputs of `paper_leak_audit.py` (not included, see above), with the SHA-256 recorded in
`leak_audit.json`:

| File | SHA-256 |
|---|---|
| `20250901.as-org2info.txt.gz` | `d20c6625e7eec3ea65e67379f68db1d260e25075262ddec5d7fd446d48d5fbfb` |
| `20251001.as-org2info.txt.gz` | `c520384743d755d9d8f4665469967793bcee2984d08f9091901f7fe21a6b32e1` |
| `20251101.as-org2info.txt.gz` | `0a40e9324a7e3e370e3a143e20a9106eeabbad18e4ca2d4c9f6ed7733d197629` |
| `20251201.as-org2info.txt.gz` | `671a0b4d996e592acb72a16461bdc6d2844a2d4e151aac8bc8fc6aaf2046dd45` |
| `20250801.as-rel.v6-stable.txt.bz2` | `edb7c58065150714229ea25e6101ad351014abe2f6a74140c904091ecf5e29aa` |
| `20250901.as-rel.v6-stable.txt.bz2` | `341ed4d67723720ccdf770ad20d07905d31a8c4f6bfe0943574c7a243c190264` |
| `20251001.as-rel.v6-stable.txt.bz2` | `dde5956633e20239af679a6a8159cd2c68fb932f83d569f3117d56414babcb30` |
| `20251101.as-rel.v6-stable.txt.bz2` | `6e46d578613786345102d7f608d0b7c0ffe225b38c0b241bcf32f873a132fc18` |
| `20251201.as-rel.v6-stable.txt.bz2` | `516032a32bec715e30f1b4f7d686fe61f773de11d55a78ff6628cb6ac520ac34` |
| `20260101.as-rel.v6-stable.txt.bz2` | `352cb095cd80fed1af531820c9e18af97565082db63ec2d3f3154077bc8e65b5` |
| `graphs/20250801.rel.parquet` | `1c388429bc626ab8cdecfa636b14092fd2ade2d3938ca7fa927ef7dfa413f073` |
| `graphs/20250901.rel.parquet` | `043ac6405f6321664fe5e880c57729634e1604bffff7d1670c2269d5867938ac` |
| `graphs/20251001.rel.parquet` | `98da405a4dba0de40c7578ef59bd08af7cbf83d9f7a3306aa1e9b6274aa15a29` |
| `graphs/20251101.rel.parquet` | `22a7f4d3fad809e244ae662ad26f3c032bfb007d9756d885570b7b8b1163c145` |
| `graphs/20251201.rel.parquet` | `135725bf3a81b68dbeedc79a68e4dde24a4187911321f2aad15f1220ff670b81` |
| `graphs/20260101.rel.parquet` | `836ca07ee7a39e5d66c03182dcfe465b920005b30c867c7a48ab0bf03cdb667d` |
| RIPEstat BGPlay `MANIFEST.json` (`--ris` directory) | `2dcad61825c8bc7f504cc1fca928bc46f8e6a9a8f990848b2c72f37077a62213` |

To rerun the leak audit, put the CAIDA-derived `graphs/` into `leak-audit-data/`, apply the R1-report adjustment below in
a copy of `repo/`, copy the 16 October package's events table into that copy
(`mkdir -p data/eventset/2025_leak && cp "$PKG/data/eventset/2025_leak/events.parquet" data/eventset/2025_leak/`; the script
records input paths only relative to `--data`, `--ris` or the repository and refuses others), and run from that copy
(`$PKG` is the 16 October package, `$CAIDA` holds the CAIDA files):

```bash
python3 -I -B scripts/paper_leak_audit.py --events data/eventset/2025_leak/events.parquet --data "$B/leak-audit-data" --r1-report .agents/operations/r1-v11-posteval-20261024/evidence/released/report.json --r1-per-event "$B/cluster/r1-release-parallel-v11-20261024/control-v1/results/per_event" --r1-arm-spec .agents/operations/r1-arm-spec-20261020/arm-spec.json --r1-manifest-30 .agents/operations/r1-v11-posteval-20261024/evidence/released/retrospective-2025-v6-d30.json --r1-manifest-60 .agents/operations/r1-v11-posteval-20261024/evidence/released/retrospective-2025-v6-d60.json --as2org "$CAIDA"/2025{09,10,11,12}01.as-org2info.txt.gz --asrel-v6 "$CAIDA"/*.as-rel.v6-stable.txt.bz2 --ris /tmp/ris_bgplay --ris-fetch --out-json /tmp/leak_audit.json --out-tex /tmp/leak_audit.tex --out-csv /tmp/leak_audit_sample.csv
```

`--ris-fetch` downloads the RIPEstat BGPlay files into the `--ris` directory again. Checked when the bundle was assembled, with the 16 October `events.parquet`, the CAIDA files and the RIPEstat files of the paper's run: `leak_audit.tex` and `leak_audit_sample.csv` came out byte-identical; `leak_audit.json` differed only in recorded input hashes (the events table's path and hash, the redacted R1 report and cohort manifests).

Every script takes `--out-json` and (except `paper_native_vs_shared.py`) `--out-tex` (and `paper_leak_audit.py` also `--out-csv`); the full command of each is in
its docstring. The scripts check every R1 per-event file against the report's `per_event_sha256` (the per-event files
are unchanged by redaction) and the R2 arm identities against the primary report.

One adjustment is needed. `paper_month_boundary.py` (constant `R1_REPORT_SHA`, which the other scripts import) and
`paper_r1_arm_levels.py` (constant `RELEASED_SHA`) refuse an R1 report whose SHA-256 is not the original
`049c7a9c433de1f4d03c4b5a3f7194316fc991f2c56e41ec64aac5c05b96339d`. Redaction changed two path strings in the
report, so its released hash differs (`MANIFEST.json`, entry
`repo/.agents/operations/r1-v11-posteval-20261024/evidence/released/report.json`). In a copy of `repo/`, set both
constants to the released hash:

```bash
NEW=$(sha256sum .agents/operations/r1-v11-posteval-20261024/evidence/released/report.json | cut -d' ' -f1)
sed -i "s/049c7a9c433de1f4d03c4b5a3f7194316fc991f2c56e41ec64aac5c05b96339d/$NEW/" scripts/paper_month_boundary.py scripts/paper_r1_arm_levels.py
```

The cohort manifests, `docs/paper/r2-report-20261030/primary.json` and `primary-scores.json` were also redacted (paths
only). The scripts do not pin their hashes but record some of them in the output JSON, so a re-run reports the released
hashes there. Checked when the bundle was assembled, after the adjustment above: `paper_set_errors.py` and
`paper_r1_arm_levels.py` reproduce `set_errors.tex` and `r1-arm-levels.tex` byte for byte, and their JSON outputs differ
from the paper's only in those provenance hashes (`provenance/R1/report_sha256`, `provenance/R2/primary_scores_sha256`,
`provenance/R2/primary_report_sha256`; `source_report_sha256`). The other scripts were not re-run for this bundle.

## Status of the results

- The R2 primary result is attempt 12's `primary.json`. D-A39 recomputed it from the same labels; the recomputation is
  canonically identical except for the path of the unblinded marker.
- D-A39 scored 266 of the 344 secondary roles. Its stable-peer lane failed in the pinned evaluator ("Empty target and
  prediction: Jaccard undefined on a scorable event"); the D-A39 `completion.json` keeps `passed: false` with
  `blocking: {families_failed: [stable]}`.
- D-A40, approved separately with one third label read for the stable-peer lane only, re-scored that lane with one added
  rule: an event whose stable-peer target and forecast are both empty is not scorable in that lane and is counted.
  Its `completion.json` has `passed: true`; all 24 stable cells are scored, with 3 events at 30 s and 3 at 60 s not
  scorable. With it, 290 of the 344 secondary roles are scored; the other 54 (count, Chronos, TGN and mean-aggregation
  roles) are retained failures. `outcome_release_authorized` stays false in both records by design.
- The approved data validator (rev5) returns FAIL in final mode on five checks and covers the D-A39 record only; the
  two runs are in `cluster/d-a39-lane-extract-20261101/out/validate-*.jsonl` and the explanation is in
  `repo/paper/generated/newperiod-lanes.json` (`validator_explanation`). No single check certifies the union of the
  D-A39 and D-A40 records.
- Both re-scorings have run. `repo/scratch/experiment-finish-20261030/code-backup/docs/experiment-completion-20261030/deviation-D-A39.md`
  is the record written before D-A39 ran and still reads "pending execution". The outcomes are recorded in the deviation
  ledger (entries "D-A39 outcome" and "D-A40 outcome") and in the two completion records:
  `cluster/data-custodian/single-R2-v1/arms/000/rescore-secondary-D-A39/completion.json` (`passed: false`, blocking
  `families_failed: [stable]`, 2026-10-31T21:53:11Z) and
  `cluster/data-custodian/single-R2-v1/arms/000/rescore-stable-D-A40/completion.json` (`passed: true`, 2026-11-01T03:29:53Z).

## Licences

- **Code** (scripts, `src/`, chain code): MIT (`LICENSE`).
- **Derived data** keep the terms and citation rules of their sources:
  - RouteViews: CC BY 4.0.
  - Cloudflare Radar: CC BY-NC 4.0. The route-leak labels in `leak-audit-data/labels/` are Cloudflare Radar data under
    this licence; name Cloudflare Radar as the source.
  - PCH: no PCH-derived files are in this bundle (no `2024_pchorigin` or `2024_leakpch` event sets or their event-id
    lists), because the PCH data page names two conflicting licences.
  - RIPE RIS: name the RIPE NCC and RIS as the source (required for commercial use). The RIS-derived tables in this
    bundle are derived research results and stay in it, with RIS named as their source.
  - BGPKIT peer statistics: free to use for any legal purpose. This bundle holds no BGPKIT data (the statistics only chose
    the collectors).
  - RIPE NCC RPKI archive and RoVista: no published terms found as of 31 October 2026.
