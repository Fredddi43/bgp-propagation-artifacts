# V45 FALSE template (author: Sonnet 5.5) - review notes

Derived deterministically by `prepare.py` from issued V44 (sha e5fab44a...) + row-spec.json (sha 89d4ea22..., independent PASS). No git, no remote, no board post.

## What changed vs V44
- prepare.py `compose()`: adds exactly `timing_d900_full_chain` = 68,719,476,736 to `models_reservations_bytes` and `earmarks` (earmark `lane: timing`, own-lane change so timing consumers rebind).
- `models_minimum_bytes` 847,577,881,600 -> 916,297,358,336; results floor unchanged; kind `root_joint_storage_v45`; supersedes V44; passed/issued/execution_authorized/issue_ready false; ROOT_FILL review; df/reconciliations null; `consumer_rebind_required` true.
- Conditions: `issue_conditions[1]` NOT ISSUABLE shortfall; `issue_conditions[5]` + earmark `file_cap_condition`: no d900 (or d300 32..63) release under 512MiB per-file cap without reviewed decision; 2GiB per-build fail-closed cap.

## Shortfall
Floor 916,297,358,336. vs last documented models free (V44 issuance df) 904,128,364,544: 12,168,993,792 B. vs root's ~902.7GB estimate: ~13.6e9 B (not a recorded measurement). No deletion credit claimed. Root recomputes with a fresh df.

## Reviewer must check
1. Every V44 row/earmark byte-identical (dry_run.py asserts).
2. Only one new row; arithmetic; results floor unchanged.
3. Row bytes/basis match row-spec; the independent-review.json pin is path-only in prepare.py (REVIEW) - verify its target sha equals row-spec sha (compose checks it).
4. Cap conditions carried; the template cannot be mistaken for issuable.
5. Lane results: timing_all refused (intended), all others accepted; 14 H1 boundaries OK.
Test: `cd /tmp && python3 -B <dir>/dry_run.py` (prepare.py regenerates template; dry_run asserts byte equality).
