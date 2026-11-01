# G1 controls binding v2 (Sonnet author; local reads + the v1 read-only lstat record; nothing executed)

Supersedes `newperiod-g1-controls-binding-sonnet-v1-20261027` (left unchanged) after sol-g1 `controls-draft-review.json` e97b64a2.

## Changes against the review
1. **Protocol name:** `controls.json` now carries `protocol: newperiod-complete400-v1` (accepted by sol-g1, `scientific-protocol-binding-acceptance.json` 08eab9b6, pinned in `controls-report.json`). New controls pin = sha256 of the regenerated `controls.json` (see SHA256SUMS). The other four refs are unchanged from v1 (cluster 0444 copies, lstat sizes equal to the local copies, shas unchanged).
2. **Mislabeled GBDT review removed:** `newperiod-gbdt-client-r3-20261024/independent-root-review.json` (kind `independent_gbdt_truthful_opus_policy_delta_review`, PASS_CODE_ONLY, scientific execution not authorized) is no longer cited anywhere (test asserts it is absent from `acceptance`). Recipe-freeze evidence is now only the freeze receipt (passed, frozen_before_r1, retuning_reserve_closed) plus the remote `review.json` 7e354b7f, which is lstat-only and NOT inspected; this packet claims no independent freeze verdict.
3. **R1 final publication/readback records FOUND** (all under `operations/r1-v11-posteval-20261024/`, pinned path+sha256 in `controls-report.json.r1_publication_records`, consistency-checked by `build_controls.py`):
   - typed JSON publication approval `opus-r1-receipt-publication-approval-v1.json` 5025edf3 (passed; receipt and local receipt both ba2a1e2e; attempt_limit 1; no retry; reviewer claude-opus-5-5 /root/opus_review);
   - typed JSON one-shot records `release-actual-v1/publication-v1/{intent 89e91d18, result ae2ee719 (rc 0, stderr empty), published 46c7961e (readback_passed true, receipt ba2a1e2e, approval 5025edf3 co-published)}`;
   - prose: final exact receipt review 55ae40e5 (byte-identical reproduction) and the independent actual assessment of the publication and readback e1440bee (stage.sh regenerated equal; two sha256sum OK lines on the cluster);
   - reviewer pointer 5da6aab2, numerical assessments d04808e3 and e40d2fca, inputs record 5cb73adb.
   Precisely: the typed one-shot publication and readback records exist; the assessments of them are prose written by an Opus reviewer; **no typed `G1_R1_RELEASE_ACTUAL_ACCEPTANCE_V1` by a distinct reviewer exists** (sol-g1 says NOT_ISSUED_FROM_SCOPED_RECORDS). The numerical assessments alone do not prove final publication, but the records above do record it (readback was the `sha256sum` check inside the one-shot stage script, not a separate later read).

## Minimal acceptance packet (proposal; nothing issued)
sol-g1 (distinct from the Opus reviewer and from this author) reads exactly the 12 pinned records, no remote action, and emits `G1_R1_RELEASE_ACTUAL_ACCEPTANCE_V1` per its own requirements file: exact release path+sha, verified kind/three true flags/retry false, pins of the numerical assessments and the development-freeze/exposure/authorization refs inside the release, and the publication receipt + readback result above; `execution_authorized=false`. If sol-g1 wants a fresh remote confirmation, add one separately scoped stat+sha exchange (extraction-style `run_once.py`, 1 file, 6220 B); not required by the records and not prepared here.

## Tests
`test_controls.py` (4): pins, flags, protocol string, acceptance contents, 12 publication records with shas, lstat refusals, files-on-disk current, feeds `g1_draft_prep.assemble_plan` (None protocol refused).

Runner recommendation for ROOT remains r3-retained d6d13ca8 (sol-g1: conditional PASS pending ROOT adopting the parsed G1 route); diff vs r2 in the draft-prep REVIEW.md.
