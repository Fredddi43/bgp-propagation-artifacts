# Review request: H1 G1 slot bindings (author: sonnet; reviewer: sol-h1, independent)

Scope: packets only. No launches, issuing, git, board posts. Remote use was stat+sha256sum of 14 exact paths on <BATCH_HOST>; no content read.

Run (from /tmp, `python3 -I -B`): `audit_gate.py` and `audit_gate.py --verify-remote` (re-hashes remotely), `python3 -B -m unittest discover -s tests`.

## Reviewer must certify
1. Pinned handoff 1da121cd... is the accepted g1-handoff; `output-hashes.json` covers exactly the 12 handoff output refs plus 2 construction refs; both construction hashes equal the handoff pins; no path outside `protected-h1-storage-v3/{d30,d60}`.
2. Each output was a regular file at hash time (size>0) and hashes are stable across `--verify-remote`. Note: hashes are of files whose done.json receipts were accepted by control hash only; the receipt `result.*` fields were NOT read, so "expected_path equals result ref" is unverified (see below).
3. The 20 H1 slots: arm_ids equal g1-slots.PENDING group h1; roles = 2 horizons x {sage,none} x seeds 0-4, K500; each slot's manifest_path/sha256 = its horizon's `export/input_manifest.json`. Certify that the export manifest is the intended slot "manifest" (the handoff has no other manifest-class output) or name the right one.
4. No fabricated input_gate/disposition/status promotion; execution_authorized false.
5. audit_gate.py checks are sufficient for hash/manifest/identity binding (mutation tests in tests/ cover flipped hash, fabricated gate, promotion, missing role, wrong namespace).

## NOT bindable yet (explicit)
- `input_gate_path` / `input_gate_sha256` (all 20 slots, per horizon): manifest-matching input gate is null in the handoff; needs an independently accepted finalizer output.
- `independent_protected_comparison_review_ref` per horizon: needs independent review of `equivalence_evidence`; kernel.finalize requires it.
- `finalized_protected_input_audit_ref` per horizon: needs finalizer run + review (phase audit is not the finalizer).
- `independently_accepted_final_disposition` (20 slots): needs G1 H1 family review, complete400 freeze.
- Receipt `result.*` ref cross-check (done.json fields vs expected paths): needs a ROOT-routed, independently reviewed reference-only extraction (handoff next_bounded_step).
- G1 items from handoff g1_must_bind (h1_input_audit flags/event IDs, 20 checkpoint/fit receipts, calibration rules, descriptors/arms hash): listed in `other_g1_requirements_not_bound`, outside this packet.
- Slot-field semantics of g1-inventory/g1-freeze for H1 not touched.
