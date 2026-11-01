# Corrections to REVIEW.md (root code/binding review 4cdf13f4), without changing the reviewed packet bytes

1. Capture authority: REVIEW.md cites approval 74a83aa3. The actual root failure capture used approval 6c919db1;
   74a83aa3 was not used.
2. Evidence strength: the captured frames show the ValueError in original_stage.utc, called from the summary-onset
   check. They do not establish actual null or empty counts. Root's whole-population diagnostic ended rc 255 with
   empty output after 304 s, so mutable summary content is not ruled out. The fix rests on the original producer's
   semantics (src/bgbench/eventset.py:72) and on null, empty and mismatch parity in the tests. It does not rest on a
   successful diagnostic. REVIEW.md's sentence "a falsy first_observation ... the actual symptom" is the
   author's inference, not a measured count.
3. Binding prose: the r3 binding request inherited r1's failure text and a 128 GiB replay figure. The current state
   is: r2 failed as job 52473649; replay is about 130 GiB, prospective only after Aug31 completes. Root's resource
   admission 479f28d9 supersedes that prose. Its allocation is 1 history + 100 Aug31 + 384 R1 (conservative)
   + 1 post-eval + 64 floor = 550 GiB.
