# Origin S3 root fill kit v4 (author: Sonnet; local only, not authority)

Copy of `newperiod-origin-s3-root-fill-v3-20261026` (fill_root.py, measure_allocation.py, test_fill_root.py); no filled-*/assemble-* dirs, no v1-v3-bound reviews. Usage unchanged from the v1-v3 REVIEW.md with `<kit>` = this dir.

## Delta
- `fill_root.py:6` PKT -> `newperiod-origin-s3-once-v4-20261026`. Nothing else in fill_root.py/measure_allocation.py.
- `test_fill_root.py`: PKT-name assertion (line 60) and one comment (line 56) now say v4.
- Tests: `cd /tmp && PYTHONPATH=<repo>/src python3 -B -m pytest -q -p no:cacheprovider <kit>/test_fill_root.py` -> 10 passed. Allocation evidence still reused by reference from the v1 kit (packet-independent).

## Codex sol-g1 must check
The one-line PKT change, then a fresh adoption (probe + fill against the v4 request) and fresh execution review; v3 ones are bound to v3 hashes.
