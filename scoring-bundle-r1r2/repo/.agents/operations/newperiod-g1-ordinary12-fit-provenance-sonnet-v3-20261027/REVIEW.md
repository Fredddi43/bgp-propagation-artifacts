# G1 M2 v3 (author: sonnet; nothing launched, no remote action). Answers sol-g1 CHANGES 21678151 on v2.
Supersedes v2 (unchanged). R1 release pin, acceptance e66d7391, 12-arm roster, inert parsing, allowlist hook, durable logging unchanged.

## Findings -> fixes (regression-first)
`test_regression_v3.py` was written first and run against the v2 sources: 15 of 16 failed (`regression-on-v2.txt`; the four missing-input cases
return rc 0 / passed true on v2 = the reproduced false PASS).
- **M2V2-1:** receipt `manifest_sha256` / `input_gate_sha256`, completion `cell`, started `package`/`cell`, authorization `release_sha256` are now strict lookups, as in
  runner.py:57-101 (a missing key raises KeyError -> rc 2, error output only). Tested both model branches x both keys (receipt and checkpoint receipt and authorization all lacking the field).
- **M2V2-2:** `validate_output` (used remotely and in local `landing`) requires: exact roster order, per-model exact check-name set (GRU 10 / GBDT 7), all checks bool, horizon == pinned role,
  row.passed == all(checks), overall == all(rows), release == pin, reads > 0 and == allowlist size (landing). `landing` additionally requires returncode == (0 if passed else 1). The fake-ssh test now uses full predicate sets.
- **Log:** `access_log` must be under <RESULTS_ROOT>/, basename exactly `g1-m2-ordinary12-fit-provenance-v3-once.log`, no `..`, not access-log*; the once creates it O_EXCL (never pre-create; never the shared access-log.jsonl).
  `make_request.py --access-log PATH` sets it and later reruns PRESERVE it (tested), so root's repin order is: run `make_request.py --access-log <root dir>/g1-m2-ordinary12-fit-provenance-v3-once.log`, then issue authority/reviews.
  `request.json` currently has `access_log: null` (ROOT_FILL; the canonical existing records dir is root's choice and I did not list the cluster).

## State
tests.txt: 41 pass (test_base.py plus test_regression_v3.py incl. log and request-preservation tests). Remote hook/venv/real pickles still untested; checkpoint-body admission and exact PASS still pending re-review. Authority template: `authority.FALSE-TEMPLATE.json` (kind ..._V3).
