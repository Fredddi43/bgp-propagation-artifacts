# rrc00-2025 real restore drill (author Opus f4d75bb1). Reviewer requirement (c9bfe805) before any rrc00 prune.

Scope: one held singleton CPU job (4 CPU, 8 GiB, 2 h, no requeue or node pin).
- It streams the immutable public archive prefix-events/rrc00/2025.tar.zst at revision e0f900c1 (9deda9d7,
  11,208,335,128 B) through the reviewed restore.py (CODE PASS 3d990bfc; byte-identical copy). This is one HF read,
  no write.
- Whole stream sha/size, every member sha/size and the member set are checked against the pinned receipts
  (verification 2f92ac1a, manifest 68ebee61).
- Exactly one deterministic member is restored: the smallest by manifest size, at most 64 MiB. It goes into a fresh
  results directory `storage-prefix25-drill-20261024/rrc00-2025` with a restore-receipt.json.
  `drill-result.json` binds that receipt for the prune successor's `restore_drills` entry.
- The live-source comparison happens later, inside prune25 before unlink: the restored sha must equal the manifest
  sha, which must equal the live source sha.
- No source read or write. No prune, delete or retry.

Transport: a minimal edit of the reviewed r3a transport (30 changed lines).
- Drill namespaces.
- Singleton held check: no array; 8G; 02:00:00.
- Stage predicates:
  * models >= phase v3 489,626,271,744 B;
  * results >= 32 GiB floor + 64 MiB. A running r3a task can hold its 20 GiB temp archive; the drill only adds one
    small member.
- Approval keys `restore_drill_authorized` and `hf_read_authorized` must be true, `prune_authorized` false, and the
  author session is refused.
- **The exact root admission ref is still required.** Root must admit the drill's small writes and the concurrent
  network/CPU.

Timing: it can run while r3a runs (different collector, read-only on HF), or after it. It is only useful once a prune
is actually wanted.
Tests: 21 passed (drill 4: smallest-member-only restore and refusals; transport 17).
