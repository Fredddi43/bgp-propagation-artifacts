# DRAFT R1 retrospective release receipt (prepared for immediately after the D2 success review)

The N path consumes this document: core-chain v4 seal and `forecast_release.authorize`, through
`forecast_manifest.verify_release` (src/bgbench/forecast_manifest.py:200).
- verify_release requires passed, development_frozen and evaluation_release_complete, the exact R1 window, a past
  completed_utc, and five {path, sha256} evidence entries.
- No reviewed producer existed. `build_release.py` builds the receipt from existing hash-bound v11 artifacts only.

**Proposed key-to-artifact mapping (a decision for review; see the docstring):**

| Key | Artifact | sha |
|---|---|---|
| evaluation_manifest | the sealed R1 evaluation, all 1156 retained cells | 1cad501a |
| source_audit | the v11 source manifest | 0bdaf006 |
| retained_arm_ledger | spec['retained_arm_ledger'] | 0c137d44 |
| prediction_ledger | the evaluation ledger | 5575ebb3 |
| score_artifacts | results/report.json | 049c7a9c |

**Refusals.** The builder refuses unless:
- the class (a)/(b) verifier output d2a18c6f is all-pass and its assessment is present;
- a D2 assessment has passed (D2 is pending);
- all 1156 statuses (1066 committed, 90 failed) are intact;
- the spec window matches.

**Open points for review:**
- development_frozen is asserted from the spec's frozen_utc. Is that the intended evidence?
- Should evaluation_manifest instead be the d30/d60 cohort manifests?
- The host path the receipt is written to (a new release/ directory), and its stage tool. Not built yet: writing on
  the host needs its own approval.

**Tests.** 6 pass. Without an assessed D2 the builder refuses. With synthetic D2 evidence, the ORIGINAL verify_release
accepts the receipt on byte-identical local copies, and refuses a changed evidence sha.
