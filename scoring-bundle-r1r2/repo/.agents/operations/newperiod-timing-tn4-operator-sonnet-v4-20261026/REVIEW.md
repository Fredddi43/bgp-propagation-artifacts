# T-N4 timing operator v4: pin-only rebind of v3 (sonnet, session <SESSION_ID>)

`../newperiod-timing-tn4-operator-sonnet-v3-20261026` is untouched; its REVIEW.md (finding map for TN4OP-V2-REMOTE-LIMITS / TN4OP-V2-DECODE-ADMISSION) applies unchanged. v4 rebinds to `../newperiod-timing-tn4-sonnet-v5-20261026`: `wave_contract.py` 41bc3fc6 -> 70f48268 and `release_once_tn4.py` ac20b5b5 -> cd7cb5c9 (both verified with sha256sum against the v5 files); controller/runner/file_limits/custody_scope/transport shas are identical in v5. No logic changed. Tests: 73 pass (`tests.txt`, `verification.json`); the later subgroup stays blocked.

## Diff vs v3 (`diff -r`, only pin/path lines)
```
diff -r ../newperiod-timing-tn4-operator-sonnet-v3-20261026/common.py ./common.py
< TN4=OPS/'newperiod-timing-tn4-sonnet-v3-20261026';PKG=TN4/'package'
> TN4=OPS/'newperiod-timing-tn4-sonnet-v5-20261026';PKG=TN4/'package'
<  'wave_contract':(PKG/'wave_contract.py','41bc3fc6d7886b1d49fa50460348258117e5d3d2b8e7759bb74b869660781fe4'),
>  'wave_contract':(PKG/'wave_contract.py','70f482682cdeeecb8ad6aed59bbd94cf190b25d375420ac8683150fc6019ac11'),
<  'release_once_tn4':(TN4/'release_once_tn4.py','ac20b5b592096d51a0097be04df9ae87d07477717256d0cf7d9eff2020ca6400'),
>  'release_once_tn4':(TN4/'release_once_tn4.py','cd7cb5c95b63890215bfebc18c199e24e62510d083a754582df665689f2e3aee'),
diff -r ../newperiod-timing-tn4-operator-sonnet-v3-20261026/driver_gate_real.py ./driver_gate_real.py
< HERE=Path(__file__).resolve().parent;OPS=HERE.parent;BOUND=OPS/'newperiod-timing-tn4-sonnet-v3-20261026/bound-d10__d5'
> HERE=Path(__file__).resolve().parent;OPS=HERE.parent;BOUND=OPS/'newperiod-timing-tn4-sonnet-v5-20261026/bound-d10__d5'
< # T-N4 timing construction operator v3 + single-horizon gate (sonnet, session <SESSION_ID>)
> # T-N4 timing operator v4: pin-only rebind of v3 (sonnet, session <SESSION_ID>)
< Supersedes `../newperiod-timing-tn4-operator-sonnet-v2-20261026` (untouched). Fixes exactly the two blocking findings of sol-final CHANGES `REVIEWER-sol-final-TIMING-TN4-OPERATOR-V2-CHANGES` (prior-round close-outs are unchanged
> `../newperiod-timing-tn4-operator-sonnet-v3-20261026` is untouched; its REVIEW.md (finding map for TN4OP-V2-REMOTE-LIMITS / TN4OP-V2-DECODE-ADMISSION) applies unchanged. v4 rebinds to `../newperiod-timing-tn4-sonnet-v5-20261026`
< ## Findings -> change -> file:line -> test
< | finding | change | where | tests (`test_v3.py`) |
< |---|---|---|---|
< | TN4OP-V2-REMOTE-LIMITS (blocking) | Every remote python program has a declared row in `REMOTE_PROGRAMS` (RLIMIT_AS, CPU, FSIZE, NOFILE, alarm, local wall, stdout/stderr caps; alarm < local wall, CPU <= alarm; programs inside t
< | same (controller stage/claim were bare `python3 -I -S -B -c`) | The adapter forwards ONLY the two reviewed controller programs (text taken from the sha-pinned controller), re-wrapped with the declared limits/alarm; the control
< | same (helpers: snapshot/preflight/permission/capture had rlimits but no alarm) | All four helpers go through `remote_call(...)` with their declared row (alarm 90/200/90/840 s vs local wall 120/240/120/960 s). The gate is wrapp
< | same (prove limits) | Local synthetic subprocesses: wrapper kills a sleeper by SIGALRM without any local kill, enforces CPU (soft=hard => SIGKILL), AS (MemoryError), FSIZE (EFBIG), NOFILE (EMFILE); the real preflight/permissio
< | same (local side bounded) | `call()` in both operators refuses input >4 MiB or a wall outside (0, 3720] and always passes `out_cap`=1 MiB and `err_cap`=4096 to the bounded transport; adoption must carry `remote_programs` equal
< | TN4OP-V2-DECODE-ADMISSION (blocking) | Exact on-disk sizes (lstat; regular, nlink 1, canonical) of plan+done, then of the six remaining documents, are admitted BEFORE any of them is read/decoded and before the custody records:
< | same (decoded memory model, not encoded bytes) | allowance = import baseline 3 GiB + serialization 256 MiB + hash buffer 16 MiB + sum(size x (raw reads + decodes x 24 expansion x 3 retained copies)); the inventory counts 2 raw
< | same (bind to actual host/AS admission; mismatch) | The gate request now carries `memory={address_space_bytes, model_sha256}`; the gate refuses a different model/size and, in a real run, an RLIMIT_AS different from the declare
< 
< Regression-first: `tests-regression-first.txt` = `test_v3.py` run against the unchanged v2 sources, 18 failed; all pass here (`tests.txt`, `verification.json`). Existing v2/operator tests were adapted only where the contract cha
< 
< ## Limits of this packet (nothing here is claimed beyond the code)
< * The decoded-memory model is a conservative analytic bound (expansion 24x, 3 retained copies, 3 GiB import baseline), not a measurement of the actual staged validators on the real documents; it is an explicit reviewed constant 
< * The remote alarms/limits for stage (150 s), claim (45 s) and snapshot (200 s) were chosen below the existing controller/local walls; the snapshot census duration on the real tree is unmeasured (it was already bounded by the 24
< * Still open (not fixable here, unchanged from v2): the later-subgroup campaign bridge, actual all-host writer inventory, 512 MiB non-build bound evidence, pinned real Slurm parser fixtures, real-tree capture runtime admission.
> ## Diff vs v3 (`diff -r`, only pin/path lines)
> ```
< 5a8af8fe3d0c40e5f9122cf5793de8cd1c89118d1fdda7c8bfd8fb12283cf9a6  common.py
< 674d2c3dfee29b7f15fd27b5ecfbebdeb08f16812bc8579e207f7f009d605987  driver_gate_real.py
> 4969a407a880a960d7aa11567669126a93d6d07e05ab9ccabad145dafac46aaf  common.py
> 1764a2dd9f8cc6cbf8ec7665f84c1f7a3179a86e8b0aed32d26f5df0efe32dba  driver_gate_real.py
< c1e298af0e95520a60eabf00b5c61b5196863f9ec5c5dac1c733f45591b70961  test_operator.py
< b12bb1405977c99b1b2f7935618d135fa9ce03482962de6c5846f363175d9928  test_v2.py
< e2d7c434afcc85c20f0b872f839e6dea1a8f6312fbf8a68f2012c4f28fa684ec  test_v3.py
> bd0f60ef9506dbcc45d1c13c498ceae169be750d58cd49de50da3dd14b4a0441  test_operator.py
> 168d509d12d871aabf62dbfac2f6308c1baff6334ee619784ecfafd7f1b25b08  test_v2.py
> c03c3dba310633864f47a081f9dc5aeb3a854a25294bb85e9865cb49489313dd  test_v3.py
diff -r ../newperiod-timing-tn4-operator-sonnet-v3-20261026/test_operator.py ./test_operator.py
< HERE=Path(__file__).resolve().parent;OPS=HERE.parent;TN4=OPS/'newperiod-timing-tn4-sonnet-v3-20261026'
> HERE=Path(__file__).resolve().parent;OPS=HERE.parent;TN4=OPS/'newperiod-timing-tn4-sonnet-v5-20261026'
< 73 passed in 27.65s
> 73 passed in 26.97s
diff -r ../newperiod-timing-tn4-operator-sonnet-v3-20261026/test_v2.py ./test_v2.py
<     assert C.TN4.name=='newperiod-timing-tn4-sonnet-v3-20261026' and C.PINS['wave_contract'][1].startswith('41bc3fc6') and C.PINS['release_once_tn4'][1].startswith('ac20b5b5')
>     assert C.TN4.name=='newperiod-timing-tn4-sonnet-v5-20261026' and C.PINS['wave_contract'][1].startswith("70f48268") and C.PINS['release_once_tn4'][1].startswith("cd7cb5c9")
<     pend=json.loads((OPS/'newperiod-timing-tn4-sonnet-v3-20261026/subgroup-d300-d900.PENDING.json').read_text());assert pend
>     pend=json.loads((OPS/'newperiod-timing-tn4-sonnet-v5-20261026/subgroup-d300-d900.PENDING.json').read_text());assert pend
diff -r ../newperiod-timing-tn4-operator-sonnet-v3-20261026/test_v3.py ./test_v3.py
<     assert C.TN4.name=='newperiod-timing-tn4-sonnet-v3-20261026' and C.PINS['wave_contract'][1].startswith('41bc3fc6') and C.PINS['release_once_tn4'][1].startswith('ac20b5b5')
>     assert C.TN4.name=='newperiod-timing-tn4-sonnet-v5-20261026' and C.PINS['wave_contract'][1].startswith("70f48268") and C.PINS['release_once_tn4'][1].startswith("cd7cb5c9")
<     assert (HERE/'driver_gate_real.py').read_text().count('sonnet-v3-20261026')==1
>     assert (HERE/'driver_gate_real.py').read_text().count('sonnet-v5-20261026')==1
<     "common.py": "5a8af8fe3d0c40e5f9122cf5793de8cd1c89118d1fdda7c8bfd8fb12283cf9a6",
<     "driver_gate_real.py": "674d2c3dfee29b7f15fd27b5ecfbebdeb08f16812bc8579e207f7f009d605987",
>     "common.py": "4969a407a880a960d7aa11567669126a93d6d07e05ab9ccabad145dafac46aaf",
>     "driver_gate_real.py": "1764a2dd9f8cc6cbf8ec7665f84c1f7a3179a86e8b0aed32d26f5df0efe32dba",
<     "test_operator.py": "c1e298af0e95520a60eabf00b5c61b5196863f9ec5c5dac1c733f45591b70961",
<     "test_v2.py": "b12bb1405977c99b1b2f7935618d135fa9ce03482962de6c5846f363175d9928",
<     "test_v3.py": "e2d7c434afcc85c20f0b872f839e6dea1a8f6312fbf8a68f2012c4f28fa684ec",
>     "test_operator.py": "bd0f60ef9506dbcc45d1c13c498ceae169be750d58cd49de50da3dd14b4a0441",
>     "test_v2.py": "168d509d12d871aabf62dbfac2f6308c1baff6334ee619784ecfafd7f1b25b08",
>     "test_v3.py": "c03c3dba310633864f47a081f9dc5aeb3a854a25294bb85e9865cb49489313dd",
<   "packet": "newperiod-timing-tn4-operator-sonnet-v3-20261026",
>   "packet": "newperiod-timing-tn4-operator-sonnet-v4-20261026",
```
