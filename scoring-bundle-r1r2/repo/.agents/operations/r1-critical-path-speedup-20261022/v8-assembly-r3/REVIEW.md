# Review packet: v8 assembly r3 (L1 fix, identity read, transition leaves, N1). LOCAL; nothing issued, captured or run

- Author: claude-opus-5-5, session <SESSION_ID>.
- Responds to `review/o1-s0b-assembly-r2-frozen-review/assembly-r2-review.txt` (c1e62f75):
  - A3 CHANGES_REQUIRED L1;
  - the N1 note;
  - the transition-leaf rule.
- **Driver:** O1 33011eed passed CODEPASS (`o1-review.txt` d5555a8b, pins 7e1a7d1f). Per root routing, O1 is the adopted
  driver and `v8-1-assembly-candidate/` (pins aa2273d2) is the assembly. D-1 (bb7f7e00, pins 2420b593) is recorded as
  the fallback.
- **Untouched:** r2 (A1/A2 CODEPASS; `check_u2.py` is reused as it is) and every frozen packet.
- **Superseded:** `a3-predecessor-capture/` (ff624ad9) is superseded by `propose_a3.py` here.

## L1: `failed_v7.py` (diff vs r2: launch.err and gate record by identity)

**Request and identity paths:**
- `request()` is now exactly the **six** JSON control records. The gate record is never in the f19 request.
- `identity_paths(census)` = `<V7_EVAL>/launch.err`, plus `<V7_EVAL>/results.resources-before-label.json` only if K1
  listed it.

**`build_evidence(census, capture, identities)`:**
- `identities` must be exactly those paths.
- Each item is `{size, sha256}` (identity form) or `{size, sha256, bytes_base64}` (content form, only with its own
  approved content read; the bytes are verified against the sha).
- Each size must equal the K1 census size.
- The gate record is bound as `{present, size, sha256}`. Its content is not read, so its `labels_opened` is not
  asserted; the marker absence carries "no labels opened".

**`check_failed_v7`:**
- JSON records are compared byte for byte.
- An identity item is compared by size and sha256 of the file on the host. A content item is compared byte for byte.
- The gate record's presence, size and sha are checked.
- No `r1-unblinding*` (glob), no results, no `complete.json`.

## `identity_read.py`: the ONE bounded identity read (needs its own exact approval, scope `r1-a3-identity-read-v1`)

**Preconditions:**
- Input is the approved K1 output only (census tool e4696da7, approval bdf45c60).
- The paths are `failed_v7.identity_paths(census)`, which refuses a v7 success, a live run, a marker or a publication.
- They must be a subset of the two allowed paths.

**Remote side:**
- One ssh, the K1 interpreter, `-I -S -B`, guarded to <USER>@<BATCH_HOST> outside Slurm.
- Each path is asserted against the allowed list, then opened with `O_NOFOLLOW`. It must be a regular file ≤ 1 GiB.
- The file is streamed into sha256 only; `fstat` before and after must agree.
- It prints `{path: {size, sha256}}`. No content is transferred and nothing is written.

**Locally:**
- `identity-records/intent.json` and `result.json` are written exclusively, then `evidence/identities.json`.
- Any failure is final.

**The approval must bind:** tool sha, `failed_v7.py` sha, the allowed paths, the cap, one attempt, retry false, and
content/label/prediction/host-write all false.

## `propose_a3.py` (r3 request derivation)

- Same as the r1 proposal, but bound to the r3 `failed_v7`.
- The request is exactly the six records.
- The plan names the identity paths and the identity-read command.

**Sequence after v7 is terminal:**
1. K1 (once, existing approval).
2. `propose_a3.py request`.
3. The f19 capture (needs the A3 capture approval).
4. `identity_read.py read` (needs its approval).
5. `failed_v7.py build`.

## `check_transition_v8.py`: the separate v7 → v8 step on the FINAL bound draft

- Changed leaves vs v7 draft 44acc870 must be **exactly these 10**, each pinned:
  1. driver == **33011eed** (one constant);
  2. the three scorer paths == pure v7→v8 root relocation, with their shas unchanged;
  3. contract == `control-v1/resource-contract.json` + d5798bee (the frozen O1-bound contract);
  4. review == `control-v1/resource-review.json` + the reviewer-issued sha;
  5. calibration approval == `control-v1/calibration-approval.json` + the reviewer re-issue.
- A null review or calibration sha refuses. Any other changed leaf refuses (decision, analysis, numbers, an extra field).
- The historical v4..v7 OPERATIONAL check in `transition.py` is unchanged. This step is added beside it when
  `transition.py` is re-pinned.

## N1: `repin_inventory.py` → `repin-inventory.json`

- Bound to the O1 assembly: the driver goes to 33011eed, and the known-now values come from `v8-1-assembly-candidate`.
- v8 work is now **14 explicit subdirectories**, including the preserved, never-used `driver-v8b/`. A new tool anywhere
  else under `r1-critical-path-speedup-20261022/` is reported as unaccounted (tested).
- Coverage now: 105 tool files, 0 unaccounted, 0 stale.
- Regenerate and re-freeze at bind time, as required.

## Verification

- `test_r3.py`: **53 passed**.
- `mutation_controls.py` → `evidence/mutation-controls.json`: the unmutated control passes 53. **9/9 mutants are
  detected:**

| Area | Mutants |
|---|---|
| L1 | identity size not checked against K1; identity path set not enforced; host identity sha not compared |
| identity read | remote allowed-path assert dropped; remote follows symlinks; second attempt allowed |
| transition | changed-leaf set not enforced; adopted driver not pinned |
| N1 | wide v8_work prefix restored |

- ruff: clean.

## Order constraint carried from the review (cross-track; routing, not code)

1. v7 terminal, then K1.
2. The newperiod placement and synthetic run happen once, under their existing approval. Local v8 work runs in
   parallel.
3. The v8 preparation launch approval requires either the newperiod terminal record or a recorded root deferral.
