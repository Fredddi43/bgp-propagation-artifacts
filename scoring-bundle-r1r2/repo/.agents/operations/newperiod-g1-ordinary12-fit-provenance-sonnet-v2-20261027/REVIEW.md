# G1 M2 v2: ordinary12 fit-provenance projection (author: sonnet; nothing launched, no remote action)
Supersedes `...-sonnet-v1-20261027` (unchanged). Answers sol-g1 ruling 77e5b507 (DESIGN_CONDITIONAL).

## Ruling conditions -> v2
- **Release:** `expected_release_sha256 = ba2a1e2e6e46b6253e85972f46b13e607ce0f32c013a07955a8408417caedba6`, all 12 arms, plus
  `release_ref` (remote r1-release.json, same sha) and `release_acceptance` = G1_R1_RELEASE_ACTUAL_ACCEPTANCE_V1 e66d7391
  (its `local_copy.sha256` must equal the pin; `run_once.py --check` verifies). Null/malformed/non-uniform pins fail before any read; the
  source additionally compares each authorization's `release_sha256` to the pin (release_chain). Record-later mode removed.
  **Open risk, precisely:** the original runner compares the authorization's `release_sha256` to the *G1 freeze's* `retrospective_release`
  sha. ba2a1e2e is the accepted R1 release and the only one the local records name for it, but the fit authorizations' own release
  hash is remote; if they were issued under a different release, release_chain fails closed (not circular, and not repairable here).
  Root must still ensure the G1 freeze pins this exact ref (same path+sha).
- **Roster/unique arms:** exact 12-id roster with model/horizon/seed/family embedded in source; spec digest (= sha256 of projection-spec.json)
  checked first; duplicates, extra, missing, wrong roles refused before any read (tested: 12 copies -> rc2, zero reads).
- **Loader containment:** no torch/GPU. `InertUnpickler` turns every global except OrderedDict/set/frozenset/bytearray into an inert stub (nothing imported or
  called), torch storages are never read (only `*/data.pkl` of the zip); tested with an `os.system` reduce payload (not executed). Only receipt
  equality is derived. Consequence: a receipt containing non-plain types compares unequal and fails closed.
- **Complete allowlist:** per-arm checkpoint/definition/completion/receipt/authorization/started plus each GBDT arm's `spec_ref` (adapter-spec.json
  79b25e0d, from the accepted assessment). The ledger's own `spec` must equal `spec_ref` else LEDGER_SPEC_NOT_ALLOWLISTED before opening it.
  If the real ledger names a different spec file the once fails closed and root must repin. Hook (installed after warm-up imports) denies every open outside
  the allowlist (read) / the log (write), exec/spawn/sockets/mutations.
- **Durable log + bounds:** fresh O_EXCL access log (`access_log` = ROOT_FILL, null refused, must be under <RESULTS_ROOT>/*.log), a line
  fsynced before each read, per-file 2 MiB / 2 GiB, aggregate 24 GiB, FSIZE 1 MiB, AS 8 GiB, CPU 600 s, alarm 900 s, wall 1000 s, stdout/stderr 64 KiB. Python `-I -S -B`, no -O, explicit raises not assert.
- **Validated output:** source rebuilds output from an allowlist (validate_output) and local landing re-validates (ids in order, release equals pin, reads count); errors reduced to a class/code.

## Root sequence
1. Independent review of this dir (SHA256SUMS; tests.txt 20 pass; nothing here ran remotely, so the hook under the real venv python and the actual
   checkpoint pickles are untested; root dry check of the hook with a trivial allowlisted file is advisable).
2. Root fills `request.json` `access_log`, re-runs `make_request.py` (repins), issues authority from `authority.FALSE-TEMPLATE.json` (kind ..._V2) with
   `admission_review` (checkpoint_body_reads_admitted, pins source/spec/release_ref) and `execution_review`; `run_once.py --check`, then once.
3. Separate reviewer fills `review-inputs/*.REVIEW-INPUT.PENDING.json` from the output; none is signed here.
