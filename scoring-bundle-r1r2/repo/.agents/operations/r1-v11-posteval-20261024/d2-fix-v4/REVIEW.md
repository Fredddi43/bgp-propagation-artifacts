# D2 r4: memory only, after the approved D2 array 52474923 ran out of memory

Actual (approval 2bf740ce, one submit, d2-fix-v3/run-records):
- 52474923_0 (d30) and _1 (d60) both ended OUT_OF_MEMORY 0:125, after 3m32s and 2m49s.
- The batch-step MaxRSS was 14,641,048 K and 14,642,352 K: exactly the 14 GiB request
  (d2-fix-v3/d2-oom-sacct.txt 79afba91).
- No fetch was made, because both tasks had to complete 0:0. Not retried.
- Read: d2_r3 assumed decoded tensors and objects stay within 2x the stored bytes. The actual peak is unknown and is
  at least about 5.1x the stored bytes (2.85 / 2.89 GB), because RSS was at the cap when the kernel killed the
  process.

Change (`build_d2_r4.py` from approved d2_r3; d2_r4.diff): MEM_FACTOR 2 -> 16 and nothing else.
- This gives 51 / 52 GiB per task, more than 3x margin over the observed lower bound, and under MEM_CEILING 480 GiB.
- run-records move to this directory, a fresh one-submit guard. The failed d2-fix-v3 records stay preserved.
- The job script e10e5f37 equals the approved 733a6676 script except `--mem=52G`.
- Same cells, code, inputs, plan 6e18854b, report 049c7a9c, 2 h and 1 CPU.
- 3 tests pass.

If an out/rescore-d*.json partial exists, the job's `test ! -e OUT` refuses, and it stays a failure. The reviewer
may want the bounded out/ stat plus log-tail diagnostic (same shape as a1fbb93e) before approving.
