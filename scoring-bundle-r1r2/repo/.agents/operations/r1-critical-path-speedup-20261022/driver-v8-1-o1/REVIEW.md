# Review packet: LOCAL O1 candidate, driver v8.1 (post-label decode-only for row payloads)

- Author: claude-opus-5-5, session <SESSION_ID>.
- Base: CODEPASS D-1 `driver-v8` (pins 0598f935, review 3c4ed35c), driver **bb7f7e00**. Not the rejected v8b.
- Requirements: reviewer static assessment `review/serial-packet-budget-and-s0-review/o1-static-assessment.txt`
  (631508e5), T1-T7 and FM1-FM5.
- Candidate driver: `forecast_retrospective_release.py` **33011eed**. Diff vs D-1: `v8-to-v8.1.diff` (59 lines).
- **Nothing approved, staged or run.** No reviewer record is written here. D-1 stays the fallback.

## What changes (and nothing else)

| Where | v8 (D-1) | v8.1 (O1) |
|---|---|---|
| Pre-label loop (L888-900) | every committed cell: read, digest check, full `payload_checks` (via `validate_payload_resources`), keep `raw` | **unchanged**, iterated through `committed_for_validation`; the validated bytes object is also recorded in `validated` |
| After the loop, before the resource gate and the marker | — | `require`: validated ids == committed ids, counted once each, and `validated[k] is payloads[k]` |
| Compute pass (L943) | `payload_checks(...)` again | `decode_validated(...)`: refuses unless the bytes are the very object validated pre-label; rows → `json.loads(raw)`; curve/count → `payload_checks` unchanged; any other kind refuses |
| Alias pass (L970) | `payload_checks(...)` again, result unused | no decode (the rows come from `scored[alias_of]`, as before) |

- Every pre-label check, cell, tolerance, membership rule, scorer and output is unchanged.
- Side effect: for row cells, D-1 F1's post-label abort path is gone. It could not fire: it re-ran the same
  deterministic predicates on bytes that had already passed.

## T1-T7

| Req | Evidence | Result |
|---|---|---|
| T1 equivalence | `compare_o1.py` → `evidence/equivalence-o1.json`: the D-1 harness, run on the v7, v8 and v8.1 trees with the D-1 extra tests plus `tests_o1.py` | 100 passed on each; exports alias-ok, alias-failed-target, groups, groups-fail, serialization; **unexplained_paths []**. Every remaining path diff is one D-1 already classifies (run-noise anchors `frozen_model_results_sha256`, `probability_calibration/approval/sha256`, a traceback frame filename) |
| T2 value identity | `test_o1_value_identity_and_call_counts`: every row-kind `payload_checks` return == `json.loads(raw)`; `test_o1_stable_payload_checks_returns_the_decoded_rows_unchanged` | pass. Mutation FM1 (a callee sorts `candidate_asns` in place) is detected |
| T3 coverage | runtime require above. Tests: on v8.1 the post-label decodes == committed non-alias cells, each once; `test_o1_coverage_refuses_before_the_marker` drops one cell from the pre-label set | refuses with "does not cover every committed cell"; **marker absent, no output dir** |
| T4 byte identity | `is`-identity against the validated object (the assessment's no-rehash option), checked at decode | `test_o1_decode_requires_the_validated_object`: an equal-but-different bytes object, a missing id and a wrong id all refuse. Mutation: rebinding `payloads` after the barrier is detected |
| T5 dispatch | `ROW_PAYLOADS` / `NPZ_PAYLOADS`; anything else raises | `test_o1_dispatch_is_exhaustive` over all 6 cases (unknown never calls `payload_checks`) |
| T6 alias | `install_alias` fixture: custody's own `verify_batch` appends an alias of the first committed R-temporal cell, which keeps its parent's role and side record, so seal, plan and evaluation agree | alias with a successful target: same per-event sha as the target. Alias whose target failed: both in `scoring_failed`, no per-event file. On v8.1 the alias gets one `payload_checks` call (pre-label) and **no** `decode_validated` call; v7 and v8 make 2 |
| T7 static no-mutation | `static_no_mutation.py` → `evidence/t7-static.json`, `test_o1_static.py` | see below |

### T7 in detail

The scanner takes the v8.1 `_finite`, `check_forecast_rows` and `payload_checks`, plus the module-local closure of what
they call in the **staged** tree. That tree is the v7 tree; the v8 assembly candidate stages the same bytes.

- `forecast_ranking.py` 4cea491a: `event_ranking_metrics` → `_clean_ranking`, `_tie_groups`,
  `expected_average_precision`, `expected_hits_at`.
- `forecast_panel_scoring.py` b7374f69: `check_curve`, `point_count`, `aligned_rows` → `check_binding`,
  `history_identity`, `history_extent`, `_asns`, `_hex64`, `require`.

18 functions in all. For each it records the file sha and the sha of the function's exact source text. It flags every
in-place write whose target is not a container the function itself built: subscript or attribute assignment,
augmented assignment, `del`, a mutating method, `out=`. Every external call must be on a listed pure set.

- **Result: 0 writes, 0 unlisted calls, every cross-module callee scanned.**
- The test regenerates the evidence byte-for-byte and pins both staged files.
- 5 scanner mutants are all flagged: a driver sort of rows, a sort in `event_ranking_metrics`, a clamp in
  `check_curve`, a `pop` in `aligned_rows`, and a new unlisted callee.

Two facts the scan cannot express, checked by hand:
- `aligned_rows` returns dicts that share the row's `curve_log_quantiles` list. Post-label (`observe=None`) that result
  is discarded; pre-label it is only observed. Under O1 the post-label rows are a fresh `json.loads` anyway.
- The stable path passes only frozen state (never `rows`) to `bound_verifier(...).complete_rows`; `rows` is only
  compared with `==`.

**This claim is void if any listed sha changes, or if a scorer or callee changes.** It is a static scan, not a proof
over arbitrary future code.

### FM5 documentation

- No text in the v8.1 driver claims a post-label re-validation. Its docstring says the reverse.
- `docs/`, `scripts/`, `src/` and the v7 execution packet have no such claim (grep).
- D-1's own REVIEW correctly describes D-1. Any v8.1 launch text must say "validated once, before the label opening;
  decoded after".

## Negative controls (`mutation_controls_o1.py` → `evidence/mutation-controls-o1.json`)

The unmutated v8.1 passes all 12 O1 tests. **8/8 mutants are detected:**

| FM | Mutant |
|---|---|
| FM1 | callee sorts rows in place |
| FM2 | coverage require removed |
| FM3 | identity check removed |
| FM3 | payloads rebound after the barrier |
| FM4 | npz decoded with `json.loads` |
| FM4 | unknown kind decoded |
| T6 | alias decoded again via `decode_validated` |
| T6 | alias still runs `payload_checks` |

## Measured synthetic performance delta (`perf_o1.py` → `evidence/perf-o1.json`)

Setup:
- Local, single thread.
- The S0 generator shape: 3,543 events, `forecast_rows_json`, fixed seed.
- Compares the D-1 post-label call against the v8.1 one on the same bytes, after an equality assert. Best of 3.

| Candidates | Bytes | D-1 post-label | v8.1 post-label | Speedup |
|---|---|---|---|---|
| 300 | 34.7 MB | 1.37 s (25.3 MB/s) | 0.39 s (88.7 MB/s) | 3.51x |
| 900 | 102.9 MB | 3.50 s (29.4 MB/s) | 1.11 s (92.7 MB/s) | 3.15x |
| 1800 | 205.3 MB | 6.64 s (30.9 MB/s) | 2.21 s (92.8 MB/s) | 3.00x |

**R1 extrapolation:**
- 438.86 GB of row payloads (`diagnosis/prediction-sizes.json` c6ab8325).
- Saves 2.6-3.5 h at local speed.
- **2.6-7.7 h at the assumed host factor 0.45-1.0. The host speed is unmeasured: the S0 host run failed, see below.**
- This is a lower bound. It leaves out the `aligned_rows` and stable-verifier work D-1 also repeats, and the alias
  decodes O1 drops entirely.

## Not here

- No v8.1 assembly: `v8-assembly-candidate` binds bb7f7e00.
  - Using O1 means rebuilding that candidate with `DRIVER=33011eed` (constants only, same 11 leaves).
  - Every driver-bound record (R3) must then bind 33011eed.
  - Per the assessment, that is free only if O1 passes review before those records are issued. None are issued yet.
- A new CODEPASS is required before any binding or execution use.

## Reproduce (local, from the repo root)

```
.venv/bin/python -B .agents/operations/r1-critical-path-speedup-20261022/driver-v8-1-o1/compare_o1.py
.venv/bin/python -B .agents/operations/r1-critical-path-speedup-20261022/driver-v8-1-o1/mutation_controls_o1.py
.venv/bin/python -B -m pytest -q -p no:cacheprovider .agents/operations/r1-critical-path-speedup-20261022/driver-v8-1-o1/test_o1_static.py
.venv/bin/python -B .agents/operations/r1-critical-path-speedup-20261022/driver-v8-1-o1/perf_o1.py
```
