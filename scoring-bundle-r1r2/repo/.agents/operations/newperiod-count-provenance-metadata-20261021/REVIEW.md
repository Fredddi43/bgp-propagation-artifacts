# Three explicit predecessor provenance metadata documents

Read-only, exact once capture using existing capture_existing_metadata.py with two
exact staging-receipt paths allowed64MiB each; integration remains16MiB and total
bound remains256MiB. No reference traversal, no remote writes, no payload or protected
outcome reads. Existing descriptor stability, root/symlink containment, SHA256 checks,
SSH timeout and exclusive local gzip output remain unchanged.

Request references are copied exactly from the already captured, hashverified combined
development staging receipt (captureSHA3796748e8bfff916aa37034ba5772ea2683797476d649cb5f682d639e1a39420).
Producer code shows 2026 staging contains restore_completions and omitted_completion;
integration contains strict_plan, omission, coverage/gap bindings. These JSON metadata
receipts can locate explicit provenance, but grant no authority to follow those refs.
2026 provenance metadata is distinct from protected outcomes. No inventories, tables,
Parquet, archives, target arrays or other document types are requested. The existing
integration JSON schema includes development source censoring-status metadata; the
request covers that already-bound provenance report, not any protected target values.

Invocation: python3 .agents/operations/newperiod-count-provenance-metadata-20261021/capture_metadata.py
.agents/operations/newperiod-count-provenance-metadata-20261021/request.json
.agents/operations/newperiod-count-provenance-metadata-20261021/capture.json.gz
(on one command line). Request scope: one bounded invocation, no retry. No scientific
execution, source-index admission or passed prerequisite flags requested.
