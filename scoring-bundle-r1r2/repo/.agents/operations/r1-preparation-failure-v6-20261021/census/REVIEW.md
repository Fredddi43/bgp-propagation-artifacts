# Preflight size census (revision request 1, R1/R2): code-review packet (NOT RUN, NOT APPROVED)

- Author: claude-opus-5-5, session `<SESSION_ID>`.
- Answers `../coordination/revision-request-1.json` e9a7d0ab and `../reviews/opus-preflight-result-review.txt`
  b5f17013.
- Preflight attempt 1 (`../coordination/preflight-result.json` f530f19e) stays as terminal evidence.
- `../preflight-r2/` (a blind 768 MiB limit) is SUPERSEDED by this request and will never be proposed for a run.

## R1: stat-only census

- `build_paths.py` builds `paths.json` locally, 154 entries:
  - the preflight's 70 exact refs, from the pinned `payload.json` 74140aed
  - 42 `run["completion_path"]` and 42 `run["out"]/fit_receipt.json` for the needed runs, from the held, SHA-verified
    fit ledgers in the parent capture, derived exactly as `register()` derives them
- The 40 H1 audit-derived paths are not listed. The audit is not held, so they stay UNKNOWN.
- `remote_template.py` / `program.py` calls only `os.lstat` and `os.path.realpath` per path. Nothing is opened,
  read, listed, globbed or written; an AST test pins the set of calls. Per path it reports {exists, is_symlink,
  is_regular, size (regular files only), realpath_equal}.
- The host, user, Slurm and `-I -B` checks are the same as before. Off-host it refuses with empty stdout (tested).
- `census.py` (driver), same pattern as the reviewed preflight driver:
  - exact independent approval in `../coordination/census-execution-approval.json`, scope
    `r1-v6-preflight-size-census-v1`, with `stat_only_authorized` true and `content_read_authorized` false
  - exclusive intent, one ssh call, the rc-255/no-stdout retry only if approved
  - output validated against the exact path set
  - write-once `../coordination/census-result.json` holding per-class counts, sums and maxima, the paths that are
    missing or non-regular, and a limits proposal
- Tests: 12 passed, Ruff clean.

## R2: what the large fit receipts contain (field names only, from the producing source; no remote read)

- **Neural receipts** come from `forecast_train.py`:403-433 in the fit snapshot 9f3e456c. A local copy is held at
  `newperiod-gbdt-20261020/scientific-source`, and all 75 files match the map.
  - **Bulk fields:** `train_inputs` and `validation_inputs`. Each is a per-event list from `load_partition` (:178)
    with keys `event_id`, `path`, `sha256` and `forecast_contract`, plus `history_provenance` for training events.
  - This is per-event INPUT provenance (paths and hashes). It holds no prediction values and no labels.
  - **Other fields:** hashes, settings, `threshold`, `threshold_grid`, `validation_jaccard`, timing and hardware, and
    `trace`, a per-epoch list of `epoch`, `training_loss`, `validation_loss` and `elapsed_seconds`.
- **GBDT receipts** come from `forecast_baseline.py`:86-104, with the same `train_inputs` / `validation_inputs`
  lists plus counts and settings.
- The validation predictions themselves live in `validation_predictions.json`, a separate file that the preflight
  never opens.
- **Limits proposal:** the driver computes per-file = measured max + 25% and total = measured sum + 25%. The 40
  unmeasured H1 files are budgeted at the largest measured receipt or completion. The reviewer decides; nothing is
  widened automatically.
- A4 (sanitized output) and the JSON-only admission stay unchanged.
