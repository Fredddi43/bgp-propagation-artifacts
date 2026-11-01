# R1 v6 remaining-guard metadata preflight: code-review packet (NOT RUN, NOT APPROVED)

- Author: claude-opus-5-5, session `<SESSION_ID>`, role `/root/opus_implementation`.
- Scope: `../reviews/opus-capture-scope-review.txt` c1bf8e83 (tier A approved in scope, narrowed A1-A6; tier B not
  authorized), on the CODEPASS candidate custody 409e1171 (`../reviews/opus-v6fix-round1-verdict.json` d8b9a3a3).
- Status: tested on synthetic files only. No ssh, no remote read. It may run only after an independent code review and
  an exact execution approval in `../coordination/preflight-execution-approval.json`. Exact bytes: `pins.json`.
- Meaning of any result: a prediction for two guards. It never replaces the one fresh full verification and grants no
  staging, retention, preparation or execution authority.

## Files

| File | Role |
|---|---|
| `build_program.py` | Builds `payload.json` and `program.py` deterministically from held, SHA-verified inputs only. |
| `remote_template.py` | Remote half (stdlib only). `program.py` = this file + the payload literal + the entry call. |
| `payload.json` | The exact scope, reviewable alone (70 exact refs, 4 held documents, 122 cells, expressions). |
| `program.py` | The bytes piped to `python3 -I -B -` on <BATCH_HOST>. |
| `preflight.py` | Local driver: approval binding, exclusive intent, one ssh, output validation, write-once result. |
| `test_preflight.py` | 53 tests. Synthetic world for execution; the real payload for scope. |

## Mapping to the scope conditions

- **A1, exact refs: 70, a subset of the approved 71.** These are the 62 decision-rule files (42 core/OOD plus 20 H1),
  the 3 published fit ledgers and 5 H1 evidence documents (spec, metadata audit, approval, selection, finals). The
  slice rule is dropped as A1 requires, and served held from tier-1 capture 37a2459e (raw bytes, sha 0291d789). It is
  also the H1 `slice_rule` evidence ref, which is why 70 and not 71. `test_real_scope_is_the_reviewed_allowlist_only`
  pins this.
- **Held documents, never read remotely, all disclosed.**
  - The H1 calibration verifier: local raw bytes 7095ccc5.
  - The publication 66c2ce8c and the H1 commitment eb610e4a. Only parsed documents are held
    (`r1-metadata-v7/r1-calibration-existing-metadata.json`), so their byte-hash binding is not recomputed. The
    publication's was proven by the v6 run at :1579. The commitment's is the captured value.
  - The scope review listed none of the four as remote refs, and custody reads all four through `reads`. Serving
    them held keeps the remote reads inside A1.
- **A2, derived refs: at most 124, enforced by `Policy.admit` (`DERIVED_MAX`).** Admitted only in `register()`:
  - from the SHA-verified fit ledgers, `run["completion_path"]` and `run["out"]/fit_receipt.json` for the 42 runs
    named by the draft-bound rule refs. A fit receipt passes custody only if its sha equals the completion's
    `fit_receipt_sha256` (`calibration_fit_evidence`). Every completion's sha is recorded.
  - from the SHA-verified H1 metadata audit, `record["fit_receipt"]` and `record["completion"]`, each with its exact
    sha.
  - 42×2 + 20×2 = 124. There is no listing, glob or walk.
  - Snapshot trees are never read. `checked_snapshot` is replaced by a view of held data that is reported in `notes`
    (see A6).
- **A3, file reads.** JSON only (`json_only`), realpath == path, O_NOFOLLOW|O_CLOEXEC|O_NONBLOCK, S_ISREG, size check
  before the read (32 MiB), 256 MiB total, read exactly st_size, stable fstat, SHA before parse. Any refusal aborts
  everything, with empty stdout and one fixed stderr line. The limits are module constants, and a run over them
  refuses.
- **A4, sanitized output.** The output holds:
  - per file: {path, sha256, size, origin}
  - per check: PASS/FAIL/ERROR with the failing candidate custody line, function and innermost frame name
  - held documents used, `notes` and `unperformed` with fixed reason codes, counts

  It holds no document body, threshold, timestamp or other field value. Raw bytes exist only in the remote process's
  memory. The driver maps failing lines to literal require messages from the pinned local candidate, never from the
  remote.
- **A5, host and attempts.** The program refuses unless user `<USER>`, host `<BATCH_HOST>`, no `SLURM_JOB_ID`,
  `-I -B`; a subprocess test checks this. There are no remote writes and one attempt, behind an exclusive intent
  record. A second attempt is allowed only after rc 255 with empty stdout, and only if the approval sets
  `transport_retry_rc255_no_stdout`. A refusal is recorded as TERMINAL_REFUSED and never repaired.
- **A6, mocks disclosed per conjunct (`preflight.DISCLOSURES`, copied into the result).**
  - **Validation-prediction digests** (42 runs, 20 H1 records): never opened, reason `UNKNOWN_tier_b_...`. The
    evidence value is the published digest by construction, so 1615(f) and the 1621 validation conjunct reduce to
    rule-file versus publication. The file itself stays UNKNOWN.
  - **H1 checkpoint digests:** never opened. `PROVEN_BY_V6_RUN_adapt_h1_checkpoint_file` applies when the audit record
    names the selected-K ledger checkpoint with the same sha, otherwise `UNKNOWN_checkpoint_digest`.
  - **Snapshots:** the fit snapshot map is held (9f3e456c); its file digests were proven by the v6 adapters. The
    calibration-source preamble was proven by the v6 run at custody :1578-1590.

## Exact validator logic reused

- The candidate custody bytes (409e1171) run unchanged: `checked_decision_rules`, `calibration_fit_evidence`,
  `checked_h1_calibration`, `bound_verifier`, `require`.
- Two names are rebound:
  - `checked_snapshot`, to the held view (A6).
  - `bound_verifier`, wrapped so the verifier's own `bound`/`sha` go through the same policy.
- The evidence expressions are extracted by AST: the `calibration_fit=` keyword of `core_cells`, and the
  `calibration['calibration_fit'] = …` value of `adapt_h1` from both the candidate and the staged a0dba7aa. They are
  evaluated with the adapters' own variables.
- The checks run:
  - per learned cell, in the candidate shape
  - per OOD cell, in the staged shape (expected FAIL at the binding line)
  - the exact 122-ref aggregate as at verify_batch :1859
  - `checked_h1_calibration` on the 20 selected cells

## Remaining-guard classification after this preflight

| Class | Guards |
|---|---|
| **Computed here from captured bytes (metadata predicates)** | `checked_decision_rules`: preamble flags on the publication, fit-ledger reads, duplicate runs. Per cell: ref present, rule flags and threshold ranges, slice provenance, fit-ledger membership, one published entry by run_id, path and sha, rule-vs-publication validation digest, run_id, threshold == fit receipt, rule source == provenance driver, slice created before fit completion, completion rc/checkpoint, receipt checkpoint/test-input/split. Aggregate `set(refs) <= learned`. `checked_h1_calibration`: commitment flags, adapter == verifier, spec/audit flags and source map, evidence == spec refs, 20 records, `approval_check`, coverage, record checkpoint sha == cell model, receipt/completion bindings, rule receipt/validation/threshold/source/path/k/slice/finals/adapter. |
| **Unperformed byte-hash (reported, never inferred as pass)** | 62 validation-prediction digests (tier B, UNKNOWN). 20 H1 checkpoint digests (proven by v6 run or UNKNOWN per record). The publication byte hash (proven by v6 run :1579). The commitment byte hash (held capture). Fit snapshot file digests and the calibration-source snapshot (proven by v6 run). |
| **Full fresh run only** | Every guard before :1859 again on a new source. The rest of verify_batch: scorer bundle, slice horizon set, arm spec, analysis constants, retention review (which must be renewed for custody 409e1171). release `ledger_view`/`refuse_regeneration`, and prepare's publication steps. Tier-B digests unless separately approved. |

## Tests (`test_preflight.py`, 53 passed; Ruff clean)

- **Real payload:** it is rebuilt byte-identically. The scope is A1, with exactly 70 refs: every draft rule ref plus
  the 5 H1 evidence documents. The slice rule is held, and no prediction or non-JSON path is exact. The custody is the
  CODEPASS candidate. The staged expression uses the 4-key `spec['core']`; the candidate projects path and sha256.
- **Synthetic world** (the real H1 verifier source, held documents deleted from disk to prove they are not read):
  - candidate core and OOD PASS, staged OOD shape FAIL at the binding line, aggregate PASS, H1 PASS
  - every unperformed path reported and never opened (a FIFO there does not block)
- **13 metadata failure paths**, each reported at the right line or check:
  - threshold
  - rule-vs-publication validation digest
  - unpublished ledger
  - run_id
  - rule source
  - slice created after the fit
  - publication not passed
  - duplicate published run
  - approval reviewer
  - H1 rule finals binding
  - H1 threshold
  - H1 checkpoint metadata
  - 19 audit records

  A completion naming another checkpoint fails that cell, not the run.
- **Policy:** each of these refuses — sha mismatch, symlink, not allowlisted, size limit, derived maximum, non-JSON,
  tampered held bytes, unapproved snapshot root. Off-host the program refuses with empty stdout.
- **Driver:**
  - it refuses without an exact, passed, independent approval: author session, case variants, wrong model, tier B,
    labels, attempt limit, program hash, scope
  - one ssh call
  - a terminal refusal is never rerun
  - the rc-255 retry happens only when approved, and only once
  - output validation rejects: a wrong exact sha, a prediction path, out-of-tree derived reads, a snapshot origin,
    an oversize file, too many derived reads, unknown notes or reasons, a foreign held document, a wrong payload
    hash, missing cells, an unknown status

## Not done

No run, no remote access, no tier B, no v7 staging. The frozen packet d898567c is untouched.
