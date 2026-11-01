# Prospective primary-score persistence seam

This sibling candidate preserves the original single-R2 scientific sources, full400 retention, one original label opening, numerical functions, bootstrap defaults and original report bytes. It is not installed, staged or executed on actual data. It cannot authorize evaluation or result release.

The original evaluator already constructs every primary per-event score list before calling `_contrast_families`. The candidate wraps that boundary only on the runner's private evaluator copy, invokes the original function first, then streams the same in-memory `arms`, aligned incident/onset `rows` and derived identity mapping into `primary-scores.json`. It performs no score recomputation, averaging, bootstrap, cohort filtering, prediction or target read. The original function is restored in `finally`; the original scientific module is never patched. If original scoring, persistence or a subsequent component fails, ordinary no-retry behavior remains; a partial sidecar is retained and no successful completion receipt is issued.

## Exact new artifact

`plan.primary_scores_output` must equal `plan.records + '/primary-scores.json'`. The source sidecar kind is `newperiod_primary_computed_scores_v1`:

- `seal`, `freeze`, `arm_spec`, `labels`, `source_closure`: exact already admitted references.
- `primary_report_path`: original unchanged primary result destination.
- `identities[model][horizon][seed_index]`: actual retained arm ID, identical to the original primary report's `arms` map.
- `arms[model][horizon][seed_index][event_index]`: the complete already computed original event-score record, including ranking status/eligibility, operational penalties, Jaccard and existing issue-time fields. No raw target AS lists or predictions are newly read.
- `rows[horizon][event_index]`: the original aligned scorable event ID, incident ID and onset. Original censored events remain counted by the unchanged report and are not imputed as scores.
- `metrics_recomputed:false`, `additional_label_reads:0`, `outcome_release_authorized:false`.

Only normal JSON serialization changes integer horizon dictionary keys to strings. Original scalar values and population ordering are preserved. A shallow wrapper references the existing score objects; incremental JSON encoding avoids a second full decoded or serialized population. The completion receipt adds `primary_scores:{path,sha256,size_bytes,bound_bytes}`. The original primary and complete report structures are unchanged. A failed run's sidecar is not a released result and must not be consumed as such.

## Hard output accounting

The existing positive `bounds.output_file_bytes` is also the sidecar's hard streaming byte limit and remains the process `RLIMIT_FSIZE`. Before each encoded chunk and final newline, the writer refuses a size beyond that cap. Exclusive no-follow creation, fsync and actual SHA/size receipt prevent overwrite or an unbound output identity. No extra label read is used to size the output.

The entire-output reservation now requires **at least `6 * output_file_bytes + access_log_bytes`**, replacing the original five-file minimum. Thus the new file is separately reserved at its full possible size, not merely its expected size. This is checked by the local transport before staging, runtime resource admission and execution before opening any labels. Existing actual storage admission, fresh free-space check including the shared64GiB floor, source/native runtime bounds, 24h maximum wall limit and sanitized failure behavior remain. The unchanged stage/held/release transport retains its separate64MiB operational package allowance. Actual output limits and whole-batch memory/storage must still be independently admitted; no capacity assertion or new actual resource allocation is made here.

`client.py` changes only the fixed sidecar path/reservation validation, truthful additional author exclusion and exact new runner SHA. `bootstrap.py` changes only that SHA. All scientific component files, scientific pins, builder, transport helper and runtime helper are unchanged. The original single-R2 remote namespace is deliberately retained: this is a prospective alternative before its first run, not permission to evade a previous marker or start a second evaluation.

## Required next review and integration

The new source closure/runner hash, complete read inventory, six-file output reservation and actual plan must receive independent review before the one existing R2 execution. The parent keeps original installed/frozen candidates intact. A separate descriptive-summary layer can later consume the accepted sidecar by SHA; no summary code or new inferential family is included here.

Tests compare the original and successor against the identical pristine full400 synthetic world with a fixture-controlled clock. The original complete report object, primary JSON bytes and every original new output file (including the unblinding marker) must match exactly, with one label opening per independent fixture execution. Separate tests exercise output-cap partial preservation, no overwrite, changed identity/path/reservation refusal, private-function restoration on failure, exact scientific component bytes, source-pinned isolated execution and the existing stage/held/admit/release flow with fake scheduler executables. No real scheduler or protected data is used.

```
PYTHONPATH=src .venv/bin/python -B -m pytest -q -p no:cacheprovider .agents/operations/newperiod-single-r2-persistence-20261024/test_persistence.py .agents/operations/newperiod-single-r2-persistence-20261024/test_transport.py .agents/operations/newperiod-single-r2-persistence-20261024/test_bootstrap.py
```
