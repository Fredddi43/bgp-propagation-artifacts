# final20-build-sonnet-v1 (author: sonnet-subagent-h1-g1) — bind accepted extraction to a fresh build namespace

Status: FALSE template, `execution_authorized=false`; the real once was NOT run. 9 tests pass (tests.txt), including a dry run of the REAL accepted stdout (b7fcd696) into a scratch dir under /tmp.

- `request.json` (make_request.py) pins all seven `next_build_pins` of sol-h1's accepted extraction verdict (acceptance 4b7f408c, authority 8b6ea7ae, builder 7dc9d8d1, input request d4416bf8, landing checker 2a4e4d86, result 44fa79c7, stdout b7fcd696) plus the board post, each re-hashed; expected 20 roles / 10 per horizon / 1289 IDs / digest 6c1cf870 / 10 failure-history entries.
- `run_build.py` is a local-only runner (no SSH/subprocess/network). `verify` checks a filled ROOT once (kind `ROOT_ONCE_H1_G1_FINAL20_BUILD_V1`, attempt 1, fresh utc, authors, independent PASS review bound to program/runner/request shas), every request pin, the acceptance (passed, ACCEPTED, scope H1_G1_FINAL20_EVENT_IDS_ACTUAL, report sha == stdout sha, landing ok, no retry) and the extraction result (success, landing ok, stdout sha). `records` must be a fresh direct child of `.agents/operations`.
- It executes the pinned `build_final20.py` (loaded by path) as `run(records, stdout, input_request)`; the builder re-validates the stdout with the pinned checker and writes only into `records` (`h1-arms.PROPOSED.json`, disposition-proposal, inventory, global-bindings, result.json). The runner then re-verifies independently (20 roles, 10 per horizon, all committed_for_prediction, IDs equal the stdout lists, digest, failure history kept) and writes `build-result.json`. One attempt; a second run is refused (records exists).
- Dry run (test_dry_run_real_accepted_stdout_into_scratch): 20 arms, 10/10, every `event_ids` == accepted stdout list (1289, digest 6c1cf870), 10 failure_history entries per arm, array 52518403 lineage, arms equal the reviewed PENDING arms minus IDs, 0 not_executable.

## ROOT sequence
1. sol-h1 reviews this packet exactly (run_build.py, request.json, template; builder/checker unchanged and pinned) -> PASS scope `ROOT_ONCE_H1_G1_FINAL20_BUILD_V1` with program (build_final20.py), runner, request shas.
2. ROOT fills `root-build.FALSE-TEMPLATE.json` (fresh `records` under .agents/operations, `authors`), rescans posts, runs `cd /tmp && python3 -I -B run_build.py <root-build.json>`.
3. sol-h1 accepts the actual (`h1-arms.PROPOSED.json`, `build-result.json`); then board steps 2-5 (G1 draft, H1 family review on the normalized draft arms, complete review, finalize) as before.

Limits: not an accepted disposition; open issues of final20-sonnet-v1 (outputs parent dir absent, protocol/publication_root for the G1 owner) are unchanged. The IDs land in a git-trackable records dir; ROOT decides on committing.
