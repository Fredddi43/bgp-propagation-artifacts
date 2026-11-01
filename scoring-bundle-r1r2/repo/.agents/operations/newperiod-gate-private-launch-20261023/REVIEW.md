# Private-runtime N witness / gate launcher

Local prospective revision of reviewed `newperiod-gate-launch-20261022/revision-v2`. No host action, new fit, real input read or gate issuance performed. The original four files remain unchanged.

Operational changes only:
- Fresh `B/newperiod-input-gate-private-v1/{witness,gate}-control-v1`, private Python at `B/newperiod-gate-private-v1/venv/bin/python`, unchanged gate revision-v5 pins `ff4a9535` and actual captured private placement `838fa32c`.
- Same-model separate-agent review allowed with truthful `codex` identity. Known author worker/session aliases rejected; no author self-approval.
- Existing placement closure checks retained. Verbatim reviewed `site_packages`, `_fd_sha256`, `verify_private` functions verify the copied runtime and reject modified/shared inodes. The private editable path is checked explicitly.
- Actual host report is required at the private prefix's `run/result.json`, with full-suite PASS, integer rc0, identical placement/tracer, and successful limits/size evidence. A missing report, smoke-only run or failed suite cannot proceed.

All original execution/authority/resource/failure functions other than `independent`, `checked_spec`, `placement` are AST-identical. The launcher and supervisor function ASTs are unchanged. Gate scientific source is not copied or modified. Witness d30 then d60 and gate issuance remain separately approved exact-once phases. Existing upstream R1 release and N input preparation requirements remain; this tool creates neither inputs nor scientific authority.

`build_candidate.py` reproduces the four operational files from exact pinned predecessors. `draft.py` reproduces the two unresolved templates from the actual captured placement. These templates refuse execution. Dynamic items: actual terminal host-report hash; actual input plans/authorities/access-log path; exact phase approval/review; gate phase also needs actual successful witness-spec/exit/output bindings. Resource values remain the predecessor finite defaults, to be reviewed against the actual witness plans before activation.

Staging precondition inherited from the old transport: the approved parent directory `B/newperiod-input-gate-private-v1` must exist and be canonical before phase staging, because the same-device checks inspect it. Each phase control root must be absent. Root operator must include parent creation in its exact staging scope; this candidate does not create or overwrite host directories.

Validation: 45 synthetic tests passed in 0.43s. Tests cover actual metadata draft reproducibility, exact source preservation, transport document binding, same-model independent review, failed/unresolved host evidence, private-copy mutation/hardlink/symlink rejection, and finite resource gates. This is a focused operational-delta suite; it does not rerun the gate's scientific test suite or claim actual host PASS.
