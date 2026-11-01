# Fresh control-v2 successor with immutable v9 science

Local operational candidate only. No host actions or actual successor runtime/approval documents generated here.

Changes from reviewed control-v1 execution code: bind controls/results/derived metadata under fresh control-v2; controller stage requires the existing canonical v9 root, verifies exact source/root-manifest bytes, and writes only new control-v2 files plus the new canonical seal. It never chmods, overwrites or removes existing source or control-v1 evidence. Existing source must already be read-only and cache-free. All other held-array/readiness/transition/evaluation behavior remains inherited.

`derive_metadata.py` compiles the exact SHA-pinned reviewed r2 derive/policy source (no bytecode import), then changes CONTROL, DERIVED and destination paths only. SOURCE and all captured v8 predecessor/scientific identities remain unchanged. `build_packet.py` accepts explicit separately prepared control metadata via --controls while taking immutable source from build3; an optional separately reviewed worker-runtime.json is included if present. It mints no approval.

Tests: 31 inherited controller/execution command tests passed in 0.55s, plus three new successor tests passed in 0.20s. The latter check exact derivation namespaces and actual local staging preservation of old source/control-v1 bytes, inode, mtime and modes, refusal of changed reused source before new directory creation, and refusal to stage control-v2 twice. Host/account and independent approval checks are stubbed only in this local staging fixture; the existing controller suite independently exercises approval checks. No scientific tests repeated because scientific source is unchanged.

Actual runtime, topology, resource review, derived metadata, transition/R1/execution approval and controller plan are intentionally not produced until their evidence is ready.

Held-display delta: accept only singleton NumNodes 1 or 1-1 and the exact submitted array job sentinel 4294967294 stdout/stderr, preserving all other admission predicates. Actual capture plus mutations tested; combined 43 tests pass.
