# D2 r5: an explicit 128 GiB per-task memory floor (supersedes the unexecuted d2-fix-v4)

The actual D2 array 52474923 (approval 2bf740ce) ended OUT_OF_MEMORY on both tasks at 14 GiB, with MaxRSS at the cap
(d2-fix-v3/d2-oom-sacct.txt 79afba91). It is preserved, with no retry and no fetch. Root relays the user's explicit
authorization for ample RAM and speed, and asks for no incremental memory guessing
(d2-fix-v4/root-memory-review-response.json).

Change (`build_d2_r5.py` from approved d2_r3; d2_r5.diff):
- `MEM_FLOOR = 128 GiB`, and `resources()` takes `max(MEM_FLOOR, the original estimate)`. This gives 128 GiB per
  task, 256 GiB in total, about 44x the stored tensor bytes.
- MEM_FACTOR stays 2, and the original estimate is kept, so a larger input would still raise the request.
- MEM_CEILING is 480 GiB.
- The job script 805f427c equals the approved 733a6676 script except `--mem=128G`. Same 66 cells, code, inputs,
  plan 6e18854b, report 049c7a9c, 2 h and 1 CPU.
- run-records move to this directory, a fresh one-submit guard.
- 3 tests pass.

d2-fix-v4 (MEM_FACTOR 16, 52 GiB) is superseded and was never submitted.
