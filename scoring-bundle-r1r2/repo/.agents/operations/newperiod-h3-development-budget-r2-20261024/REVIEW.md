# H3 four-group development package: actual pins + 8 GiB writer successor (author Opus 4ba6111c)

Author: claude-opus-5-5, worker /root/opus_review, session <SESSION_ID>. This session cannot approve it. Independent
reviewer: f4d75bb1 (/root/opus_implementation), as for timing r2. This is local code and metadata only:
- no host calls;
- no protected-payload reads;
- no stage, submit, release, fit or admission.

## Files

### `assemble_actual.py`
It closes C1 of my review (61a93880) of the prospective assembler
`newperiod-h3-development-launch-20261024/assemble.py`. That assembler (900ce0a0, author f4d75bb1) is loaded by sha
and is not edited.

The 17 published refs come only from the accepted finalize capture. Each link is checked:
- assessment f5100a6b: the ACCEPTED verdict, job 52498300, done 83e8a6a3, plan f1bd211c;
- capture `execution-v1.out` e291d9cd, which names done 83e8a6a3 and 17 files;
- `done.json` 83e8a6a3 itself: passed, gate_issued, predictions_computed false, result fit_authorized false and
  graph_payloads_read false, the four groups;
- exactly 17 names at the published remote paths;
- every local captured copy hash-equal to its ref;
- each gate: passed, `supervised_graph_build` only, with its single manifest equal to the published construction
  ref.

The kernel plan is the local 4791f41f, which equals the finalize plan's `kernel_plan` ref.

The single delta is `writer_bytes` 2 GiB -> 8 GiB, set through the module's `R` before `assemble()` runs.
- It is the same reason and value as the reviewed H1/timing r2 successors. Timing wave 0 failed only at
  original_budget.py:24 under 2 GiB, and H1 wave 0 measured a max shard of 3,080,729,723 B for the same
  14,787-event population and grid.
- Namespace is unchanged (`sensitivity-parallel-v1`): H3 never ran there, and controller claims are per group key
  (controller.py:173-176), so a stale claim would make staging fail rather than reuse anything.

### `actual-v1/`
The frozen output:
- plan e32b00eb, 279 files;
- unchanged original controller 027b7a68, root `.../controls/mixed7-d30__mixed7-d60__ris7-d30__ris7-d60`;
- `binding.json` recording every ref above.

The owner `build_package` and `controller.groups()` validated it during assembly. A rebuild reproduces it: the
package/plan/binding are byte-identical, and `config.json` differs only in local template paths.

### `waves.py` 5301e876
A port of my timing r2 dispatcher 78e81655 (CODE PASS by f4d75bb1). Deltas, shown by `diff`:
- the exact four H3 groups;
- controller pin 027b7a68;
- the frozen grid also requires `scratch_bytes == 256 MiB` and arm mixed7/ris7;
- authority kind `h3_development_phased_release_v1` and admission kind `newperiod_h3_initial_wave_admission_v1`;
- the audit-chain reservation adds `audit_concurrency x scratch_bytes`, i.e. H3's own audit scratch, which the
  controller reserves (controller.py:56) and timing does not have.

Everything else is byte-identical: the build wave of 132 GiB, the prior-output assessment, the >6 GiB growth
review, the held/script/df checks, and the initial binding only on the first build wave.

### `completion-tools-v1/`
A port of the timing r2 completion tools (outcome_capture 30ca6377, size_capture f63c564e):
- namespace/root/groups changed;
- the shard `arm` must equal the requested group's panel (it was `== 'timing'`).

Still metadata/lstat only, logged first. H3 shard roots also hold about 263 `*.status.json` files. That is under
LIMIT 4096, and they are counted as other_regular.

### `resource-proposal.json`
Finite and honest:
- 132 GiB per live build wave and 40 GiB per audit chain;
- declared upper bound 2,357,937,045,504 B, which is not a request;
- an estimate from H1 measurements (not measured for H3): <= 646.5 GiB logical / ~97 GiB allocated for all four
  groups.

Root phase16 (8d3f22e4, 634 GiB) holds 0 for H3. The first wave needs a root decision (>= +132 GiB), and the 43 GiB
substitution is not assumed.

## Tests
- `test_waves.py`: 24 passed. The 19 ported timing r2 tests plus:
  - H3 audit-chain scratch reservation;
  - the delta vs the prospective assembler: only writer, with the upper bound exactly 2,357,937,045,504;
  - capture-binding refusal;
  - frozen reproduction.
- `completion-tools-v1`: 17 passed (16 ported plus a foreign-panel shard refusal).
- Negative control: dropping the scratch term fails exactly the two audit-chain tests.

## Not included; each still needs its own step
1. Independent review of this candidate by f4d75bb1.
2. Root joint storage phase for H3.
3. Stage plus held submission through the original controller, then a held-readback review.
4. Initial binding (approval + admission) and the wave-0 root authority.
5. A wave waiter for the H3 job ids (a successor of the reviewed H1 wave-waiter-v2), which needs its own review.

One live H3 wave at a time, in group order, is a root-authority policy. As with timing R1, waves.py does not
enforce it.
