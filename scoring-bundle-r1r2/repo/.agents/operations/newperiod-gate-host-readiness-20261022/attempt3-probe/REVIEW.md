# Attempt-3 host probe proposal (after the log-only capture r2)

Author: claude-opus-5-5, session <SESSION_ID>. Local only; nothing here has run on the host.

## What capture r2 proved

Capture r2 ran once (approval a777a706), returncode 0. Output `../attempt3-diagnosis-r2/evidence/diagnosis-capture.json.gz`
24871f7d; outcome `../attempt3-diagnosis-r2/coordination/capture-outcome.json` 809c1e97. Log: 352045 B, sha 4dc9e76f,
"97 failed, 52 passed, 13 errors".

Witness stage counts in the log: `readers` 114, `trace` 17, `postimage` 7, and `audit` 74 (every one
of these is the expected side of an assertion; no host run actually ended at `audit`). Two separate host-only failures:

- **F1, stage `readers`.** Every witness run with the default denylist stops in `install_readers`, including the
  unchanged audit (`test_real_unchanged_audit_passes_under_the_hooks_in_a_fresh_process`, line 612) and every
  denylist-backstop probe (expected `audit`, got `readers`). With `REFUSED_READERS = {}` (`NO_DENYLIST`) the same
  runs pass that stage. `install_readers` can only fail there on a listed reader the host lacks (`AttributeError`) or
  on a reader bound in a module outside `READER_LIBRARIES`. Host polars does have `read_lines`: the no-denylist
  `read_lines` probe ran and reached `trace` (log line 3419).
- **F2, stage `trace`.** With no denylist, even the honest probe `open(P['csv']).read()` fails at `trace`
  (`test_recorded_probe_reads_pass_and_agree_with_the_trace`). In the no-denylist probes, after the probe path is
  masked, `syscall_trace.verify` still raises "Open outside the data and reference roots" (line 3178). So some open in
  every host run lies outside the reference roots and is not a fixed system path. The parser itself works on strace
  6.1 output (it reached that check), which argues against H-a. No data path is involved (that would be "Unrecorded
  data open"), which argues against H-c.

Not established: which reader or alias (F1), and which path (F2). Both messages are fixed by design.

## Local checks

- The two focused groups (13 tests) under the host run's exact child environment (`PATH=/usr/bin:/bin`,
  `HOME=TMPDIR` under `run/tmp`, 2 threads, LANG, USER) pass locally. So the environment variables alone do not
  explain it; the cause is in the host itself (library versions, filesystem or cgroup layout, or pandas present).
- Local versions: polars 2.0.0, pyarrow 26.0.0, numpy 2.5.4, torch 2.14.0+cpu, pandas absent. The host shared venv's
  versions are not recorded anywhere local, and `uv.lock` is untracked.

## No fix yet

No fix is evidence-supported yet. Widening `SYSTEM_PREFIXES`, dropping a denylist entry or loosening the alias rule
without the exact name would weaken the default deny blindly. That stays excluded.

## Proposal: `probe.py`, one read-only run (scope `newperiod-attempt3-host-probe-v1`)

One ssh, base interpreter `-I -S -B`. Under the attempt-3 placement venv, with the host run's child environment,
nice 10, RLIMIT_AS 8 GiB and CPU 600 s:

- **A:** import the placed audit_witness.py (sha 62e0ca7e, checked) in a throwaway process. Report the library
  versions, listed readers the host lacks, aliases outside `READER_LIBRARIES`, and the exception `install_readers`
  raises (type and message).
- **B:** the same import plus one in-memory polars/pyarrow/numpy operation under the pinned strace, with the
  witness's exact flags (`syscall_trace.command`). The trace goes to a pipe. It is parsed with the placed
  syscall_trace.py (sha 2278e71d), and the opens neither under `reference_roots()` nor `system_path()` are listed.

It reads no data and runs no gate test. On the host it writes only local records and stdout. Output is capped at
1 MiB. One attempt, no retry.

Limitation: B covers import and library start-up, not the audit itself. F2 occurs in every run including the
trivial probe, so start-up is the likely place; if B lists nothing, F2 is audit-time and needs a different design.

## Verification

`test_probe.py`, 17 passed:
- 11 approval cases;
- payload shas equal the CODEPASS package;
- one attempt with records; failure is final for rc and shape;
- the remote program run locally against the local venv and package:
  - `install_readers` ok, nothing missing, no outside aliases;
  - 1572 traced opens, 0 outside;
- a changed package sha refuses.

The local run first caught an artefact of my own: loop variables in the probe's `__main__` held a reader and tripped
the alias check. Introspection now runs inside a function.
