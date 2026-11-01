# D0/D1 fix after the actual D0 attempt (approval 29832ae4)

**What happened.** D0 ran once at 2026-10-24T03:02:34Z and exited rc 0. Its stdout was
`{"cells": 66, "tensors": {"30": 3543, "60": 3543}}` with no sha line. The tool recorded `{"cells":` as the digest and
refused with a ValueError. Records: classd-host/phase-records/d0-intent.json fced0513, d0-result.json 4b98fd15. D1
was NOT run; with the reviewed tool it would have passed the bogus token as --plan-sha256.

**Root cause.** `d0_command`/`d1_command` end in `exec <python> run_adapter.py ...`, and `run_remote` appends
`&& sha256sum <out>`. `exec` replaces the shell, so the sha256sum never runs. The inherited fake-ssh test always
returned a sha line and could not see this. `test_bug_reproduced_in_reviewed_command_and_fixed_in_r2` runs the real
command in bash with a stand-in interpreter: the reviewed command ends on `{"cells": 66}`, and r2 ends on the plan
sha.

**Fix.** `phases_r2.py` is built by `build_fix.py` from the reviewed bytes 72a6d837. The diff is in phases_r2.diff:
- no `exec`;
- a read-only, one-attempt `d0-readback` (`sha256sum DEST/out/plan.json`). It is allowed only for an rc-0 D0 record
  without a valid digest, so D0 is never rerun; RECORDS is the same classd-host/phase-records;
- 64-hex digest validation;
- a new scope r1-posteval-classd-d0-d1-r2 with phases ['d0-readback', 'd1'].

HOST, DEST and the interpreter are unchanged. DEST/out was empty at the transport readback (T2 asserts it), so
plan.json can only come from this D0.

**Tests.** 18 pass (`.venv/bin/python -B -m pytest -q -p no:cacheprovider d0d1-fix-v1`).

**Ask.** An exact approval accepted by phases_r2 checked_approval (scope r1-posteval-classd-d0-d1-r2, tool sha in
review-ready, phases ['d0-readback', 'd1']). Then run `phases_r2.py d0-readback`, then `phases_r2.py d1`, each once.
