# stable-source-v6 MIXED32 ASSEMBLY v3: author packet, UNSIGNED, not an authority

Author: sonnet (claude-sonnet-5-5, session <SESSION_ID>). Successor of v2 (untouched, `../newperiod-stable-assembly-mixed32-sonnet-v2-20261026`) after sol-h3t CHANGES `REVIEWER-sol-h3t-STABLE-ASSEMBLY-MIXED32-V2-CHANGES-session<SESSION_ID>` (R3). Everything else is v2 (link/population expectation R1, 64 GiB R2, A1-A7 mapping in the v1/v2 REVIEW.md). No remote action was taken for v3.

## R3: capture hashed receipt-supplied table paths before the scope check, unbounded
Reproduce first: `test_R3_pinned_v2_opens_an_unapproved_table_path_v3_never_does` pins v2 operator 2e33b0bc and runs the real generated capture program under a Python audit hook with a receipt whose table source points to a marker outside the tree: v2 opens the marker (tables_exact false, yet fh() called); v3 never opens it.
Fix (`operate_assemble.py`, remote program, fh at line 347, verify at line 364):
- Tables are hashed only at the FIXED path `<attempt>/output/<role>/<relative>` built from the expectation's five exact [role,relative] pairs, and only after `tables_exact` is true (exact five relative paths, each link's source == that fixed path). No receipt-supplied string reaches `fh`. Ledgers were already fixed paths and now use the same bounded helper (receipt ledger refs are only compared afterwards).
- `fh` order: canonical check (`realpath(p)==p`, under `output/`) -> `os.open(O_RDONLY|O_NOFOLLOW|O_NONBLOCK)` -> fstat regular-file + size <= per-file cap (request output_file_bytes 512 MiB) + aggregate cap (request output_total_bytes 1152 MiB across all hashed files) -> read exactly st_size bytes -> second fstat (size/mtime_ns unchanged, no extra byte). Anything else raises before content is read and the check reports false.
- Tests (real program, synthetic trees): outside table path never opened; symlinked table and symlinked ledger refused before open (audit hook); FIFO table does not hang; sparse file 512 MiB+1 refused; directory ledger refused; aggregate cap smaller than the tables refused; structure test pins the order canonical < open < S_ISREG < read and that `fh(t[2])` no longer exists. All v2 link/population/R1 refusals kept.
Output stays compact (digests and booleans only). Capture reads elsewhere were already bounded (records <=16 MiB via O_NOFOLLOW + fstat, receipt <=128 MiB via fstat).

## State
Operator sha256 prefix 02329df6 (pinned in pins.json and verification.json); RECORDS dir `newperiod-stable-assembly-mixed32-actual-v3-20261026` (unused). `tests.txt`: 84 passed in 51.58s. Unchanged: resources 4 CPU/65536 MiB/28800 s, floors 848,785,841,152, closure 55,685 files, appends 55,930 x 746, control names, reason codes 100-111. Root sequence as v1/v2 REVIEW.md with H = this dir.
