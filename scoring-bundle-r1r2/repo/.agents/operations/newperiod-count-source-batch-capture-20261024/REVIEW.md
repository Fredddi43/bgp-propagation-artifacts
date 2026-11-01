# Exact count source metadata batch

Author: /root/deadline_audit. Independent review and exact capture approval required before execution.

This batches 9,739 SHA-bound JSON metadata files: 6,054 daily manifests, 1,246 native reconstruction receipts, and 2,439 directly named task reports. The immutable file list derives from accepted captured source receipts and the fixed 14,787-event sealed development join. The five original missing day manifests remain explicitly missing; no paths or proof are invented for them. Already captured exact task metadata is reused.

Exactly one additional schema-specific level is permitted: each of the 1,246 reconstruction receipts must match its bound event ID and original source_occurrences_restored status. Its original pairs/tasks fields may name task reports only under the exact crossday-repair/tasks root, with integer task-index filenames and SHA256. Conflicting references fail. The combined discovered set is deduplicated against fixed and captured tasks, with a ceiling of 65,536 additional files. Task reports are leaves: their references are never followed. No listing, recursive traversal, source payload, tensors, predictions, scores, or labels are requested.

Each read is durably logged before opening. Canonical paths, nofollow regular descriptors, file identity stability and exact hashes are checked. Limits: 4 MiB per file, 2 GiB total raw metadata, 32 GiB address space, 480 CPU seconds, 256 MiB compressed stdout and 64 KiB captured stderr. Invocation must use remote timeout 900 seconds (kill-after 5) and outer transport timeout 930 seconds. Only host mutation is the fresh exclusive declared access log; local intent and evidence paths must also be exclusive. No automatic retry.

This capture supplies evidence for the existing parser/source equivalence bridge. It confers no coverage admission and never substitutes aggregate counters for complete per-hour parser-success evidence. The original population, gaps and failure dispositions remain unchanged.

Validation: python3 -m pytest -q .agents/operations/newperiod-count-source-batch-capture-20261024/test_capture.py (8 tests). Includes complete actual fixed-request reproduction, missing-day retention, schema/identity/conflict refusal, leaf-only discovery, and byte limits.
