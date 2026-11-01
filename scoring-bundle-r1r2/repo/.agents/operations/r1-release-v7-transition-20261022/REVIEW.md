# R1 v7 post-success transition packet (LOCAL; nothing authorized)

- Author: claude-opus-5-5, session <SESSION_ID> (`/root/opus_implementation`).
- Purpose: when the live v7 preparation succeeds, move straight to B8, the independent sources/fits assessment,
  the R1 authorization and the exact final-evaluation approval, with no further design work.
- Live run: `B/r1-release-assembly-v7-20261022/control-v1`, supervisor 263785 / worker 263786. It was still
  running at 20:25Z: no `execution-exit.json`, no `prepared/complete.json`. Untouched.
- Reused unchanged:
  - CODEPASS evaluation v7: review-pins 4d9a37b4, verdict 360ab81f, review 6d39f2ba
  - the reviewed capture tool `r1-prerequisite-evidence-20261021/capture_metadata.py` (f19d1066)
  - the R1-authorization template 7f67f584
  - the author exclusions in `execute.py` (`AUTHOR_SESSIONS` f1d352ff + 065d2f16)
- No new science, retry or P9 decision. No template is regenerated or rewritten.

## Files

| File | What |
|---|---|
| `transition.py` | `bridge`, `request-a`, `request-b`, `fill` (see its docstring) |
| `source-fit-bridge.json` | the bridge, generated now from local bytes; a test proves it is byte-exact |
| `capture-request-a.json` | request A for the reused capture tool; a test proves it is byte-exact |
| `terminal_status.sh` | bounded operational status probe (see §2) |
| `test_transition.py` | 22 tests |
| `mutation_controls.py` | 9 guard removals |

## 1. Source/fit bridge (now, local): `source-fit-bridge.json`

**Held evidence** (26-family / 19-parent; Astra-reviewed):
- inventory 26659200: 26 families, `sources_satisfied` and `fits_satisfied` false, three items remaining
- anchor map 0d331dc4
- parent verdict 8d75c9b9: 19 verified parents, binding v4 draft e3601a20 and consumer custody 818497e4
- assessment da503e1d and capture verdict cf56da7e

**Draft chain** (recomputed field by field from the local package bytes):
- v4 e3601a20 → v5 7c8d7f9c → v6 c084ddfc → v7 44acc870.
- Every step, and v4→v7 overall, changes only `release_resources.{contract,review}.{path,sha256}` and the three
  `scorer.*.path`.
- The scorer sha256s and every science key are equal: families, consumer sources, history, recipes, exposure,
  retained-arm, secondary, window, decision rules, calibrations.
- Anything else refuses.

**Custody chain** (each step tied to its independent review):

| From | To | Change | Review |
|---|---|---|---|
| 818497e4 | fb9468b8 | horizon fix | 2fdc08e3 |
| fb9468b8 | a0dba7aa | order fix | 6e3e4ca8 |
| a0dba7aa | 409e1171 | calibration-binding fix | d8b9a3a3 |

The v7 source manifest 7f35bd22 binds custody 409e1171.

**Held anchors:** the template's history-withholding (82a59256), new-period recipes (2d9f2797) and exposure
(ba323f55) preconditions, plus its retained-arm, secondary and window, are checked equal to the v7 draft.

**Success-dependent refs are all null.** Claims: fresh verification done = false; the parent verdict covers v7 by
itself = false; R1 authorized = false.

The assessor's job, unchanged, is a fresh sources/fits assessment against the v7 seal that uses this bridge.
The v4-bound verdict is never cited as covering v7 by itself.

## 2. What must be read after the terminal state

| Class | Artifact | Who may read |
|---|---|---|
| operational status | `execution-exit.json` (≤ 4 KiB), stat of the start and prepared records, last 64 KiB of `launch.err` | `terminal_status.sh`, within root's bounded status scope |
| operational records | `execution-exit.json`, `execution-started.json`, `launched.json` | capture A |
| release metadata (B8) | `prepared/complete.json`, `prepared/spec.json`, `prepared/evaluation/ledger.json` | capture A, **needs an exact capture approval** |
| release metadata (B8) | `B/occurrence-final-v1/custody/r1-access/r1-seal-<spec sha>.json` | capture B (path from complete.json), same approval |
| protected (never) | labels, payloads, validation predictions, scored outputs | nobody in this packet |

**Capture tool limits** (the tool is unchanged): JSON only under B, explicit paths, at most 16 MiB per file and
256 MiB in total, no references followed. A file over a cap fails closed and leaves empty evidence. That would
need a new reviewed request, never a workaround.

**`fill` re-checks on the captured bytes exactly what `execute.prepared()` checks:**
- the exit record holds an integer `returncode` that is 0;
- `complete.json` has the right kind, `passed`, exactly one verification pass, `labels_opened` false,
  `r1_authorized` false, and `fresh_evaluation_reverification_required` true;
- spec and ledger are at their destinations, with the captured hashes;
- the seal is at `r1-seal-<spec sha>.json`.

It then writes three files:
- `execution-spec-FILLED.json`: the CODEPASS template with the actual `prepared_complete`/spec/seal/ledger; the
  `r1_authorization_sha256` stays null and three items stay pending.
- `r1-authorization-DRAFT.json`: the unchanged 7f67f584 template with `prediction_commitments` set to the seal and
  `evaluation_ledger_sha256` filled. It stays `passed: false`, with every precondition `satisfied: false` and no
  independent review.
- `transition-summary.json`.

## 3. Post-success commands (in order; each step after 1 needs its stated approval)

1. **Status, authorized now** (operational):
   `mkdir evidence && ssh -o BatchMode=yes <BATCH_HOST> 'bash -s' < terminal_status.sh > evidence/terminal-status.txt`
   - **If `returncode != 0`:** stop. Open a failure packet, as for v4-v6. No retry, no B8.
2. **Capture A, needs an exact approval** binding `capture-request-a.json` 088248dc and tool f19d1066:
   `python3 -B ../r1-prerequisite-evidence-20261021/capture_metadata.py capture-request-a.json evidence/capture-a.json.gz`
3. `python3 -B transition.py request-b --capture-a evidence/capture-a.json.gz > capture-request-b.json`
   - This refuses unless A is exactly a successful preparation.
4. **Capture B, same approval scope:**
   `python3 -B ../r1-prerequisite-evidence-20261021/capture_metadata.py capture-request-b.json evidence/capture-b.json.gz`
5. `python3 -B transition.py fill --capture-a evidence/capture-a.json.gz --capture-b evidence/capture-b.json.gz --out filled-v1`
6. **Independent assessor** (not 065d2f16, not f1d352ff): the sources and fits documents against the actual seal,
   using `source-fit-bridge.json`.
7. **Independent R1 authorization receipt:** the DRAFT completed only by the reviewer, with every precondition
   satisfied by actual evidence.
8. **Exact final execution approval:** `execution-spec-FILLED.json` plus the receipt sha, staging of the four
   CODEPASS evaluation files, and one launch.
9. `evaluate`'s own fresh full reverification, before any label marker. None of it is claimed here.

## Tests

| Suite | Result |
|---|---|
| `test_transition.py` | 22 passed |
| `ruff check` | pass |

The tests cover:
- the bridge: deterministic, the exact chains and anchors, all success refs null, live science-change refusal,
  refusal of changed local evidence;
- the requests: exactly six paths within the tool's limits, the tool sha equal to the real file; request B is the
  one bound seal;
- `fill` positive: filled copies; the templates stay byte-identical, including 7f67f584; nothing claimed;
- `fill` refusals (12): returncode 1, a string or bool returncode, not passed, labels opened, R1 authorized, two
  passes, another kind, a spec sha mismatch, a ledger path mismatch, a seal path mismatch, a missing record. A
  wrong seal, an inconsistent capture, a reused output and a non-CODEPASS evaluation package also refuse;
- the frozen bridge and request files regenerate byte-exactly.

**Mutation controls:**

| Mutation | Targeted tests |
|---|---|
| returncode 0 not required | 1 failed |
| complete predicates removed | 5 failed |
| captured spec/ledger binding removed | 2 failed |
| seal destination unchecked | 1 failed |
| capture A set unchecked | 1 failed |
| bound seal unchecked | 1 failed |
| codepass package unchecked | 1 failed |
| draft science rule removed | 1 failed |
| filled authorization may claim | 1 failed |

All 9 guard removals make a targeted test fail.
