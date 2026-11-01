# prune25-v1: code-only successor of the reviewed prune-r3 for 2025 cold-prefix groups (author Opus f4d75bb1)

**Status.** Code for review only. No request is frozen, nothing executes, nothing is authorized. The executable request
needs the actual r3a verification receipts and the inputs listed under "Not in this packet".

**Scope.**
- At most the ten 2025 collector groups.
- rrc00 receipts sit in the 52477689 r2 root; the other nine in the 52479088 r3 root.
- Batches are sequential, at most 3 groups each and at most 4 batches.

**Unchanged from prune-r3.**
- prune.py: authorization/request/admission binding, the 600 s fresh mechanical admission, verification + source
  manifest binding, in-process open-FD scan, and the public LFS sha/size check at the receipt revision. Per file it
  checks type, owner, nlink, device, size, mtime, inode and full sha, then writes an exclusive fsynced unlink journal
  and pruned.json.
- consumer_probe.py: argv/cwd/fd/maps capture of own processes, bounded.
- execute.py: both-host fresh probes before each batch, only named unreadable-daemon exceptions, stop on the first
  mismatch, no retry.

**Changes.**
1. Paths: a per-group backup root and its own archive.py sha (r2 6a397277 for rrc00, r3 b1441c21). Year 2025.
   Control files go into one fresh `storage-prefix25-prune-20261024`; the stage refuses an existing root.
2. Terminal check: `sacct -j 52477689,52479088`. Task 0 and every selected group's task must be COMPLETED 0:0.
3. Active inputs: the stale R1-v10 disjointness and R1 process special case are replaced by
   `request.active_input_disjointness`, a record that root/native must supply. It lists every active or pending
   job's bound input metadata, each with an empty `prefix_events_references`. Any probe match (argv/cwd/fd/maps)
   refuses.
4. Restore drill (reviewer requirement 3b614f41 / c9bfe805): groups in `request.restore_drills` (rrc00-2025) need a
   real restore.py receipt for the same revision/archive with at least one restored member. Each restored file is
   re-hashed to the manifest sha, and the live source sha is checked against the same manifest sha before any
   unlink. pruned.json binds `restore_recipe_sha256` and the drill receipt, and execute.py checks both in every
   proof.

**Tests: 25 passed.**
- prune: real prune.py on a synthetic world for both roots, with refusals for drill mismatch, missing drill, changed
  source, stale admission, wrong approver and changed remote. Every refusal leaves all sources in place, and each
  fails at its intended assert.
- execute: two-array scheduler parsing, consumer capture damage, and the full 4-batch run with refusals for an
  expired capture, source use, a partial prune, a missing drill proof, a prefix_events disjointness reference and a
  non-root approver. The last two make zero host calls.
- generated stage/batch scripts run locally.
- probe: a clean world, then an open selected FD is detected; out-of-scope groups are refused.

**Not in this packet; required before an executable request.**
- The r3a terminal capture and per-task verification assessment (the nine receipts).
- Root/native active-input disjointness and confirmation that no pending N op reads 2025 prefix_events.
- The real rrc00 restore drill under its own approval naming the HF read.
- Unreadable-process exceptions observed on both hosts.
- Root's exact one-shot authorization (reviewer_worker /root).
