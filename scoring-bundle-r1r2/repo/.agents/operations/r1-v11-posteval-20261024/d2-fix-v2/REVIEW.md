# D2 blocker: D1 census not_regular = 7086 (all gate tensors are symlinks)

Executed D0/D1 fetch (approval c7e1fab0) gives capture classd-host/evidence-d0d1.json.gz e5e08ddd.
- Plan 6e18854b: 66 cells, report 049c7a9c.
- Census 7b746087: 106 regular files (predictions and rules, 28,570,374,661 B) plus 7086 entries of lstat type
  `other`, sized 148-149 B.
  - These are exactly the d30 and d60 gate tensors `occurrence-final-v1/graphs/2025-v6/d{30,60}s/*.pt`,
    3543 each.
  - The 148-149 B sizes are link-text lengths, so these are symlinks.
- The rescore reads tensors through the original `bgbench.forecast_train.load_partition` (with gate-bound shas),
  which follows links as the evaluator did.
- Two things still block D2 or make it wrong: `d2.captured_inputs` requires `not_regular == []`, and D2 memory and
  time sizing from the census would count link sizes, not tensor bytes.
- Not related to the cold-prefix prune, which covered archived 2023/2024 prefix groups only.

Evidence step (this packet, revised to the reviewer D1b spec in d0d1-capture-and-transport-assessment 287b1e58): `link_census.py`, metadata only, one attempt on <BATCH_HOST>.
- Its paths come only from the approved capture: exactly the census not_regular list, each also a plan tensor path.
- Per path it records lstat == symlink, the readlink text, the realpath, and the target's type and size.
- The target must be a regular file under <MODELS_ROOT>/nobackup/<PROJECT>.
- It sums target bytes over the accepted targets only. No content is read.
- Then a small reviewed d2 change can accept exactly these resolved links and size D2 on the real bytes.

3 tests pass: the payload is exactly the 7086 plan tensor links; the REMOTE program, run locally on synthetic links,
accepts in-root regular targets and flags outside, dangling and non-link entries; the approval gate refuses the
author.

r2 revision (D1b spec):
- The root is the adapter ROOT_FILTER, `.../forecasting-20261017/`.
- Link hops are counted, with HOP_CAP 4.
- Per path: readlink, realpath, hops, the target's type and size.
- A named refusal reason for each failing path: not_symlink, hops, outside_root, not_regular, error.
- Output: a per-horizon summary for d30s and d60s (files, bytes, max), the max hop count, and the distinct target
  directories.
- The tool writes the full output exclusively, then refuses if any path failed.
- 4 tests pass.

r3 revision (review d2-fix-v2-link-census-review: B1-B3):
- B1: the tests now match REMOTE as written. The doc carries hop_cap, the root ends with "/", and the asserts use
  summary/bad/entries. Actual run: 5 passed.
- B2: added cases for a chain longer than HOP_CAP (bad "hops"), a link cycle (bad "hops"; it terminates without
  hanging), relative link text (accepted; the chain is resolved against the link's directory), and a d30s/d60s split
  with per-horizon files, bytes and max_bytes asserted.
- B3: every hop's absolute normalised path is recorded in "chain", and a new bad reason "chain_outside_root" fires
  when any hop leaves the root, even if the final realpath is inside it. No external intermediate hop is allowed.
- The payload is now 4cc45b96, not 6a1ec366, because the payload carries hop_cap 4 and the run_adapter root.
