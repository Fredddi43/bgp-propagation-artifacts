# Stable history provenance witness v1 — once packet (opus-science, author)

Closes GAP-1/GAP-2 of map v1 and proves the A-C reuse premise, by reading JSON receipts only.
Host <BATCH_HOST>, `/usr/bin/python3 -I -S -B -` (3.11.2, stdlib only), source via ssh
stdin. No Slurm, no remote writes, no parquet/label/score/prediction/gate opens, no custody
log appends. Output: one JSON line of counts, booleans and SHA256 commitments; no event IDs.

Reads (all under <MODELS_ROOT>/nobackup/<PROJECT>, canonical paths checked
2026-10-26 by stat/realpath; sizes 0.1-32 MB, all pinned by sha256 in request.json):
dev staging a7ed6ae8, primary staging 751e356e, R-stable input 2d0ee46a, R-stable stage
99f45aeb (+ its files.json via its own pin), 8 restoration shard completions, omitted-part
completion; then <=2010 per-event receipts pinned by those completions (1010 + 1000 exist).
Also os.path.realpath on the 2d0ee46a membership source paths (metadata).

Note for reviewer/root: 751e356e is the protected-period primary staging receipt (metadata
JSON; the accepted stable v4 audit read it under its scope). It is used only for W1
(primary.development_staging_receipt == a7ed6ae8, primary history == dev history, custodian
history membership == data membership). If you prefer, strike W1; the rest stands.

Checks: W1 above. W2 segments A/B/C: 2d0ee46a membership source == new-period history
membership (realpath+sha); summary/anomalous present; disposition counts; repair receipts.
R-stable: input pin == 2d0ee46a, tables == v4 history tables, passed, parity all passed,
membership digest recomputed, coverage of A-C. W3 seg E: receipt bound by completion sha;
source role crossday_repair; canonical membership == history; canonical summary == data
summary; output == data anomalous; source is sibling of history membership. W4 seg F:
receipt bound; canonical membership == history; canonical summary/anomalous siblings;
output == data anomalous. Commitments per segment = canonical_sha of sorted
[eid, role, path, sha] bindings, for a later N-stable stage to bind.

Failure semantics: an anchor failure refuses with one static code (ANCHOR_HASH,
PATH_OUTSIDE_ROOT, PATH_NOT_CANONICAL, FILE_TYPE_OR_SIZE, DUPLICATE_*, UNCLASSIFIED_EVENT,
UNEXPECTED_<class>). A bad per-event receipt is counted unbound, never trusted, never
refuses. Counts below the segment size are findings, not retries.

Bounds: RLIMIT_AS 6 GiB, worker alarm 1200 s, transport timeout 1320 s, anchors <=64 MiB,
per-event receipts <=4 MiB, stdout/stderr captured <=1 MiB each.

Operator (root only): `python3 -I -B operator.py --authority <abs> --check-only`, then
without --check-only once. Authority kind ROOT_ONCE_STABLE_HISTORY_PROVENANCE_WITNESS_V1,
pins request/worker/operator/review, fresh actual_dir under witness/actual/, control
snapshot epoch + exempt list (root's own GO). Review file must pin the same three files,
verdict PASS, reviewer_worker != opus-science, author_worker == opus-science. Creating the
actual dir is the consumption; one transport; no retry.

Tests: `python3 -I -B test_worker.py` (14 synthetic checks incl. hash/root/symlink refusals,
tampered receipts unbound, no IDs in output) and `python3 -I -B test_operator.py` (8:
check-only no consumption, run, second-run refusal, control-post refusal, self-review
refusal, changed-worker refusal). Synthetic only; no real data used.
