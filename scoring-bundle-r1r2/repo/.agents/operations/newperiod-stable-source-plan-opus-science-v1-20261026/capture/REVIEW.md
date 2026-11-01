# N-stable source-plan capture once v1 (opus-science, author)

Purpose: the existing stable stage (`newperiod-stable-inputs-20261023/stage.py`, 36 tests, never
run) needs a `newperiod_stable_source_plan_v1` with a sized ref for every source role of every
successful event. Most refs are already local (v4 finite inventory: all memberships, custodian
files, tables, manifests, coverage; dev receipt a7ed6ae8: B/C/D/E summary, B/D anomalous, C
restored anomalous). This once captures only what is not local, using the accepted witness's
anchors and segment logic:

- A 2023-24 (1998): summary/anomalous source refs from the R-stable input receipt 2d0ee46a
  (disposition must be inherited_unchanged, as the witness found).
- B boundary (2) + C (1259): `pre_repair_anomalous` via the exact R-stable chains
  (`scripts/stage_stable_peer_inputs.py:120-145`): boundary receipt original_inputs.anomalous;
  metadata receipt -> reconstruction receipt -> source. Each receipt hash-bound by its parent.
- E (1010): anomalous = restoration receipt `source` (canonical crossday rows; decision S-E).
- F (1000): summary/anomalous = omitted-part receipt `canonical_sources` (decision S-F).
- Feature files: primary data-root graphs/rpki file links, the `inventory` directory link
  expanded (metadata probe: 3 symlinked files, 282 B of links), and the written ROVista series.
- Coverage: the 1,311 query `coverage.json` leaves (the primary receipt never hashed them; the v4
  inventory has sha null). Path = parent of the primary data summary + coverage.json (the accepted
  v4 audit's derivation). Hashed only, never decoded, <=64 KiB each. These are protected-period
  files; the stable v4 audit read the same leaves with 0 custody appends.

Refs are {realpath, sha256 from the binding receipt, size_bytes from os.stat}. No parquet or
summary content is opened; only inventory (<=64) and coverage (1311) files are hashed. The stage re-verifies every
sha on read, so a wrong receipt hash fails the stage, not silently. No remote writes, no Slurm,
no custody appends. Output: one JSON line, est. 2-4 MB (dev-period event IDs/paths only; custodian
refs come from the local v4 inventory, not from this capture). stdout cap 32 MiB.

Operator: the accepted witness operator with kind ROOT_ONCE_STABLE_SOURCE_PLAN_CAPTURE_V1,
packet tokens STABLE-SOURCE-PLAN, stdout cap 32 MiB; same guards (pins, independent review
pinning request/worker/operator, control rescan, exclusive actual dir, one transport, no retry).
Request = witness request with the same anchors (pins unchanged), new kind/reads/stdout cap.

Tests: test_worker.py 12/12 (incl. coverage) (A/C/E/F/feature refs, B/D nothing remote, canonical sized refs,
broken repair chain and anchor hash refuse); test_operator.py 8/8 (witness operator tests).
Not covered synthetically: the 2 B boundary events (code mirrors R-stable lines 127-138).

Next (local, no authority): build the full plan from capture + local refs and cross-check every
segment against the accepted witness commitments before any stage.
