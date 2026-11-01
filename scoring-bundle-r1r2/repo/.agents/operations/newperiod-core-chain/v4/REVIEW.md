# N-core v4 independent Codex reviewer compatibility

Prospective candidate only; no execution approval, actual R1 release receipt, submission or scientific input read. Original reviewed v3 remains untouched.

The runner accepts truthful `codex` reviewer identity and requires an independently identified reviewer worker and session. Current and inherited author aliases and ambiguous root aliases remain disallowed. Versioned control records/root advance to v4 to preserve historical evidence. Existing scientific sources, recipe, marker, 40 fits, 20+20 waves, eight memory profiles, resource limits and first-wave memory gate are unchanged. The standalone placement source is byte-identical to v3.

`make_package.py` checks the original v3 review-request hashes and generates v4 spec and a non-passing approval template. Actual R1 release remains mandatory before any preparation/submission; the separate private-runtime host test does not satisfy that scientific dependency.

Validation: `.venv/bin/python -B -m pytest -q .agents/operations/newperiod-core-chain/v4/test_opus_newperiod_core_chain_v4.py` — 107 passed. Includes inherited command/resource/failure tests, Codex acceptance, author/session alias rejection, full function AST preservation except approval policy, and exact scientific spec preservation. No host operations performed. Independent review required; author `/root/remaining_work_audit`, model `codex`.
