# G1 custody bindings v3 (M3) — fixes the consumed once's remote refusal `E_LENGTH_TYPE_collectors`

**Root cause (from producing code, not guessed):** the 9th document, `signature-source-2026-leak.json`, is a causal-library SOURCE DECLARATION. Its exact contract is enforced by the reviewed consumer `newperiod-history-inference-20261023/reviewed_helpers.py::library()`: key set exactly `{root, years, family, collectors, availability_delay_s, digest, files}`, with `family=='leak'`, `availability_delay_s==0`, **`collectors is None`** (primary pooled library; every production call is `CompletedEventLibrary.from_eventsets(..., collectors=None)`, scripts/custodian_newperiod_inputs.py:258/260/348/780), `years==[2026]` for the signature library, `files` a list. v2 listed `collectors` among the named containers (list/dict) so the real `null` refused (`E_LENGTH_TYPE_collectors`, remote rc1, once consumed, no retry). The manifest/master/inventory shapes were re-derived from the writer (`custodian_newperiod_inputs.py` master()/export(), `forecast_manifest.py` PREDICTION_KEYS/STATUSES): their named containers (`events`, `reference_rows`, `parse_receipts`) are lists and their allowlisted scalars (`schema_version` int 2, `manifest_kind`, `protocol` "newperiod-development-v1", hex digests, `delta_s`, `input_profile`) fit the validators; no other change was needed.

**v3 changes:** `collectors` moved from LENGTHS to the declaration scalar allowlist with the exact validator `is None` (any non-null panel refuses `E_FIELD_TYPE_collectors`); `availability_delay_s` must be 0; `years` exported as a validated list of ints; `files` length only; `key_set_exact` (observed, not refused remotely) reports whether the doc has exactly the contract key set. The local landing checker additionally requires for `signature-source`: key set exact, family leak, delay 0, collectors null, years [2026], root = the staging-v2/data signature library root, files > 0 (`X_DECLARATION_CONTRACT`). request.json repinned (producer sha), run_once CHECK_SHA repinned.

**Regression:** `test_producer_shapes.py` builds producer-shaped fixtures (master with graph_path/custodian_label_files/feature_contract etc., inventory, prediction manifests, and the declaration with `collectors: null` and `files` entries) and (1) reproduces the exact `E_LENGTH_TYPE_collectors` on the pinned v2 bytes, (2) shows v3 accepting it with only the allowlisted fields exported (no paths/IDs/labels), (3) shows every named container/field fails closed on non-contract values. Total 40 tests.

Note: a NEW ROOT once and a new independent review are required (the previous once is consumed).

---
# G1 custody bindings v2 (M3) — Sonnet author; source only, nothing executed

**v2 closes sol-g1 CHANGES (SOL-G1-M3-CUSTODY-BINDINGS-REVIEW; v1 unchanged on disk, its bytes pinned in `test_v1_reproductions.py`).** Regression-first: that test reproduces each finding on the exact v1 bytes and shows v2 refusing.
1. **M3-EXPORT-1 (generic scalar dump):** `extract_custody.py` now exports only an explicit per-kind ALLOWLIST of named non-protected scalars, each type/pattern-validated (hex digests, closed horizon {30,60}, tokens, bool, `<CLUSTER_STORAGE>/` path for the declaration root), plus lengths of named containers only; everything else in a document (including top-level canaries `event_id/label/outcome/input_path` and the whole observe-only declaration beyond 4 fields) is never read into the report. A wrong-typed allowlisted field REFUSES (`E_FIELD_TYPE_*`) instead of exporting. `input_status` is a closed enum (`forecast_manifest.STATUSES`); anything else refuses. The remote and local allowlists are asserted identical.
2. **M3-LANDING-2 (landing bypass):** `check_report` (which `run_once.real_validator` calls) is now the full semantic landing: every document's exact key set, per-field type/value semantics, count consistency (status counts sum to the test population), all 9 required labels and all four manifests, strict stat rows (exact keys/types; any `exists:true` or extra key refuses `X_DESTINATION_PRESENT`/`X_STAT_ROW`), and the cross-document analysis (population 1289/6c1cf870, manifest<->inventory<->master shas and anchors, horizon/profile). Nothing is bound before it passes; the CLI prints PASS only after all of it.
3. **M3-BINDING-3 (substring binding):** arms bind ONLY by exact (manifest_path, manifest_sha256) equal to an observed manifest, with role horizon == manifest horizon; every executable arm of the four groups must bind (no skip), exact 122 required, duplicates/ghost bindings/non-executable arms with custody refuse, and `apply_bindings` proves the other 278 arms and every other field of all 400 roles are unchanged.

Tests: 37 (`test_custody.py` 7, `test_landing.py` 6 against the real request/fragment, `test_v1_reproductions.py` 3, `test_runner.py` 21). The v1 text below remains the design description (request/transport unchanged except the repinned program/checker).

# (v1 design text)

Answers sol-g1 `promotion-evidence-review.json` missing_items.M3 for primary56, history48, ordinary12, baseline6 (all other 278 roles untouched; all 400 preserved).

## What the arms must carry and who consumes it
`retention.py` draft/finalize itself consumes only `event_ids`, manifest/gate/model slots and destinations (checked against the original `freeze`: test population == manifest, gate passed and bound, outputs absent) and PRESERVES every other field. `custody_inputs {task_protocol_sha256, reference_population_sha256, source_inventory{path,sha256}}` and `sources` are the fields the reviewed inference runners require from the frozen arm (`frozen-inference/predict.py` checked_batch; history `runner.py:75-90`; baseline `reviewed_helpers.py:235`), and the family reviews bind them. This packet supplies them from the ACTUAL documents, not from scalar equality:

| field | source document (bound by sha256, projected by the once) |
|---|---|
| `event_ids` | accepted event-ID actual 45661db3 (4 manifests x 1289, exact path+sha); this once additionally re-derives each manifest's test-ID digest and requires it equal 6c1cf870 and equal the master's ID digest |
| `custody_inputs.task_protocol_sha256`, `reference_population_sha256` | top-level fields of the exact accepted export manifests (core-d30/d60, temporal-d30/d60), cross-checked equal to the exact accepted `source-inventory.json` (cd646f5f d30, 941d8001 d60) |
| `custody_inputs.source_inventory` | inventory path + sha256, which must equal `manifest.source_inventory_sha256` |
| `sources.master` | accepted `custodian-master.json` (72d15738 d30, aae10967 d60), sha must equal `manifest.parent_master_sha256`, event-ID digest equal the manifest's |
| `sources.signature` | `primary-issue-time-v1-signature-source/signature-source-2026-leak.json` (676637 B, 0444): observed (sha reported, scalars + files length) so it can be pinned by acceptance |
| destinations | the 244 predictions/commitment paths: lstat-only absent check and parent-dir status at the once; all 400 roles/destinations remain in the fragment untouched (kernel re-checks absence for all 400 at draft/finalize) |

## The finite read-only once (design; ROOT launches)
`extract_custody.py` + `run_once.py` (event-ID packet launcher: ROOT SSH standard, one exchange, rc0+empty stderr+landing check `check_custody.py`, fresh records dir, no retry) read exactly the 9 documents of `request.json` (4 manifests, 2 masters, 2 inventories, 1 declaration; no-follow, regular, nlink 1, size == pin, double fstat + lstat stable, sha pinned; <=64 MiB each, 256 MiB total) and lstat 244 destination paths. Exports only allowlisted named scalars, container lengths, test-population counts, closed-enum status counts and sorted-ID digests; **no event ID, input path, label, outcome, tensor, gate body or prediction leaves the process** (tests plant canaries). Writes nothing (RLIMIT_FSIZE 0). Review scope kind `ROOT_ONCE_G1_CUSTODY_BINDINGS_V1`; template `root-once.FALSE-TEMPLATE.json`.

After it lands: `check_custody.check_report` (landing) -> `analyse` (cross-document bindings, fail closed: horizon, population, inventory/master/scalar equality, core and temporal of one horizon share anchors, destinations absent) -> `bind_arms` (122 arm bindings) -> `apply_bindings` (sets `custody_inputs`, refuses conflicts). Tested on the real fragment with a synthesized consistent report (122 bound, 400 roles kept).

## What this does NOT supply (stated precisely)
1. `sources.history` and `sources.signature` LIBRARY declarations (documents with root/years/family/collectors/availability_delay_s/digest/files, used by history48, the 6+6 history-kNN baselines and baseline6) are the M4 packet's scope (core/history consumer, separate Sonnet author); the signature-source file above is only observed here. Until M4 lands those arms have no `sources`/`baseline_sources`.
2. Content of `reference_rows` / `parse_receipts` is not read (counts only), nor any tensor/input; the inference runners validate those at run time.
3. Output parent directories: the reviewed inference runners require `Path(output).parent.is_dir()` ("frozen output directory must already exist"); the once reports which parents are missing (all, at the last lstat). Creating them is a separate reviewed step and is not proposed here; the draft/finalize kernel does not need them.
4. This is evidence for promotion review, not a promotion; ordinary12 per-arm GRU/GBDT completed-fit acceptance (M2) and core/history consumer acceptance (M4) are other authors' items.

Runner: stay on reviewed r2 `runner.py` 180bdcab (ROOT decision); nothing here depends on r3.

## Tests
`test_custody.py` (7) + `test_runner.py` (21, launcher family tests with constants changed). Synthetic temp dirs only; no ssh.
