# R1 final-evaluation v7 candidate: code review only (UNAPPROVED)

- Author: claude-opus-5-5, session <SESSION_ID> (`/root/opus_implementation`).
- Base: the CODEPASS v6 candidate `.agents/operations/r1-evaluation-v6-20261021`: review-pins 853ec1db, review
  e8f0b337, verdict 3422896a (reviewer session <SESSION_ID>), 58 tests. It is left byte-unchanged; this is a separate
  copy.
- Target: the v7 preparation that is now running (packet `r1-release-v7-20261022`):
  - execution spec 0cb262fb, draft 44acc870, launcher 6ea224eb
  - source manifest 7f35bd22, which binds custody `forecast_retrospective_custody.py` 409e1171
  - remote root `B/r1-release-assembly-v7-20261022/control-v1`

**Not done:**
- nothing was run remotely, and the live v7 run (supervisor 263785 / worker 263786) is untouched
- no v7 outcome exists or is claimed: no complete/spec/seal/ledger, R1 authorization, approval, label access,
  scoring, staging or launch
- all prepared references in the templates are null until v7 succeeds

## Deltas from the CODEPASS v6 bytes (everything else is byte-identical)

| File | Change |
|---|---|
| `execute.py` | `SOURCE_ROOT` → `r1-release-assembly-v7-20261022`, which moves `PREPARATION`, `ROOT`, `OUT`, the staged source and manifest root, the custody module used for the fresh re-verification, and the disk check. Two comment/docstring lines name v7. |
| `launch.py`, `run.sh`, `supervise.py` | the evaluation-control-v1 root → v7 |
| `build_candidate.py` | `PREP` → `r1-release-v7-20261022/execution/package` |

**Unchanged:**
- the driver, the science, the evaluation scope `r1-single-evaluation-execution-v1`, the six R1 preconditions
- the independence rule (`AUTHOR_SESSIONS` f1d352ff + 065d2f16, labels, Astra/Opus paths)
- the authorization template

`test_operational_files_differ_from_the_codepass_v6_only_by_the_declared_root` proves this. It applies exactly
these four text replacements to the CODEPASS v6 bytes and requires equality for all five files.

**Regenerated templates** (`build_candidate.py`, unchanged logic):
- **spec template 91e7403c:** differs from v6 only in `files`, `launcher_sha256`, `root`, `output` and
  `source_manifest_sha256` (now 7f35bd22). Python 62f0c11a and resources are equal to the v7 spec.
- **approval template 529c95a7:** differs only in `launcher_sha256`.
- **R1-authorization template 7f67f584:** byte-identical to v6. The v7 draft's science anchors equal v6's. The
  draft differs from v6 only in the staged-root paths of `scorer` and `release_resources`, which `execute.py` does
  not read.

## Tests

| Suite | Result |
|---|---|
| `test_evaluation.py` | 61 passed |
| CODEPASS v6 suite, unchanged | 58 passed |
| reviewed base package `r1-evaluation-20261021` | 44 passed |
| `ruff check` | pass |

`test_evaluation.py` is the 58 v6 tests, with the 2 v6-specific tests replaced by 5 v7 ones:
- `test_v7_retarget_constants`: roots in all four operational files; no v4/v5/v6/execution-v3 residue in those
  files or the builder.
- the byte-equivalence test above.
- `test_v7_templates_bind_v7_preparation`: spec 0cb262fb, draft 44acc870 and launcher 6ea224eb by hash;
  python, resources and manifest equal the v7 spec; all prepared refs null; nothing authorized.
- `test_v7_source_manifest_is_the_staged_v7_source_with_the_custody_fix`: the manifest's root is
  `SOURCE_ROOT/source` (what `execute.package` requires), and it binds custody 409e1171.
- `test_templates_are_regenerated_exactly_by_the_builder`.

**Negative controls** (`mutation_controls.py`), each in a throwaway copy:

| Mutation | Result |
|---|---|
| `execute.py` root back to v6 | 5 failed |
| `launch.py` root back to v6 | 4 failed |
| `run.sh` root back to v6 | 4 failed |
| builder PREP back to v6 | 3 failed |
| spec template with the v6 manifest | 3 failed |
| current author dropped from `AUTHOR_SESSIONS` | 8 failed |
| a fabricated prepared reference | 2 failed |

## Still required before any evaluation (none exists yet)

1. The actual successful v7 preparation:
   - supervisor `execution-exit` `{returncode 0}`
   - `prepared/complete.json` and `prepared/spec.json`
   - the seal `<registry>/r1-seal-<spec sha>.json`
   - the ledger `v7/control-v1/prepared/evaluation/ledger.json`

   No v4/v5/v6 artifact may be cited as v7 output.
2. A fresh sources/fits assessment against the v7 seal, and the independent R1 authorization receipt.
3. The exact final execution spec and approval binding those actual refs.
4. Staging of these four files into `B/r1-release-assembly-v7-20261022/evaluation-control-v1` only after the v7
   run has finished.
5. The evaluation's own fresh full re-verification before any label marker.
6. An independent code-only review of these bytes by a session that authored none of them.
