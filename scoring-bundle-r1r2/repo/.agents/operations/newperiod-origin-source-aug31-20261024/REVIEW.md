# Aug31 download-only source acquisition (successor of source-repair, review-ready 4ecbf784)

PAUSED-20261024 note: ten 2026-08-31 collector-days have historical manifests but no retained raw acquisition. The
note asks for the original forecast_acquire download-only path, complete calendar/receipt/hash/error accounting, no
rerun of identification and no inference of historical raw identity.

`build_successor.py` takes the reviewed source-repair files by hash. `successor.diff` shows the only edits:
- ROOT becomes the fresh `data-custodian/newperiod-origin-source-aug31-v1`.
- TASKS is the 10 collectors on 2026-08-31, and `N=len(TASKS)` replaces every 13.
- The custodian pass phase and `validate_pass` are removed. `run()` stops after the reviewed `acquired()`
  verification and writes done.json: archives.json ref, every acquisition-receipt ref, raw bytes,
  `pass_run: false`, `events_identified: false`, `source_equivalence_to_historical_not_asserted: true`.
- `independent()` also refuses this author's worker, /root/opus_implementation. The custody-log kind is renamed.
- build.py: the plan kind, and the array `0-{N-1}`.
- The supervisor (dd8ff4b1) and the 89-file source closure are byte-identical.

Unchanged, and to note for admission:
- The plan still binds the proven Polars 1.44.1 runtime and the Rust parser path, although nothing parses here.
- check() still requires `parser_memory_admitted` and 8 CPU / 64 GiB or more.
- The approval's `reviewer_session` must be a /root/... path.

Tests (/tmp/np-hostver-venv, Polars 1.44.1): 23 pass. They cover reproduction, the unchanged closure, the ten tasks,
the full Aug31 grid per collector with refusal of incomplete or foreign listings, identity refusal, check() for N=10,
the held array 0-9%10, and a synthetic download-only run(): receipts recorded, a single forecast_acquire command, no
data/ or pass/. They also show an incomplete listing fails before any download, is preserved, and is not retried.

Not authorized: anything on the host. Still needed: resource admission (10 x (raw+output) plus the 64 GiB floor; the
earlier term was 16 GiB, the reviewed caps allow 4 GiB raw per task), a held-array plan via build.py, an execution
approval, then a single release.
