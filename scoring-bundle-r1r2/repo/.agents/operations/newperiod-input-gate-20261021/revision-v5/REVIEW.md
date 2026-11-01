# Gate revision 5 (LOCAL; an author-found test defect in revision-v4, found by a host-version rehearsal)

Author: claude-opus-5-5, session <SESSION_ID>. Local only. `revision-v4` (pins 1cf54a2c, under review) and `revision-v3`
are preserved byte for byte. **The gate code is unchanged from v4.** Only two v4 tests, their relocation constants and
one added test change.

## Why v5 exists

To check v4 against the execution host without a host read, I built a throwaway local venv with the host's library
versions from probe r4 (evidence 4ef29caf): python 3.12.8, polars 1.44.1, pyarrow 25.0.1, numpy 2.5.2, pandas 3.0.5,
torch 2.14.0 (CPU build; the host has cu130). It lives at `/tmp/np-hostver-venv`; the build command is in
`../../newperiod-gate-host-readiness-20261022/attempt4-candidate/test_host.py`.

Under those versions, **v4's own suite gives 166 passed, 2 failed.** Both failures are v4 tests that assumed the
development host's polars 2.0.0, where no listed reader is absent:

- `test_v4_a_listed_reader_absent_from_the_installed_library_is_recorded_not_fatal` expected `absent_readers` to be
  exactly the injected name; under polars 1.44.1 it also holds `polars.scan_external_reader`.
- `test_v4_absent_readers_is_empty_for_the_reviewed_environment` expected `[]`; under polars 1.44.1 it is
  `['polars.scan_external_reader']`.

The witness behaved correctly in both cases. The expectations were wrong. A host attempt 4 on v4 would have failed
on these two tests alone.

## The change (`diff-v4-v5.diff`)

- `listed_readers()` (new test helper): the `(module, name)` pairs of `audit_witness.REFUSED_READERS`, read from the
  witness source with `ast`. The module is not executed. It includes the conditional pandas entry when pandas is
  importable, as the witness does.
- `environment_absent()`: the listed names the installed libraries lack (`hasattr` on the imported module).
- The first test now expects `sorted({*environment_absent(), injected})`.
- The second test is replaced by `test_v5_absent_readers_are_exactly_the_listed_names_the_installed_libraries_lack`:
  the honest chain records exactly `environment_absent()`.
- Added `test_v5_listed_readers_are_read_from_the_witness_source`, a sanity check of the parser: it finds three known
  pairs and no duplicates.
- Relocation only: `synthetic_world.CODE` and `mutation_controls.py` name `revision-v5`.

## Verification

- **`test_gate.py`: 169 passed** with the development venv (`evidence-local/pytest.txt`), and **169 passed** with the
  host-version venv in the environment `host_run` gives the tests (`evidence-local/pytest-hostversions.txt`).
  - v4 under the host-version venv: 166 passed, 2 failed (`evidence-local/v4-hostversions.log`).
  - v3 under the host-version venv: 83 failed, 66 passed, 13 errors (`evidence-local/v3-hostversions.log`).
- **`mutation_controls.py`: 26/26 detected** (`evidence-local/mutations.txt`); the same cases as v4.
- `audit_witness.py`, `syscall_trace.py`, `boundary.py`, `input_gate.py`, `label_handoff.py` are byte-identical to
  v4. ruff: clean.

## What else the host-version rehearsal showed about attempt 3 (evidence for the probe-r4 review)

The v3 suite was run under the host versions, locally, with the environment `host_run` gives the tests
(`evidence-local/v3-hostversions.log`): **83 failed, 66 passed, 13 errors (96 failing)**. The attempt-3 host log (4dc9e76f)
had 97 failed, 52 passed, 13 errors (110 failing). Per test function:

- All 96 local failures also failed on the host. This is the F1 reader failure, reproduced by the library versions
  alone.
- The 14 failures seen only on the host are exactly the tests whose witness runs with `REFUSED_READERS = {}`, so they
  skip the `readers` stage:
  - `test_round2_probe_readers_without_any_denylist_are_caught_by_the_syscall_trace`: 9;
  - `test_recorded_probe_reads_pass_and_agree_with_the_trace`: 3;
  - `test_data_copied_or_linked_outside_the_roots_is_refused_by_the_trace`: 2.

  On the host these stop at `trace`. That fits a host-only system open, and `/etc/locale.alias` does not exist on the
  development host. The attribution to `/etc/locale.alias` itself is still **inferred**; the attempt-3 traces were
  deleted.
