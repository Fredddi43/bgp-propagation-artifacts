# Generic H3 and timing continuation

Local candidates for separate sol-h3t review. No issued authority. Original v28
runners, execution directories, captures, releases, jobs and source packages remain
unchanged. This package derives new runners from those sources; scientific assessors
and transports retain their original gates.

`resume_support.py` validates a complete oldest-to-newest history of stopped
execution directories, their full file inventories and each original authority.
History must reach the original non-resume authority and include each intermediate
generation. Root's new authority binds the exact evidence hash, independent review,
phase and a fresh exclusive output path. Evidence alone authorizes nothing.

The runners restore prior assessments/censuses, retain allocated maxima across
groups, skip every successfully released wave and final phase, and carry released
assemblies/audit chains forward. A captured wave stopped by A2/A3 is reassessed
locally through the original assessor using its original capture request/source
hashes, without another remote capture or release. Other partial or failed releases
and captures refuse before network IO. An absent assessment never implies an
unreleased wave. H3 original audit jobs remain held. Timing retains the one-live
audit-chain rule.

Every new release keeps the original fresh df, foreign-job, held-identity, transport,
growth, file and shard checks. Exact phase bytes are rechecked. The generic runner
also refuses at a release boundary if a newer issued versioned joint-phase file is
present. It never adopts that phase automatically. New phase/evidence/authority
bindings need no source edit. Failed or uncertain scientific work still needs
separately reviewed recovery; this is not automatic retry.

## Root procedure

1. Stop the current timing v28 runner at a release boundary with the existing
   ROOT STOP mechanism. Wait for immutable `STOPPED.json`. Do not snapshot a live
   runner, kill it mid-capture or assume a new phase file stops it.
2. Freeze evidence once with:
   `python3 -B freeze_evidence.py --family timing --predecessor <stopped-chain-dir> --output <fresh-evidence.json>`.
   The existing H3 candidate evidence includes ris7-d30 wave0 captures and the
   already released mixed7-d30 assembly. New evidence needs separate exact review.
3. Issue independently reviewed v29 capacity from its false template after fresh
   df and the root sequencing conditions. All actors that may release against old
   minima must stop/rebind or be serialized before new writers start.
4. Copy each family's canonical `root-authority.TEMPLATE.json` to a fresh sibling.
   Fill `passed=true`, `independent_review` with the exact generic source/evidence
   verdict, `reviewer_model`, `root_issued_utc`, current `notify` identity,
   `joint_resource_admission`, exact `models_minimum_bytes`/`results_minimum_bytes`,
   `resume_evidence`, fresh absolute `execution_output`, and capacity-covered
   `allowed_concurrent_jobs`. Keep all source/job/plan/binding/growth/scan fields.
   Encode with the real transport's `c.encoded(doc)`, not an arbitrary serializer.
5. Run `python3 -B dry_run_authority.py --family h3|timing --authority <filled.json>`.
   It validates actual final bytes with the real constructor and derives the first
   future phase through the real consumer, in an isolated temporary directory.
   It must pass before GO. Do not create the production output directory.
6. Immediately before intent, acknowledge applicable obsolete STOP posts under the
   new root authority, rescan all old directories and the shared board, verify no
   previous consumption, then invoke once. STOP means preserve records and request
   a new reviewed scope; never reinvoke the consumed authority.

Default dry-runs use a synthetic candidate phase/review. The timing default uses
the OLD stopped wave0 history solely as a schema fixture because the live v28
runner was still progressing when this package was authored. Neither is execution
evidence. Final timing history and final root authority dry-runs remain required.

The v29 capacity proposal is already independently accepted. Its latest H3 census
was subsequently accepted by `REVIEWER-sol-h3t-H3-A2-METADATA-ACCEPTED.json`; the
proposal retains its original then-pending wording to preserve the reviewed hash.
