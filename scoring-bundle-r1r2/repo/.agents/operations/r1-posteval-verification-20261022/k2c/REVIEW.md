# K2c: capture request for the spec-bound slice rules (separate; the approved K2b and pins f2b223ee are unchanged)

- Author: claude-opus-5-5, session <SESSION_ID>. Nothing has been run or read.
- **Why:** the verifier's C1-C4 slice family (`verifier/REVIEW.md`, request K2c) needs the frozen issue-time slice
  rule.
- **What and where:** spec 17f81575 (held, captured in A) binds `slice_rules` =
  `<FORECAST_ROOT>/occurrence-final-v1/slice-rules/issue-time-slice-rule-v6b.json`
  at sha256 `0291d789ed0e2f9df87a7aac55414ca4c755ba0eaae545c0643bcf2a29759004`.
- **Label-free:** the file holds one rule per horizon: `{variable, cut}`.
- **Tool:** the reviewed f19d1066, unchanged. It reads JSON under the forecasting root, asserts the given sha on the
  host, fails closed if the file is over 16 MiB, and writes its output exclusively.

## Exact steps (once each; no retry; stop and report on any refusal)

1. From `.agents/operations`:
   `<REPO>/.venv/bin/python -I -B r1-prerequisite-evidence-20261021/capture_metadata.py r1-posteval-verification-20261022/k2c/request-k2c.json r1-posteval-verification-20261022/k2c/evidence-capture-k2c.json.gz`
2. `…/.venv/bin/python -I -B r1-posteval-verification-20261022/k2c/extract_k2c.py --capture r1-posteval-verification-20261022/k2c/evidence-capture-k2c.json.gz --out r1-posteval-verification-20261022/evidence/released/slice-rules.json`
   - `extract_k2c.py` requires exactly the one path at the bound sha and the two horizon rules, and writes once.
   - Its output dir is the one K2b's extract creates. If K2c runs first, the request may name another fresh
     path instead.

K2c does not depend on the evaluation's results, but it is only useful together with K1/K2. Root routes it once,
after an exact independent approval.

## Tests

| Suite | Result |
|---|---|
| `test_k2c.py` | 5 passed |
| `ruff check` | pass |

- The request is f19 at its reviewed sha, and the path and sha equal what the held captured spec binds.
- Extraction writes once.
- Extraction refuses another sha, an extra file and a malformed rule, writing nothing.
