# Origin S3 exact once v2 (author: Sonnet; local only, not authority)

v1 (`newperiod-origin-s3-once-astra-v1-20261026`, untouched) was refused pre-effect with S3_R11: under LANG=C.UTF-8 the pinned python maps
`/usr/lib/locale/C.utf8/LC_CTYPE` (353616 B, sha256 e4b5576b...c52120), absent from runtime-pins.json. Same fix as timing S2 v4.

## Delta (the only thing to re-check)
- `runtime-pins.json`: exactly one added entry under `files` (`/usr/lib/locale/C.utf8/LC_CTYPE`), canonical sorted/indent-2 encoding. Nothing else.
- Regenerated for the new dir with the packet's own generators (`python3 -I -B prepare.py`, `python3 -I -B bind.py --out templates`):
  `ssh-contract.json` (= `ssh_contract.contract()`, no v1 paths), `request.json` (only source/ssh_contract paths + hashes differ), `remote-command.txt`
  (only the packed payload differs: pin added), `templates/*`.
- Byte-identical to v1: entry.py, once_operator.py, prepare.py, bind.py, runtime_guard.py, ssh_contract.py, supervisor.py, transport.py, worker.py, reason-codes.json, root-fill-instructions.txt, test_once.py.
- Not copied: `actual/` (v1 consumed), `verification.json` (v1 evidence, stale for v2). Output namespace (`...newperiod-origin-s3-boundaries-astra-v1`) is unchanged and was never created by v1 (refused pre-effect); root must still see it ABSENT.

## Tests (run from packet dir)
`PYTHONPATH=<repo>/src python3 -B -m pytest -q -p no:cacheprovider test_v2.py test_once.py` -> 18 passed. `test_v2.py` proves the delta
(pins, sources, ssh-contract, request, payload, remote-command, templates); `test_once.py` is v1's suite re-run on v2 (needs bgbench on path).

## Codex sol-g1 must re-check
Only the delta above (pin value vs live stat/sha256 on <BATCH_HOST>, test_v2.py), plus a FRESH adoption and execution review bound to v2's file hashes
(v1 review/adoption do not transfer: request/remote-command/runtime-pins hashes changed).
