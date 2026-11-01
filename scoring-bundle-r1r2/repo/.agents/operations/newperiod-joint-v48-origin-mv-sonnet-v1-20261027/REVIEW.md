# V48 origin meta+valid joint storage phase (FALSE template; author Sonnet; NOT authority, not issued)

Root sequence: sol-storage review -> root issues `root-joint-storage-phase-v48.json` as a fresh canonical sibling. Nothing here was issued, launched, written remotely or committed. Only read-only `df` ran on <BATCH_HOST> (`fresh-df.json`, 2026-10-27, via `measure_df.py`).

## Derivation (prepare.py, pure)
Issued V44 (e5fab44a, models floor 847,577,881,600, results floor 45,231,374,336) + exactly two rows, amounts taken from the v6 `templates/storage-proposal.CANDIDATE.json` (sha cd73e59c, bound to V44 e5fab44a) and cross-checked in tests against `chain.META_ROW_BYTES` and `chain.row_need('valid')`:
- `origin_meta_precision` 369,098,752 (3 x 96 MiB + 64 MiB)
- `origin_construction_valid` 19,436,113,536 (2 x 9,718,056,768; valid-d30 + valid-d60)
New models floor 867,383,093,888 = V44 + 19,805,212,288 = exact row sum. Results floor unchanged. Every V44 row/earmark byte-identical; two origin-lane earmarks added (borrowing false, execution false). Not added: `origin_construction_invalid` (127,131,534,336), and none of the unissuable V45-v4 rows (d900 64 GiB, T-N4 d5/d10).

## Fresh df (read-only, 2026-10-27)
models free 876,660,916,224 (V44 issuance 904,128,364,544; 27.5 GB consumed since). Headroom over the new floor: 9,277,822,336 B (9.28 GB). Results free 50,710,183,936 vs floor 45,231,374,336: headroom 5,478,809,600, unchanged. Same rule as V41-V44: free >= floor, no cleanup/predicted credit. Adding the invalid row would need 994,514,628,224 B, 117.85 GB over free, so it is correctly excluded. No accepted-actual credit ledger is added (V44's ledger is carried unchanged; no new accepted actuals claimed).

## What the construction gates require (read from v6/prep v5 source, tests prove it; source NOT edited)
- `chain.phase_check(raw, short)`: always OC_17 meta row >= META_ROW_BYTES; OC_18 per family row only for `short` (or all rows if `short is None`).
- `operate.gate`: group targets and `valid`/`invalid` family targets pass their own `short`, so `valid-d30/d60 stage..gate`, `valid precision`, `valid review_install` PASS with meta+valid only. **target `meta` (meta_review) passes `short=None`, so it requires BOTH family rows, including invalid at >= 127,131,534,336 -> OC_18 under V48.** (prepare for groups lists meta_review only as optional `meta_review?`, so valid groups can run without it, but the metadata review itself and valid precision's meta evidence cannot start.)
- Prep v5 launch kit: `launch_construction.fresh -> prep_lib.phase_hook -> chain.phase_check(raw)` (no `short`) for EVERY action, and then sums all three rows (`KeyError` otherwise) and requires `models_avail >= floor + sum(three rows)`. Under V48 every launch action is therefore refused with OC_18. Even with that fixed, the hook demands floor + added rows = 887,188,306,176 vs free 876,660,916,224 (short 10.5 GB) because it counts the rows twice (the phase floor already includes them).
- No encoding trick helps: an invalid row smaller than `row_need` fails OC_18, a larger one makes the floor unissuable, and rows must sum to the floor (OC_15), so an "unfunded reservation" cannot exist.

## Smallest correct fix (needs a reviewed source successor, not done here; not part of V48)
1. `chain.phase_check`: treat `short='meta'` as checking only the meta row; `operate.gate`: `short = ... else ('meta' if target == 'meta' else None)`.
2. `prep_lib.phase_hook(..., short)`: pass the target's short to `phase_check`, sum only required rows, and drop the double count (the floor already contains them; check `models_avail >= models_minimum_bytes`).
3. `launch_construction.fresh(a, action, target, ...)`: derive short from target and pass it. Update tests expecting OC_17/OC_18.
Alternative without source change: fund the invalid row, which needs ~118 GB more free space after independently accepted deletions (then this V48 is superseded by a full-three-row phase).

## Consumers (tests/test_v48.py, 7 OK; `tests.txt`)
phase_compat v2 on a synthetic issued V48 (temp tree only): H1, H3, stable, timing, exact old origin rows accepted; origin-prefix (`startswith('origin_')`) consumers REFUSED (own-lane rows added: explicit rebind needed); construction consumers bind the V48 file itself. FALSE template is not admitted by the consumer ("No issued phase").

Files: `prepare.py` (compose), `root-phase.FALSE-TEMPLATE.json`, `fresh-df.json` + `measure_df.py`, `test_v48.py` + `tests.txt`. Template sha256 is listed in `SHA256SUMS`.
