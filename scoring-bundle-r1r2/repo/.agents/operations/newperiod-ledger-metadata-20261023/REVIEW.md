# Exact source-coverage ledger capture

Root candidate, not yet approved or executed. Six exact existing references come from
`newperiod-readiness-20261023/explicit-metadata-leads.json`, each already bound by
captured integration/closure records. An lstat-only probe established canonical regular
<USER>-owned files, 5.8–63.3 MB each, approximately 212 MB total. It read no contents.

Purpose: obtain archive-gap dispositions and source-part ownership metadata for the
existing N count coverage/index prerequisites while R1 evaluates. These are historical
source/audit ledgers, not R1 evaluation outputs, N protected masters, labels or scores.
The capture opens only the six named files; no referenced parquet, archive, summary,
membership, daily manifest or other payload is followed. It neither selects a cohort
nor establishes historical parser execution, actual development population or admission.

Schema basis: `scripts/forecast_2025_gap_ledger.py:43` emits event/collector interval,
gap status and archive-gap references. `scripts/forecast_2026_omitted_part_inputs.py:147`
emits the corresponding 2026/retained gap rows, with source coverage metadata and row
counts. `scripts/forecast_part_coverage_evidence.py:76` and `:145` emit archive slot,
manifest and coverage status metadata. `scripts/forecast_occurrence_population_audit.py:51`
and `:93` emit source-part ownership, source hashes, equality checks, source/canonical
onsets and source-filter AS identities. Those metadata values are preserved exactly;
they are not recomputed or interpreted as model performance. A fixed top-level schema
allowlist rejects extra fields; malformed/duplicate keys refuse. Reviewer must confirm
this actual content scope is appropriate, beyond the earlier metadata-only leads.

64 MiB/file, 256 MiB total, 2 MiB/row, 200000 rows/file, 180-second remote deadline.
Canonical paths, no symlink leaves, regular files, descriptor identity/size/mtime/ctime
stability, externally bound SHA256 and local hash/schema verification are enforced.
Fresh exclusive output directory, stdout/error retention, no automatic retry. No
remote writes, imports from captured data or scientific computation. A failure leaves
its output/diagnostics for assessment. Nine focused tests pass, including isolated
remote-code execution against a synthetic ledger and preservation of archive gaps.

After separate exact code/scope approval:
`.venv/bin/python -B .agents/operations/newperiod-ledger-metadata-20261023/capture.py --output .agents/operations/newperiod-ledger-metadata-20261023/execution-v1`
