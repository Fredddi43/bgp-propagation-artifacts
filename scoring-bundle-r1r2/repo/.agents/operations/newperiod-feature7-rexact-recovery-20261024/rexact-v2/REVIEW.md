# Witness fix: gate package revision-v2 (staged link targets) + R-exact-v2 packets, binder, B builder

Author: claude-opus-5-5 f4d75bb1. Basis: the postimage actual assessment 914db904 (R1-R4). Code and spec only;
nothing staged, launched or bound. The failed v1 A roots (temporal and core R-exact-v1), their records and the
original roots stay preserved. The old core authority 8355e495 stays HELD and unconsumed. There is no retry under
any old authority.

## R1: the rule, in `newperiod-input-gate-temporal-20261023/revision-v2/`
- `syscall_trace.py` has three new pure helpers, shared by the witness and B:
  - `staged_targets(stage_doc)` reads the sha-pinned staging receipt's own `links` (as written by
    custodian_newperiod_inputs.stage). It yields {resolved file: pinned bytes} and [exact linked directories].
    Every record must be complete. A target pinned twice must carry the same bytes. A resolved path must be absolute,
    canonical and contain no `..`.
  - `staged(value, targets)` admits an exact file target, or a path at or below an exact linked directory. A sibling
    prefix such as `graphsX` does not count. No broad roots are admitted.
  - `staged_layout_holds(stage_doc)` requires every receipt link (data/history root + relative path) to still
    `realpath` to its pinned target. A retargeted link refuses, including one that points at another pinned file.
- The receipt is a plan-bound declared document (stage_receipt sha in the A plan, hashed in preimage), so the set is
  fixed before launch and never discovered at runtime.
- The staging-v2 receipt itself is NOT available locally. Its link records are only checked at runtime, where
  anything inexact refuses at stage `chain`.

## R2: the same rule in all three checks
- `audit_witness.py`:
  - chain stage: compute the targets and require the layout to hold;
  - postimage: an observed resolved path outside the data roots is admitted only if `staged`. The existing
    identity/ctime/device checks apply, plus the pinned byte count for file targets. The listings check gets the
    same admission. The layout is re-checked after the audit.
  - The scope carries `staged_targets_sha256`.
  - The untraced parent's trace stage re-derives the targets from the plan's stage receipt, logged in custody as
    `witness trace stage: staging receipt link targets` and read through `image()` against the plan sha.
- `syscall_trace.verify(raw, scope, recorded, targets)`: the scope digest must match. A staged open counts as data
  and must be recorded, exactly like a data-root open. Anything else is still default-denied.
- `input_gate.py` (B): recompute the targets from B's own sha-checked stage receipt. Require the layout to hold, the
  receipt history_root to equal the master's, and the scope digest to match. Pass the targets to `trace.verify`.
- R3: no new system allowances were needed. The trace's /proc and /sys cpu files are already in SYSTEM_FILES or
  traced-pid /proc.

## Tests (local .venv): revision-v2 194 passed (test_gate 169 + test_temporal 11 + test_staged 14)
- Harness changes, test-only:
  - `synthetic_world` now lays the roots out like staging. The target event's replay files and the history
    memberships move to a source tree outside the roots and are linked back, and `graphs` is a directory link. The
    receipt carries exact `links`.
  - `trace_reference_roots` also binds the editable .pth root. This fixes the inherited harness, which predated the
    final bootstrap delta, so every synthetic plan refused at `plan`.
  - The CODE pins name revision-v2.
  - Inherited tests are adapted where the new behaviour is intended:
    - observed paths are now resolved targets;
    - one extra parent custody record per run;
    - verify gets `targets`;
    - the positive-control classifier gains a `staged` class (asserted non-empty, OUTSIDE still 0).
- `test_staged.py`:
  - The layout really is symlinked.
  - A legitimate pinned target passes the real witness.
  - These refuse:
    - an escape link to a copy outside the receipt (stage `chain`);
    - a link retargeted to another PINNED target (`chain`);
    - changed target bytes with identical rows (`postimage`; mutation check: dropping the byte rule makes that test
      pass the witness);
    - trace verify unit cases (pinned + recorded passes; unpinned, unrecorded, digest mismatch and sibling dir
      refuse);
    - inexact or conflicting receipt records.
  - B issues for the pinned layout, then refuses after a retarget with exactly "Staged link layout differs from the
    staging receipt" at `evidence-d30`. B also refuses a re-anchored witness whose scope names other targets
    ("Staged targets differ from the witness scope").

## R4: new pins, new A roots, binder and B builder in step
- `build_v2.py` -> `packets/{temporal,core}` (`test_build_v2.py`, 7 passed). The packets are derived from the
  reviewed v1 packets by these substitutions only:
  - A roots `newperiod-input-gate-{temporal,private}-rexact-v2`;
  - package path revision-v2;
  - the five package members, with pins.json ef273b1d (runtime hashes, base 228f0e6d);
  - GATE_PINS;
  - plan code pins; stage-command checksums (regenerated; the generator reproduces v1's byte for byte as a
    self-check); spec file shas and launcher; transport LAUNCH_SHA; the deterministic authority documents.
  - The other 91 source members, including verifier 6171148c, are byte-identical.
  - Manifests: temporal ee3684ab, core 41f73bc0. Specs: temporal 2b20d659, core 229db3ae. Both pass the v2
    `gate_execute.checked_spec`.
- `newperiod-input-gate-plan-bindings-20261024/rexact-v2/`: binder generated from rexact-v1 (`build_bind.py`, an
  explicit substitution list). It covers:
  - v2 roots and v2 manifest pins;
  - package revision-v2;
  - plan code may name neither revision-v1 nor revision-v5;
  - request kind `_rexact_v2`;
  - an explicit result kind `_rexact_v2_result` (the v1 derivation `KIND.replace('_v1', ...)` would have left it
    equal to the request kind).
  Tests: 25 passed, including v1<->v2 refusal both ways. rexact-v1 still has 23.
- `gate-phase-core/`: B spec builder generated from the reviewed v1 one (`build_gate_v2.py`): v2 root, v2 spec and
  manifest, v2 binder kinds. Tests: 16 passed.

## Not done / needed, in order
1. Your review.
2. Root resource admission (16 GiB each for temporal and core A, as before) and execution approvals.
3. Each profile once: source stage, transport stage, launch, waiter, capture.
4. Successful A, then binder and B under their own approvals and the root gate authority.
The old v1 records are never credited or re-bound.
