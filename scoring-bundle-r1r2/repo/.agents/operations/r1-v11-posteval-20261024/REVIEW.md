# R1 v11 post-evaluation rebinding and K1 census request

Local packet only. No host command was run, and nothing under results/, no label, prediction or score was read.

## What this is

The v10 post-evaluation packet, which independent review fb023c7b passed (`r1-v10-posteval-code-review.json`,
PASS_CODE_ONLY, 274 tests), mechanically rebound to the actual v11 evaluation that ended with returncode 0.
`build_v11.py` takes the 31 reviewed v10 files by hash and rewrites only these:

- the six v10 execution anchors become v11's: execution spec 2233750e, spec 134d74fb, ledger 5575ebb3,
  seal 1cad501a, R1 authorization dd54f44f, source manifest 0bdaf006. Each is re-hashed from the local file.
- the namespaces `r1-release-parallel-v10-20261023`, `r1-parallel-execution-v10-20261023` and
  `r1-posteval-classd-v10-20261023` gain their `-v11-20261024` successors. The class-(d) code destination is new.
- `census.py`: `SUPERVISOR_PID` goes from None to 788181, the actual v11 launch PID (launch-result 85e92767,
  waiter request 8921617e, terminal observation c4ac734a).
- every `AUTHOR_SESSIONS` gains this author, f4d75bb1, so it can never approve its own packet.
- the two pins.json files and the sha cascade that follows from the changed bytes, as in the v10 builder.

The source closure differs from v10 only in `src/bgbench/forecast_metric_bounds.py`, the reviewed mapping-key bound,
and the builder refuses any other source delta. `verify_r1.py` and `k2c/` are byte-identical. Every function in
adapter, run_adapter, run_verify, phases, stage_code, vrun, d2 and requests is AST-identical to v10. The census
REMOTE program, scope, manifests and caps are unchanged.

## K1 request

`k1-request.json` is the exact census request: the tool sha, the payload root
`.../r1-release-parallel-v11-20261024/control-v1`, PID 788181, one attempt, no retry and every read flag false. The
census still re-checks every terminal predicate on the host itself: the exit record, supervisor gone, no marker
process, complete.json, report.json, the registry complete marker present and the failure marker absent.

**Note for the reviewer:** the registry `occurrence-final-v1/custody/r1-access` is shared with earlier attempts. If an
earlier run left `r1-unblinding.failure.json`, the census judges "not terminal success" and K2 stops. That outcome is
reported, never worked around.

## Tests

282 pass in about 9 s with `.venv/bin/python -B -m pytest -q -p no:cacheprovider .agents/operations/r1-v11-posteval-20261024`.
That is the 267 inherited v10 tests run on the v11 bytes, plus the 15 in `test_v11.py`:
- exact reproduction;
- the six-anchor map against the actual files;
- AST preservation;
- every change inverts to the reviewed v10 bytes;
- the pins;
- the census against the actual launch;
- the reviewer 4ba6111c is accepted and author f4d75bb1 refused by all five approval checkers;
- the 66 fixed cells, unchanged from v10's selection;
- custody against the actual v11 driver;
- the K1 request refs.

`census.py check` (local) prints the v11 payload, tool sha 4229ec2c.

## Not authorized here

The census itself, which needs an independent census approval accepted by `census.py`. Also K2/K3 captures, class-(d)
transport, D0/D1/D2, the verifier job, any result read, retry or N admission. Each later step still needs its own exact
approval on actual sizes.
