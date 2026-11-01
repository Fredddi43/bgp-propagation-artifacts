# d300 operator v4 (recovery-parent successor of v3)

Prepared for independent review; no execution authority. v3 (including its consumed `actual-stage_hold`) is untouched.

Cause: v3 stage consumed with D300_REMOTE_NAMESPACE_PATH because `recovery/` (parent of the fresh namespace) never existed.

Change (only `remote.py`; `remote-delta-v3-to-v4.patch` is the full diff). operate.py, prepare.py, transport.py and ssh_contract.py are byte-identical to v3 (same sha256), only their directory differs:
- The namespace predicate no longer requires `FRESH.parent.is_dir()` for every action. `recovery_state()` is read-only: if the parent is absent and action is `stage`, it requires the grandparent to be a canonical dir owned by the running user with the setgid bit (else D300_REMOTE_RECOVERY_GRANDPARENT). If the parent exists it must be a non-symlink dir owned by the user (else D300_REMOTE_RECOVERY_PARENT). Absent parent on pre_submit/install/preflight still refuses with D300_REMOTE_NAMESPACE_PATH.
- Stage creates `recovery/` with a single `os.mkdir(..., 0o700)` (no parents) only after custody/floor/source-set preflight and the NAMESPACE_EXISTS check, immediately before `FRESH.mkdir`. The result carries `recovery_created` (path, device, inode, mode, uid, gid, allocated_bytes), written by the operator into `stage.json`; it is null when nothing was created.
- Cap charge: the created directory's allocation must be <= 1 MiB (D300_REMOTE_WRITE_CAP) and it joins the allocated-bytes census (<= 64 paths, <= 1 GiB, D300_REMOTE_ALLOCATED_CAP) and reported `allocated_bytes`.
- Live facts (read-only ssh stat, 2026-10-27): grandparent `sensitivity-parallel-timing-budget-v2` is <USER>-owned, mode 2755 (setgid), inode 24497606, contents claims/ controls/ work/ .allocation-probe-shard27-cleanup-v3-lock; `recovery/` is absent.
- Actual namespace is `actual-stage_hold` / `actual-install_release` under the v4 directory; none exist. Candidate request/job.sh and the frozen plan/successor are byte-identical to v3.

Tests (python3 -I -B from /tmp): test_operate 11, test_prepare 8, test_reason_codes 3, all pass. New: `RecoveryParentTest` loads the real v3 and v4 remote.py against a temp tree: v3 raises D300_REMOTE_NAMESPACE_PATH for the absent parent and creates nothing; v4 creates it once (identity/mode/uid recorded, allocation counted), refuses a second stage and absent-parent pre_submit; v4 refuses non-setgid grandparent, symlinked or non-dir parent, and leaves nothing behind on a failed floor preflight. The reason-code test now diffs v4 against v3: the only removed predicate is the old namespace one; added are the new checks listed above. Both FALSE root templates refuse `--check-only` at the issued-root gate.

Templates regenerated for phase V48 (`newperiod-joint-v48-20261027/root-joint-storage-phase-v48.json`, sha256 913754c6...baa) and v4 pins (remote.py 2c244ccb...aaae; others unchanged hashes).

Re-review set: see report to root. Adoption-007 pins only phase and plan (no operator path/hash), so it stays valid for v4.
