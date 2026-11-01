# Review packet: independent R1 numerical verifier (LOCAL; synthetic fixtures only; nothing authorized)

- Author: claude-opus-5-5, session <SESSION_ID> (`/root/opus_implementation`).
- Governing documents: contract 48238fc3, addendum-1 7c161f63, root adopted-rules.
- **No real input read:** no report, per-event, label, prediction or manifest bytes were touched. No host action,
  no job submitted, no number posted.
- The companion capture packet (K1-K3) is reviewed separately: `../REVIEW.md`, pins f2b223ee.

## Files

| File | What |
|---|---|
| `verify_r1.py` | Pure functions. Imports only hashlib, json, math, datetime, operator and numpy (an AST test enforces no bgbench). |
| `run_verify.py` | Host CLI: integrity_exact + independent_recompute from hash-bound JSON inputs. Exclusive output. Not authorized to run. |
| `test_verify.py` | 53 tests, synthetic only. |
| `mutation_controls.py` | 12 guard removals. |

## Independence

- Definitions come from the staged-equal sources at the addendum's citations. Their arithmetic is re-derived, never
  called:
  - **Tie-aware AP:** an expectation per ranked slot, summed with `fsum`. The evaluator uses harmonic numbers per tie
    group.
  - **P@k:** an expectation per slot.
  - **Jaccard and `new_tp`:** integer set ratios.
  - **Slice variables and the two-threshold decision.**
  - **Blocks:** the first-onset UTC day per incident. Ranking families use blocks of eligible rows only, and
    Jaccard families use all rows, as in the source.
  - **Bootstrap:** the `default_rng(seed)` stream restarted per contrast, with draw order seeds then blocks, and
    blocks sorted by `str` (rule C-b).
  - **Percentile:** linear interpolation.
  - **Holm:** stable order with a running maximum.
  - **Arm derivation:** gbdt skipped, frozen-library history excluded, one configuration, paired seeds.
  - **Retrospective-14 grouping.**
- The staged evaluator modules (sha-pinned in the test) serve only as a **test oracle**. Against them:
  - per-event metrics agree on 700 random rows, including the full `score_membership` output with slice decisions;
  - AP and P@k equal exact `Fraction` enumeration over tie orderings;
  - bootstrap and interval match, including broadcast deterministic arms;
  - Holm, the C1-C4 families with the whole-system pair, the arm derivation and the retrospective-14 all match.
- **Rule V1** (`close`): counts, memberships, hashes, flags and decisions are exact. Floats pass when
  |a-b| ≤ 1e-12 + 1e-10|ref|. p-values compare by the tail count recovered exactly from p (rule C-c); p = 1 is
  compared as p. Near-zero samples are a diagnostic, and a count mismatch still fails.
- **Findings** carry one of the kinds integrity_exact, independent_recompute, rescored_from_labels or
  projection_lossless, and are never merged into one flag.
- **Contract stop conditions S2/S3:** any integrity failure stops the recompute. It is reported as "not run", with
  no partial recompute on unverified bytes.

## What each class covers

**integrity_exact:**
- B1: hashes, identity, and the driver 4573658e and custody 409e1171 shas.
- B2: the per-event key set and file set, and each file's sha.
- B3: the 90 pre-declared failures byte-equal and first, and every scoring failure a committed cell.
- B4: unique ids, `population_sha256` equal to the seal's, and aliases equal.
- B5: extent and reliability denominators and bin counts exact, means and bin float sums by V1. Each sum
  aggregates one value per event, at most 8,399 terms, so `fsum` against the evaluator's left fold stays near
  1e-12 relative, inside the rule.
- B6: the analysis status comes from the evaluator-scored set.
- B7: the flags, and `declares_primary_finding` false.
- The arm derivation must equal the held arm spec 9a6d36e8.

**independent_recompute:**
- C1: every family and contrast: difference, ci95, tail count, events, blocks, training seeds, eligible and
  without-new-member counts.
- The eligibility block.
- C2: Holm p values and rejects, the family size, and the whole-system family.
- C5: the 14 named contrasts × 2 horizons, each scored or unavailable with exactly the failed arms, and intervals
  per block type (incident_day, incident, actor).

**rescored_from_labels:**
- The pure per-event math is implemented and tested (`rescore_event`, `compare_event`): AP and P@10 by V1; jaccard,
  `new_tp`, eligibility, new-member counts, slice membership and the two-threshold Jaccard exact.
- **Not implemented:** the adapter that decodes the 66 cells' `forecast_rows_json` payloads and gate 7e48955b's
  test tensors (`target_asns`) on the host. It depends on the class (d) request (addendum §6d), which is not
  written yet. P1, the cited cells beyond the 66, is still pending. Cells are never chosen by results.

**projection_lossless:** the unchanged K3 projection 72bb5d9f/442f3cbc (capture packet). Not evidence for any
number.

## Decisions requested BEFORE any run (pre-results; reviewer, then root)

**P-b: bootstrap sample summation (`--sample-sum`, required, no default).**
- Rule C-a allows `math.fsum` or numpy pairwise sums.
- The synthetic tests show the choice matters only for samples that are exactly zero in exact arithmetic, which
  discrete metrics such as P@10 produce:
  - `fsum` puts such a sample on 0.0, counted in both tails;
  - the evaluator's pairwise sums put it on ±ulp, counted in one tail;
  - so the recovered tail count differs, and rule C-c fails it.
- `test_fsum_sample_sums_differ_only_in_tail_counts_with_exactly_zero_samples` shows that every fsum mismatch is
  exactly such a tail count on a contrast with near-zero diagnostics, and nothing else.
- `numpy_pairwise` forms block sums and per-sample totals with numpy's pairwise `sum` over the same seed × block
  layout. It matches the oracle exactly, with zero failures on the same synthetic families.
- **Author recommendation:** `numpy_pairwise`. It is permitted by C-a and is not a loosening: tolerances, exact
  tail counts and fsum means are unchanged. Otherwise, run with `fsum` and pre-declare that such tail-count failures
  are expected discrepancies of this known kind.
- Either way, the choice is fixed before results and never changed after a mismatch.

**K2c: slice rules 0291d789.**
- The C1-C4 slice family needs the spec-bound, label-free `…/occurrence-final-v1/slice-rules/issue-time-slice-rule-v6b.json`.
- It is not held locally, and it is not in the frozen capture packet's K2b.
- Requested: one more f19 read by sha, under the K2 approval or an addendum to it.
- The arm spec 9a6d36e8 is held locally. The spec and seal are held in captures A/B.

## Proposed host execution (NOT submitted; needs its own exact approval after K1/K2 and class (b))

**Interpreter:**
- `<RESULTS_ROOT>/work/<PROJECT>/venv/bin/python -I -B run_verify.py …`
- numpy 2.5.2, the evaluation runtime; the verifier refuses any other version.
- This venv carries the stock `_virtualenv.pth`, which is reviewed and accepted.

**Inputs, all read in place and read-only, each checked against its anchor before parsing:**
- `evaluation-control-v1/{complete.json, results/report.json, results/per_event/}`;
- `control-v1/prepared/{spec.json, evaluation/ledger.json}`;
- the seal;
- the two manifests;
- the slice rules;
- the arm spec.

**Output:**
- one exclusive JSON in a fresh directory under B, read back with f19;
- findings only, no per-event content.

**Resources and placement:**
- Bounded by the measured census, not guessed: memory about 10× the per-event bytes, and CPU dominated by about
  76 bootstraps × 10,000 repetitions.
- A single process: a Slurm job on partition `cpu`, 4 CPUs, no node pin, within the user cap.
- One attempt, no retry.
- No labels or predictions; that is class (d), separate.

## Tests

| Suite | Result |
|---|---|
| `test_verify.py` | 53 passed |
| `ruff check` | pass |

**`mutation_controls.py`:** all 12 detected.

| Mutation | Targeted tests |
|---|---|
| AP within-group expectation wrong | 5 failed, 1 passed |
| P@k one slot too many | 5 failed, 1 passed |
| learned decision threshold strict | 1 failed |
| slice cut strict | 1 failed |
| bootstrap draw order swapped | 8 failed |
| percentile interpolation dropped | 8 failed |
| tail count excludes zero | 2 failed, 1 passed |
| Holm running maximum dropped | 1 failed |
| ranking contrasts use all-row blocks | 1 failed |
| reported tail count not compared | 1 failed |
| population check removed | 1 failed |
| integrity stop removed | 1 failed |

Three of these were undetected at first and were closed by strengthening the fixtures: thresholds on the score
grid, an identical-arm zero-sample test, and onset days varying inside an incident.
