# Origin S3 workspace screen v2 (author: Sonnet; local only, not authority)

Copy of `newperiod-origin-s3-workspace-astra-v1-20261026` (untouched). Reason: once v3 refused W21. Read-only dry run on <BATCH_HOST> (screen with recording `need`) found
`screen.py:40` `sum(len(m[part]) for part in PARTS)<=ROWS` fails for the valid family (136,833 rows per horizon: events 136,832 + excluded 1 + source_failures 0; invalid 32,903 passes).

## Delta (only thing to re-check)
- `screen.py:8` `ROWS=100000` -> `ROWS=262144`. It bounds both the per-horizon row total (line 40) and the unknown-id list length (line 43). No other line changed (`diff` vs v1).
- Margins on the real projection: rows 136,833 of 262,144 = 1.92x headroom (margin 125,311); unknown ids 96,399 of 262,144 = 2.72x (margin 165,745). 262144=2^18, chosen as the next power of two above ~1.9x/2.7x; the bound only refuses, never drops rows.
- `callback.py`: byte-identical to v1 (still pins reader/screen/protocol/boundaries by request sha). `prove_workspace.py`: boundaries path -> `newperiod-origin-s3-boundary-source-v2-20261026`, `count=262144`, label text. `test_screen.py`: boundary path -> boundary source v2; appended `test_bounds_value_and_exact_boundary` (ROWS==262144; ROWS==max rows passes, one fewer refuses; unknown ids one over refuses).
- Tests: `PYTHONPATH=src .venv/bin/python -B -m pytest -q -p no:cacheprovider <dir>/test_screen.py` -> 15 passed (14 old + 1).

## Synthetic proof at the new bounds (`verification.json`)
262,144 rows per family, 512B IDs, 32B actors, original protocol, all four original replays under AS 16GiB: peak RSS 3.69GB (allowance 8GiB replay workspace), wall 80.5s, screen passes, manifests replay.
Honest caveat: at the full synthetic row count each boundary would be 173.5MB, over the unchanged 128MiB file cap, so the writer would refuse such a shape (fail-closed). The proof only counts bytes. The real projection is far smaller (measured 7.92MB total), so the row bound is not the binding limit; the caps stay the final guard.

## Codex sol-g1 must check
`diff` v1 vs v2 of screen.py is exactly one line; the new test's boundary logic; that the memory proof (3.69GB) fits the 8GiB workspace premise (REVIEW of v1: 8GiB workspace + 6GiB predecode + 2GiB, AS 16GiB); that the v1 workspace conditional-pass acceptance does not transfer by hash and a fresh acceptance bound to the v2 sha is needed.
