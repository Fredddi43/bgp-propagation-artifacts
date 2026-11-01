# Exact origin source inventory probe

Author `/root/deadline_audit` (Codex). Actual execution pending separate root review.
No actual remote calls or protected payload reads were performed during authoring.

The two exact data roots come from the parent's existing bounded source-path
capture and `protected-staging-actual-verdict.json`: historical project DATA_ROOT
and newperiod-identification-v1/data. Original config.py establishes
`manifests/<collector>/<date>.json`; original custodian_newperiod_pass.py establishes
`pass-source-receipts/<collector>/<date>.json` and its exact operational fields.
Neither manifest nor receipt references are followed to any additional input.

One capture probes August1–October16 inclusive,77days×10collectors×2roots:
1540 exact `.origin_changes.parquet` **lstat only** operations; up to3080 bounded
producer-defined JSON metadata reads. Missing or symlinked metadata is reported,
not followed. Parquet files are never opened or hashed. No directory listing,
recursive walk, event payload, target, score or label access is included.
Producer metadata can contain source counters; unlisted counters are not returned.

Only operational manifest fields and pass-source binding fields are projected.
Origin/edge/element/per-hour counts and other unlisted payload summaries are not
returned. Receipt digests and exact pass-manifest identity comparison establish
what was captured; **coverage_established remains false** regardless of existence.
File limit1MiB, aggregate metadata read64MiB, output8MiB. No nested path/URL/archive
reference is opened. Parent capture review is needed before interpreting evidence.

The only remote write is one durable append to the already established canonical
custody access log, before any source probe. It refuses a missing/symlinked log.
No source mutation, output root creation, acquisition or scientific computation.
The local caller verifies exact request/source and separate reviewer approval,
creates execution-v1 once, uses isolated stdlib Python on <BATCH_HOST>,180s remote
alarm and210s SSH timeout, and writes one local result. No automatic retry.

`approval.json` must bind exact request SHA and independent worker, passed=true,
metadata_inventory_authorized=true, retry_authorized=false and
scientific_execution_authorized=false. No approval/template is supplied by author.
This request is independent of the future-origin population amendment; it only
locates and binds source evidence needed to review actual acquisition/identification.
