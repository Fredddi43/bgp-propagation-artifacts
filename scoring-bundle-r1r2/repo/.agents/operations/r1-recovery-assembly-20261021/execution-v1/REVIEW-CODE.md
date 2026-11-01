# Recovery metadata wrapper: code review only

Author /root/reference_reuse_recovery. Exact fresh root assembly-v4/control-v1.
Inherited reviewed execution-v2 launcher/supervisor/resource/audit/once-only boundaries
are preserved. Source/retention/preparation/resource binding remains mandatory.

Changes: new scope r1-reference-reuse-metadata-execution-v1, explicit independent
reference_reuse_recovery_authorized flag, author identity excluded. Failed preparation
witness must match immutable previous metadata and returncode1 with no spec/complete.
The separate diagnostic must have an exact captured terminal started/failed/exit
witness, same live bytes, exact diagnostic spec, ValueError and untruncated frame at
old source verify_batch:1759, old source SHA2180791d, no success marker. Any earlier
failure, alarm, missing terminal, changed bytes, or unexpected completion refuses.

No terminal diagnostic witness exists yet: package/spec remain deliberately absent.
No old attempt restarted or modified. Future exact package requires its own review.

Bounded exception rendering is 16 code filename/function/line frames with filename512,
function128,type128 caps and truncation bit; never values/locals/source lines. Phase
messages contain only literal phase, bound family IDs(max128,26), started/complete.
Logged stderr is flushed+fsynced. Wrappers preserve arguments, return identities,
exceptions and original adapters and are restored in finally. Full verify_batch still
executes once inside unchanged preparation; evaluate still requires fresh full verify.
No phase marker creates a preparation output dir or bypasses any gate.

58 tests pass including inherited audit/transport/approval/once-only tests, bounded
failure secrecy, wrapper restoration on failure/success and ten predecessor mutation
cases. Ruff/bash pass. Request CODE PASS or findings with exact code pins. No staging,
execution, scientific/protected read, R1/scoring/publication authority in this review.
