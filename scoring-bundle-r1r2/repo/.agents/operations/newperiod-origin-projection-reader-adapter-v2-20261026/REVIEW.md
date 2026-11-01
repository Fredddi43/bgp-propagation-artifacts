# Origin projection reader adapter v2 (author: Sonnet; local only, not authority)

v1 (`newperiod-origin-projection-reader-adapter-astra-v1-20261026`, untouched) refused deterministically in the S3 v2 once (W20) at the
predecode screen: `need(model()<=DECODE_MODEL_LIMIT)` (v1 adapter.py:55, now adapter.py:60), model = 256MiB + 16*bytes + 512*nodes, limit 6GiB.

## Measurements (<BATCH_HOST>, read-only, counts only, nothing else printed)
Pinned python (`newperiod-gate-private-v1/venv/bin/python`, 3.12.8), `-I -B`, RLIMIT_AS 16GiB, file sha256 48a70fd0... and size 172310430 re-verified first.
- Exact structural node count (v1's own `structural_budget` logic, limit lifted): **7,904,963** nodes, max depth **8**, longest string token **389 B** (incl. quotes; caps: depth 64, string 1MiB).
- Screen model at that count: 7,072,743,392 B (6.59GiB) > 6GiB => v1 refusal explained. Capacity at 6GiB was 6,673,923 nodes.
- Actual `json.loads` of the full projection under 16GiB AS: success, 1.7 s decode (13.4 s scan, 28.2 s wall incl. sha), **peak RSS 756,736 KiB (/usr/bin/time -v; ru_maxrss 774,897,664 B)**, scan-only RSS 186.6 MB. Real decode is ~9x below the 512B/node model; the model is a screen, not a bound.
- Not measured: the S3 callback work after decode (boundary replay/write); that is covered by the 16GiB RLIMIT_AS, not by this screen.

## Change (adapter.py, only this; diff vs v1 = docstring line + limit block)
- adapter.py:14 `DECODE_MODEL_LIMIT=8<<30` (was 6<<30). Node capacity at exact input size: (8GiB-256MiB-16*172310430)//512 = **10,868,227** (1.37x the measured count; screen margin 1,517,191,200 B = 1.41GiB).
- adapter.py:15-17 new constants + module-level `assert DECODE_MODEL_LIMIT+IMPORT_TRANSIENT_ALLOWANCE<=PROCESS_AS_LIMIT` (8+2<=16GiB): the screen plus the 2GiB import allowance of the v1 proposal stays under the worker's RLIMIT_AS (worker.py W14 / entry.py E19 / request resource.per_process_AS_bytes = 16GiB), leaving >=6GiB for S3 work by the model, >15GiB by the measurement. All other limits (depth 64, string 1MiB, number 64B, base 256MiB, 512/node, 16x) unchanged.
- Safety is unchanged in kind: a larger-than-screen projection still refuses before decode; RLIMIT_AS remains the hard stop.

## Tests (`cd repo; PYTHONPATH=src .venv/bin/python -B -m pytest -q -p no:cacheprovider <dir>/test_adapter.py` -> 30 passed)
v1's 26 unchanged + 4 new: limits/process-bound assert; v1-refuses/v2-admits at measured count with >=1GiB margin; exact boundary formula on a small input (passes at k nodes, fails with limit-1);
**synthetic exact-size (172310430 B) input at exactly 10,868,227 nodes passes, 10,868,228 refuses**. `prove_large_reader.py` (synthetic, 16GiB AS): passes, 533 MB RSS. No remote action beyond the read-only measurement above.

## Sol-g1 must check
1. The single limit change (adapter.py diff vs v1) and the assert; formula arithmetic above.
2. Independently re-run the structural scan (node count 7,904,963) and decode peak RSS if desired; no content needs to be read.
3. That the v1 conditional-pass acceptance conditions transfer (family/builder pins aa7f633d/32c5b92a unchanged; PROJECTION pin unchanged).
adapter.py sha256 67ae8340ae699f255ee60eea71108f95f70225147b1be765c972c936515493bb (replaces v1 c53846dc...).
