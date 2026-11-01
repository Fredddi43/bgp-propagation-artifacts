# Count34 failure-evidence staging (Sonnet author; source only, nothing executed)

**Question answered:** can the draft read the count34 failure evidence (accepted R-b disposition, 13884 B, sha 0e537a99) from the repo path instead? **No.** The draft's Reader runs on the cluster and requires a canonical regular file at the arm's `failure_chain` path; read-only `ls` of <BATCH_HOST> shows `<HOME>` does not exist there, and the declared destination parent `.../data-custodian/complete-retention-bindings-astra-v1` does not exist yet (cluster lstat: 1 distinct count ref, 0 staged). All 34 count arms reference the same single ref `(DEST, 0e537a99)` (test asserts it). Therefore one minimal bounded write is needed.

## What is staged
`stage_evidence.py` (remote, stdin request, argv-free) = the reviewed `newperiod-g1b-count-stage-v1` worker logic (fresh parent dir as durable consumption marker, exclusive 0400 files, readback, fsync) writing exactly: parent dir, `intent.json`, `count-rb-disposition.json` (the 13884 bytes, sha pinned), `receipt.json`. RLIMIT_FSIZE 1 MiB, AS 128 MiB, CPU 30 s, alarm 60 s. No custody-log read/append, no payload/label/gate read, no output slot created.

## Difference from the older operator (why a new packet)
The old `operator.py` connects with plain `ssh <BATCH_HOST>`; this packet uses the ROOT SSH standard launcher (strict pinned known_hosts, ProxyCommand, bounded streams, kill-on-overflow/timeout, rc0 + empty stderr + landing check `check_stage.py`) shared with the event-ID packet. Added to the launcher: `WRITE_BYTES = 1 MiB` (fresh-df must cover floor + the write), request floors must equal the issued phase's minimums (`R_REQUEST_FLOORS`), and a ROOT capacity document (`root_g1_count34_stage_capacity_v1`) whose named phase row (>= 1 MiB) contains the reservation, as the old operator demanded (`R_CAPACITY_*` refusals, 8 tested). The remote program additionally requires `free >= floor + 1 MiB` on both filesystems before creating the parent.

## Root sequence (nothing issued)
1. ROOT supplies an ISSUED joint-storage phase with an explicit row for this 1 MiB and the capacity document (`capacity.FALSE-TEMPLATE.json`).
2. `make_request.py --phase <phase> --out request.json`; sol-g1 reviews program/runner/check/request (scope `ROOT_ONCE_G1_COUNT34_EVIDENCE_STAGE_V1`).
3. ROOT fills `root-once.FALSE-TEMPLATE.json` and runs `cd /tmp && python3 -I -B run_once.py <once>` once (also board rescan; one unconsumed once). A partial/uncertain result consumes the once (parent dir exists = refusal on any rerun).
4. Independent acceptance of `receipt` (size 13884, sha 0e537a99, custody_appends 0); then count `failure_chain` is readable by the draft Reader. Count family review and complete disposition review remain separate.

## Tests
`test_stage.py` (7) synthetic temp dirs with patched PARENT/DEST/statvfs/user, `test_runner.py` (22). No network, no <CLUSTER_STORAGE> writes.

Runner for the later draft/finalize: recommend r3-retained d6d13ca8 (diff vs r2 in the draft-prep REVIEW.md).
