# Prospective N count coverage and custody export — code review only

Authors: `/root/temporal_guard_recovery` and `/root`. Review must be by a separate
agent/session. No actual source access, staging, submission, execution, model fit,
forecast, scoring, release, retry, or N unseal is requested by this review.

## Behavior and current limits

`run_package.py` offers two prospective phases. Both require the exact R1 release,
development manifests and core gates through the copied N source guard. Every
actual prerequisite in `spec.json` remains pending. Execution refuses those before
reading any production inputs.

`coverage` reads metadata receipts and checks canonical source bindings, archive
acquisition, extraction windows, parse status and merge-part counts. It reports
missing collectors, gaps and parse failures rather than inventing zero counts or
dropping events. It does not decode membership or archives. This is source receipt
evidence, not independent re-derivation of membership or peer-session continuity.
Actual ownership/index producers and their independent admission remain required.

`export` is a custodial operation, not a physically issue-window-only reader. It
reads complete hash-bound membership Parquet bytes and complete summary JSON bytes.
The Parquet query selects `first_seen`, `collector`, and `asn`; its null check
examines the entire `first_seen` column, and its later filtering limits the rows
that become contexts. Predicate pushdown is not a physical access boundary.
The operator must obtain explicit full-file/projection/summary authority in both
the phase approval and custody handoff. Coverage approvals explicitly deny those
three protected access scopes. This corrects the prior unfinished candidate's
misleading issue-window-only access description. The copied Chronos preparation
helper has the same physical-read distinction; this package does not revise or
authorize its separately reviewed execution.

The exporter uses the unchanged availability/count helpers and writes only
issue-bounded count contexts. It computes no target arrays. All five input states
are retained; failures cannot silently become zero inputs. It writes four
count-specific manifests for the two issue horizons and two grids. It does not
invent compatibility with the graph/temporal manifest schema. The loader is for
frozen inference only, with external task, population, inventory and whole-input
gate bindings. Actual prediction adapters and final N sealing remain separate.

Protected reads log before opening. The logger now fsyncs both record and parent
directory before returning; failure prevents the source open. Raw reads are
bounded by `max_file_bytes + 1` even if the file grows after stat. Shared JSON
outputs use exclusive creation and fsync. Publication is not an all-or-nothing
filesystem transaction: a failed attempt retains its partial files.

The fixed CPU job has no requeue or array, uses four native threads and a 112 GiB
address-space limit inside 128 GiB allocation. These remain resource proposals,
not demonstrated sufficiency. Exact production runtime/resource/index bindings,
source metadata authority and independent protected custody handoff are missing.
Do not run this package against real data or copy it to the cluster.

## Validation

68 synthetic tests pass, using real scientific helpers and existing guard fixtures.
They cover source coverage failures, metadata-only coverage access, all retained
status classes, actual count export/load, payload and gate drift, pending-before-read
refusal, normalized author rejection, phase-scoped full-file authority, audit
disclosure, future-AS exclusion, logging failure before protected reads and
allocation guards. Ruff passes on the eight new/modified Python files.

`review-pins-v2.json` binds the revised candidate, tests, copied sources and this packet.
Please review the whole unfinished custody candidate, not only the latest scope
correction. Return code PASS or concrete changes required. A PASS is not execution
authority: all actual-operation flags must remain false. Record actual reviewer
model and independent session, spec and pin hashes, review text and verdict.

## Changes after the first independent review

The first review and its original `review-pins.json` are preserved in place.
The four findings are addressed as follows:

- F1: independence rejects both normalized full author identities and author
  basenames. Both consuming gates have alias regressions, and the actual separate
  reviewer remains eligible.
- F2: failed artifacts contain only a bounded exception type and fixed metadata.
  The CLI catches execution-time `BaseException`, including `SystemExit`, and
  reports only that sanitized record. Tests inject a protected sentinel after the
  exporter is entered and separately exercise the CLI in subprocesses.
- F3: protected masters, export admission and count manifests require either the
  complete canonical reference panel or the documented pooled representation.
  Reduced-panel masters/statuses are refused, not relabeled. Tests construct
  consistent inventory/status/master metadata for both legitimate pooled and
  invalid reduced-panel cases.
- F4: inventory and parse receipts are captured through the bounded logged reader.
  `validate_captured` reuses each original validator's unchanged code in a private
  namespace whose only `Path` capability returns that exact captured buffer for
  that exact path. No global monkeypatch or original-source edit occurs. Tests
  cover growth at both protected read sites and prohibit unrestricted reopening.
