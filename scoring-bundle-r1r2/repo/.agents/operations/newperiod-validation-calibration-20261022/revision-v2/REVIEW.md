# Review packet: N-core validation calibration producer, revision-v2 (non-blocking findings N1-N5)

- Author: claude-opus-5-5, session <SESSION_ID> (`/root/opus_implementation`).
- Base: the CODEPASS candidate one directory up, unchanged and committed at 18062ee:
  - pins d0fde45f; review a1a50d94, verdict 1aa09dc9 (reviewer 4ba6111c), no findings
  - the root's C1/D1 adoption, `coordination/root-policy-adoption.json` a9f6ad21
- Policy addendum: the reviewed and adopted `../POLICY-ADDENDUM.md` (ecccd698) is used as is (`ADDENDUM =
  HERE.parent / ...`). This revision changes no policy, no science and no reused source.

**Not done and not authorized:** no real ledger, fit, label or remote read, and no execution, freeze or seal.
P9 (the failed-fit policy) stays unresolved and unchanged: any failed or missing fit refuses. Automated wakes are
not scientific approval.

## Changes from the CODEPASS `calibrate.py`

| Finding | Change |
|---|---|
| depth | `REPO = HERE.parents[3]` (one directory deeper); `ADDENDUM` points at the adopted file above |
| N5 | `checked_imports()` at stage `inputs`: every loaded `bgbench` module must be a file under `REPO/src/bgbench`, and the two reused scripts must be `REPO/scripts/<name>.py`. An editable install pointing at another checkout therefore refuses, so the hashed closure is the code that runs. |
| N2 | `checked_destination()` at stage `fits`, after the ledger check and before the output exists. It refuses an output equal to or inside any `run['out']`, the ledger's directory or the snapshot, compared as resolved paths. A symlinked parent already refuses earlier, at `inputs` ("fresh canonical directory"). |
| N1/X4 | The completion check is split. A completion naming another run or ledger now refuses as "Completion does not name this run and ledger", not under the slice-timing message. |
| N3 | `verify_output(out, expected_publication_sha256)` checks a finished output for the freeze. The directory must hold exactly `intent.json`, `rules/`, `publication.json` and `completed.json`. `completed.json` must name this publication. Every rule file must match its entry, the count must be 40, and the intent must name the publication's approval. A publication without `completed.json`, such as a crash in between, refuses. The producer itself is unchanged in what it writes. |

Everything else is byte-identical in behaviour: the approval rules, the slice anchor, the R1 separation, the
`core_fit` re-authorization, H2/H3/H4 reuse, the intent-before-tensors order, all results before the first write,
and exclusive files.

**`EXECUTION-EVIDENCE-TEMPLATE.json`** (N3, N5 and contract E1-E5). This is the record the execution and freeze must
fill.
- Already filled: the adopted addendum and root adoption, the frozen slice rule 0291d789, the frozen-2025
  publication 66c2ce8c, and the freeze requirements (`verify_output`; 40 fits with none dropped; A1 separation).
- Left null: every actual identity (producer revision pins, ledger, approval, out, outputs, host
  `bgbench_origin`/closure check).
- Status: E1-E5 are all pending, P9 is unresolved, and every authorization is false.

## Tests

| Suite | Result |
|---|---|
| `revision-v2/test_calibrate.py` | 64 passed |
| original CODEPASS suite (unchanged) | 45 passed |
| `ruff check` | pass |

The 45 original tests run unchanged. The 19 new ones:
- **N2 (4):** an output inside a fit output, the ledger directory, the snapshot, or the completions directory
  refuses at `fits` and creates nothing. A symlinked alias of a fit output refuses at `inputs`. Control: a
  campaign sibling that only shares a name prefix produces 40 rules.
- **N1/X3:** a ledger naming arm N-h1 refuses.
- **N1/X4:** a completion naming another ledger refuses with its own reason. The reviewed driver's `check()` alone
  accepts it, which shows this guard is the only one.
- **N4:** a decision-preserving rewrite of one fit's stored rows refuses at `rules` through the unchanged H2
  ("Recomputed global threshold differs").
  - At the fit's threshold every decision stays the same, so H3's Jaccard binding still holds (asserted).
  - True additions move to 1.0 and false additions down to the threshold. A higher threshold now scores at least as
    well, and ties go to the higher one, so the recomputed global threshold differs (asserted).
- **N5:** a `bgbench` module from another checkout refuses at `inputs`. The real imports resolve to this REPO.
- **N3 (6):** `verify_output` on a finished output returns the four identities. It refuses each of: a crash before
  `completed.json`, a `completed.json` naming another publication, an extra file, a changed rule file, a missing
  rule file.
- **Template:** all actual identities null; adoption, addendum, slice, frozen-2025 and E1-E5 as stated.
- **A1 regression** (inference review N1) against the unchanged CODEPASS consumer `revision-next/predict.py`
  5e36a2f6: a frozen-2025 publication naming a copy of the N ledger (another path, the same sha) is refused
  ("share a fit ledger"). Control: a distinct ledger is accepted beside this producer's real publication.

**Mutation controls** (`mutation_controls.py`; the 12 original cases plus 6 new):

| Mutation | Targeted tests |
|---|---|
| approval binding removed | 9 failed, 5 passed |
| approval independence removed | 5 failed, 9 passed |
| frozen slice anchor removed | 1 failed |
| R1 publication as input allowed | 1 failed |
| R1 output overlap allowed | 1 failed |
| slice-before-fits removed | 1 failed, 2 passed |
| complete 40-fit ledger check removed | 2 failed, 1 passed |
| driver check() skipped | 2 failed |
| release authorization equality removed | 1 failed |
| split check removed | 2 failed, 1 passed |
| receipt validation identity removed | 1 failed |
| H3 binding of stored predictions removed | 3 failed, 1 passed |
| N2 destination guard removed | 4 failed |
| N1/X3 ledger arm check removed | 1 failed |
| N1/X4 completion ledger binding removed | 1 failed |
| N5 import origin check removed | 1 failed |
| N3 completed.json binding removed | 1 failed, 5 passed |
| N3 rule file check removed | 1 failed, 5 passed |

All 18 guard removals make a targeted test fail.

## Remaining conditions before any real run (unchanged in substance)

1. Independent review of this revision (or the CODEPASS original is used as is; the v2 guards are additive).
2. The 40 real N-core fits exist and `check()` passes. They need the N development gates and the complete R1
   release; R1 v7 is still running. P9 decides only if a fit fails.
3. A real execution approval binding this producer, its closure, the adopted addendum, the real ledger, the slice
   rule 0291d789 and the output path.
4. On the execution host, the editable `bgbench` must be that host's `REPO/src`. `checked_imports` now refuses
   otherwise, and the evidence template records it.
5. The freeze fills the evidence template, runs `verify_output`, binds `completed.json`, and passes the E4 review.
