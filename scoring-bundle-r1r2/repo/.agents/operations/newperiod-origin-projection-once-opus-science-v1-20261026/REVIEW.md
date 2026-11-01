# Origin cohort projection once v1 (opus-science, author)

Produces the origin branch decision (valid20 fits vs one-week extension) and the private
d30/d60 family manifests that development construction consumes. Depends on the witness
binding (board/AUTHOR-opus-science-ORIGIN-WITNESS-BINDING-V1-REVIEW.json, under review).

What runs (one ssh, <BATCH_HOST>, private runtime venv python sha 62f0c11a, polars 1.44.1):
- remote-command.txt: own bounded supervisor (same code as the accepted v3 wrapper, except
  RLIMIT_AS 8 GiB and RLIMIT_FSIZE 512 MiB, wall 1800 s) reading the worker on stdin.
- worker.py = projection.py + compressed payload {request, sources} from prepare.py. Sources are the
  reviewed `cohort.py` (newperiod-family-metadata-20261023) and `src/bgbench/forecast_protocol.py`
  (pin f0d3d230, stdlib only), registered as module `bgbench.forecast_protocol` before exec.
- Reads exactly the six tables the accepted v3 audit read (same pins), columns
  event_id/t0_obs/error and event_id/validity only, with the v3 Reader rules (declared reads,
  nofollow walk, size/digest, row cap).
- Merge rule (witness binding PASS conditions): exactly the v3 audit eligibility on every source:
  historical START (2025-01-01) <= onset < SPLIT (2026-09-01); prospective SPLIT <= onset <
  end_exclusive (2026-10-16). Every row must have an onset; validity population must equal the event
  population per group; identities disjoint. Error rows inside the window are passed (derive keeps
  them as source failures). Every row not passed is counted by reason; the ledger asserts
  passed + dropped == rows per source (no silent drop) and reports error_rows_seen/passed.
- Calls unchanged `cohort.derive(events, validity, end_exclusive, coverage)`; coverage = the
  binding's proposed argument with source_references = the 15 evidence pins + the binding itself.
- Writes the full internal projection and the row ledger to a FRESH custody dir
  data-custodian/newperiod-origin-projection-v1/{projection.json,ledger.json} (exclusive mkdir + O_EXCL, fsync).
  Existing dir = consumed/collision, never retry.
- Public stdout (<= 64 KiB): valid_family_incident_count (the only allowed pre-seal field),
  branch, next_end_exclusive, projection path/sha256/size, the private ledger's path/sha256 and
  all_rows_accounted=true. The per-source row ledger (counts by reason) is written to custody as
  ledger.json by the same exclusive writer and is disclosed only after sealing (cohort.py:64 allows
  one pre-seal field). No IDs, onsets, splits or counts are public.
- The certificate passed to derive carries the PASS-required `scope` text (SC2 + Aug10 + S-ROA) and
  a pin of the witness PASS.
- Custody: reads are the same private metadata the v3 audit read with 0 appends; no log append here.

Operator (root only, `cd /tmp && python3 -I -B once_operator.py --authority <abs> [--check-only]`):
the accepted witness-operator guards (pins of request/worker/operator/remote-command, independent
reviewer PASS pinning all four, control rescan, exclusive actual dir, one transport) plus:
bound phase unchanged + issued, phase earmark `origin_projection` >= 512 MiB reservation, authority
`capacity_row` + `root_current_phase_acknowledged`, and the worker's embedded payload decoded and
compared to request.json and the pinned source hashes.

Not generated yet: request.json/worker.py/remote-command.txt for the real phase. v40 has no
origin_projection row; run `prepare.py --phase <v41> --phase-sha256 <sha>` once v41 is issued
(dry-run on v40 into /tmp: compiles, payload == request).

Tests: test_projection.py 11/11 (incl. row ledger and an in-window error row) (real cohort.py + forecast_protocol.py on synthetic tables: public
output keys only, branch extend at count 1, Aug-31 boundary and post-end rows excluded, history and
in-window rows present, projection hash bound, no IDs public, second run refused, changed source
refused, incomplete coverage refused by derive). test_operator.py 6/6.
