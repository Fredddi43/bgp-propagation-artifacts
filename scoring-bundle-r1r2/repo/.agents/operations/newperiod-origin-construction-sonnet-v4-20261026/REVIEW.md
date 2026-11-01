# Origin construction v4 (closes sol-g1a OCV3-R1: directory growth / mkdir charged against the cap before creation)

Author sonnet-origin-construction (claude-sonnet-5-5). v1-v3 untouched; v4 sibling with `origin-*-v4-20261026` namespaces. Source-only, non-authorizing; no launch, commit or cluster write. Everything else as v3 (R1 child process, R3 independence, aggregate assembly budget, native guards, residual/controls breakdown).

## Finding -> regression (fails on v3, passes on v4) -> fix
| Reviewer reproduction (live permanent hook, ext4) | v3 result (test_v4 reproduces it by running the v3 dir) | v4 |
|---|---|---|
| mkdir at cap: cap = dir block + 1 MiB, file written, then `mkdir` | 1,052,672 -> 1,056,768 (exceeded) `test_v3_mkdir_overrun_reproduced` | `science.allocated_budget` charges `allocated(root)+FS_RESERVE <= cap` BEFORE every mkdir under the root (OW_43); file admission is `allocated+per_file+FS_RESERVE <= cap` (OW_37). `test_v4_mkdir_never_exceeds_cap`: tight cap -> file refused (OW_37), funded cap -> mkdir stays inside |
| Final graph insertion that grows the parent directory | 1,400,832 -> 1,409,024 (exceeded) `test_v3_final_insertion_directory_growth_reproduced` | same reserve at admission, so the insertion that adds a directory block is pre-charged: `test_v4_final_insertion_never_exceeds_cap` (tight refused, funded not exceeded) |
| Native sinks | not covered by a directory-growth case | torch.save and polars write_csv go through the same `reserve`; pytest `test_native_sinks_charge_directory_reserve` (both refused with OW_37 when file + reserve crosses the cap, nothing created) |
Reserve = `FS_RESERVE` 64 KiB, a separate funded line `filesystem_residual_reserve` in the task cap and part of ASSEMBLY_ALLOC, outside the spendable data bytes (they are still `graphs + small files + entries + fixed dirs + native + FILE_CAP` as in v3, so the reserve is not borrowed from them). Basis: one insertion or mkdir grows allocation by 1-2 blocks (4 KiB each) on ext4; 64 KiB = 16 blocks >= 3x the largest whole directory measured in the H3 walk (16,896 B). Hook scope: mkdir/open inside the budget root only.

## Rows (changed by +65,536 per task and per assembly)
| Row | v3 | v4 |
|---|---|---|
| origin_construction_invalid | 127,123,014,656 | **127,131,534,336** (63,565,767,168 per group; task cap 974,338,408) |
| origin_construction_valid | 19,433,885,312 | **19,436,113,536** (9,718,056,768 per group; task cap 531,871,732) |
| origin_meta_precision | 369,098,752 | **369,098,752** |

## Limits stated
The reserve bounds the per-admission growth; it relies on a directory not growing more than 16 blocks per single insertion/mkdir (true for ext4/xfs/ZFS; unmeasured on the cluster filesystem beyond the du walk). Runtime closure, custody convention, resource analogs and real-data prepare/meta_review remain as in v3.

## Tests
tests.txt: 24 packet + 9 v2 + 9 v3 + 6 v4 stdlib tests, 4 pytest (real original builder/guards).
