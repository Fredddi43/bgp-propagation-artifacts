# G1 history source declaration WRITE (exclusive create) — Sonnet author; source only, nothing executed

Prepared per `declaration_write_requirements` in sol-g1 `M4-history-sources-verdict.json`. It must NOT run before the corrected read-only packet (`../newperiod-g1-history-sources-sonnet-v2-20261027`) has an independent exact-pin PASS and its ROOT once has landed; it needs its own independent review of writer, launcher, request and landing validator, and a fresh current-phase ROOT once.

| requirement | where |
|---|---|
| deterministic bytes: 7882720 B, SHA 5571dcd6..., 18136 entries | request payload = `common.candidates()['history']` of the pinned v2 read-once `common.py` (sha pinned in `make_request.py`); `write_declaration.PAYLOAD_*`, `check_write.EXPECTED`; tests decompress the request and compare |
| fixed destination `.../newperiod-inputs-v1/primary-history-source-v1/history-source-2023-2026-leak.json` | constant `DEST`; request destination must equal it |
| canonical, no symlink parent; any parent creation explicit and bounded | `canonical_dir` (realpath == path) on `newperiod-inputs-v1` and `DEST_DIR`; the ONLY directory it may create is `DEST_DIR` itself via non-recursive `os.mkdir(0755)`, only when `create_parent` is true (request must say true; the checker requires it) |
| exclusive create, no overwrite/unlink/retry | `O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW`, mode 0444; existing file/symlink/dir refuses `E_DESTINATION_EXISTS`; source contains no unlink/remove/rename/replace/makedirs (test); launcher: one attempt |
| finite FSIZE/write budget | `RLIMIT_FSIZE = 7882720 + 4096`; launcher `WRITE_BYTES = 8 MiB` in the df/floor check (models filesystem) |
| stable regular single-link read-only output, durable | `fchmod 0444`, `fsync` file and directory; post-write fresh no-follow open: regular, nlink 1, mode 0o444, same inode as lstat, canonical path |
| post-write content verification, not stat-only | re-read bytes: size, SHA256, JSON parse, exact 7-key consumer schema with typed file entries, exact scalars, closure and tuple digests; exports only booleans/counts/digests |
| landing validator | `check_write.check_report` (full gate, pinned constants, strict types; launcher `real_validator` calls it; CLI refuses); `analyse` yields the `sources.history` ref only after PASS |
| ROOT once, SSH standard, independent reviewer exclusions | launcher derived from the passed custody-v2 launcher (sha fb5a8086), `ONCE_KIND ROOT_ONCE_G1_HISTORY_DECLARATION_WRITE_V1`; `root-once.FALSE-TEMPLATE.json` is `template_only` |

Failure semantics: a refusal before the create leaves the filesystem unchanged (tested). If the file exists but post-verification fails, the program exits rc 1 without cleanup and its stderr says `destination_may_exist`; recovery is a new reviewed packet (no retry, no unlink).

Not in scope: library content hashes (inherited), four-library memory/graph/evidence bounds, any prediction gate. The review of this packet must also state that it reviewed the read-once acceptance as its prerequisite (the launcher cannot check that).

Tests `test_write.py` (15): payload pin, request==builder, embedded constants == read-once candidates, no-delete source scan, synthetic-tree write (algorithm real, constants patched): success/mode/dir mode, second write refused unchanged, symlink destination and parent refused, parent missing refused, tamper/schema refused before any write, post-verify failure leaves file, non-canonical root; landing: 19 mutations through `check_report`, real launcher validator and CLI.
