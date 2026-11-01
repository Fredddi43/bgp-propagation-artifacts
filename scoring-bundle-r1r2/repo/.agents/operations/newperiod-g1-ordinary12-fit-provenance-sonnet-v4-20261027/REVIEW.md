# G1 M2 v4 (author: sonnet). Answers the consumed v3 once: rc 2, `ProjectionError:READ_BOUND`.

## Diagnosis (read-only; one ROOT-SSH exchange: os.stat of the 61 unique allowlisted paths + read of our own v3 O_EXCL access log; no allowlisted body read) -> `stat-sizes.json`
- v3 log (982 B) holds 4 read records; the 4th is `gru-d30-s0/fit/fit_receipt.json` with limit 2 MiB. All 12 `fit_receipt.json` are 31,368,464..31,373,331 B, i.e. >2 MiB, so every arm would have tripped (the first one did).
- Everything else fits the old bound: authorizations 597..2626, completions 1075..2002, started 1222, package 41,691, ledger 2931, adapter-spec 3159; checkpoints 21.8..25.8 MB (old 2 GiB bound). Total of all 72 reads = 678.95 MB.
- Receipt bodies are only compared/hashed inside the process; none of their content is emitted (output allowlist unchanged).

## v4 changes
- `projection-spec.json` now = {arms, bounds}: per allowlisted path bound = exact stat size + 256 B margin (build.py reads `stat-sizes.json`, refuses any unmatched path). Spec digest covers both. Source refuses before any read unless bounds keys == allowlist paths (int, 0 < b <= 2 GiB) and `aggregate_bytes` == sum of per-read bounds (678,951,119 B).
- Effective per-read limit = min(absolute ceiling 64 MiB docs / 2 GiB checkpoints, pinned bound); the log line records the effective limit.
- Errors name the allowlist index only: `ProjectionError:READ_BOUND@<i>` (also READ_SHA, AGGREGATE_BOUND, BOUND_MISSING); no path content.
- New log name `g1-m2-ordinary12-fit-provenance-v4-once.log` (v3 log exists; v3 name refused); request fills `<RESULTS_ROOT>/nobackup/<PROJECT>/logs/g1-m2-ordinary12-fit-provenance-v4-once.log`. Kind `..._V4`, output kind `..._projection_v4`.
- Everything else from v3 (release pin ba2a1e2e, roster, inert parsing, hook, strict predicates, validated landing) is carried; v3 regression tests kept (`test_regression_v3_carried.py`).
- `test_v4_bounds.py` uses the real sizes: reproduces that the old bound fails a 31.37 MB receipt and the pinned bound passes it; every receipt > 2 MiB and nothing else non-checkpoint is; bounds == stat+margin; index-only error; bounds/aggregate tamper refused before any read.

## Caveats
Root must re-run independent review and issue a fresh authority (v3 authority is consumed). Remaining runtime risks unproven: CPU 600 s / AS 8 GiB for json-parsing 12 x 31 MB receipts and 12 x ~25 MB pickles (estimated well within), and whether the real checkpoints/receipts satisfy the predicates.
