# G1 custody bindings for the 122 slot-complete arms (M3) — Sonnet author; source only, nothing executed

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
`extract_custody.py` + `run_once.py` (event-ID packet launcher: ROOT SSH standard, one exchange, rc0+empty stderr+landing check `check_custody.py`, fresh records dir, no retry) read exactly the 9 documents of `request.json` (4 manifests, 2 masters, 2 inventories, 1 declaration; no-follow, regular, nlink 1, size == pin, double fstat + lstat stable, sha pinned; <=64 MiB each, 256 MiB total) and lstat 244 destination paths. Exports only top-level scalars, list/dict lengths, test-population counts and sorted-ID digests; **no event ID, input path, label, outcome, tensor, gate body or prediction leaves the process** (tests plant canaries). Writes nothing (RLIMIT_FSIZE 0). Review scope kind `ROOT_ONCE_G1_CUSTODY_BINDINGS_V1`; template `root-once.FALSE-TEMPLATE.json`.

After it lands: `check_custody.check_report` (landing) -> `analyse` (cross-document bindings, fail closed: horizon, population, inventory/master/scalar equality, core and temporal of one horizon share anchors, destinations absent) -> `bind_arms` (122 arm bindings) -> `apply_bindings` (sets `custody_inputs`, refuses conflicts). Tested on the real fragment with a synthesized consistent report (122 bound, 400 roles kept).

## What this does NOT supply (stated precisely)
1. `sources.history` and `sources.signature` LIBRARY declarations (documents with root/years/family/collectors/availability_delay_s/digest/files, used by history48, the 6+6 history-kNN baselines and baseline6) are the M4 packet's scope (core/history consumer, separate Sonnet author); the signature-source file above is only observed here. Until M4 lands those arms have no `sources`/`baseline_sources`.
2. Content of `reference_rows` / `parse_receipts` is not read (counts only), nor any tensor/input; the inference runners validate those at run time.
3. Output parent directories: the reviewed inference runners require `Path(output).parent.is_dir()` ("frozen output directory must already exist"); the once reports which parents are missing (all, at the last lstat). Creating them is a separate reviewed step and is not proposed here; the draft/finalize kernel does not need them.
4. This is evidence for promotion review, not a promotion; ordinary12 per-arm GRU/GBDT completed-fit acceptance (M2) and core/history consumer acceptance (M4) are other authors' items.

Runner: stay on reviewed r2 `runner.py` 180bdcab (ROOT decision); nothing here depends on r3.

## Tests
`test_custody.py` (7) + `test_runner.py` (21, launcher family tests with constants changed). Synthetic temp dirs only; no ssh.
