# G1 literal event-ID extraction (Sonnet author; source only, nothing executed)

**Why:** the original `custody.freeze` requires every executable arm's `event_ids` to equal its manifest's `split=='test'` population; no owner fragment carries them. This packet extracts them from the exact accepted test-population manifests under one ROOT once.

## Scope and consistency with the H1 packet
- Transport, launcher and digest are the H1 final20 ones (`newperiod-h1-g1-final20-sonnet-v1-20261027`): `run_once.py` is its launcher with only these edits: once kind `ROOT_ONCE_G1_EVENT_IDS_V1`, `STDOUT_MAX` 1 MiB (H1: 256 KiB), landing check module name/pin. Same ROOT SSH standard (`root-ssh-standard-20261026`, strict pinned known_hosts, ProxyCommand), same stdin-request/argv-free remote program via base64 `-I -B -c`, one exchange, rc0+empty stderr+landing check, fresh records dir, no retry, review binds program/runner/request shas, issued phase + fresh df/custody evidence. Digest = `sha256('\n'.join(sorted unique ids))`, ID regex and E_*/X_* refusal style identical. Review both packets together; the only semantic difference is the source: H1 reads two finalized audit JSONs (event_ids field), this reads `input_manifest.json` test rows.
- `extract_ids.py` (remote, RLIMIT_FSIZE 0, writes nothing): per entry exactly one regular single-link file named `input_manifest.json` under `.../data-custodian/newperiod-inputs-v1/`, O_NOFOLLOW, parent not a symlink, size == pinned (<=16 MiB; <=32 entries; <=64 MiB total), double fstat + lstat stable, sha256 == pinned. Uses only `protected_test/locked_test`, `split`, `event_id`; exports only sorted unique test IDs (<=20000/entry, output <=960 KiB). No input paths/hashes, labels, outcomes, tensors, gates or predictions leave the process (tests assert a planted SECRET label never appears).
- `request.json` (built by `make_request.py` from the pinned merged fragment be7c140c + the pinned lstat record): 4 distinct manifests (core-d30/d60 755116 B, temporal-d30/d60 760276 B) covering all 56+48+12+6 executable primary/history/ordinary/baseline arms. `expected` is null (counts/digests unknown until the extraction); `check_extraction.per_arm_digests` then yields the per-arm (count, sorted-ID digest) table and `g1_draft_prep.fill_event_ids` fills the arms (test proves both).
- Later groups are added by pin without editing code: `make_request.py --extra LABEL=PATH:SHA256:SIZE[:COUNT:DIGEST]` (e.g. h1 manifests with the 1289/6c1cf870 pins, h3/timing/stable/origin) or `--group` once their fragments carry manifests. Each addition changes request.json and needs a fresh review + once.

## Root sequence (nothing issued)
1. sol-g1 (or sol-h1 together with the H1 packet) reviews program/runner/check/request; review file with scope `ROOT_ONCE_G1_EVENT_IDS_V1` and fields `passed,verdict(PASS*),scope,program_sha256,runner_sha256,request_sha256,reviewer_worker,reviewer_session,reviewer_model`.
2. ROOT fills `root-once.FALSE-TEMPLATE.json` (fresh utc, rescan of unhandled ROOT/REVIEWER posts clear utc, issued phase, fresh df/custody/all-writer evidence, authors, fresh records dir) and runs `cd /tmp && python3 -I -B run_once.py <once>` once. Records: intent, stdout.json, stderr.txt, result.json.
3. Independent actual acceptance of `stdout.json`; then `check_extraction.per_arm_digests` + `fill_event_ids` produce the fragments the draft plan uses.

## Tests
`test_extract.py` (9) + `test_runner.py` (21, the H1 runner tests with only the constants changed). Synthetic temp dirs only; no ssh is started.

Runner for the later draft/finalize: recommend r3-retained d6d13ca8, diff vs r2 stated in `../newperiod-g1-complete400-draft-prep-sonnet-v1-20261027/REVIEW.md`.
