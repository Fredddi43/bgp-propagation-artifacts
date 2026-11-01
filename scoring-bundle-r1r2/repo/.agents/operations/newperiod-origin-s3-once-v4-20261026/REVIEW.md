# Origin S3 exact once v4 (author: Sonnet; local only, not authority)

v3 (`newperiod-origin-s3-once-v3-20261026`, untouched, consumed/refused W21 at the screen's `ROWS`) -> v4 re-pins the science screen and boundary source to
`newperiod-origin-s3-workspace-v2-20261026/screen.py` (ROWS 262144) and `newperiod-origin-s3-boundary-source-v2-20261026/boundaries.py` (MAX_ROWS 262144). Reader stays adapter v2.

## Delta (the only thing to re-check)
- `prepare.py`: +2 constants `SCREEN=`/`BOUNDARIES=` (lines 7-8), +1 override line in `generate()` (line 17: `science['sources']['screen']=ref(SCREEN);science['sources']['boundaries']=ref(BOUNDARIES)`), comment reworded (line 15). The accepted science request file is NOT edited and is still pinned unchanged as `base.science_request`.
- Regenerated with the packet's own generators in the new dir: `python3 -I -B prepare.py` (writes ssh-contract.json from `ssh_contract.contract()`, then request.json, remote-command.txt) and `python3 -I -B bind.py --out templates`.
  request.json: new-dir paths; `base.science_screen`, `base.science_boundaries` (new shas); payload (remote-command.txt) carries the new screen/boundaries texts and the embedded request's two pins.
- Byte-identical to v3: entry.py, once_operator.py, bind.py, reason-codes.json, root-fill-instructions.txt, runtime-pins.json, runtime_guard.py, ssh_contract.py, supervisor.py, transport.py, worker.py, test_once.py.
- Not copied: `actual/`. Output namespace unchanged; W21 refused before any write, root must still see it ABSENT.
- Hashes: screen v2 7700570a2f0b..., boundaries v2 dbf2b8a1053c..., reader 67ae8340ae69..., protocol f0d3d2309093..., task protocol dfb9594206600d....
- `base.accepted_workspace` / `base.accepted_boundary` still name the v1-bound acceptances; they do not cover screen v2 / boundaries v2. A reviewer must accept v2 (or state the v1 acceptances transfer for a 1-constant change) before adoption. Adapter v2 acceptance note from v3 still applies.

## Dry run (read-only, <BATCH_HOST>): `dryrun-v4.json`
Exact v4 sources (unmodified), pinned venv python `-I -S -B`, AS 16GiB, CPU 1800, FSIZE 0, payload via stdin, audit hook, no writes. Result: reader, screen, branch/45365, unknown-id bound (96,399 of 262,144), rows
(max 136,833 of 262,144), original replay manifest equality for all four groups, output sizes (7,923,294 B total vs 128MiB/256MiB), peak RSS ~0.91GB: ALL PASS. Run twice, replay sizes identical.
Not covered: worker W13-W19 io-guard/device/space checks and runtime guard (need the real once). Harness audit saw 14 stdlib .pyc loads (modules runtime_guard.py:7-8 preloads; R16 forbids late imports), 0 writes.
Harness: `dry4.py` with payload built from this packet's own remote-command payload (scratchpad `d4/`, sha in dryrun-v4.json).

## Tests (repo root): `PYTHONPATH=src .venv/bin/python -B -m pytest -q -p no:cacheprovider <dir>/test_v4.py <dir>/test_once.py` -> 20 passed
`test_v4.py` proves: sources byte-identical to v3; prepare.py differs by exactly the stated lines; screen v2 / boundaries v2 differ from v1 only in the bound constant; ssh-contract equals `contract()` with no older paths;
request differs only in paths and the two pins; payload differs only in screen/boundaries texts and pins (embedded request == accepted parent with reader/screen/boundaries replaced; parent hash unchanged);
remote-command differs only in payload; templates bound to v4, no `actual/`, no filled-*/assemble-*.

## Codex sol-g1 must check
Delta above, screen/boundaries v2 acceptance, then FRESH adoption + execution review bound to v4 hashes (v3's review/adoption do not transfer). Kit: `newperiod-origin-s3-root-fill-v4-20261026`.
