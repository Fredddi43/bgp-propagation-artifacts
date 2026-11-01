# Review packet: N input-gate package, revision-v2 (round-1 findings G1-G5)

- Author: Opus 5.5 implementation session `f1d352ff` (claude-opus-5-5), role label `/root/opus_implementation`.
- Status: synthetic-only candidate, ready for independent code review.
- Answers `reviews/opus-gate-round1-review.txt` and its verdict (CHANGES_REQUIRED; reviewer session <SESSION_ID>).
- Revision-v1 (`../pins.json` d9497c05) and the reviewer's artifacts are unchanged. This directory is a separate
  candidate. Exact bytes: `pins.json` here.

**Not done and not authorized:**
- no run of A or B on real data
- no protected or remote read, and no host probe (§G3 proposes one; it was not run)
- no authority, gate issuance, freeze, prediction or scoring
- no commit, stage or push
- the inference candidate 3366fd5a and the reader 5bf2e46d were not touched
- the A1 frozen-R1 publication pin stays queued

## Files and changes from revision-v1

| File | Change |
|---|---|
| `boundary.py` | byte-identical to v1 (e0afe503). The reviewer accepted the three allowances. |
| `audit_witness.py` | G1, G3 (A side), G4, G5a. Witness kind is now `newperiod_audit_witness_v2`. `REPO = HERE.parents[3]`. |
| `input_gate.py` | G2, G3 (B side), G5b. It requires witness kind v2. |
| `label_handoff.py` | byte-identical to v1. |
| `synthetic_world.py` | `REPO` depth, revision-v2 code-pin paths, and `gate_plan(..., bindings)` |
| `test_gate.py` | the 43 v1 tests, adapted to the v2 contracts, plus 34 new tests: 77 in total |

## G1: every native-reader alias (`audit_witness.install_readers`)

- **(a) Reader classes.**
  - These readers are now refused as well:
    - `pyarrow.dataset.dataset`
    - `pyarrow.feather.read_table` and `read_feather`
    - `pyarrow.ipc.open_file` and `open_stream`
    - `pyarrow.csv.read_csv`
    - `pyarrow.orc.read_table` and `ORCFile`
    - `polars.scan_pyarrow_dataset`
  - pandas `read_parquet`, `read_feather` and `read_orc` are refused whenever pandas imports. It is not installed in
    this venv, so it is never imported.
  - All of these modules are imported before the hooks. The D1b "no import under the hooks" check still holds.
- **(b) Prebound aliases.**
  - Before the hooks, `aliases()` scans every loaded module's globals for every reader object: each refused one
    and the recorded `read_parquet`.
  - A binding in any module outside the reader libraries (polars, pyarrow, numpy, pandas) refuses the witness at
    stage `readers`. This catches, for example, `from polars import read_parquet` in an audit-path module, or in a
    driver.
  - An empirical scan of the real import closure found no such binding today.
- **Library-internal aliases.** These go further than the reviewer's (a)/(b). Real examples:
  `polars.io.scan_parquet`, `polars.io.parquet.functions.scan_parquet`, `pyarrow.parquet.core.read_table`,
  `numpy.lib._npyio_impl.load`.
  - Every alias of a refused function is replaced by a refusing stub, not just the package attribute.
  - Two exceptions keep the libraries working:
    - polars' own `read_parquet` calls `scan_parquet` internally. The stub lets exactly that call through: the
      calling frame's code object must be `inspect.unwrap(polars.read_parquet).__code__`.
    - A refused class (`memmap`, `ParquetFile`, `ORCFile`) keeps the binding its own methods resolve globals in.
  - Every alias of `read_parquet` becomes the recording delegate.
- **Residual, disclosed:** a refused class is still reachable through its defining module's own global, for
  example `numpy._core.memmap.memmap(...)`. Reads that never pass a Python-visible reader are out of scope as
  before (D2): for example, Rust code opening files that no Python path or reader call names.
- **Tests:**
  - `test_further_readers_and_internal_aliases_refuse_the_witness` has 13 cases, each giving exactly
    `WitnessFailure: audit` and no witness. It covers every new class plus the four internal aliases above.
  - `test_prebound_reader_alias_refuses_before_the_audit` has 4 cases. Each gives `WitnessFailure: readers`, no
    report, and no `automated` audit log record.
  - `test_internal_read_parquet_alias_is_recorded_not_missed`: a read through `polars.io.read_parquet` of an extra
    parquet file under the data root is recorded in `observed_data`.
- **Reviewer probe** `probe_native.py` (43228dd9), re-pointed at revision-v2 (`/tmp/gate-v2-scratch/probes/`). All
  three cases now refuse; none writes a witness or records the extra file.
  - All three refuse at `readers`, because that driver prebinds `polars.read_parquet` at module level in every case.
  - The dataset paths without a prebinding are the new suite cases above, which refuse at `audit`.

## G2: B binds the witness producer, its A plan and its authority

- Each horizon of the externally pinned B plan now carries
  `witness_binding = {plan_sha256, authority_sha256, code, modules, python_executable}`.
- `checked_inputs` requires the exact key set and types; a missing key refuses at `plan`.
- `evidence()` requires all of the following:
  - `witness.plan_sha256` and `authority_sha256` equal the binding
  - `witness.code` equals the binding's code map exactly: all pins, including `boundary.py`, `audit_witness.py`,
    both verifiers and the access log
  - `witness.modules` equals the binding's module map (G4)
  - `witness.python.executable` equals the binding's interpreter
  - `binding.code['scripts/custodian_newperiod_inputs.py'] == plan.auditor_sha256`
- **Tests** (all refuse at `evidence-d30`):
  - `test_gate_refuses_a_reanchored_witness_from_another_producer` has 5 cases: a re-anchored forged witness with
    zeroed code pins (the reviewer's probe), a foreign interpreter, a changed module hash, a foreign plan SHA, and a
    foreign authority SHA.
  - `test_gate_refuses_a_binding_that_does_not_name_this_witness` has 5 cases: the other horizon's A plan and
    authority, a changed module or code pin, and a different interpreter.
  - `test_gate_plan_requires_an_exact_witness_binding`.
- **Reviewer probe** `probe_witness_code.py` (2d58fd03), re-pointed. It now prints
  `REFUSED Input gate refused at stage evidence-d30`. On v1 it issued gate 3209744f.
- In the synthetic tests the expected module map comes from the observed run. An execution plan takes it from its
  reviewed environment closure.

## G3: same-device marker proof, mount record, and honest NFS limits

- **A.** Before the hooks, `mount_table()` parses `/proc/self/mountinfo` once. `mount_of(path)` picks the entry
  whose `major:minor` equals the path's `st_dev` and has the longest mount point covering the path. It records
  `{mount_point, fstype, source}`.
  - The witness records `marker.mount` and a `mounts` map for every declared input.
  - Every observed data file must satisfy `os.stat(path).st_dev == st_dev(marker)`, in addition to the v1
    conditions (unchanged stat image, ctime ≤ the marker's, equal `f_fsid`).
- **B.** For every export input, `mount_of(path)` must equal the witness's recorded mount view.
- **What this proves, and what it does not:**
  - `st_dev` is compared only inside one process on one host, never recorded for, or compared on, another host.
    That keeps D4's rule (no `st_dev` in the cross-host identity).
  - A's `f_fsid` check stays, but on Linux NFS `f_fsid` is 0, so it proves nothing there. The `st_dev` check
    carries the same-device proof.
  - B's mount comparison binds the *mount view* (same export source, fstype and mount point). That is not a proof
    that the server object is identical.
  - Content binding remains B's identity (`ino`, `size`, `mtime_ns`, `ctime_ns`, `fsid`) plus the sha256 stream.
  - B on another host with the same export mounted at the same path passes the mount check. That is intended: same
    export, same bytes, same server-side stat.
- **Correction of the v1 REVIEW D4 sentence** ("A different mount/host view refuses (fail closed)"). The code
  enforces exactly this:
  - B refuses when an input's mount view (point, fstype, source) differs from the witness's.
  - B refuses when any identity field or the byte hash differs.
  - Equal `f_fsid` is not evidence of the same mount on NFS.
- **Tests:**
  - `test_fsid_zero_with_data_on_another_device_refuses`:
    - The world is on `/dev/shm` (tmpfs) and the witness output on the disk tmp filesystem.
    - `os.statvfs` is replaced so every `f_fsid` is 0, the Linux NFS behaviour.
    - Result: `WitnessFailure: postimage`.
    - Control: the same world with the output on the same device passes, with `marker.fsid == 0`.
  - `test_witness_records_mount_views_and_the_gate_compares_them`: B refuses at `bytes-d30` when the mount source
    differs.
  - `test_mount_table_parses_this_hosts_mountinfo`.
- **Execution-host probe (proposed only, not run; needs routing).** This is filesystem metadata only on
  <BATCH_HOST>, for the exact roots an execution plan names. No file content is read:

  ```
  for p in <out parent> <data_root> <history_root> <export_dir> <access-log parent>; do
    stat -c '%n dev=%d' "$p"; stat -f -c '%n fsid=%i type=%T' "$p"; findmnt -n -o TARGET,SOURCE,FSTYPE,MAJ:MIN -T "$p"
  done
  ```

  - It answers whether those roots share one device with the witness output.
  - If they do not, the single-marker design refuses, and per-device markers become a real requirement.
  - It also records the NFS `f_fsid` (expected 0).

## G4: every loaded repo module is hashed

- `repo_modules()` hashes every module file under repo `src/`, `scripts/` and this package. That covers all of
  `sys.modules`, plus the audit script and the hook copy: those two are loaded from file without a `sys.modules`
  entry. A first run found them missing, and this was fixed.
- It runs immediately before the hooks, and again after the audit; an unequal map refuses at `postimage`.
- The map is the witness's `modules`, and B compares it with the plan's binding (G2).
- The two verifier scripts that the unchanged audit re-executes via `load_script` (no `sys.modules` entry, under
  the hooks) stay pinned through `plan.code`.
- Interpreter, stdlib, site-packages and tz data remain unpinned. Environment closure is an execution-plan
  prerequisite, which the reviewer accepted.
- Test: `test_witness_records_every_loaded_repo_module` checks the required set, including
  `custodian_newperiod_inputs.py`, `boundary.py`, `audit_witness.py` and the bgbench modules, and checks every
  recorded hash against the file.

## G5: exact durable log paths

- **(a) A.**
  - The pre-audit records keep their exact paths.
  - The history-root and data-root classes, whose file count is not known before the run, are now logged with
    `files: None`. The purpose names the history years. v1 put the year count in `files`.
  - After the audit and before the witness is written, A logs one durable record per directory the audit actually
    read observed data from, with its exact file count (`witnessed audit (post-hoc): ...`). Each is an
    append-only LOG write under the hook (allowance 1).
  - Tests:
    - `test_real_unchanged_audit_passes...` asserts the history record has `files None`, and that every pre-record
      precedes the audit's own record.
    - `test_post_hoc_records_name_every_observed_directory_with_exact_counts` asserts the post-hoc map equals the
      witness's `observed_data` grouped by parent directory.
- **(b) B.**
  - After the assembly receipt is read and before any `build-binding.json` read, `shard_bindings` logs each exact
    shard directory with its binding count, then fsyncs.
  - v1's record naming the assembly directory is removed.
  - Test: the instrumented `test_gate_never_deserializes_and_logs_every_class_before_its_first_read` captures the
    log at each `build-binding.json` read and finds `{path: <shard dir>, files: 1}` already there.

## Mutation controls (each fix removed in a throwaway sibling copy; the targeted tests must fail)

Script: `revision-v2/mutation_controls.py` (pinned). It copies revision-v2 into `revision-v2/mutation-tmp/`, applies
one anchored text replacement per case (an anchor that is not unique aborts the run), runs the targeted
`pytest -k` selection against the copy, and deletes the copy in `finally`. Command, run from the repo root:

```
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B .agents/operations/newperiod-input-gate-20261021/revision-v2/mutation_controls.py
```

Final run against the pinned files: exit 0, `mutation-tmp/` gone afterwards. Every mutation is detected.

| Mutation | Targeted result |
|---|---|
| G1 no refusal at all | 13 failed, 64 deselected |
| G1 only package attribute patched (aliases left live) | 4 failed, 9 passed, 64 deselected |
| G1 prebound check removed | 4 failed, 73 deselected |
| G2 binding check removed | 10 failed, 67 deselected |
| G3 A st_dev check removed | 1 failed, 76 deselected |
| G3 B mount check removed | 1 failed, 76 deselected |
| G4 explicit loads dropped | 1 failed, 76 deselected |
| G5a post-hoc records removed | 1 failed, 76 deselected |
| G5b shard records removed | 1 failed, 76 deselected |

- "G1 only package attribute patched" gives 4 failures among the 13 alias cases. That count matches the four
  internal-alias cases (the last four params). The nine direct package-attribute calls stay covered by the patch
  this mutation keeps, so they are expected to pass. The log records counts only, not test IDs.
- An earlier scratch run gave different G1 counts. It ran against an older `test_gate.py`, which was edited after
  it; only the final run above is quoted.

## Verification

All runs from the repo root with `PYTHONDONTWRITEBYTECODE=1`, all exit 0.

| Command | Result |
|---|---|
| `.venv/bin/python -B -m pytest -q -p no:cacheprovider .agents/operations/newperiod-input-gate-20261021/revision-v2/test_gate.py` | 77 passed in 63.82s |
| `.venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_custodian_newperiod_inputs.py tests/test_forecast_manifest_contract.py tests/test_forecast_custody.py .agents/operations/newperiod-custodian-reader-20261021/test_reader.py .agents/operations/newperiod-frozen-inference-20261021/test_predict.py` | 273 passed, 1 warning in 21.65s |
| `.venv/bin/python -B -m pytest -q -p no:cacheprovider .agents/operations/newperiod-input-gate-20261021/test_gate.py` (original, unchanged) | 43 passed in 20.47s |
| `.venv/bin/ruff check .agents/operations/newperiod-input-gate-20261021/revision-v2/` | All checks passed |

- The one warning is torch's `torch.jit.script` deprecation `FutureWarning`, in
  `test_isolated_fit_loop_preserves_original_globals_and_never_opens_test`. It is unrelated to this gate.
- `ruff format --check` would reformat 7 revision-v2 files. Left unformatted on purpose: the mutation anchors match
  exact text. The original gate fails the same check (6 files).
- No `.pyc` or `__pycache__` was written into the package. `/dev/shm` test worlds are removed in `finally`.
- No actual gate, audit or N-period payload was read or run. Every test runs on synthetic worlds.
- The original gate (`pins.json` d9497c05) and its files are unchanged.

## Known limitation, recorded and not hidden

- The R1 v6 builder-b1 frozen test `test_candidates_are_byte_reproducible` fails (81/82): the once-only control stage
  wrote two extra stage records beside the candidates. Candidate bytes are unchanged and the pins were not rewritten
  (checkpoint commit f41af5d). It is outside this gate and not touched here.
- G1 residual: see above (`numpy._core.memmap.memmap` through its defining module's own global).
