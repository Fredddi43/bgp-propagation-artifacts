# G1 M2: ordinary 12 completed-fit provenance (author: sonnet; nothing launched, no remote action)

## What exists locally (proved by `build.py`, `local-proof.json`)
Original predicates: `newperiod-ordinary-inference-20261023/runner.py` (sha cd0b3cfe...) `fit_provenance`.
Exact path+sha chain equality of checkpoint/completion/receipt/definition/authorization/started for all 12 arms across
the gru10 actual (c6d8461e), the temporal completion capture, the GBDT assessment (d3ae81da) and the 12 pending templates.
GRU authorization = the staged per-arm copy (identical sha f324abd0 for all 10; `original_embedded_authorization_equal` true).

## What is NOT local (stated plainly)
No body of receipt, completion, started, authorization, definition/ledger/spec or checkpoint exists locally, so the
predicates themselves (checkpoint['receipt'] vs receipt incl. GBDT int-key/JSON semantics, completion/cell/started/auth
equalities, development manifest, and the release chain `release_authorization.release_sha256 == freeze release`)
are unproven. Hash rows and the GBDT metadata-only assessment do not satisfy them.

## Proposed finite read-only projection (needs separate independent admission, then ONE root once)
`projection_source.py` runs the same predicates (all except the reviewer-identity clause) over `projection-spec.json`
(12 arms, pinned refs). Reads: 12 receipts, 12 completions, 10 started, 12 authorizations, 1 GRU package, 1 GBDT ledger +
spec, 12 checkpoints (bytes sha-verified before load; needed for receipt equality; the checkpoint is loaded, only
booleans/hashes leave). Output: per-arm booleans, observed release sha and receipt release sha; no metric, threshold, label,
score, prediction, tensor value. Zero writes (stdout only). Root must: pick python with torch (GRU) and pickle-safe
bytes (pins verified), `-B`, RLIMIT bounds, set `expected_release_sha256` in the spec from the
G1 freeze `retrospective_release` before running (null here: the freeze is not issued; `release_chain` then only checks
shape and the all-12-equal set must be compared to the freeze by root). Reviewer must decide whether loading
checkpoint bodies is admissible; if not, M2 stays partial and checkpoint equality cannot be proven.

## Root sequence
1. Independent review of `projection_source.py` + `projection-spec.json` + tests (tests.txt: 25 pass).
2. Root fills `request.json` `expected_release_sha256` (ROOT_FILL, null now; `run_once.py` refuses while null; `record_later` mode refused unless authority `record_later_allowed` AND admission review allow it), regenerates pins, issues authority from `authority.FALSE-TEMPLATE.json` with `admission_review` (must state `checkpoint_body_reads_admitted` true and pin projection_source) and `execution_review`, then `python3 -I -B run_once.py --check --authority A` and once without `--check`. Operator: one ROOT-SSH exchange with the pinned venv python `-I -S -B`; remote RLIMIT FSIZE 0/AS/CPU + alarm, source sha verified; torch imported before the audit hook (denies write-opens except /dev/null, subprocess, sockets, unlink/rename/mkdir), so no probe-v2 allowances are needed; stdout/stderr bounded; local landing check (12 arms, writes 0, ids in order). The hook's torch.load-time behaviour is untested locally (no torch here): a real-venv dry check by root is advised.
3. A separate reviewer reads the projection output and fills `review-inputs/<arm>.REVIEW-INPUT.PENDING.json`
   (scope `newperiod-ordinary-completed-fit-v1`; reviewer_model/worker/session, passed true) per arm; none is signed here.
No refit/recalibration/predictions authorized; `passed` false and `execution_authorized` false in all 12 inputs.
