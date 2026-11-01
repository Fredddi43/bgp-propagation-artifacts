# T-N4 v5 (sonnet) — answers sol-final TIMING-TN4-V4-CHANGES (TN4-V3-G1-EVIDENCE-NOT-VERIFIED)

v4 untouched. The package, per-horizon plans, 12-job d5/d10 plan, bridge (author-excluding), storage request (**68.5 GiB = 73,551,314,944 B, accepted as a proposal, unchanged, unfunded**; retained 13.84 GB planning only) and custody model are unchanged from v4. `tests-regression-first.txt` = 32 new tests failing on the v4 G1 helper (incl. the reviewer's 12 hashed-but-bad files returning ready); `tests.txt`/`verification.json` = 98 tests pass. Operator dir not edited.

## G1 helper: typed semantics (`tn4_lib.py`: `verify_rows`, `_evidence_doc`, `check_binding`, `require_g1`, `campaign_inventory`, `default_binding`)
Readiness is derived, never claimed, and now needs a **binding** (`TN4_G1_BINDING` if missing/incomplete: population dc8f0976 + a sealed development manifest ref and a bound subgroup plan ref for each of the four horizons; `default_binding()` supplies d5/d10 only, d300/d900 must come from the caller once sealed). Per evidence slot the file is parsed (bounded, local; no protected body) and must satisfy, in this order:
1. kind + scope of the slot (`seal_acceptance` = `timing_development_seal_acceptance_v1`/`timing-development-seal-acceptance`; `chain_acceptance` = `timing_construction_chain_acceptance_v1`/`timing-construction-chain-acceptance`; `gate_acceptance` = `timing_input_gate_acceptance_v1`/`timing-input-gate-acceptance`); non-JSON/non-object -> `TN4_G1_EVIDENCE_KIND`.
2. `passed` and `independently_accepted` true, `execution_authorized` false -> `TN4_G1_EVIDENCE_STATUS`.
3. reviewer worker/session/model present and NOT any author: same sets and normalization as the bridge (`author_sets()` executes the frozen package's `BRIDGE_AUTHOR_NAMES/SESSIONS/AUTHORS`; slash-split, casefold, strip) -> `TN4_G1_EVIDENCE_REVIEWER`.
4. `horizon` equals the slot's horizon string and is one of the plan's four (999, another planned horizon, an int all refused) -> `TN4_G1_EVIDENCE_HORIZON`.
5. binding -> `TN4_G1_EVIDENCE_BIND`: seal.manifest == binding seal manifest; chain.plan == binding plan, chain.development_manifest == the same manifest, 37 tasks completed, all zero exit, 1124 events, population digest equal, typed export/audit refs; gate.plan == binding plan, typed gate ref.
6. pairing -> `TN4_G1_EVIDENCE_PAIR`: gate.export_manifest == chain.export_manifest per horizon and the four export manifests are distinct (swapped pair / shared artifact refused).
Before parsing (unchanged from v4): four unique horizons (`HORIZON_SET`), ACCEPTED states (`REQUIRES_ALL_FOUR`), evidence shape (`EVIDENCE_REFS`), existing canonical regular file with matching sha (`EVIDENCE_FILE`), twelve distinct refs (`EVIDENCE_DUPLICATE`). The distinct-code test now exempts the shared `TN4_G1_*` family (same code from the three slots by design; semantics asserted per case).
Tests: `test_v5_reviewers_twelve_hashed_but_bad_files_do_not_unblock_g1` (failed/unaccepted/author/unrelated kind/horizon 999, all twelve at once), `test_v5_positive_typed_fixture_is_ready` (genuine mutually consistent four-horizon fixture), 25 parametrized negatives (failed, unaccepted, execution flag, sonnet, alias, root, author session + variants, missing model, unrelated kind, wrong scope, slot-kind swap, horizon 999 / other planned / int, wrong seal manifest, other plan, dev-manifest mismatch, 36 tasks, non-zero, other population, wrong count, gate other plan, gate export differs, malformed gate ref), swapped pair across horizons, shared export artifact, non-JSON, author-set identity with the bridge, default-binding limits, retained v4 guards. Author fixtures are typed positives, not `{i,acceptance}` stubs. Scope note: the three document kinds are the schema this packet requires of future acceptances; none exists yet for d300/d900, so G1 stays blocked.

## Operator v3 (`newperiod-timing-tn4-operator-sonnet-v3-20261026`, not edited): pin-only rebind to v5
`operator-reuse.json` pins its ACTUAL files (sha256 of every file observed now) and the rebind table below (computed from its `common.py` PINS vs this package). Repoint two path constants: `common.py` `TN4=OPS/'newperiod-timing-tn4-sonnet-v3-20261026'` -> `...-v5-20261026`; `driver_gate_real.py` `BOUND=.../newperiod-timing-tn4-sonnet-v3-20261026/bound-d10__d5` -> `...-v5-20261026/bound-d10__d5`. Package pins:

| operator PINS entry | operator v3 pin | v5 actual | rebind? |
|---|---|---|---|
| controller (`PKG/controller.py`) | 0836ba13... | 0836ba13... | no |
| wave_contract (`PKG/wave_contract.py`) | 41bc3fc6... | **70f48268...** (author-excluding bridge) | **yes** |
| runner | cd51633b... | cd51633b... | no |
| file_limits | c0207e4e... | c0207e4e... | no |
| custody_scope | f358466c... | f358466c... | no |
| release_once_tn4 (`TN4/release_once_tn4.py`) | ac20b5b5... | **cd7cb5c9...** (forwards `request.bridge` to both `admit` calls) | **yes** |
| transport (`TN4/transport.py`) | a418543d... | a418543d... | no |
Full 64-hex values are in `operator-reuse.json package_pin_rebind_table`. Also repin anything the operator reads from the bound subgroup (`subgroup-d5-d10.plan-ref.json`: the plan sha changed because `wave_contract.py` changed; storage spec, bridge template and the G1 helper are listed under `must_pin`). The operator's own `OPERATOR_FILES` hashes, reason-code list and tests change with those pins, so it needs its own reviewer pass; its sol-final operator CHANGES (remote self-timeout/resource limits, pre-decode memory admission, scoped permission history for d300__d900, control-census growth) remain with its author.

Still open: funded phase + all-host log adoption, d300/d900 seals, 37-task per-group chains, typed acceptances/gates (the evidence documents above), G1 and inference blocked.
