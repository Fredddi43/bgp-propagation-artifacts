# Origin construction v2 (answers sol-g1a CHANGES on v1: OCV1-R1/R2/R3 + storage basis)

Author sonnet-origin-construction (claude-sonnet-5-5). v1 dir is preserved unedited; v2 is a sibling with new namespaces (`origin-*-v2-20261026`). Source-only, non-authorizing; no launch/board/git. Everything not listed below is unchanged from v1 (see v1 REVIEW.md: slot map, root sequence, requirements map). The accepted rulings stand: counts-only precision, shared R1 binding, scoped source-audit derivation.

## Finding -> test (reproduced first, test_v2.py) -> fix
| Finding | Reproduction (fails on v1) | v2 fix | v2 proof |
|---|---|---|---|
| R1 hook blocked job's own record | `R1_HookBlocksRecord.test_v1_failure_reproduced`: pinned original Budget hook installed, then a write outside the root is refused ("Write outside fixed producer output"); v1 job.py called `science.build_task(req)` in-process | science runs in its own `python -I -B science.py <action>` child (`job.run_child`, job.py:~39); the parent never holds the hook and writes intent/result records itself | `test_v2_science_runs_in_its_own_process` (no in-process call; hooked child exits, parent writes) |
| R2 allocation checked after writes | `test_v1_budget_has_no_allocated_bound`: 8 MiB written against a 3 MiB share, every write admitted | `science.allocated_budget` (science.py): before each new file `allocated(task dir)+file_cap <= task_alloc_cap` else OW_37, so no write crosses the cap whatever the compression. Assemble: FSIZE 128 MiB. Metadata writers: `science.charge` pre-write 64 MiB quota (OW_32). Meta/precision rows: 3 x 96 MiB namespaces + 64 MiB (was one 512 MiB limit per namespace in one 512 MiB row) | `test_v2_refuses_before_the_write_that_would_cross_the_cap`, `test_group_bound_is_sum_of_enforced_task_caps`, `test_metadata_writers_are_prewrite_capped_and_rows_sum`, test_packet `test_meta_row_funds_three_namespaces` |
| R3 attestation independence | `test_v1_condition_accepts_excluded_author`: v1 check (passed + nonempty strings) accepts the construction author and an author session | `science.check_independent` (same normalization as common.independent, plus /root worker) applied inside `meta_review` (OW_35/36) with the author lists in the request; `operate.request_for` also runs `C.independent` on the local attestation, whose bytes are shipped and hash-checked (OW_40) | `test_v2_refuses_authors_and_sessions_normalized` (case, `//`, trailing slash, upper-case session, non-/root, None) |
Also from the review: precision key renamed `onset_day_clusters` (unique onset UTC dates, not incident-day pairs), precision now requires distinct accepted d30 and d60 manifests (OW_39), source audit `scope` text limited to historical staging provenance (no occurrence closure, immutability or training authority).

## Storage re-derived (reviewer reasons: unmeasured compression, post-write accounting, shared meta row)
Measured analog (read-only, H3 mixed7-d60): 14,681 graphs, 20,787,770,880 B allocated (1.416 MB/graph), max file 231,815,463 B. It is now only a planning estimate; the admitted bound is the enforced cap:
task cap = ceil(rows_upper/tasks) x 1.416 MB x 1.25 + 4 KiB/event + 256 MiB (file cap, = analog max +10 %, FSIZE and Budget); group = tasks x task cap + 128 MiB assembly + 1 GiB controls. If origin compresses worse, tasks FAIL at the cap before writing; they cannot borrow other rows.
| Row | v1 | v2 (bytes) |
|---|---|---|
| origin_construction_invalid (2 groups, 64 tasks each, task cap 939,043,744) | 87,854,061,408 | **122,613,518,336** (61,306,759,168 per group) |
| origin_construction_valid (16 tasks, task cap 518,582,992) | 10,148,656,608 | **19,010,574,848** (9,505,287,424 per group) |
| origin_meta_precision | 536,870,912 | **369,098,752** |
Rows upper bounds still S3 artifact size / 150 B (invalid 24,155, valid 2,255); the real count only lowers real use, never the cap. Per-file cap lowered 512 -> 256 MiB (risk: a larger origin graph fails its task). Logical writer caps unchanged (8 GiB invalid / 4 GiB valid per task).

## Still for the reviewer
Same list as v1 items 2, 4-8 (runtime closure, custody convention, resources are an H3 analog, prepare/meta_review not run on real data). New: confirm 256 MiB file cap and 1 GiB controls headroom; prepare's science quota (64 MiB) must exceed manifest+gate+audit+receipt for 24k rows (H3 manifest analog 8.8 MB).

## Tests
tests.txt: 24 stdlib packet tests + 9 v2 finding tests (`/usr/bin/python3 -I -B`) + 2 pytest on the real original builder (`.venv/bin/python -m pytest test_science.py`). Any source edit: `build_templates.py`, tests, verification.json.
