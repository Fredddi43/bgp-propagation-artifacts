# Review packet: class (d) adapter, round 2 (A1-A3 + re-pin to verifier-r2). LOCAL; synthetic and held metadata only.

- Author: claude-opus-5-5, session <SESSION_ID>. Base: `../adapter` (pins a42c8918) is preserved byte-unchanged.
  Round-1 verdict e84e580d (review 6637b76c): CHANGES_REQUIRED A1-A3.
- No prediction, label, report or per-event byte has been read. No host action, no job.

## Deltas

| Item | Change |
|---|---|
| Re-pin | `VERIFIER` = `../verifier-r2/verify_r1.py`. `load_verifier` first requires the verifier-r2 `pins.json` to have sha `2a861eb0…` (`VERIFIER_PINS_SHA256`), then `verify_r1.py` to match those pins. These are the current frozen r2 bytes. **Execution additionally needs verifier-r2's CODEPASS**, which is still pending. |
| A1 | `plan` and `rescore` take a mandatory `--report-sha256` (the sha bound by the K2a-captured `complete.json`). The report bytes are checked before parsing. `rescore` also requires it to equal the plan's recorded report sha. |
| A2 | `census` and `rescore` take a mandatory `--plan-sha256` (the D0 output sha recorded at D0). The plan bytes are checked before parsing. The outputs record the plan sha. |
| A3 | `check_bgbench_closure(source_src, manifest_raw, sys.modules)`: the manifest must be the held v7 source manifest 7f35bd22. Every loaded `bgbench*` module must have a source file, resolve inside `--source-src`, and match its `src/bgbench/…` sha in that manifest; `bgbench.forecast_train` must be among them. It runs right after the reader's import and again after every `load_partition` call, since `forecast_train` imports `forecast_protocol` lazily. `rescore` takes `--source-manifest` (on the host, `B/r1-release-assembly-v7-20261022/source-manifest.json`). |
| Disclosure | The `rescore` output records `label_reader`: the module, the checked closure, and the stated limitation. It reads: "a target-decoding fault common to the evaluator and this reader is NOT detectable here; ids/candidates/seeds are cross-checked against the committed predictions". |
| Rules | The output records `comparison_rule` (atol 1e-12, rtol 1e-10, adopted-rules fe602370) and `verifier_pins_sha256`. Per-event rescoring uses no bootstrap. The P-b `numpy_pairwise` choice is fixed in verifier-r2's `run_verify` for the aggregates. |

## Tests

| Suite | Result |
|---|---|
| `test_adapter.py` | 40 passed (32 + 8) |
| `ruff check` | pass |

**New tests:**
- **verifier-r2 pins:** a changed pins file refuses.
- **CLI `plan`, A1:** an unanchored report refuses and writes nothing.
- **CLI `census`, A2:** a wrong plan sha refuses, and so does an edited plan under the original sha.
- **CLI `rescore`,** with the label reader substituted and the local numpy pinned for the test:
  - plan sha refuses;
  - report sha refuses;
  - report bytes refuse when only the bytes changed (the planned sha is still given);
  - a clean run records the disclosure, closure, comparison rule and verifier pins.
- **A3:** the staged closure is accepted, with `graph_metrics` among the loaded modules. Refusals: a module from
  outside the tree, a module missing from the manifest, changed bytes, another manifest, a module without a file.

**`mutation_controls.py`:** all 17 detected. The 10 round-1 controls are re-run against r2.

| New mutation | Targeted tests |
|---|---|
| A1 plan report anchor dropped | 1 failed |
| A1 rescore report anchor dropped | 1 failed |
| A2 census plan anchor dropped | 1 failed |
| A2 rescore plan anchor dropped | 1 failed |
| A3 closure path check dropped | 1 failed |
| A3 closure bytes unchecked | 1 failed |
| verifier-r2 pins not bound | 1 failed |

"A1 rescore report anchor dropped" was undetected until the bytes-changed-under-the-planned-sha case was added,
because the plan-binding check masked it.

The host phases are proposed separately: `../classd-host/` (code transport, then D0 plan and D1 census). D2 needs
its own review after D1's measured bytes.
