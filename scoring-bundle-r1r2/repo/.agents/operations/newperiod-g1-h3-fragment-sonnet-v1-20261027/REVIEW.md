# G1 H3 owner fragment, 80 arms (Sonnet author; local, metadata only, nothing executed)

`h3_fragment.build()` -> `h3-arms.PENDING.json` (all 80 arms still `PENDING`; `executable:false`). `promote()` is the only path to `committed_for_prediction` and refuses unless every binding exists.

## Bound now (exact path+sha, sources pinned and re-hashed on build)
- 80 original arm_ids/roles preserved (pending fragment be7c140c); frozen/refit x ris7/mixed7 x sage/none x d30/d60 x s0-4.
- 40 refit models: `model_path/sha` = checkpoint ref of the matching cell in capture actual 805d275a (job 52558223), accepted by astra-final 40ba557a. `provenance` = `{kind newperiod_h3_fit_v1, package, completion(complete.json path+sha)}`; `fit_receipt` carried. Limit carried: checkpoint/receipt payload hashes are completion-declared, not recomputed.
- 160 destinations: `.../data-custodian/complete400-outputs-astra-v1/h3/<arm_id>/{predictions,commitment}.json`, same convention as primary; unique, canonical, disjoint from every other group's paths in be7c140c (tested).

## NOT yet accepted / null (listed per arm in `pending_bindings`)
1. 40 frozen models: bound to the matching N-core updated history-on PRIMARY arm (`model_binding.primary_arm_id`, 20 distinct checkpoints, each shared by ris7 and mixed7) with its core-ledger provenance, `checkpoint_generation N-core-updated-primary`. Source arms are PENDING (M1/M3/M4 outstanding), so these are provisional; `promote` refuses a frozen arm unless `frozen_accepted` names that primary arm. No refit substitution (tested).
2. Protected manifest, input gate, availability, panel_audit, panel_review and custody anchors (source_inventory, task_protocol, reference_population) per 4 scopes (panel x horizon): null until sol-h3t2 accepts the protected H3 chain. Development refit manifests are not substitutes.
3. Literal event_ids: need the extraction below over the accepted manifests.
4. Absence evidence for the 160 destinations plus capacity/retention admission (stat evidence not collected here).
5. Refit `provenance.package.path` is the staged `<stage>/package.json` (stage dir from the stage actual) with the sha of the bundle's `package.json` (30df3084, equal to the staged binding); the remote path convention is inferred, not stat-verified. Reviewer must confirm (read-only stat) before promotion.
6. Independent owner-fragment identity/provenance/disposition acceptance, then family review `newperiod-h3-retention-v1` over the normalized H3 arms hash plus controls.

## Extra event-ID request
`make_h3_request.py --out request.json --scope ris7-d30=PATH:SHA:SIZE ... (4 scopes)` wraps the extraction packet's `build(extras=...)`; labels `h3-<panel>-d<h>`, refuses paths outside `newperiod-inputs-v1/**/input_manifest.json`, duplicates, or missing scopes. No real request exists yet: its inputs are the accepted protected manifests. `request.PENDING.json` is shape only. Adding it changes request.json, so it needs the extraction packet's fresh review + ROOT once (or a separate once if request 1 already ran).

## Root sequence (who reviews what)
1. astra-final (or another fresh reviewer, not this author): review this fragment source/tests/pins: items 1-5 above, esp. the frozen-source mapping and package path.
2. sol-h3t2: accept the protected H3 chain (4 scopes), yielding manifest/gate/availability/audit/review/anchors with sizes.
3. sol-g1: review the H3 extra request built from step 2 (`make_h3_request.py`) + extraction program; ROOT once; independent acceptance of stdout.
4. M1/M3/M4 acceptance of the primary updated arms (also unlocks the 40 frozen sources).
5. Root/reviewer: destination absence + capacity admission; astra-final or sol-g1: owner-fragment disposition acceptance naming arm_ids (input to `promote`).
6. Author runs `promote` (then G1 `fill`/`static_checks`); family review `newperiod-h3-retention-v1`; sol-g1 integration review.

Tests: `tests.txt` (10): pins, 40 refit models equal capture cells, frozen never refit, nulls listed, destinations disjoint/collision refusal, promote gating (acceptance, 4 scopes, ids, refs, frozen source), request scope guards. No claim above is made in present tense about artifacts that do not exist; every PENDING item is explicit.
