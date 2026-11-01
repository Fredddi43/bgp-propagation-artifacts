# Exact receipt publication (local code candidate)

Reuses the independently reviewed replay-release f92a3127 pattern: fixed canonical existing parent, fresh exclusive directory, exact in-memory two-file tar, keep-old-files, no ownership import, SHA readback. Added exact file+directory fsync. No scheduler, source payload, existing-artifact mutation, or scientific execution.

Fixed destination: v11/control-v1/release-native-v2/r1-release.json. The accompanying publication-approval.json is preserved at the same new directory. Existing original release artifact references remain unchanged. Final emitted receipt SHA is the external anchor for later N plans; this transport does not alter any N gate or launch N.

Prerequisites: actual independent D2 assessment, generated exact receipt, and independent exact publication approval. Code-only approval cannot be used as publication authority. Approval fields: passed=true, release_receipt_publication_authorized=true, receipt={path:<fixed remote receipt path>,sha256:<actual>}, builder_sha256, transport_sha256, reviewer_worker/session (root or current separate Opus reviewer), automatic_retry_authorized=false, scientific_execution_authorized=false. CLI requires exact approval SHA. No actual approval or receipt is fabricated in this packet.

Single SSH <BATCH_HOST>; bash fixed script, Python -I -S -B fsync only. Receipt<=256KiB, approval<=64KiB; captured stdout/stderr<=8KiB, timeout90s; exclusive local evidence directory and intent before network. Any partial failure remains, with no automatic retry. Four tests cover actual generated wire success/duplicate refusal and exact preserved bytes, local once-only attempt, wrong approval refusal before network and failure retention.
