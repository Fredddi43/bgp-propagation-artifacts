# H3 packet #2a: chained H3 release runner (ROOT-SPEED-CHAINED-WAVES)

Author 4ba6111c (h3_author). Reviewer review2 7f4c18c0. Local only; nothing executed.

- `chain_h3.py`: a port of f4d's d60 chain.py (same gate/assessment predicates), using waves_v2 bdaf8e14 as the only
  release primitive.
  * Per group in `authority.groups`: waves 0..3, then the assemble-only release.
  * At the end it awaits every assembly (sacct singleton) and runs `assembly_capture.py` once per group, then writes
    `predecessors.json` (the input to the H3 audit-only v4 freeze).
  * Gates G1-G3 before every release: posts STOP-scan, no foreign live dev job except root's
    allowed_concurrent_jobs, fresh df models/results.
  * After each wave: the reviewed H3 waiter terminal_state, then outcome_capture 4e51e245 and size_capture 8a3a524e.
    It stops on: any non-COMPLETED task, a changed earlier shard, a file > 512 MiB, a shard > 8 GiB, a shard > 6 GiB
    (growth review is not mechanical), or a cumulative H3/H1-d30 apparent ratio > 1.10 (H3-C2).
  * No A2 credit: the H3 row is a per-live-wave cap and completed outputs are resident.
  * Never: release audit/audit-finalize, retry, cancel or delete.
- `assembly_capture.py`: the assemble-phase subset of the reviewed H1 r3 chain_capture read discipline, plus a check
  that audit-plan.json binds the same receipt and manifest. It exports refs, counts and lstat sizes only.
- `chain-authority.TEMPLATE.json`: what root signs. One authority covers all four groups (order mixed7-d30, ris7-d30,
  mixed7-d60, ris7-d60; first = the binding first_group).
- Tests: test_chain_h3.py (stateful simulator over the ACTUAL held records) and test_assembly_capture.py; 11 passed.
  `mutation-proof.txt`: 4/4 caught.
- Conditions it implements: review2 C6 (waves_v2 only), C7 (no scancel; the originals stay held), C8 (binding from
  build_binding.py ebc432c4 with root's real minimum; no ROOT_FILLS may reach an executed authority).

## v2 amendment (review2 concurrency ruling K1-K5)
- K3: assess() also stops if the cumulative H3 allocated bytes / H1 d30 allocated bytes of the same indices > 1.50
  (authority field allocated_ratio_max 1.50). Every group's wave 0 is therefore a measured wave on both apparent and
  allocated bytes before its wave 1. Test + mutation M5.
- K1: the df gate uses the authority's models_minimum_bytes. Root sets it to the v26(-concurrent) joint minimum.
- K2: groups run sequentially, so at most one live H3 build wave. An assemble may overlap the next group's wave; the
  h3_assembly row is in the joint sum.
- K5: no node pinning, no cancel/resubmit; each wait poll also records a read-only `squeue -h -j <job> -o '%i|%T|%r'` (PENDING reason) to <step>-wait/latest-squeue.txt as evidence, never as a decision input.

## v3 amendment (review2 moved run dirs, ROOT 05:33:35Z)
- Scan/event directories are no longer constants: authority field scan_dirs (>= 2 existing canonical dirs under the worker tree; the first holds handled-posts.txt). A STOP posted in any current review2 run dir is seen. Test added (14 passed).
