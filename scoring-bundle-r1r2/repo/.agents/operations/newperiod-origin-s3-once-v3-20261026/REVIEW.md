# Origin S3 exact once v3 (author: Sonnet; local only, not authority)

v2 (`newperiod-origin-s3-once-v2-20261026`, untouched, consumed/refused W20 at the reader's predecode budget) -> v3 re-pins the science reader to
`newperiod-origin-projection-reader-adapter-v2-20261026/adapter.py` (sha 67ae8340...; DECODE_MODEL_LIMIT 8GiB, see its REVIEW.md: 7,904,963 nodes, peak RSS 757 MB).

## Delta (the only thing to re-check)
- `prepare.py`: 3 added lines: `READER=` path, and `science['sources']['reader']=ref(READER)` in `generate()` (prepare.py ~line 13). The accepted science request file
  (`newperiod-origin-task-binding-astra-v1-20261026/request.FALSE-TEMPLATE.json`) is NOT edited and is still pinned unchanged as `base.science_request`; the embedded
  payload copy of it differs only in `sources.reader` (path+sha). callback.py, task protocol (dfb95942...), projection, output namespace are unchanged (task protocol does not bind the reader).
- Regenerated with the packet's own generators in the new dir: `python3 -I -B prepare.py` (writes ssh-contract.json from `ssh_contract.contract()` then request.json, remote-command.txt), `python3 -I -B bind.py --out templates`.
  request.json: source paths/hashes for the new dir, ssh_contract path, `base.science_reader`; remote-command.txt: payload only (reader text + science request reader pin); templates: new-dir bindings.
- Byte-identical to v2: entry.py, once_operator.py, bind.py, reason-codes.json, root-fill-instructions.txt, runtime-pins.json (C.utf8 LC_CTYPE pin kept), runtime_guard.py, ssh_contract.py, supervisor.py, transport.py, worker.py, test_once.py.
- Not copied: `actual/`. Output namespace `...newperiod-origin-s3-boundaries-astra-v1` unchanged; W20 refused before any write so root must still see it ABSENT.
- Hashes: request.json 5dc485dc..., remote-command.txt 9d1dd66a..., ssh-contract.json 02b56a40..., prepare.py bf6e53ae...
- Note: `base.accepted_reader` still names the v1 reader's conditional-pass review; it does not cover adapter v2. A reviewer must accept adapter v2 (or state the v1 acceptance transfers) before adoption.

## Tests (from repo root: `PYTHONPATH=src python3 -B -m pytest -q -p no:cacheprovider <dir>/test_v3.py <dir>/test_once.py` -> 19 passed)
`test_v3.py` proves: sources byte-identical to v2 (list above); prepare.py differs by exactly the 3 lines; adapter v2 differs from v1 only in docstring + limit; ssh-contract equals `contract()` and has no older paths;
request differs from v2 only in paths and `science_reader`; payload differs only in reader text and the embedded request's reader pin (embedded request == accepted parent with reader replaced, parent hash unchanged); remote-command differs only in payload; templates bound to v3, no `actual/`, no filled-*/assemble-*.

## Codex sol-g1 must check
Delta above (test_v3.py, `ref()` hashes vs live files), adapter v2 acceptance, then FRESH adoption + execution review bound to v3 hashes (v2's review/adoption do not transfer). Kit: `newperiod-origin-s3-root-fill-v3-20261026`.
