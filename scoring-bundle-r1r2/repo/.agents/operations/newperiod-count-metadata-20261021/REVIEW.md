# Exact existing development metadata capture

Read-only capture of two explicitly hash-bound JSON documents; no reference traversal,
no glob, no membership/archive/label reads, no remote writes, no admission flags.
Existing capture_existing_metadata.py reused with one narrow change: the exact known
staging-receipt path gets64MiB rather than16MiB allowance because prior schema evidence
records32,137,259bytes. Other per-file16MiB and total256MiB bounds remain unchanged,
including canonical-root checks, descriptor stability and exact SHA256 verification.

Capture supplies raw metadata bytes missing from existing parsed source-audit and
staging-schema samples. Request contains only the two immutable references already
bound in the independently reviewed count-custody specification. It does not authorize
following any metadata reference, nor protected2026 payload access. Result will be local
gzip raw-byte capture for further source mapping and independently reviewed admission.
