# Origin 40-fit execution operator v3 (valid20 + invalid20): S3 actuals bound, candidates built

Author sonnet-origin-fit40 (claude-sonnet-5-5). v3 = v2 (F1 sacct parser, F2 reviewer-identity normalization kept: operate.py:154, remote.py:150-185, regression tests `Regressions.*`) plus the changes below. v1/v2 unedited. No launches, no board posts, no git; remote actions were read-only stat/sha256sum/sacct only. `execution_authorized` is false everywhere; every candidate is non-authorizing.

## What changed in v3
1. **S3 actuals bound** (accepted b71cbf0c, map 3fc4c9cf): all four boundary refs and `boundary_actual_review` (= acceptance.json) are copied verbatim into `templates/release-inputs.<valid|invalid>.PARTIAL.json`; `s3_acceptance` = acceptance.json. Test `test_real_acceptance_binds_each_boundary_and_is_independent` checks the real acceptance embeds each boundary ref and its reviewer sol-g1 is independent.
2. **Local review shipping** (prepare.py:285 `evidence`, remote.py:171-178): the acceptance lives under `.agents` (not on the cluster). The operator ships its exact bytes (`review_text`) and the remote helper hash-checks them, then applies the same binds/independence rules; only `<CLUSTER_STORAGE>/` subject refs are hashed remotely. No staging of review copies is needed for the outer reviews. Reviews the science consumer itself reads (`metadata_review`, `precision_review`) and every `plan` ref must be cluster paths (prepare.py:134, `OP_CONSUMER_REF_NOT_REMOTE`): those two do need staging at an `<CLUSTER_STORAGE>/` path before they can be bound.
3. **Capacity**: stdout is embedded in `<arm>.result.json` (entry.py:125-139, not a separate file, never truncated: >256 KiB marks the cell not-passed), so cells use 7 files: closure budget is now 49 files / 37 dirs (was 29).
4. **Locale pin**: `LC_CTYPE=C.UTF-8` in job.sh env and `locale_pin` (/usr/lib/locale/C.utf8/LC_CTYPE, 353616 B, sha e4b5576b..., same pin as S2 v4; re-verified live) checked on <BATCH_HOST> at stage/preflight (remote.py:65, OF_R52-54). Compute-node identity of that file is a new adoption flag `compute_node_locale_identity_admitted`. No runtime_guard hash closure is used by this packet, so no further runtime pins exist; the immutable-runtime flags remain adoption items.

## Slot table (38 evidence slots: 9 resolved, 29 still missing)
Machine-readable: `templates/slots.json`.

| Slot kind | Count | State | Source / reason |
|---|---|---|---|
| shared.recipe | 1 | RESOLVED | frozen recipes.json, sha 6d851282 = RECIPE_SHA, at the all-recipes evidence path (prepare.py RECIPE_REF; stat+sha256sum verified read-only) |
| group.boundary | 4 | RESOLVED | S3 v4 artifacts, acceptance b71cbf0c |
| group.boundary_actual_review | 4 | RESOLVED | acceptance.json b71cbf0c (local path, shipped by bytes) |
| shared.metadata_review | 1 | MISSING | independent machine review binding projection 48a70fd0 + recipe + projection coverage (what family.fit_cell reads). Only the public ORIGIN-PROJECTION-V3R3-ACTUAL-ACCEPTED exists and the scope doc states it is not this review. Owner: independent reviewer (sol-final / sol-g1a); then stage at an <CLUSTER_STORAGE> path |
| group.construction | 4 | MISSING | family.construction/build_shard outputs; S3 boundary now exists but own source inventory, retrospective release and construction run do not. astra-g1b + a once |
| group.construction_actual_review | 4 | MISSING | independent review after the construction actual |
| group.manifest | 4 | MISSING | family.assemble output from the construction shards |
| group.gate | 4 | MISSING | sealed development integration gate on that manifest |
| group.gate_actual_review | 4 | MISSING | independent review of the gate actual |
| group.retrospective_release | 4 | MISSING | no origin retrospective release exists on the board or in operations |
| family.precision | 2 | MISSING | per-family validation precision assessment; needs construction + release first |
| family.precision_review | 2 | MISSING | independent review of it, staged at <CLUSTER_STORAGE> |

History-r3 library: accepted evidence exists (`l6-summary.json` 45f6f456, history root and source digest in the followup/scope doc) and is consumed by construction; there is no separate fit slot for it, it is covered by the fit_input_review flag `history_r3_library_complete`. Count of still-missing slots: **29**. Also missing, not slots: `fit_input_review`, `metadata_review` staging, source-closure independent acceptance, resource admission, adoption, operation reviews.

## Candidates now resolved from accepted metadata
- `source-closure.CANDIDATE.json`: static import closure (33 files incl. `bgbench/__init__.py`, 29 bgbench modules, family.py, reviewed_build.py, adapter.py), real paths and sha256 from local source; passes `prepare.closure` (<=49 files). It is a static over-approximation, runtime closure needs independent confirmation.
- `manifest.<valid|invalid>.CANDIDATE.json`; sha256 valid 58afbbe24c508713f68fdda5feb993c46789127b27c320f35254d308df3aa125, invalid c1ec345eef8114a1716d6805030fa61b2cea9ce974f644806eb05a4bd62cb96d. Filled into the 8 FALSE root/review templates. These change if closure, resources or any operator file changes (test `test_candidate_closure_and_manifest_sha`).
- `resource-admission.<fam>.CANDIDATE.json` + `resource-evidence.core-analog.json`: read-only sacct of the 40 accepted COMPLETED 0:0 `bgb-forecast-newperiod-core-development` fits (same trainer; gpu-rtx8000, 4 CPU, ReqMem 240G): max RSS 167182684160 B (155.7 GiB), max VMSize 177825964032 B (165.6 GiB), elapsed 2607-4495 s. Candidate asks 4 CPU / 245760 MiB / wall 86300 s / concurrency 1; RLIMIT_AS (mem-256 MiB) exceeds the measured VMSize. This is an ANALOG, not an origin measurement: timing40 fits (job 52555460) are still held, no origin fit has run. `passed` false and reviewer null, so `prepare.resources` refuses it until an independent reviewer admits origin memory.

## Exact root sequence for the 8 onces (per family, valid and invalid independent)
0. Before any once: independent acceptance of the source closure and resource admission; operating adoption (all flags true, fresh custody device/inode/EOF/growth, manifest sha bound) per family; control snapshot after a fresh board scan; independent operation review per action. Run `cd /tmp && /usr/bin/python3 -I -B <v3>/operate.py --authority <root-file> --check-only` before each real run; never with cwd in a dir containing operator.py.
1. `stage` (root-<fam>-stage): needs only closure, resources, adoption and phase; evidence slots may still be missing. Then independent acceptance of `actual-<fam>-stage/result.json`.
2. `submit_held` (needs accepted stage): holds array `0-19%1`; readback of all 20 held tasks; independent acceptance.
3. Gate to release: all 29 missing slots resolved with independent reviews, `fit_input_review` (nine flags true, bindings sha, embeds every ref), `metadata_review` and `precision_review` staged on <CLUSTER_STORAGE>. Then `release` (needs accepted held actual, release_inputs, operation review bound to the bundle sha): exclusive install, final preflight, `scontrol release`.
4. When all 20 tasks are COMPLETED 0:0: `capture` (needs accepted release), metadata only; per-role completed-fit review and G1 merge are separate.
Each actual directory `actual-<valid|invalid>-<action>` is consumed before the first remote effect; failure consumes authority.

## Reviewer must check
- release_bundle bindings prepare.py:300+; evidence/review shipping prepare.py:285, remote.py:159-185; closure candidate completeness (build_templates.py:20); candidate resource arithmetic; embedded stdout entry.py:125-139; the CELL_FILES=7 capacity change (prepare.py:44).
- Risks: static closure over-approximation; analog resource numbers; RLIMIT_AS vs CUDA reservations (measured VMSize 165.6 GiB below the 239.75 GiB cap); remote helper CPU limit 180 s for evidence hashing (projection 172 MB plus manifests); compute-node locale equivalence unproven.
- Tests: tests.txt (31 pass) includes the F1/F2 regressions, slot count, real S3 acceptance binding, candidate sha, locale and review-text refusals.
