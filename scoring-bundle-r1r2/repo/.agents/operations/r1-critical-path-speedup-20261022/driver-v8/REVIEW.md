# Review packet: v8 release-driver candidate, D-1 partition-group scoring (LOCAL; synthetic only)

- Author: claude-opus-5-5, session <SESSION_ID> (`/root/opus_implementation`).
- Base: the staged v7 driver `forecast_retrospective_release.py` 4573658e (source manifest 7f35bd22). It is copied
  here, not edited.
- Candidate: `forecast_retrospective_release.py` bb7f7e00. The full change is `v7-to-v8.diff` (137 lines).
- **Why:** `../diagnosis/DIAGNOSIS.md`. The frozen scoring loop decodes the whole 72-105 GB target partition once per
  cell: 1,032 cells, about 80 TB, at least 24 h even page-cached.
- **Not done:**
  - no host action, no real prediction or label or tensor, no run;
  - nothing frozen is changed;
  - this alone does not authorize any relaunch.

## The change (scoring section of `evaluate` only)

**Two passes after the label opening:**
1. **Compute pass.** Non-alias committed cells are processed in `partition_order`, which groups them by a label-free
   hint and keeps seal order inside a group.
   - The hint is the reference or cell manifest path, the gate sha, the h3 flag and the side population sha.
   - Each cell runs exactly the v7 body: `payload_checks` (outside the try, so a failure still aborts the run), the
     scorer, the coverage check, `write_once` of its per-event file, and the v7 serialization check, which moved
     here from `ScoredFiles.store`.
   - Failures are recorded with `bounded_failure`, as in v7.
2. **Seal-order pass.** For every committed cell in seal order:
   - store the computed file, so `files` and `scored` insertion order equal v7's;
   - or append its failure, so `failed_cells` order equals v7's;
   - or, for an alias, run the verbatim v7 alias path.

**`PartitionMemo`:**
- It wraps `forecast_train.load_partition` only during the compute pass and is restored in `finally`.
- It returns the previously decoded partition only when all of these are identical:
  - the resolved manifest path;
  - the manifest-file bytes (sha);
  - the manifest document;
  - the split;
  - `expected_hashes` (every test tensor pinned; `load_partition` refuses any other bytes).
- It never memoizes unpinned loads, graph dirs, prediction inputs or label containers.
- One partition is resident at a time. In v7 it lived for one scorer call. The certified budget already adds target
  resident + scorer transient + forecast workspace.
- **Scorers only read the returned events.** Checked statically: `score_membership`, `membership_metrics`
  (graph_metrics L16), `score_panel` and `score_stable` use `tolist`, `set(map(...))` and `_array` reads only; every
  `.update` is on result rows. **Reviewer: please re-check this.**

**Correctness never depends on the hint.** A wrong hint only costs extra decodes.

## Equivalence evidence (`compare.py`, `evidence/equivalence.json`)

**Method:**
- `harness.py` builds an exact copy of the staged v7 tree and runs the repo's synthetic release world against it.
  It adds the reviewed v6 synthetic resource fixture verbatim, as in `r1-release-memory-20261020/v6`.
- `extra_tests.py` is run unchanged on three trees:
  - frozen v7;
  - frozen v7 again, as the control;
  - v8.
- Its scorer obtains targets through `forecast_train.load_partition`, so grouping and memo hits are real.
- Exports hold the per-event files verbatim and a normalized report. Normalization removes root paths, anchors bound
  to driver bytes, `release_resource_proof`, and the line numbers of frames inside the driver file, since
  `bounded_failure` records code locations.

**Result:**

| Tree | Tests |
|---|---|
| v7 | 88 passed |
| v7 control | 88 passed |
| v8 | 88 passed |

All 83 inherited tests and 5 new ones pass on each tree. Exports cover three cases:
- **groups:** 19 per-event files;
- **groups-fail:** two scorer failures, 17 files;
- **serialization:** one cell whose rows do not survive JSON.

**Every v7 to v8 difference is accounted for** (`unexplained_paths: []`):
- `prerequisites/history_sensitivity/frozen_model_results_sha256` also differs between v7 and v7 control. It is run
  noise of the synthetic world.
- `prerequisites/probability_calibration/approval/sha256` differs because the world's calibration approval binds
  `release_driver_sha256` (test fixture `probability-review.json`). It must change with any driver change.

**All per-event bytes, metrics, failures and their order, and every analysis and contrast block are identical.**

**Partition decodes:**
- On v8, decodes equal the number of groups, which is fewer than cells.
- On v7, decodes equal the cells, in seal order.

On the real seal (held capture 6412d726), the 1,032 label-loading cells form 58 manifest/gate groups, with 346 switches
in seal order. Decodes drop from 1,032 to about 58, roughly 18× fewer: about 80 TB becomes about 5 TB.

## Negative controls (`mutation_controls.py`): 8/8 detected

| Mutation | Targeted tests |
|---|---|
| memo ignores pinned hashes | 1 failed |
| memo caches unpinned loads | 1 failed |
| memo ignores manifest file bytes | 1 failed |
| grouping dropped | 3 failed |
| failures in compute order | 1 failed |
| memo left installed | 2 failed |
| serialization check dropped | 1 failed |
| aliases scored in compute pass | 1 failed |

## Known gaps

- **The synthetic world has no alias cells.** The alias path is v7's code, verbatim, in seal order.
  `partition_order` excludes aliases, which is tested. An end-to-end alias test needs a world-fixture change.
- **Real-scorer equivalence on real tensors is not run.** That needs labels. The memo key/argument contract is
  unit-tested instead.
- `ruff` on the driver shows only EXE001 (shebang without exec bit), which v7 has identically.

## D-1 alone is not enough: wall-time model for a v8 run

Serial, with local Zen 3 rates; the Zen 1 host is slower.

| Stage | v7 | v8 (D-1) |
|---|---|---|
| Verify (measured) | 3.75 h | 3.75 h |
| Label-free validation, 438.9 GB under tracemalloc at 8 MB/s | ≥ 15 h | ≥ 15 h |
| Post-label payload re-parse at 23.8 MB/s | ≥ 5 h | ≥ 5 h |
| Partition decodes | ≥ 30 h | ≈ 2-3 h |
| Analysis bootstraps | unmeasured | unmeasured |

So D-1 removes the largest post-label cost, but even v8 needs **≥ 27 h wall**. The 12 h `signal.alarm` and the 48 h
`RLIMIT_CPU` in the launcher must be re-derived (D-3).

**D-2 decisions are needed before a v8 launch package** (reviewer/root):
- **(a) Keep serial.** Set the alarm to about 48 h and `RLIMIT_CPU` to about 72 h. Simplest: no new semantics.
- **(b) Parallelize the parses.** The current launcher's audit hook forbids `os.fork` and subprocess (`execute.py`).
  A pool needs a new launcher and resource-contract review, because the RSS gate measures the main process.

## Requests

- Code review of D-1, especially the read-only-events claim and the equivalence normalization.
- Decision on D-2 (a) or (b).

After that, a v8 launch package (driver + launcher limits + resource contract) would follow its own review chain. It
also needs a decision on how R1 is re-authorized: the v7 run's R1 authorization file already exists in the ledger
directory, and `execute.py` refuses a second one.
