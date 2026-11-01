# Origin 4-group construction chain (29 missing evidence slots): source-only, non-authorizing

Author sonnet-origin-construction (claude-sonnet-5-5). No launches, no board posts, no git. Remote actions were read-only: `du/find/stat` on the H3 mixed7-d60 construction work dir, `sha256sum` of the R1 release, `stat` of the projection. `execution_authorized` is false in every template; v3 operator and all reviewed sources are unedited (reused by sha pin, common.py PINS).

## Slot -> producing step -> file:line (full machine map: templates/slot-fill.PENDING.json, chain.slots chain.py:24)
| Slot (x4 groups unless noted) | Step (root once) | Code | Output |
|---|---|---|---|
| retrospective_release | **BIND EXISTING, no step**: the one accepted R1 receipt ba2a1e2e (live sha verified). `verify_release` (src/bgbench/forecast_manifest.py:200) hard-codes window 2025-09-01..2026-01-01 and H3 binds the same file (h3-forty-refits bindings), so an "own" origin release cannot exist. The earlier "no origin release" claim in v3 slots.json is superseded | science.py:78 (construction gets it), common.py R1_RELEASE | R1_RELEASE |
| construction (receipt) + manifest | `stage` -> `prepare` -> `submit_held` -> `release` -> `capture` | prepare science.py:70 (family.construction + source audit + construction gate + real authorize supervised_graph_build); build science.py:109 (family.build_shard, original write budget); assemble science.py:132 (family.assemble); sbatch/held chain.py:181,201; entry job.py:39; capture operate.py:~205 | output/assembly/construction-receipt.json, development_manifest.json |
| gate | `gate` (needs accepted capture) | science.py:141 mirrors the reviewed H3 issuer (newperiod-h3-integration-gate-astra-h3t-v2 h3_issue_gate.py:build/issue), real authorize(core_fit) before link | output/gate/integration-gate.json |
| construction_actual_review, gate_actual_review | independent reviewer (sol-g1a); FALSE templates review-construction-actual-*/review-gate-actual-* list the checks | build_templates.py REVIEW_* | local ok (v3 ships review bytes) |
| metadata_review (1) | `meta_review`: the reviewer signs `metadata-review-attestation`; producer recomputes sha/coverage facts and writes the machine review family.fit_cell reads (family.py:121-124) | science.py:198 | META_PATHS/output/results/metadata-review.json |
| precision (2) | `precision` per family after both captures accepted; count-based, see risk 3 | science.py:176 (satisfies family.py:139-146) | origin-precision-v1-*/output/results/precision.json |
| precision_review (2) | reviewer authors it; `review_install` stages it on <CLUSTER_STORAGE> unchanged after normalized independence and exact `precision` binding | remote.py:177 | .../output/precision-review.json |

Hidden prerequisites not in the 29 (produced inside `prepare`): the family.construction manifest, an origin source audit derived from the accepted history-r3 L6 summary 45f6f456 + l6-audit.txt 1c42ac60 (carries signature_source_digests 2025/2026, data_root, history digests), and the supervised_graph_build gate. Reads the 172 MB projection only through the accepted exact reader adapter (family_with_reader).

## Exact root sequence (29 onces; groups are independent chains, run in parallel)
0. Prerequisites: phase with new rows (below), independent source-closure acceptance (templates/source-closure.CANDIDATE.json, 35 files static over-approximation), resource admission per group, adoption (all FLAGS true, custody device/inode/EOF), operation review per once, control snapshot after a fresh board scan, `cd /tmp && /usr/bin/python3 -I -B operate.py --authority <file> --check-only` before each real run.
1. `meta_review` (once, needs a reviewer attestation file) -> independent acceptance.
2. Per group g in {invalid,valid}-{d30,d60}: `stage` -> accept; `prepare` (needs stage accepted) -> accept (rows, years, authorize passed); `submit_held` -> accept (both held readbacks); `release` (needs prepare+submit accepted; installs release.json then `scontrol release build,assemble`); `capture` (sacct COMPLETED 0:0 for all build tasks + assemble, hashes receipt+manifest) -> accept + construction review; `gate` -> accept + gate review.
3. Per family: `precision` (both captures accepted) -> independent precision_review authored -> `review_install`.
4. Fill the 29 slots into fit40 bindings from the accepted actuals; this packet fills none.
Dependency edges: chain.dag chain.py:45.

## Storage vs V44
V44 has NO construction row: `origin_fit_twenty`/`origin_invalid_twenty` (22 GiB each) fund fits only, `origin_s3_boundary_metadata` is consumed by S3. Need new rows (templates/storage-proposal.CANDIDATE.json; chain.storage chain.py:64): `origin_construction_invalid` 87,854,061,408 B (2 groups x 43.9 GB), `origin_construction_valid` 10,148,656,608 B, `origin_meta_precision` 536,870,912 B. Basis, measured read-only on H3 mixed7-d60: 14,681 graphs, 20,787,770,880 B allocated (1.416 MB/graph), 158,362,880,213 B logical, max file 231,815,463 B. Row counts are upper bounds from S3 artifact size / 150 B (invalid 24,155, valid 2,255); +25 %; +4 KiB receipt/event; +1 GiB controls. `operate.gate` refuses any phase lacking these rows (chain.phase_check OC_17/OC_18); exact need is recomputed from the real row count at release.

## Requirements map
ROOT SSH standard: pinned ssh_contract (sha d5103fae) via operate.exchange. Distinct codes OC/OR/OW/OJ (test). `python -I -B` everywhere (remote loader, job.sh, operate). FSIZE: remote 2 GiB, job.sh `ulimit -f 2097152`, above the custody ceiling; zero custody appends; the log is only stat()ed (test). LC_CTYPE=C.UTF-8 in job.sh, remote env, and a hash-checked locale pin. sacct `-n -P -X --format=JobID,State,ExitCode` parsed as exactly 3 fields (common.parse_sacct). Control snapshot of all ROOT-/AUTHOR-/REVIEWER- posts (common.controls). Reviewer independence normalized (common.independent; remote.review_install).

## What sol-g1a must check
1. Claim that retrospective_release is the shared R1 receipt (forecast_manifest.py:200-215) and needs no origin-specific release.
2. Origin source audit synthesized from L6 (science.py:83-90): is that an acceptable `source_audit`? Per-event occurrence file links are NOT checked at admission (H3 runtime.verify_population_sources has no origin analogue); the original builder status receipts retain failures.
3. Precision is count-based (validation incidents/actor-days/incident-day blocks); NOT the AP half-width simulation, which needs baseline validation predictions that do not exist for origin before fitting. family.fit_cell only needs the document shape. Scientific ruling required.
4. Storage: origin tensor compression is unmeasured (H3 ratio 0.131); worst case is the logical cap (chain.storage logical_cap_bytes ~551 GB invalid). Resource numbers are the H3 analog (2 CPU, 128 GiB, concurrency 16).
5. Source closure is static; runtime import/native closure, private venv and compute-node locale identity remain adoption flags. `family.build_shard` shards/years: YEARS [2025,2026] taken from family_contract windows; prepare verifies against actual manifest years via release_bundle.
6. Custody: plan assumes H3 convention (no log append for metadata/construction reads). Confirm for the projection read in prepare/meta_review.
7. Not exercised on real data: prepare_group, meta_review, build_task budget wrapper, remote subprocess science run. Exercised with the real original builder/guards on fixtures: assemble, issue_gate (real authorize core_fit), precision, signature-mismatch refusal (test_science.py).
8. Cap: remote science AS 12 GiB vs projection decode screening model 6 GiB.

## Tests
tests.txt: 23 stdlib tests (`/usr/bin/python3 -I -B test_packet.py`) + 2 pytest (`.venv/bin/python -m pytest test_science.py`, real original code on synthetic fixtures). Any source edit requires `build_templates.py` then tests then verification.json.
