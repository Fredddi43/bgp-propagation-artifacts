# N-stable stage32 transport v3 (opus-science)

Successor of transport v2 (newperiod-stable-stage32-transport-opus-science-v2-20261026, unchanged). It addresses
opus-review2 REVIEWER-opus-review2-STABLE-RUNNER-V3-PASS-TRANSPORT-V2-CHANGES.json. Runner v3 PASSED there and is not
touched here.

- S1 (blocking): `build_transport.py:27` `CPUS,MEMORY_MIB,WALL_SECONDS=2,16384,7200` -> `2,32768,14400`. Runner
  RLIMIT_AS follows (memory_mib - 512 MiB = 31.5 GiB). The submit argv becomes `--mem=32768M --time=240`.
- S2 (text): the root template `custody_log_preflight` now names the H3 budget v3 campaign gate (stable_source_stage
  writer, adoption issued before staging, growth since the H3 baseline + attested remaining reservations <= 160 MiB,
  size <= 2 GiB - 64 MiB). It is only template text. The gate itself belongs to the B3 operator (opus-h3, see
  AUTHOR-opus-science-STABLE-STAGE32-OPERATOR-V1-HANDOVER.json).
- test_transport.py: only the two resource asserts change (`(2,32768,14400)`, `--mem=32768M`, `--time=240`).
- draft-v40/: the build_transport.py output for the same plan-v40 + phase v40 as v2. A semantic diff against v2's
  draft-v40 shows only resources.memory_mib/wall_seconds, the submit argv --mem/--time, and the shas that cascade
  from them (resource binding, admission, plan, review, approval, scripts, tar). kernel-plan.json, control/stage.sh
  and all 98 package files are byte-identical.
- S3: the append COUNT bound is AUTHOR-opus-science-STABLE-APPEND-BOUND.json (114,104 lines, max 739 B/line).
- S4: the draft binds v40 (floor + 20 GiB), which stays conservative under v41. The B3 operator resolves newer
  floors through phase_compat.

Run: `cd <repo> && PYTHONPATH=src .venv/bin/python -B -m pytest -q -p no:cacheprovider <dir>/test_transport.py`
(results in tests.txt).
