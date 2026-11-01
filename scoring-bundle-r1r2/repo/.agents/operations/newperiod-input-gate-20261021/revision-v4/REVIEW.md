# Gate revision 4 (LOCAL proposal after host probe r4)

Author: claude-opus-5-5, session <SESSION_ID>. Local only: no host edit, no gate host test, no attempt 4. `revision-v3`
(CODEPASS) is preserved byte for byte; this is a copy with two code changes and their tests.

## Evidence (probe r4, run once 2026-10-22T14:28:44Z-14:29:01Z, rc 0, approval 28030200)

Records: `../../newperiod-gate-host-readiness-20261022/attempt3-probe-r4/` evidence `probe.json` 4ef29caf, outcome
`coordination/run-outcome.json` 7354389a (committed 6da41eb).

- **F1 (stage `readers`), observed.** A: host polars 1.44.1 has no `scan_external_reader`, which `REFUSED_READERS`
  lists. `install_readers` fetches every listed name with `getattr`, so it raises `AttributeError` (A records exactly
  `missing ['polars.scan_external_reader']` and `install_readers ['AttributeError', "module 'polars' has no attribute
  'scan_external_reader'"]`). No outside aliases. Local polars is 2.0.0, which has the name, so local tests never hit it.
- **F2 (stage `trace`), observed in part.** B: the only open outside the reference roots and `SYSTEM_FILES` at import
  and start-up is `/etc/locale.alias` (glibc locale alias table, LANG=C.UTF-8). The 10 cwd-relative attempts are all
  `libcuda.so.1` lookups that got ENOENT, which the trace does not treat as opens.
  - **Inferred, not observed:** that this same path was the outside open in the attempt-3 witness trace.
  - **Not covered by the probe:** audit-time opens (the stages after `readers`), stage-time lazy imports, a repo-root
    file read through the cwd (the probe's cwd was the scratch), and descendants that call setsid().
  - So v4 can only remove the one observed cause. Another outside open, if one exists, would still stop the gate at
    `trace`, which is the intended default-deny behaviour.

## Changes (`diff-v3-v4.diff`)

1. **`audit_witness.py` `install_readers`:** a listed name the installed module does not define is skipped and
   recorded in `recorder.absent_readers`; every present name is still wrapped and refused exactly as before. The
   untraced witness (and so the witness) gains the key `absent_readers` (sorted `module.name` strings).
   - Why this is not an allowance: a name the library does not define cannot be called through it. Whatever a
     different reader would open is still caught by the default-deny syscall trace, as for any unlisted reader.
   - The input gate reads the witness with `.get()` and has no exact-key check on it, so the new key changes nothing
     there; the binding's exact-key check is untouched.
2. **`syscall_trace.py` `SYSTEM_FILES`:** adds the exact path `/etc/locale.alias`. It is an exact-match set, so no
   prefix, sibling or directory is allowed with it.
3. **Relocation only:** `synthetic_world.CODE` and `mutation_controls.py` point at `revision-v4` instead of
   `revision-v3`. History comments that say "revision-v3" are left as they are.

Nothing else changed: no other reader, path, root, stage or binding.

## Tests (added to `test_gate.py`)

- `test_v4_a_listed_reader_absent_from_the_installed_library_is_recorded_not_fatal`: the host failure reproduced by
  listing a name this polars lacks (`scan_reader_not_in_this_version`). v3 stops at `readers`; v4 passes, records
  the name in `absent_readers`, and refuses nothing.
- `test_v4_present_readers_stay_refused_when_another_listed_name_is_absent` (3 of the reviewer's round-2 bodies:
  `pyarrow.parquet.read_metadata`, `polars.read_parquet_metadata`, `polars.read_lines`): with the absent polars name
  listed, present readers, including polars ones, are still refused at `audit` with exactly their label.
- `test_v4_absent_readers_is_empty_for_the_reviewed_environment`: the honest chain records `[]` locally.
- `test_v4_locale_alias_is_one_exact_system_file`: `/etc/locale.alias` is a system file;
  `/etc/locale.alias.d/x`, `/etc/locale.aliases`, `/etc/passwd`, `/etc/locale.gen` are not.

## Verification

- **`test_gate.py`: 168 passed** (`evidence-local/pytest.txt`): the 162 of v3 plus the 6 above. The v3 suite run in
  place today, unchanged: 162 passed.
- **The host failure reproduced on v3 bytes** (`evidence-local/v3-repro.txt`): a throwaway copy of revision-v3, with
  the same absent polars name listed, exits 1 with exactly `WitnessFailure: readers` and no witness. The copy was
  deleted afterwards.
- **`mutation_controls.py`: 26/26 detected** (`evidence-local/mutations.txt`): the 22 v3 mutations, plus four new
  ones: absent names fetched again (= v3 behaviour), absent names not recorded, present readers dropped together with
  an absent one, and `/etc/locale.alias` removed from `SYSTEM_FILES`.
- `boundary.py`, `input_gate.py`, `label_handoff.py` are byte-identical to v3. ruff: clean.

## What this does not do

- No host change, no placement, no shared-venv change, no gate host test, no attempt 4. Each needs its own review,
  approval and root routing.
- It does not claim attempt 4 would pass: see the uncovered cases under F2.
