# Origin construction v3 (closes sol-g1a OCV2-R2: aggregate proof for every sink + funded residuals)

Author sonnet-origin-construction (claude-sonnet-5-5). v1/v2 preserved; v3 is a sibling with `origin-*-v3-20261026` namespaces. Source-only, non-authorizing. Unchanged from v2: R1 child-process isolation, R3 independence, precision/source-audit rulings, slot map and root sequence (v1/v2 REVIEW.md).

## OCV2-R2 -> change -> test (test_v3.py, reproduction first)
| Point in the finding | v2 state (reproduced) | v3 |
|---|---|---|
| Assembly: 128-MiB per-FILE limit for two files vs one 128-MiB total | `test_v2_has_no_file_or_directory_count_and_assembly_had_no_counter`: v2 admits 300 files; assemble only set FSIZE | `science.assemble` runs under `allocated_budget` with an aggregate counter: logical total 128 MiB (original Budget `used+per_file<=total` before each write), per-file 64 MiB, allocated cap, files<=4 (OW_41), 1 directory (OW_42). Test `test_assembly_aggregate_counter_refuses_third_write_before_creating_it` |
| File/directory growth uncovered | no count bound | `allocated_budget(files_cap, dirs_cap)` for build tasks (files 2*rows+16, dirs 4) and assembly; `test_v3_file_count_refused_before_creating_the_file`, `test_v3_directory_count_refused_before_mkdir` (child process: mkdir refused, path absent) |
| Native CSV (tgn_data.py:607 polars write_csv) and torch.save not demonstrated | build_task patched torch only; polars unguarded | `install_native_guards` reserves the path before torch.save and `pl.DataFrame.write_csv` (also in assemble); pytest `test_native_sinks_refuse_before_writing` (third native write refused, file absent) |
| Capture accounting too late | remote.accounting at capture | kept only as a secondary check; the claimed bound is the pre-write admission above (remote.py comment unchanged) |
| Residuals unfunded | 1 GiB controls unitemized | chain.RESIDUALS and chain.CONTROLS_BREAKDOWN: named terms below; `test_every_residual_is_a_named_measured_allowance`, `test_controls_breakdown_is_funded_before_residual_slack`, `test_group_row_is_sum_of_funded_parts` |

## Measured analog (read-only walk of H3 mixed7-d60 build-0000/0017/0040, assembly, supervision)
8 directories 110,592 B allocated (max 16,896 B, ~265 entries -> ~63 B/entry); 749 small files: 2,364,249 B apparent (mean 3,157), 3,619,328 B allocated (mean 4,832 B). Graph analog as before (1.416 MB/graph allocated, max file 231,815,463).

## Task cap (per build task; invalid values, rows_per_task_upper 378)
graphs estimate 669,060,000 (rows x 1.416 MB x 1.25) + small files 3,096,576 (8,192 B/event, 1.7x measured) + directory entries 96,768 (2 x 128 B/event, 2x measured) + fixed directories 131,072 (>= 4 x max dir) + native/allocator 5 % 33,453,000 + next-file headroom 268,435,456 (= FILE_CAP) = **974,272,872**. Valid (141 rows/task): 531,806,196.
Assembly: aggregate 134,301,696 = 128 MiB logical total + residual (4 dirs x 16,896 + 4 x 4096). Controls 1 GiB funds, in order: stage sources 16 MiB, evidence 4 MiB, prepare outputs 64 MiB (pre-write quota), gate outputs 64 MiB (quota), records 64 MiB, ops files 8 MiB, assembly dir residual 2 MiB, directories/inodes 8 MiB = 241,172,480 B, leaving ~832 MB unallocated slack.

## Final row bytes (changed)
| Row | v2 | v3 |
|---|---|---|
| origin_construction_invalid | 122,613,518,336 | **127,123,014,656** (63,561,507,328 per group) |
| origin_construction_valid | 19,010,574,848 | **19,433,885,312** (9,716,942,656 per group) |
| origin_meta_precision | 369,098,752 | **369,098,752** (unchanged) |

## Still for the reviewer
Runtime/native closure, custody convention, resource numbers (H3 analog), prepare/meta_review on real data, 256 MiB file cap, and the 5 % native allowance as an engineering margin not a measured allocator bound (the pre-write allocated() measurement is what actually bounds the task; the residual terms only size the cap).

## Tests
tests.txt: 24 packet + 9 v2-finding + 9 v3 stdlib tests, 3 pytest on the real original builder/guards (`.venv/bin/python -m pytest test_science.py`).
