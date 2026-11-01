# Stable rerun4 launch helper (author: sonnet, claude-sonnet-5-5; not authority)

Helper for the reviewer's root_sequence steps 1-5 for signed request 33f20a85 (operator e289832f, shards 8,10,13,15). Derived from the v6 helper
`newperiod-stable-v6-v44-launch-root-v2-20261026`. Nothing here issues, submits, releases or consumes. No Python runs on <SUBMIT_HOST> (only `squeue`).
Remote reads: `du`/`find|wc`/`stat`/`date` and a `python3 -I -S -B` stat+df+lexists query on <BATCH_HOST>; `squeue` on <SUBMIT_HOST>.

## What it does
- `--census`: one ssh to <BATCH_HOST>: `du -s --block-size=1 .` + `find . | wc -l` over the whole stable-source-v6 root (counted once) and custody `stat` (EOF/dev/ino);
  refuses a custody identity different from the pinned H3 baseline or EOF below it.
- `--fill-adoption`: base = pinned issued adoption 853c606f (records `supersedes_adoption`). Only the `stable_source_stage` writer is replaced: identity
  `stable-stage32-rerun4-request:33f20a85...`, 63204 x 746 = 47,150,184 B (equals append-bound.json), status bounded_active_or_authorized. Every other writer keeps its adopted
  bound (no append credit, no baseline reset); root's writer inventory must list every non-zero base writer, never exceed its bound, show stable = 47,150,184 with no job,
  and partition the live squeue exactly into: running n-* writer jobs (with bounds), held jobs (non-writers needing root release, recorded in
  `scheduler.reconciliation`) and other-project non-writers; a live `n-stable-source-stage` job or a rerun4 target path that already exists refuses.
  Row check: fresh census root allocated + pinned envelope parts (new4 outputs, attempt records, scheduler logs, control-rerun4, assembly = 4,229,379,773)
  <= newest accepted phase `stable_source_stage` (V44: 21,474,836,480; also >= 20 GiB). The 447 MiB v5b row is never used. The 11 adoption flags, 4 assumption flags
  (row covers whole v6 root, ratio 1.08/4096 B-entry/finite streams, plan path <=200, no v5b credit) and the finite-stop risk acceptance (640 MiB/512 MiB caps,
  64 GiB, no completion guarantee, no retry/scope reduction) must each be explicitly true in root's facts; template defaults are false.
  Floors = request minimum + newest phase models floor - V44 floor (V44 floor 847,577,881,600 + 4 x 1152 MiB = 852,409,719,808 minimum), results floor from the newest phase;
  custody arithmetic identical to Operator.gate. The bytes are validated with the real `Operator.load_adoption` before writing.
- `--fill-once`: from the pinned FALSE template (d46e8476): drops `template_only`, `passed=true`, request/operator hash/records
  (`.../newperiod-stable-stage32-rerun4-actual-v1-20261026`), adoption ref, review, control snapshot, scan_dirs, finite `maximum_wait_seconds` (7200..604800) and `root_issued_utc` from root facts;
  keeps kind, array 8,10,13,15, custody literal, one invocation, no retry; key set must equal the operator's AUTH_KEYS.
- `--check`: real `Operator(authority, consume=False)`, then helper-added gates: operator/request pins, adoption made by this helper and stable bound exact, the review file mentions this
  adoption's sha256 (the operator itself binds only operator+request), fresh census row cover, scheduler unchanged since adoption, floors/custody/FSIZE/growth, rerun4 target paths absent, records dir unused.

## Root commands (cd /tmp; H=<REPO>/.agents/operations/newperiod-stable-rerun4-launch-sonnet-v1-20261026; R=fresh dir outside H)
1. `python3 -I -B $H/fill.py --census > $R/census.json` and `python3 -I -B $H/fill.py --probe > $R/probe.json` (note scheduler_sha256).
2. Root writes `$R/writer-inventory.json` and `$R/facts.json` from `$H/facts.FALSE-TEMPLATE.json` (everything true only if root accepts it).
3. `python3 -I -B $H/fill.py --fill-adoption $R/facts.json --out $R/root-operating-adoption.json`
4. Route adoption + census + inventory to sol-h3t; obtain actual-adoption acceptance and the operation review (operator e289832f + request 33f20a85) naming the adoption sha256.
5. Add `once` block (review ref, control snapshot, scan_dirs, maximum_wait_seconds) to fresh facts, then
   `python3 -I -B $H/fill.py --fill-once $R/facts.json --adoption $R/root-operating-adoption.json:<sha256> --out $R/root-once.json`
6. `python3 -I -B $H/fill.py --check $R/root-once.json` (passed true; repeat immediately before launch), re-scan ROOT/REVIEWER posts, then one
   `python3 -I -B <REPO>/.agents/operations/newperiod-stable-stage32-rerun4-sonnet-v2-20261026/operate_stage32.py operate --authority $R/root-once.json`. No retry.

## sol-h3t must check
Pins match the bound inputs; the base-adoption derivation keeps every non-stable writer byte-identical (tested); partition/held handling; row arithmetic vs reviewer's 6,985,369,789;
check's extra review-binds-adoption gate is a helper rule, not an operator rule. Tests: 24 synthetic passes (injected census/observation; real constructor with consume=False).
