# R1 final-evaluation v6 candidate — code review only (UNAPPROVED)

Author: claude-opus-5-5, session <SESSION_ID> (/root/opus_implementation).
Base: the reviewed package `.agents/operations/r1-evaluation-20261021` (commit eaf0ed8, pins 6c7703b3,
Astra round-2 CODEPASS, 44 tests), left byte-unchanged. This is a separate copy that applies only the
B1-B7 deltas of the reviewer's v6 compatibility note
(`.agents/workers/opus-takeover-20261021/review/r1-evaluation-v6-compat/note.txt`, which supersedes the
version-specific parts of v5 review f6872daf / verdict abac270f).

Nothing here was run remotely. No preparation outcome, complete/spec/seal/ledger, R1 authorization,
approval, label access, scoring, staging or launch exists or is claimed. The v6 preparation
(supervisor 193917 / worker 193918) is a separate live operation and is not touched by this package.

## Deltas (all others byte-identical to the reviewed package)

- B1 `execute.py:18` SOURCE_ROOT -> `r1-release-assembly-v6-20261021` (moves PREPARATION = v6 control-v1,
  ROOT/OUT = v6 evaluation-control-v1, the staged source/manifest root, the custody module used for the
  fresh re-verification, and the disk-space check).
- B2 `launch.py:13`, B3 `run.sh:8`, B4 `supervise.py:8`: the evaluation-control-v1 root -> v6.
- B5 `build_candidate.py:7` PREP -> `r1-release-v6-20261021/execution/package` (spec ce9e6bfc, draft
  c084ddfc). Regenerated templates: spec template differs from the reviewed one only in `files`,
  `launcher_sha256`, `root`, `output`, `source_manifest_sha256` (97f7af7c; python 62f0c11a and resources
  unchanged). Approval template differs only in `launcher_sha256` and the new `reviewer_session: null`.
  The R1-authorization template is byte-identical to the reviewed one (7f67f584), consistent with the
  note's A2 finding that the v6 draft's science anchors are unchanged.
- B6 `execute.independent` ports the v6 release rule: reviewer `gpt-6-astra`, or `claude-opus-5-5` with a
  string `reviewer_session` of length >= 8 that contains no author session. `AUTHOR_SESSIONS` keeps the
  frozen legacy v6 preparation author <SESSION_ID> and adds the current author
  <SESSION_ID>. The worker label still refuses root, impact_consumer_review,
  reference_reuse_recovery (the reviewed package's author), now also opus_implementation and any label
  containing an author session (case-folded). The Astra path is otherwise unchanged.
- B7 `test_evaluation.py`: the 44 reviewed tests unchanged, plus 14 new: v6 constants across all four
  operational files (no v4/execution-v3 residue), templates bound to the v6 package (spec ce9e6bfc,
  manifest 97f7af7c, live file hashes, null prepared refs, unsatisfied preconditions), separate Opus
  reviewer accepted, 10 self-review refusals (legacy/current session, case, short, missing, labels, wrong
  model), and author-label refusal on the Astra path.

## Verification (local)

- `.venv/bin/python -m pytest -q -p no:cacheprovider .agents/operations/r1-evaluation-v6-20261021/test_evaluation.py` -> 58 passed.
- Reviewed package suite unchanged -> 44 passed. `ruff check` on both packages -> all checks passed.
- No `__pycache__` in the candidate at pin time.

## Still required before any evaluation (B8 and later; none exists yet)

- The ACTUAL successful v6 preparation: supervisor execution-exit {returncode 0}, complete.json, spec,
  seal at `<registry>/r1-seal-<spec sha>.json`, ledger at `v6/control-v1/prepared/evaluation/ledger.json`.
  No v4/v5 artifact may be cited as v6 output.
- A fresh sources/fits assessment against the v6 seal bridging parent verdict 8d75c9b9 (draft e3601a20)
  to v6 draft c084ddfc, the independent R1 authorization receipt, the exact final execution spec and
  approval binding those actual refs, and evaluate's fresh full re-verification before any label marker.
- An independent code-only review of these bytes by a session that authored none of them.
