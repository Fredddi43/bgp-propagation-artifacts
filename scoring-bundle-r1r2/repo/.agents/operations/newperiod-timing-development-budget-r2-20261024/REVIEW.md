# Timing resource-only successor (budget-r2), frozen candidate, nothing executed

Author: claude-opus-5-5 4ba6111c (/root/opus_review). For this timing artifact I am acting as implementation author by
root assignment. **I must not review or approve it.** The independent reviewer is f4d75bb1 (/root/opus_implementation).

## Why

The original four-horizon timing campaign (plan 7c900715) released wave 52480019_0..15 (timing-d10). All 16 tasks
failed at `original_budget.py:24`, "Producer cumulative output budget exhausted":
- the writer budget was 2 GiB per shard, with a 512 MiB per-file reservation;
- the failure was proven by frames capture 2cc4280b (assessment a62c8d24);
- partial shards were about 1.50 GiB logical each.
This was a resource failure, not a data or source failure. This is the same mechanism as H1, so this successor
mirrors the reviewed H1 budget-r2 design (package review 99e95118, growth delta 0d35613f).

## What changes (`assemble.py`, deterministic, `assembly.json`; plan 06b4b953)

- Fresh namespace: `sensitivity-parallel-v1` becomes `sensitivity-parallel-timing-budget-v2`. It appears only in the
  22 operational files that name it: `controller.py`, `source-timing.json`, the 4 `audit-templates/*.json` and the 16
  `jobs/*.sh`. Each is byte-equal to the original after the substitution (tested). The other 258 of the 280 files, including
  every scientific, source, client and runtime file, are byte-identical.
- `writer_bytes` goes from 2 GiB to 8 GiB for timing-d5/d10/d300/d900. All other resources (2 CPU, 128 GiB RAM, 24 h,
  512 MiB per file, concurrency 16/8, 64 shards, 32 audit shards) and every group field (manifest, gate, years,
  coverage, horizon, audit_callable, limits) are unchanged. The other 6 planned groups are byte-identical.
- The dependent shas are recomputed: source_closure, audit_plan and the files map. `storage.reservation_bytes` is the
  declared theoretical upper bound, 4 + 4 × (64×8 + 1 + 33) = 2188 GiB. It is **not** an admission.
- The original controller validates the plan (`groups()`).

## Dispatcher (`waves.py`), the delta from the reviewed timing `waves.py`

- The controller is loaded from the successor package (a18e2dba).
- `writer_bytes == 8<<30`.
- The initial admission reservation is 132 GiB (4 + 16×8), up from 36.
- **The H1 r2 gates are ported,** additionally bound to the horizon (`group`):
  - each later wave requires root's `prior_output_assessment`: completed indices, retained bytes ≤ previous×8 GiB,
    max file ≤ 512 MiB, max completed shard, preserved, and reflected in fresh df;
  - any completed shard above 6 GiB requires a root `large_shard_growth_review` for that group.

## Completion tools (`completion-tools-v1/`)

These derive from the reviewed H1 r2 outcome/size tools (8e1c6d09). The changes:
- a fresh namespace;
- `arm=='timing'`;
- a request `group` that must be one of the four horizons and selects only `work/<group>`;
- cumulative `through ∈ {16,32,48,64}`;
- no event identifiers or graph contents read or exported.

## Preserved

`old-campaign-disposition.json` covers the following:
- 52480019_0..15 stay failed;
- 52480019[16-63%16] and 52480020-34 stay held and are never released;
- the old partial outputs are retained and never reused.

## Resources

See `resource-proposal.json`. Nothing is admitted. The options for root are:
- logical: 132 GiB per wave, not admissible today;
- measured-allocated: about 43 GiB per wave, admissible after the reviewed prunes.

At most one live timing wave runs at a time, in the order d5 → d10 → d300 → d900.

## Tests

- `test_waves.py` + `test_assemble.py`: 22 passed.
- `completion-tools-v1`: 16 passed.

## Not authorized

Stage, submit, release, retry, cancellation, prune, fit, prediction, score or gate issuance. Each needs f4d75bb1's
independent review and then root's exact authority.
