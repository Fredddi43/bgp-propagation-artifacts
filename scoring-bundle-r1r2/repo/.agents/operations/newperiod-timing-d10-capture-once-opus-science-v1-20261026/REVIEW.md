# Timing d10 publication capture: once operator (opus-science)

Source only. Not executed, nothing consumed.

Why: the 40 timing fits need all four development horizons (5/10/300/900 s). d10's 98 logical jobs completed
0:0 without restarts (sacct 2026-10-25 18:50Z, `newperiod-timing-next-preparation-v1-20261026/sacct.stdout`), but its
publication was never captured. astra-v28 prepared the exact request. sol-h3t reviewed that preparation as
PASS_PREPARATION_ONLY and named what was missing: a bounded once operator, current-phase floors and a custody proof.
This packet supplies the operator.

What it runs: the reviewed generic `chain_capture.py` (1c462358), unchanged, over
`ssh <BATCH_HOST> 'python3 -I -S -B -c <source>'`, with the prepared request (9a159ec2) on stdin. Same transport as
the earlier timing chain captures (chain_timing.py:277-286).

Guards (once_capture.py):
- Authority: exact key set, kind `ROOT_ONCE_TIMING_D10_CAPTURE_V1`, issued by root, one attempt, no retry. Operator,
  capture source and request are sha-pinned. The independent PASS review must pin the same three, and its reviewer is
  neither opus-science nor root.
- Custody: the issued root H3 v9 operating adoption (budget v3 07c637e7, baseline e516a3d8). Every flag must be true,
  the writer arithmetic must hold, and writer `timing_cohort_recovery_and_capture` must be active with at least
  1 x 30,928 B. The DRAFT-v4 already lists it as "exactly one pinned timing d10 capture (30928 bytes exact)". I
  recomputed the record from the real source with a mocked `os`: 30,928 B, sha be2b877d, equal to the prep.
- The stat gate runs before sacct, before the capture and after it: same log device/inode as the campaign baseline, no
  shrink, size + 30,928 <= 2 GiB - 64 MiB, growth since baseline + all adoption reservations <= 160 MiB (the
  release_once arithmetic), and fresh df >= the floors of the authority's current phase.
- Scheduler: `sacct -X -P -n --array` on the 4 d10 jobs must return exactly 64+1+32+1 rows, all COMPLETED 0:0 with
  0 restarts. A foreign or failed row stops the run before the capture.
- Control scan: a ROOT-/REVIEWER- post that names the packet and is newer than the snapshot refuses the run.
- RECORDS (`actual/v1`) is created with an exclusive mkdir, and that creation is the consumption. Every remote call
  records intent, stdout, stderr and result. Any refusal writes STOPPED.json. Nothing is retried or cancelled.

Tests (tests.txt, `cd /tmp && python3 -I -B test_once_capture.py`), 12 PASS. The first one is the consumer dry run: the
real DRAFT-v4 adoption with flags flipped in temp, the real pins and the v41 phase pass check(). The others cover a full
fake run (stat, sacct, stat, capture, stat, exactly one capture), a second run, an adoption without the d10 writer, an
unflipped adoption, a failed job (no capture), growth over 160 MiB (stops at preflight), self-review, an extra
authority key and a later control post.

Not covered: the actual acceptance of the capture output (prep `postcapture_acceptance` list). That needs a separate
independent review. If opus-h3's adoption revision changes the operating budget bytes, the BUDGET pin here must follow.
