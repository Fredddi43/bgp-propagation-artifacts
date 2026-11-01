# Review packet: N input-gate package (A witnessed audit, B primary-core gate, C label-handoff guard)

- Author: Opus 5.5 implementation session `f1d352ff` (claude-opus-5-5).
- Status: synthetic-only candidate, ready for independent code review.
- Subject design: `implementation/GATE-PRODUCER-DESIGN-v2.md`. The original `GATE-PRODUCER-DESIGN.md` 5d3184e7 is unchanged.
- Conditions answered: D1-D9 of `review/gate-design-review/verdict.json`, reviewer session <SESSION_ID>.
- Exact bytes: `pins.json`.

**Not done and not authorized:**
- no run of A or B on real data
- no protected or remote read, no authority, no freeze, prediction or scoring
- no commit, stage or push
- the frozen-inference candidate (pins 3366fd5a) and the reader (pins 5bf2e46d) were not touched

## Files

| File | Role |
|---|---|
| `boundary.py` | Wrapper-local copy of reviewed `audit_boundary.audit_hook` (b8ba55c9) with three allowances |
| `audit_witness.py` | A: fresh-process witnessed run of the unchanged `custodian_newperiod_inputs.audit` |
| `input_gate.py` | B: hash-only paired 30/60 primary-core gate |
| `label_handoff.py` | C: pure label-handoff guard |
| `synthetic_world.py` | Test helper: synthetic stage/data/history/custody tree on which the real audit passes |
| `test_gate.py` | 43 tests |

## D1-D9 mapping

**D1 (hook, bytecode, real audit).**
- `boundary.py` differs from b8ba55c9 by exactly:
  - the `log` parameter and its resolve
  - (1) an append-mode open of exactly the configured LOG
  - (2) `os.chmod` of a path inside `out`
  - (3) `os.mkdir` of exactly the LOG's existing parent
- Pinned by `test_boundary_differs_from_the_reviewed_hook_by_exactly_the_three_allowances`. It rebuilds the expected
  source from the reviewed file with those edits and compares ASTs. A mutation control (a 4th `os.rename` allowance)
  makes it fail.
- **Allowance (3) goes beyond D1's two and is disclosed.**
  - `custodian_access_log.log_read` calls `LOG.parent.mkdir(parents=True, exist_ok=True)`, which raises the
    `os.mkdir` audit event before the harmless FileExistsError.
  - It is allowed only when the path resolves to LOG's parent and that directory already exists.
  - `test_hook_allows_only_log_append_chmod_inside_out_and_existing_log_parent` covers the allowed and refused
    cases: log 'w'/'r+', other append, chmod outside out or of the log, other mkdir, a missing log parent, remove,
    subprocess, socket.
- `audit_witness.py`:
  - sets `sys.dont_write_bytecode` as its first statement
  - imports every module first, including the lazy ones the audit path pulls in: `concurrent.futures`,
    `numpy.testing`, `torch.utils.serialization.config`
  - refuses the witness if any module enters `sys.modules` while the hooks observe the audit. This was found by
    running it: before the pre-imports, 7 modules were imported under the hooks.
  - is run as `python -B` with `PYTHONDONTWRITEBYTECODE=1`
- `test_no_bytecode_written_and_every_import_precedes_the_hooks`:
  - no pyc mtime changes under `scripts/__pycache__` or the package dir across both runs
  - AST: no import inside any function; both `sys.addaudithook` calls are inside `run`
- `test_real_unchanged_audit_passes_under_the_hooks_in_a_fresh_process` runs the REAL unchanged `audit()` in a
  subprocess for both horizons. The report shows passed, no failures, rows 2, one tensor checked, one status, and 2
  independent history events compared. Its `write_once` chmod 0444 and LOG append both succeed under the hook.

**D2 (fail-closed native IO).**
- `polars.read_parquet` is a recording delegate: the original is called with exact args.
- Refusing stubs replace:
  - polars scan/read for parquet, ipc, csv, ndjson, json, database, excel, avro, delta, iceberg, and the schema
    readers
  - pyarrow.parquet `read_table` and `ParquetFile`
  - numpy `load`, `fromfile`, `memmap`
- The recorder keeps Python `open` paths, `os.listdir`, `os.scandir` and `glob.glob`. It counts and refuses int-fd
  opens and non-path open arguments.
- Every declared path must be observed. Every observed path must lie under a data root, the out dir, or a reference
  root.
- `test_native_bypasses_..._refuse_the_witness` injects each of these into the unchanged audit's call path through
  a driver; each gives exactly `WitnessFailure: <stage>` and no witness:
  - `polars.scan_parquet`, `numpy.load`, `pyarrow.parquet.read_table` → audit
  - an int-fd open → postimage
  - `os.listdir('/etc')` → postimage
  - an external write → audit, and the file is not created

**D3 (declared set hashed; observed set stat-only).**
- Pre and post images use sha256 plus `{ino, size, mtime_ns, ctime_ns, fsid}`, only for the declared set: stage
  receipt, construction, master, export manifest, every export input, every master graph.
- A read is refused if the size differs from the planned `size_bytes` before streaming. Only the four JSON
  documents are kept in memory.
- Every other observed data file is stat-imaged at first observation. It is never rehashed, and must be unchanged
  post-run, have `ctime_ns <=` the marker's ctime, and share the marker's statvfs `f_fsid`.
- The test asserts history membership files are in `observed_data` and not in `declared`.
- **Simplification, disclosed:** one marker only. Observed data spanning several filesystems is refused, not given
  one marker per filesystem. Per-filesystem markers are a planned extension only if a real layout needs them.
- The durable log names every class with its count before the hooks:
  - stage, construction, master, export (n+1), graphs (per parent dir), replay dir (2 × events), history root
    (years), data root
- Bound in the execution plan, NOT in code:
  - memory, walltime and the read-byte budget for history reads

**D4 (NFS-safe identity).**
- The identity never uses `st_dev`; fsid comes from `statvfs(path).f_fsid`.
- B compares the full identity with the witness image, so A and B must see the same `f_fsid`. A different
  mount/host view refuses (fail closed). Running B on the same host and mount as A is therefore an execution
  precondition.
- `test_ctime_only_change_of_one_input_after_the_witness_refuses`:
  - a `chmod` to the same mode leaves bytes, size and mtime unchanged
  - B refuses at `bytes-d60`
  - negative control: dropping ctime from B's identity makes this test fail
- chmod 0444 is applied only to the NEW `witness.json` and gate files. The audit's own `write_once` report sits in
  `out`. The export-chmod residual is deleted.
- The happy-path test asserts the export files' full `os.stat` results are unchanged by B.

**D5 (primary variant).**
- The plan requires `variant: 'primary'`, `input_profile: 'core'`, and anchors for `availability_delay_s` and the
  `library_protocol` digest.
- B verifies:
  - `construction.sensitivity is None`
  - the construction and library delay equal the anchor
  - `digest(library_protocol)` equals the anchor, and master equals construction
  - no `-delayN` path component in master graph or shard-binding paths
  - `assembly.passed`, and every shard `build-binding.json` (SHA-checked against the assembly receipt) has
    `history_frozen_at is None` and `manifest_sha256 ==` the construction SHA
- Tests:
  - `test_gate_binds_the_primary_variant_only` builds real delay-900 and frozen-history worlds; both refuse at
    `variant-d30`
  - anchor-mismatch cases are in the parametrized refusal test

**D6 (guard C).** `label_handoff.check` requires:
- the gate, plan and authority SHAs
- gate kind and `passed`
- the exact reader authority
- `plan.masters[h].sha256 == gate.horizons[h].parent_master_sha256` for 30 and 60
- `plan.extension_decision.sha256 ==` the evaluator's expected extension SHA
- `record.plan_sha256 ==` the plan SHA `== authority.plan_sha256`, and `record.authority_sha256`
- `record.scope == 'prepared_labels_only'` and `released is False`
- `record.output == {path: labels_path, sha256: expected_labels_sha256}`

It opens nothing. Tests: the label file is absent on the happy path, and 12 single mismatches each refuse with the
fixed message.

**D7 (minimal gate).**
- Gate fields:
  - `kind`, `passed` (read by `load_inputs` and `freeze`), `consumer`, `input_profile`, `variant`, `task_protocol_sha256`
  - `manifests[{sha256, delta_s, inputs[{event_id, sha256}]}]`
  - per-horizon export/master/construction/inventory/report/witness/reference SHAs
  - `stage_receipt_sha256`, contract digests, producer/plan/authority SHAs, five false flags
- There are no label-derived fields; the test greps for every `LABEL_KEYS` name.
- `input_profile != 'core'` and any extra plan key refuse at `plan`.
- The self-check is the verbatim `load_inputs` 278-283 and `freeze` 70-74 predicates over in-memory documents.
- The happy-path test also calls the UNCHANGED `forecast_inputs.load_inputs` with the gate for both horizons, and it
  accepts.

**D8 (errors, order, no deserialization).**
- `GateFailure('Input gate refused at stage <s>')` has `__cause__` and `__context__` None, checked by the tests.
- The witness prints exactly `WitnessFailure: <stage>`.
- B's first durable records precede its first document read (an instrumented test):
  - each export dir with its rows + 1
  - master, construction, stage, inventory, assembly, report, witness
  - plus one record naming the assembly directory for the shard build-binding reads
- The no-deserialization test patches `torch.load`, `torch.serialization.load`, `pickle.load`, `pickle.loads` and
  `pickle.Unpickler` to raise; B still issues the gate.
- **Disclosed:** B imports `bgbench.forecast_inputs` for the unchanged `source_inventory`, which imports torch at
  module level. B calls no deserializer.

**D9.**
- Nothing was executed outside synthetic temp trees.
- B refuses any report without a matching witness of that run. Tests cover the other horizon's witness or report,
  an unwitnessed report copy, and a wrong auditor pin.
- A and B each need their own reviewed plan, resources, one-attempt accounting and authorization. The execution
  preflight of inputs and exact authority stays a prerequisite and is not implemented here.

## Other disclosed choices

- **Reference roots.** A allows observed reads under repo `src`/`scripts`, the package dir, `sys.prefix`,
  `sys.base_prefix` and `zoneinfo.TZPATH`. The real run opened `/usr/share/zoneinfo/Etc/UTC` via Python's zoneinfo.
  - Only `plan.code` is SHA-pinned.
  - stdlib, site-packages and tz data are neither pinned nor ctime-checked. Environment pinning belongs to the
    execution plan.
- **Required code pins.** The audit script, both verifiers, the access log, `boundary.py` and the wrapper. An
  execution plan should add the bgbench modules on the audit path.
- **Pairing.** The per-horizon `source_inventory_sha256` differs by construction, because each inventory binds its
  own construction. It is bound per horizon, not across the pair. The stage receipt must be equal.
- **Load-script re-execution.** The unchanged audit's `load_script` re-executes the two verifier sources under the
  hooks. This only reads `.py` files under `scripts/` with bytecode off, and it adds no `sys.modules` entry.

## Integration delta for the frozen-inference candidate's next round (not applied; candidate 3366fd5a untouched)

1. I2: arm `custody_inputs` must equal `gate.task_protocol_sha256`, `gate.horizons[h].reference_population_sha256`
   and `gate.horizons[h].source_inventory_sha256`.
2. I3: refuse unless `kind == newperiod_prediction_input_gate_v1`, `consumer == frozen_inference`,
   `input_profile == core`, `variant == primary`, and every `*_authorized` flag is false.
3. P7: the checkpoint `feature_contract` and `library_protocol` digests equal `gate.contracts.feature_contract_sha256`
   and `library_protocol_sha256`.
4. Keep naming the gate in the staged durable record (round-1 F2 already does).

The guard C call belongs in the execution wrapper, before the evaluator receives `labels_path`.

## Verification

- `pytest .agents/operations/newperiod-input-gate-20261021/test_gate.py`: 43 passed. It needs about 20 s, since the
  A runs are real subprocesses.
- Unchanged related suites: 273 passed:
  - `tests/test_custodian_newperiod_inputs.py`, `tests/test_forecast_manifest_contract.py`, `tests/test_forecast_custody.py`
  - the reader's `test_reader.py` and the inference `test_predict.py`
- Ruff 0.17.1: all checks passed.
- Negative controls: removing ctime from B's identity fails the ctime test; a 4th hook allowance fails the AST test.
