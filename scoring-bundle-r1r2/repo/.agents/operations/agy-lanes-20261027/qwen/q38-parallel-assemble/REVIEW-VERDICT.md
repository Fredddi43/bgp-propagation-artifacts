# Independent review: q38 parallel assemble (A) and q32 seam fix (B)

Read-only review; the only file written is this one. No protected data read.

## (A) q38-parallel-assemble: PASS (NITs only, 0 BLOCKER, 0 RISK)

1. Checks skipped or weakened: none found.
   - parallel_assemble.py:127-143 repeats the pinned loop body (custodian L465-482) per shard: manifest sha check,
     check_shard_binding, Unbound-shard require, the pinned `verify_outputs` object (imported as at pinned L458),
     contract reads, population require, bindings over every file in the shard dir.
   - Cross-shard "Shards differ" / "Shard contracts differ" requires, global population require, fresh-dir guard,
     mkdir(parents=True), contract bytes, sorted ledger and receipt field set are kept (L146-174).
   - Pool re-raises the lowest-index shard's error (ex.map in order, L90): first failing shard wins.
   - NIT parallel_assemble.py:127-143 vs custodian L471-474: serial raises "Shards differ" at shard i BEFORE
     verify_outputs(i); parallel runs verify first, so with two faults the message can differ. It still fails.
2. Sha map: sound.
   - Keyed by str(path) only; a miss falls through to the pinned real sha and is cached (L56-62). Resolved path added via
     setdefault (L51); symlink and target hash identically.
   - Precompute runs after the fresh-dir check, over write-once shard files whose builds are all done (driver waits for
     every build done.json). Same single-read-moment argument as serial, minutes earlier.
   - pre_hash swallows errors, so an unreadable file stays unmapped and the real sha re-raises at check time.
   - sha patched in both module dicts and restored in finally (L169-172); map cleared. Preamble manifest check uses
     real_cust_sha directly (L113).
   - NIT: a different path spelling is a miss and is recomputed (safe).
3. Merge order and tree: identical to serial.
   - Shards merged in a.shard order (L146-152); per-shard bindings use sorted(iterdir()) filtered to files as serial.
   - Symlink target str(t.resolve()) as pinned L485-487; creation order is not output content.
   - assembler_sha256 = original.sha(original.__file__), the custodian module as pinned.
4. Tests. `pytest` collects 0 tests (it is a script). Run as documented from /tmp:
   `PYTHONPATH=<repo>/src <repo>/.venv/bin/python -B -I test_parallel_assemble.py /tmp/q38rev.X/fx` -> rc 0,
   `FINAL={"events": 2, "built": 2, "unbuildable": 0, ...}` (internal asserts: byte-compare, corrupt and missing .pt
   fail identically, empty-map fallback).
   - NIT: fixture is 2 events / 3 shards; many-shard ordering is verified by reading only.
5. Pins and chaining.
   - sha256sum parallel_assemble.py = f35ba54e6870d376534e3ca246afbcc7d7a750623a16549c3e6ee182801d4406 = literal at
     run_assemble_par.py:100 (`plan['files'].get(...) or PA_SHA256`).
   - group_phases_par_job.sh:29-30: nonzero rc or missing done.json after assemble does `exit 1` before the
     master/export/audit loop; each later phase also exits 1 on failure.
   - NIT: "assemble-already-done" trusts an existing done.json (same as the pinned flow).
6. sbatch quoting (REPORT.md:107-110): `--wrap="'/bin/bash $C/... valid $G $2 112'"` expands locally, remote shell strips the
   single quotes, giving one clean wrap string. Needs DC/B set (REPORT.md:84 does). NIT: REPORT.md ~L95 contains a
   non-runnable placeholder line `bash <CLUSTER_STORAGE>/.../q38-validate...`.

## (B) q32 seam fix: CHANGES (diff against the equivalence-tested copy not possible)

- 3 hunks present: parallel_phases.py:142 and :342 (`getattr(adapter, "_pp_seam_master"/"_pp_seam_audit", adapter.master/.audit)`),
  and :437-440 (capture of mod.master/mod.audit before the lambdas). No other use of the shadowed attributes remains (grep).
- Behavior-preserving by reading: the seam is read from the same adapter-replaced function objects the harness uses; the
  unshadowed harness path has no `_pp_seam_*` attribute so the getattr fallback is the original expression.
  _replay_dir (L54-66) walks co_consts, which explains the failure on a lambda.
- BLOCKER (verification gap, not a code fault): <BATCH_HOST> NFS reads of `$EQ/parallel_phases.py` and `.seamfix` timed
  out 3 times (60-100 s); no older local copy exists. Local sha 6fddec14bb0ab3fa962a65c014cbfe26c513039cc35f8a87130b7845ee2237b3
  matches the sha in q27-origin-export/STATUS.md:26 (OLD bddb56da...). Root must run
  `sha256sum $EQ/parallel_phases.py.seamfix <both controls>/parallel_phases.py` and diff `$EQ/parallel_phases.py` (old) against the local file,
  expecting exactly those 3 hunks. The 05:36Z root decision still requires an equivalence RESULTS.json for this exact sha.

## Addendum (late read succeeded)
- A background read finished: `$EQ/parallel_phases.py` listed with sha bddb56da... (OLD) in the same command that then `cat`
  returned bytes whose sha is 6fddec14... and diff to the local file is empty. So the file at `$EQ` was replaced by the fixed
  bytes between the two reads (consistent with the STATUS note that the fixed file is re-pushed to `$EQ`). Local file == fixed
  `$EQ` bytes: confirmed. The OLD bytes are no longer available to diff, so "only the 3 hunks changed" is still unproven;
  the hunk-by-hunk reading above stands. Equivalence RESULTS.json for sha 6fddec14 is the remaining gate. (B) stays CHANGES
  only for that unverified claim; code review of the 3 hunks is clean.

## Could not verify
- Anything on the cluster (live jobs, $EQ bytes, controls copies, plan.json pin).
- 128-shard behavior (ordering argued from code only).
