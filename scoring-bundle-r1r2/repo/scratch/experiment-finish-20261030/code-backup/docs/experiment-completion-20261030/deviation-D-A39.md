# D-A39: secondary-only recovery — pending execution

Status at2026-10-30T14:49Z: label-free preparation is running; no second label read has occurred, and final data readiness has not been certified.

Original R2 job52700052 opened labels once and persisted primary.json (SHA-256849e064518d1aa7e0b1c61c4c5836acd75864de12dce0278dab75918493e9ac1) and primary-scores.json (SHA-256af9656ac8e1961eccbda75c590e5c8361a640229127dc122e79611d0365cef59). It then failed in the secondary membership decision check. At least counts had been computed before failure; no complete secondary report was persisted. Earlier wording that no secondary outcome had been computed was incorrect.

<AUTHOR> selected “Re-score lanes (Recommended)” at2026-10-30T11:28:07.645Z in the original session, approving one disclosed second label read for secondary scoring with the primary locked. The record is user message609fd1d3-d8b9-4ea4-b855-7d4daae83be3 in session3c9c66d7-481f-4410-a617-db603d53eeb7. No automatic third read is authorized.

The recovery uses the same sealed forecasts, freeze, labels and committed decisions. It applies the producer-compatible float32 comparison privately to membership scoring and leaves the primary scorer unchanged. The reviewed successor binds exact preparation bytes and runtime code to a fresh label-free dry run; its opening must use those same preparation bytes. All nine scoring callbacks must persist, both canonical primary comparisons must pass, and the final independent data checks must pass before completion is recorded.

Current preparation job:52709453. Successor driver:chain-d39-v2/r2_rescore_secondary.py, SHA-256bce67ffcbcb10d1a246a74da4951a7ffffcad61af3f93ea55075958182d4c8d8. Runtime bindings and implementation reviews are retained beside this record. Final execution ids, receipts and completion result will be added after the run.
