# T-R2 packet (sonnet): fixed-ID core input projection + projected-manifest gate stage

Author: sonnet (claude-sonnet-5-5), session <SESSION_ID>. Source/templates/tests only. **Nothing issued, run, posted or written remotely.** `execution_authorized=false` everywhere; every `*.FALSE-TEMPLATE.json` refuses at the issued-root gate (tested through the real CLI `--check`).
Tests: `tests.txt` / `verification.json` (cd /tmp && .venv/bin/python -I -B -m pytest ...). Requirements source: REVIEWER-sol-final TS4-V3 ... N4-R2 (da318a28), `T_R2_required_packet_contents` + `shared_required_packet_contents`.

## Files
| File | Role |
|---|---|
| `request.json` (+`plan.json`) | exact projection request: pins, sizes, read scope, decode admission, limits, own row, lineage. `plan.json` is the consumer plan `newperiod_timing_core_input_projection_v1` (bytes travel on stdin, written remotely exclusively) |
| `tr2_operator.py` | root-only once for the projection (derived from the reviewed T-S4 v3 operator; ROOT SSH standard; bounded transport; one exchange) |
| `tr2_gate_issue.py`, `tr2_gate_operator.py` | SEPARATE stage: independently issued gate for the two projected manifests |
| `tcommon.py`, `transport.py` | shared helpers; transport byte-identical to T-S4 v3 (a418543d) |
| `build_packet.py`, `test_tr2.py`, `verify.py` | generator, 60 tests, verification writer |
| `templates/` | 7 FALSE templates (root-once, execution review, adoption, control ack, gate root-once, gate review, projection acceptance) |
| `roles20.PENDING.json` | 20 role bindings (2 horizons x sage/none x 5 seeds), all slots PENDING |

## Checklist item -> where it is satisfied
**Shared**
- Immutable sibling package, absolute path+sha everywhere, SHA256SUMS: `SHA256SUMS`, `request.json`; accepted T-S4 actual, receipt 17b2443c, 1124 ids / dc8f0976, audit 86b7ef84, cohort review f907a960, canonical cohort 0deeb97d, kernel-plan 8e7fe2ae, staging 751e356e: `request.json` `timing_cohort`, `event_*`, `cohort_refs`, `lineage`, `ts4_result`, `ts4_acceptance` (`build_packet.py:50-94`; test `test_lineage_pins_bound_but_not_read`, `test_request_shape_and_fixed_population`).
- Finite read/write allowlists: reads = 8 exact metadata documents (`request.json` `read_scope`, digest `read_scope_sha256`, `tr2_operator.py:147` `read_scope`); enforced in the remote process by an audit hook that RAISES at the offending open/exec/socket/remove (`tr2_operator.py:80-97`, scope test `test_bootstrap_scope_hook_refuses_unlisted_read` proves the gate content read is refused when not listed). Writes: exclusive creation inside the fresh output dir only; exact output names checked `tr2_operator.py:104`. No tensor, prediction, label or score is in any list.
- Root operating adoption bound to the newest compatible phase: `tr2_operator.py:120-146` (own row `timing_protected_cohort`, all-writer enumeration, custody EOF + all remaining growth below 2 GiB-64 MiB `:46`, devices, locale pin, import baseline, decoded memory, read scope, 3 local processes). **Zero custody appends**, so FSIZE is a small output-only 64 MiB (valid only for the proven zero-append path; the custody log is lstat-ed, never opened `:41-47`).
- FALSE templates, current five-directory control acknowledgment, once recipe, fresh actual namespace, durable intent/stdout/stderr/terminal/STOPPED, no retry: `templates/`, `tr2_operator.py:153-172` (validate), `:189-219` (consume: result write failure is nonzero + STOPPED, tested), `:220` (run; `actual/` created exclusively = consumption).
- Missing upstream actuals explicitly pending and refusing: `roles20.PENDING.json`; `tr2_gate_operator.build_request` refuses `TR2G_PROJECTED_SIZE_PENDING` (test `test_gate_build_request_pending_and_filled`).
- Public output only count/digest/pin: bootstrap result `tr2_operator.py:111`; test asserts no id appears in stdout.

**T-R2**
- `plan.json kind=newperiod_timing_core_input_projection_v1`, `timing_cohort` = the accepted receipt, primary keys exactly {30,60} with manifest/source_inventory/input_gate: `plan.json`; consumer predicate `core_projection.py:32,36`. Original inventory/protocol/manifest identities agree before subset: `core_projection.py:38-39` + `forecast_inputs.source_inventory`. Gate must bind the complete original population: `core_projection.py:44`, and again independently `tr2_gate_issue.py:71` (`TR2G_ORIGINAL_GATE_POPULATION`). Ancestry: `request.json primary_acceptance` = REVIEWER-sol-final primary-export key correction (9164553f, gate 5b0ebfdd and manifests 88473cf4/3bb6bcc3 named); the gate is one paired document used for both horizons.
- Pins: core_projection dca0341b, corrected protected_cohort e1377ae8 + reviewed_source_io 5c61a00e + original_pack 8bdc1551 (remote kernel files hash-checked `:53`, python `:54`), bgbench closure = the 87 modules of the T040 control `construction/source` (shas from plan v31; remote `forecast_manifest 6b7e3dce`, `forecast_inputs deab11d8`, `forecast_train`, `__init__` verified by a read-only remote sha256sum; every loaded `bgbench.*` module is re-hashed in the process `:66-71`, `TR2_R_BGBENCH_BYTES`), python sha 62f0c11a, locale pin `/usr/lib/locale/C.utf8/LC_CTYPE` prefix e4b5576b (`:55`, `TR2_R_LOCALE`; remote hash confirmed read-only).
- Explicit allowlist includes receipt, audit, cohort review, two manifests, two inventories, the gate; **reading the gate content needs reviewed scope**: `read_scope_sha256` is bound into the adoption template and the execution-review template (review decision R-2).
- Decode/allocation admission covers FULL documents: audit 59,760,447 B + receipt 39,535 + review 4,672 + 2x(755,116 + 667,839 + 369,494) = 63,389,552 B x factor 32 (T-S4 measured pessimal bound 29.7x) + 256 MiB margin + import baseline 8 GiB (PROVISIONAL, see P1) = 10,886,835,712 B <= RLIMIT_AS 24 GiB (`request.json decode_admission`, `tr2_operator.py:120-146`, remote re-check on live VmSize `:72`).
- Fixed-ID zero-copy subset: `core_projection.py:45` refuses a missing id (no intersection); test `test_core_projection_refuses_missing_id_no_intersection_fallback`; rows byte-equivalent in value, contracts unchanged: test `..fixed_ids_byte_equivalent`; independently again in the gate stage `TR2G_ROWS_NOT_BYTE_EQUIVALENT`, `TR2G_CONTRACT_DRIFT` (`tr2_gate_issue.py:63-65`).
- Fresh output with the five files and aggregate flags `input_bytes_unchanged=true, full_statuses_retained=true, prediction_computed=false, gate_issued=false`: `core_projection.py:33,58`; `tr2_operator.py:104-108`. Both projected manifests are sealed/validated by the real consumers inside core_projection (`validate_prediction_manifest`, `seal_manifest`, `source_inventory`).
- Original gates do not authorize projected hashes: test `test_gate_issue_passes_real_consumer_predicate` shows the original gate has no member for the projected manifest sha; the gate stage issues one (`tr2_gate_issue.py:43-79`), mirrors the load_inputs gate predicate verbatim (`:36`, self-check `:78`), then 20 role bindings (`roles20.PENDING.json`, fill rule inside).

## Remote refusals (every one a distinct ValueError reason)
Projection `TR2_R_*` (31 codes, one site each; test `test_bootstrap_reason_codes_distinct_per_predicate`; 16 exercised end-to-end through the real subprocess: FLOOR, CUSTODY_ID/SHRUNK/GROWTH, MEMORY, KERNEL, PYTHON, LOCALE, INPUT_SIZE, CORE_BYTES, PLAN_BYTES, BGBENCH_BYTES, AS_ADMISSION, OUT_EXISTS, COHORT_REFS, SCOPE). Gate remote `TR2G_R_*` (25, 7 exercised) plus the issuer's own `TR2G_*` (23, 5 exercised by direct tests). Local codes `TR2_*` / `TR2G_*`.

## Root sequence (nothing below is done)
1. Independent execution review (template) of this packet incl. decisions R-1..R-3; root fills adoption (custody identity/devices/writers, `remote_import_vm_peak_bytes <= 8 GiB`), control acknowledgment, issues `ROOT_ONCE_TIMING_CORE_PROJECTION_TR2`.
2. `cd /tmp && /usr/bin/python3 -I -B <packet>/tr2_operator.py --authority <auth> --check`, then without `--check` (one SSH session, consumed by creating `actual/attempt1`).
3. Independent acceptance of the actual (`projection-acceptance` template); root stats the five outputs (sizes).
4. `tr2_gate_operator.build_request(request.json, <accepted stdout.json>, <sizes>)` -> exclusive `request-gate.json`; independent gate review (R-4, R-5), adoption, `ROOT_ONCE_TIMING_PROJECTED_GATE_TR2`; run `tr2_gate_operator.py`; accept the gate actual.
5. Fill `roles20.PENDING.json` (manifest, inventory, gate, matching accepted core checkpoint); prediction projection stays after global G1 and committed primary predictions (outside T-R2).

## Pending slots
`request-gate.json` (built after step 3), `roles20.PENDING.json` (manifest, source_inventory, input_gate, checkpoint x20), adoption custody identity/devices/vm peak, all reviewer/root fills.

## Storage (V44 `e5fab44a`)
Own row `timing_protected_cohort` = 1,073,741,824 B (unchanged, T040 reservations retained, credit 0). T-S4 reserved a 128 MiB cap; T-R2 cap 32 MiB; gate stage <= 4 MiB. Measured basis: outputs = 2 manifests (755,116 B each, same 1124-row population as the primary) + 2 inventories (667,839 B) + projection.json + plan.json ~ 3.1 MB. Remaining row >= 860 MiB: **V44 funds T-R2 and its gate stage; no new row needed.**

## Findings / premises for the reviewer (open)
- P1 import baseline: remote venv torch build not measured here (local CPU build VmPeak 1.54 GiB). Provisional 8 GiB; adoption must record a measured value; the remote also refuses on live VmSize.
- P2 bgbench closure: chose the T040 control `construction/source` closure (87 modules). The builder snapshot `code-bea2d2da` carries different `forecast_manifest` (6a901d5f) / `forecast_inputs` (15bd5ae0). Confirm which closure produced the d30/d60 primary manifests; the real consumers (`validate_prediction_manifest`, `source_inventory`) refuse a mismatch at run time, after consumption.
- P3 custody read-log: `s.document` never appends; request pins 0 appends. If the reviewer requires read-log records for the primary content reads this request is refused and needs a successor with an FSIZE-above-log appender (log EOF 1,526,065,393 B on 2026-10-26).
- P4 premise: receipt[eligibility_audit]/[review] equal `cohort_refs` (T-S4 finalize wrote them from those exact refs; receipt body not reopened). A mismatch refuses `TR2_R_COHORT_REFS` before the run but consumes the once.
- P5 the audit hook is a Python-level scope guard (like the accepted writer), not an OS sandbox.
- P6 gate stage is hash-only: no input tensor is re-hashed (R-4).
- P7 a separate standalone acceptance record for the original gate issuance was not found; ancestry is the key-correction review that names the gate.
