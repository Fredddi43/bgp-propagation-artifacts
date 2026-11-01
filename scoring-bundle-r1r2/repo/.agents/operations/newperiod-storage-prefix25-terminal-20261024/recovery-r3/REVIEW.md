# Cold-prefix 2025 backup: r3 successor for the nine unstarted tasks (author Opus f4d75bb1)

**Evidence.** Capture approval d23a6a2e; capture-v1 passed; diagnosis `../diagnosis-v1.json`.
- Task 0 (rrc00) completed and verified. verification.json 2f92ac1a: full remote download and all 1460 members
  verified, revision e0f900c1, archive 9deda9d7 / 11,208,335,128 B, sources kept. Its temporary archive was removed.
- An author public-metadata check (`../hf-metadata-v1`, paths-info only, no download) matches the lfs sha and size.
- Tasks 1-9 each failed 0-4 s after start, all at archive.py L81 `free>=500GiB` on the models filesystem, before
  `dest.mkdir`. All nine logs are identical (b7ae1449). No dest, temp or hf-cache exists for 1-9, and no source was
  touched.
- The 9 public targets are absent at main (head e0f900c1).

**The change is resource and namespace only.** The diff against r2 is exactly that; a test pins it.
- archive.py:
  * new OUT/TEMP namespaces (`*-r3-20261024`), so r2 evidence stays untouched;
  * index must be 1-9 (task 0 refused before any write);
  * models predicate 500 GiB -> 483,183,820,800 B, the root joint phase v2 minimum (74f93332, which includes the
    1 GiB archive metadata);
  * results 52 GiB unchanged (one 20 GiB temporary archive + 32 GiB floor).
  * Source checks, member hashing, no-overwrite, immutable commit, full remote download hash and source preservation
    are byte-identical.
- transport.py:
  * r3 ROOT/TEMP;
  * stage predicate 483,183,820,800 B;
  * held array `1-9%1`, job name `bgbench-cold-prefix25r3`;
  * reviewer `/root/opus_review` allowed, author session <SESSION_ID> refused;
  * **an exact root joint storage admission ref is required in the review**.
- job.sh: r3 ROOT only.

**Capacity at capture (08:00Z), informational only; root owns admission.**
- models free 534,414,098,432 B, above 483,183,820,800.
- results free 56,270,782,464 B, against 55,834,574,848 needed: about 0.4 GB margin. Any other results writer would
  make a task fail closed at L83.
- Sequential `%1`: each task deletes its verified temporary archive before the next starts. Task 0 took 55m45s for
  11.2 GB, so about 8-9 h for nine.

**Not requested:** a retry of 52477689, pruning, deleting r2 evidence, or any HF overwrite. A source prune stays a
separate proposal after all ten verifications plus a fresh consumer proof and root review.

Tests: `python3 -m pytest -q -p no:cacheprovider test_archive.py test_transport.py` -> 22 passed.
