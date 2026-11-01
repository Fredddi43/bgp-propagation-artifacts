# Review packet: N frozen-inference adapter, revision-next (finding A1 only)

- Author: Opus 5.5 implementation session `065d2f16` (claude-opus-5-5), role label `/root/opus_implementation`.
- Status: synthetic-only candidate for independent review. No commit.
- Base: the CODEPASS candidate (round-2 verdict, pins 3366fd5a, `predict.py` a2c0285b, `test_predict.py` 35c79dbe).
  Those files in `..` are unchanged. This directory is a separate candidate. Exact bytes: `pins.json` here.
- Answers finding A1 of the N-validation contract review
  (`.agents/workers/opus-takeover-20261021/review/n-validation-contract-review/review.txt`, lines 122-131).

**Not done and not authorized:** no real data, remote read, fit, calibration, freeze, seal, prediction, label read or
scoring. The R1 publication file itself (remote) was not read. The fit contracts are unchanged:
`provenance_frozen` (frozen-2025 plan) and `provenance_updated` (N-core ledger, `fit_count` from the recipe) are
byte-identical to the CODEPASS candidate.

## A1: the frozen-2025 publication is pinned and kept apart from the updated one

`checked_publications(batch['publications'])`, called from `checked_slice_batch` (stage `slice`, before any custody
read or access-log record):

1. `publications['frozen_2025'].sha256` must equal `FROZEN2025_PUBLICATION_SHA256` =
   `66c2ce8c04aabd80236e2576b29d19a913f67d82706d8c37250de41638583def`. That is the decision-calibration receipt
   the R1 release draft binds (`r1-arm-spec-20261020/draft-with-arms.json`, sha 62e383e1,
   `decision_calibration.receipt`). A freshly computed frozen-2025 publication, including one recalibrated on
   N-validation, has other bytes and is refused.
2. The `updated` publication must differ from it in both sha256 and path.
3. Both publications must list fit ledgers as `{path, sha256, ...}` objects, and no path or sha256 may appear in
   both. So an `updated` publication that names a 2025 ledger is refused, and so is the reverse.

`checked_rules` is unchanged. It still requires the arm's own fit ledger and published rule entry in the
publication of its training period.

## Files

| File | Change |
|---|---|
| `predict.py` | `REPO = HERE.parents[3]` (one directory deeper), the constant, `checked_publications` and its call |
| `test_predict.py` | `REPO_ROOT`/`prepare.py` paths for the depth; `build_world` pins the synthetic frozen publication; 6 new tests |

## Tests

- `test_predict.py`: 62 passed (the 56 CODEPASS tests unchanged in behaviour, plus 6 new).
- New: the constant equals the R1 draft's receipt sha (draft byte-anchored); the real constant refuses the
  synthetic frozen publication; 4 parametrized refusals (recalibrated frozen-2025 publication, frozen reused as
  updated, updated naming the 2025 ledger, frozen naming the N-core ledger). Each asserts its exact internal reason,
  the public stage `slice`, and that no access-log record was written.
- Negative control: with the `checked_publications` call removed, the 5 behavioural A1 tests fail and 57 pass.
- `ruff check`: pass.

## Limits

- The pin binds the publication's bytes, not its remote file. The run reads it through the existing `bound_json`
  (sha-checked). Whether the file at that path still has those bytes is checked only at run time.
- Ledger separation compares path and sha256 only. It does not parse the ledgers.
