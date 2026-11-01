# Pure current-input comparison and coverage contract

Implementation of conditional design ba30fbe63d66b565109711fe12316b37f539dc75dae384c87f57ccb683e8c980.
No filesystem/network reader, job, acquisition, native receipt adapter, source
index writer or execution path. Synthetic in-memory inputs only were tested.

contract.py compares complete frozen model row schemas and occurrence multisets,
including nulls and repeats. Independent raw-byte-bound expected-plan metadata
must match the supplied event/panel/slots/extraction windows/canonical endpoints.
It calls the existing coverage_gaps helper separately for expected nominal
slots, acquired parsed archives and extraction windows. Missing/failed/unproven
archives remain visible even when rows match. Train uses7200s; validation uses60s
for both forecast manifests, matching the current development consumer.

Bridge metadata is mandatory and binds exact event/stream/membership/summary
endpoints. This is a proposed pure evidence contract, NOT an adapter asserting
that heterogeneous existing native receipts already have this schema. No bridge
receipt is issued and no real native record was converted. Semantic validity of
the existing stream-to-canonical bridge remains an independent-review condition.

The raw metadata hashes prevent accidental substitution within this contract;
they do not prove an expected plan was independently frozen or a producer told
the truth. Caller-side authentication of archive/acquisition/parse evidence,
parser failure semantics, expected-plan completeness, canonical-byte binding and
bridge semantics remains explicitly pending in every result. checks_passed is
only these local consistency checks; admission_authorized is always false.
Historical raw identity is never claimed. Frozen broader source-gap/censor and
lookback rules remain binding; this helper only computes the count query.

31 synthetic regressions pass; Ruff passes. Test command:
PYTHONPATH=src .venv/bin/pytest -q .agents/operations/newperiod-count-reproduction-20261021/test_contract.py

Please review whether this narrow API is useful and fail-closed for a future
reviewed actual validator without pretending native schema conversion is done.
No raw-data or metadata-capture authority is requested by this packet.

Round1 candidate preserved in revision-v1. Fixed independent findings: exact
full canonical schema (including UInt32 ASN columns and String source columns),
per-collector reproduced row count bounded by total successfully parsed elements,
and nonnull row clocks inside the inclusive full frozen extraction-window union.
Tests reject identical wrong schemas, zero/insufficient parse counts, null and
out-of-window clocks while preserving empty parses and pre-onset context rows.
Canonical schema follows the existing Rust writer/ROW_COLS output; no runtime
coercion occurs. Other source schemas require separately reviewed explicit
normalization before this comparator, never silently casting within it.
