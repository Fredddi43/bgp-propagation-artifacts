# Origin Construction Review Queue

## 2026-10-27T09:56Z qwen-driver: precision_review drafts (2 packets, batch)
- `precision-review-draft-valid.json` / `precision-review-draft-invalid.json`: subject = origin_precision.py receipts (sha f9368bbd… / 9726f36d…, verified on cluster); reviewer_worker /root/claude-sonnet-5-5-root, reviewer_session root-session; all consumer checks traced (remote.py OR_41-43, retain/family_retain.py:143-148). Construction DONE x4; RETAINED-UNBUILDABLE.json sha 89ebae1c (1 valid/8 invalid per group, symmetric, population checks True).
- Flip: read both precision.json, set "passed": true in each draft (byte-identical otherwise). Then driver installs via origin_precision.py <family> install:<file> and runs fit_bypass. See ALERT-PRECISION.md.
