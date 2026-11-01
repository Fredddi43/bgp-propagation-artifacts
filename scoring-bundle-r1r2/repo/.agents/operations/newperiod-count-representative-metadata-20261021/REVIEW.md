# Six explicit representative provenance receipts

Read-only schema/feasibility inspection, not source coverage or population inference.
Each path/hash is copied from the independently reviewed17-document metadata capture.
Select lexicographically first event in each declared category:2025metadata,boundary;
2026restored normal,boundary-censored;omitted no-declared-gap,archive-gap. Preserves the
actual14 archive-gap and2 boundary-censored cases; no omission, repair or reclassification.
Selection is deterministic from existing metadata, never based on model outcomes.

Byte-identical existing capture helper with unchanged16MiB/file256MiBtotal, exact
hash/descriptor/root checks and exclusive local output. No automatic traversal,
remote write, Parquet/archive/model/prediction/target payload read or new job. Receipts
contain source statuses, timestamps/windows, part/archive references and occurrence
proof flags. Producer schemas: forecast_restore_2026_occurrences.py:639-687;
forecast_occurrence_metadata.py:38-74;forecast_boundary_occurrences.py:163;
forecast_2026_omitted_part_inputs.py emits its source/occurrence receipt.

Legacy7,151-row events.jsonl is explicitly bound but intentionally not captured:
forecast_occurrence_population_audit.py:76-106 emits per-part hashes/collectors/rows
and exact multiset/first_seen checks, without per-archive acquisition/parse evidence.
Its schema cannot honestly fill count_coverage archives fields. That remains an
explicit scientific evidence gap, not an ownership-schema renaming opportunity.

One invocation after separate approval:
python3 .agents/operations/newperiod-count-representative-metadata-20261021/capture_metadata.py .agents/operations/newperiod-count-representative-metadata-20261021/request.json .agents/operations/newperiod-count-representative-metadata-20261021/capture.json.gz

No retries, N/R1/protected-outcome execution, source-index admission, source coverage
satisfaction, inference of missing source as empty or scientific gate changes.
