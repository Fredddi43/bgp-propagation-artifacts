# Independent review: q44 audit_fast_v1.py (sha256 3c966a7c...588ab, py_compile OK)

Read-only review; no cluster contact, no protected data. Compared against q32 parallel_phases.py (sha 9d94de1d...) L255-415,
pinned scripts/custodian_newperiod_inputs.py L642-862, and the adapter seam list in
newperiod-family-protected-inputs-20261027-sharded/kernel.py L72-82. Local equivalence tests were NOT run (they need the
synthetic world fixture; see EQUIV.md Gate 0, which should be run first and would have caught the blocker).

## Verdict: CHANGES (1 BLOCKER, 3 RISK, 3 NIT)

## BLOCKER
B1. F4 `_independent_library_fast` hardcodes the pre-adapter paths. audit_fast_v1.py:205 uses `eventset/{year}_{family}` and
    :190/211 use `events_replay_{family}`. The deployed audit calls `adapter.independent_library`, whose body kernel.py:81 rewrites to
    `(f"{year}_{family}" if family else str(year))` and `(f"events_replay_{family}" if family else "events_replay")`. The origin audit
    runs with family "" (checked at audit_fast_v1.py:241), so the fast code reads `eventset/2023_/events.parquet` and
    `events_replay_/` (nonexistent) and the audit crashes in the prepass. This is the same class of defect as the q32 hunk-4 crash
    (REVIEW-VERDICT-HUNK4.md), reintroduced one function over. Fail-closed (no wrong report), but the speed-up cannot run.
    Fix: do not reimplement the library body. Either call `adapter.independent_library` per event row via the adapter's own code
    (e.g. split per year and shard rows), or derive the paths from the adapter function constants the way `_replay_dir` does, and pin
    both literals with an assertion that the fast result equals `adapter.independent_library` on the fixture.

## RISK
R1. (4) Memory claim is not delivered by this file. The 10 GB/worker COW growth comes from the pinned `audit_event`
    list-comp over `library_order` (custodian L749-750: `included`, `participation.update`), which touches every `order` tuple
    refcount on every event. audit_fast_v1.py leaves audit_event untouched (:141), so each worker still privatises the parent heap;
    REPORT's "~1.0 TB at 96 workers" is the unchanged 10.3 GB x 96 estimate, only the cold-NFS read amplification is cut.
    Nothing is shared read-only; `_S`, `order`, `rov`, `expected_by_id` are fork-inherited and refcount-dirtied. Plus gc can dirty
    pages too. No gc.freeze() before fork.
R2. (4) Worker cap not enforced in code. `_pool_fast` (:88-91) uses `min(workers, n)`; 96 vs 208 is purely whatever the env gives
    (run_step default 96, but BGBENCH_PARALLEL_WORKERS=208 would still run). F6 is documentation only. Add `workers=min(workers, 96)`
    or a hard `require(workers <= 128)`; and verify total RSS headroom (96 x 10.3 + parent 8-10 GB + prepass pool 48 forks, which run
    while the parent is small so are fine).
R3. (5) A dead worker (OOM kill) makes `Pool.map` hang forever, not fail: multiprocessing replaces the worker but the lost task never
    completes. With ~1 TB RSS on a 2.04 TB node an OOM kill is the likeliest failure, and it would present as a stuck job, not
    an error. Same in q32, but the speed-up lowers the bar for "it is just slow". Use `imap` with a per-result timeout or
    `concurrent.futures.ProcessPoolExecutor` (raises BrokenProcessPool). Per-event Python exceptions do propagate through map, the
    `with` block terminates the pool, and the report is only written at the end (write_once :318), so no partial report: OK.

## NIT
N1. `_pool_fast` has no inline path for n==0/1 (q32 `_pool` had one): `Pool(processes=min(workers, 0))` raises ValueError for an
    empty year table (audit_fast_v1.py:90, called from :213). Guard `n==0` returning [].
N2. Argument-evaluation order differs: the pinned code reads membership.parquet before anomalous.parquet (q32 :287 area); the fast
    code reads anomalous first (:140 vs :142). Only matters for which FileNotFoundError text appears when both are bad; no report
    results either way.
N3. Two extra stdout JSON lines (`q44_timing`, :259, :278) precede the final result line. q32 printed only the final line. I did not
    find a consumer that parses the last line vs the whole stdout; confirm the run-step/entry do not `json.loads` the whole stdout.

## Per-change proof (1)(2)(3) - verified clean
F1 sha memo (:96-104, :161): output-neutral. `dynamic.relationships` is an `lru_cache` keyed on (path, expected_sha)
   (verify_forecast_dynamic_features.py L78-81); its integrity check `sha(path) != expected_sha` only fires on cache miss, and the
   expected_sha is itself computed from the same file just before, so in the original it is tautological per event and effective once per
   (path) per worker. Memoizing the key per worker keeps the first-use check (still hashes once per worker per month) and returns the
   same value. Only difference: a mid-run byte change would be caught at first use per worker in both. Files are immutable (fresh dirs).
F2 load fusion (:123-136): `scan_developer_file` for .pt is exactly `scan_payload(torch.load(p, weights_only=True), p.name)`
   (custodian L695-706), json and unexpected branches replicated verbatim (:126-131). `scan_payload` is read-only (set/intersection only);
   audit_event and the later loop only read payload (`.tolist()`, column `.numpy()` compare), no mutation. Failure order preserved
   (scan findings first). A torch.load error raises in both.
F3 anomalous once (:140): audit_event -> rule_a_messages takes the frame read-only (column access); the later use is
   filter/select/to_dicts, which return new frames. No in-place mutation seen at custodian L721-760.
F4 merge order: table order preserved by Pool.map, duplicate `require` replayed in order, only `sorted(order)` and `len` consume the dict;
   `order` tuples `(available, eid, onset, targets)` have unique eid so frozenset is never compared. Pickling round trip of
   datetime/frozenset is value-exact. (Blocked by B1 only on paths.) `compare_libraries` and `from_eventsets` stay serial and unchanged.
F5 torch.set_num_threads(1): elementwise/equality ops, no numeric drift; chunksize does not affect Pool.map order.
Merge/tail (:280-321): byte-identical code to q32 L374-415 (same Counter replay order, refs only on tensor rows, same report keys,
   `auditor_sha256` of original.__file__ unchanged). No verification dropped; none moved after a point where the original would have
   failed (the original also had none after the pool except scan of input_manifest.json, kept at :294).

## (6) install pattern
`install_into` sets `pp.parallel_audit` (:73); q32's wrapped lambda resolves `parallel_audit` as a module global at call time
(parallel_phases.py L442), so the swap works, and `source()` registers the module in `sys.modules` (run_step_origin_par.py `source`), so
pool pickling of `_audit_event_fast` by name works in forked children. `_PP._replay_dir/_log_pending` exist (q32 L54, L71). Literal-sha pin
pattern matches the seam fix. With BGBENCH_PARALLEL_WORKERS=96 the signature `workers=` is honoured; prepass uses a separate env
BGBENCH_PARALLEL_PREPASS_WORKERS (default 48) that the job wrapper does not set: fine but undocumented in the job shape.

## Not checked
Real timing, real-data byte compare (EQUIV Gates 1-2), actual RSS, local equivalence tests, stdout consumers (N3).
Required before re-review: fix B1, run Gate 0 (it exercises family "" and would have failed), then Gate 1.
