# V45 v2 FALSE template (author: Sonnet 5.5) - review notes

`prepare.py` derives the template from issued V44 (e5fab44a) + d900 row-spec (89d4ea22, independent PASS) + T-N4 storage.json/REVIEW.md + H1 capture13 acceptance + `h1-measurement.json` (read-only `du -sB1`/`df` over ROOT SSH standard v1, `measure_h1.py`, 0 writes). No git, remote, board post, issue or launch. Test: `cd /tmp && python3 -I -B <dir>/dry_run.py`.

## Rows vs V44
- Added `timing_d900_full_chain` 68,719,476,736 (as v1, file-cap condition carried).
- Added `timing_tn4_export_wave` 156,766,306,304 (146 GiB = 1+64+4+77, T-N4 REVIEW storage section / storage.json), lane timing.
- Retired to 0 (earmarks kept, `retired_by_v45` records prior bytes): `protected_h1_controls` 1 GiB, `_live_phase` 64 GiB, `_operational` 4 GiB, `_physical_padding` 77 GiB = 146 GiB.
- Added `protected_h1_v3_retained_outputs` = measured retained bytes (stays reserved, no credit).
- `h1_stage_controls` and `h1_future_campaign_contingency` (46.2 GB) are NOT retired (not named in the task). Every other V44 row/earmark byte-identical; results floor unchanged.

## Measurement (protected-h1-storage-v3, whole tree incl. claims/controls)
- Allocated `du -sB1`: **6,416,736,768** (d30 3,197,230,592 + d60 3,217,767,936 + controls/claims ~1.7 MB). Apparent: 31,743,145,520 (not the reservation basis; allocated matches df basis and all earlier phases; reviewer should confirm no thin/compressed-fs surprise).
- Credit = 156,766,306,304 - 6,416,736,768 = **150,349,569,536**. It does NOT cover the 146 GiB row; retirement shortfall = 6,416,736,768 (the retained bytes).
- Floor: 847,577,881,600 + 68,719,476,736 + 6,416,736,768 = **922,714,095,104**. (v1 floor 916,297,358,336; the 146 GiB row nets against the retired H1 rows.)
- df models free 895,449,300,992 -> **floor shortfall 27,264,794,112**. Results floor unchanged, free 50,710,183,936 (floor met per V44 value). No deletion credit claimed; root recomputes with a fresh df.

## Consumers
Lane check: h3/stable/origin accepted; **h1 and timing_all refused (Own-lane changed)**. H1 is explicitly retired: all 14 boundaries refuse against v45 (chain complete/accepted, nothing left to release) and all 14 still pass against V44 alone. False template refused by `capture_once.current_phase`.

## Reviewer must check
1. H1 accepted actuals really prove the whole tree unused for further releases (G1 still binds these outputs; retained row keeps them reserved).
2. Retiring rows to 0 (vs deleting keys) is acceptable to consumers keyed on the names.
3. Row arithmetic; T-N4 findings N4-F1..F7 remain open (planning row only); retained timing growth ~12.9 GB unfunded.
