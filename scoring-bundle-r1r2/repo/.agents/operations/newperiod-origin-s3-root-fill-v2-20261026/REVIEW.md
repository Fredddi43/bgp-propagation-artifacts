# Origin S3 root fill kit v2 (author: Sonnet; local only, not authority)

Copy of `newperiod-origin-s3-root-fill-sonnet-v1-20261026` (fill_root.py, measure_allocation.py, test_fill_root.py) without filled-1/, assemble-1/
and the v1-bound sol-g1 review. Usage is unchanged from v1 REVIEW.md, with `<kit>` = this dir.

## Delta
- `fill_root.py` PKT: now `newperiod-origin-s3-once-v2-20261026`.
- Bug fix in `assemble()`: it used undefined `packet` in the `--check` subprocess (NameError live). Signature is now
  `assemble(a,op,tpls,aref,check,packet=PKT)` and `main` passes `packet`.
- `test_fill_root.py`: allocation evidence reused BY REFERENCE from the v1 kit dir (not copied; same-export measurements are packet-independent);
  new `test_assemble_check_path_no_nameerror` runs assemble with check=True against the real v2 packet (unissued authority -> rc 1, no exception)
  and `test_assemble_uses_given_packet`.
- Tests: `cd /tmp && python3 -B -m pytest -q -p no:cacheprovider <kit>/test_fill_root.py` -> 10 passed.

## Codex sol-g1 must re-check
The delta only (the three edits above), plus a fresh adoption (probe + fill against v2 request) and a fresh execution review; the v1 adoption/review
(`execution-review.sol-g1.v44-adoption.json`) are bound to v1 hashes and do not carry over. Allocation-model acceptance still needs judging as in v1 REVIEW.md.
