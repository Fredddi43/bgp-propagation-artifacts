# D2 r3: accept exactly the D1b-verified links, then size D2 on the real tensor bytes

Executed D1b link census (approval ded3cf10): link-census.json 2890fcee, intent 5e9b6ebb, result 5eca8ab2.
- bad = 0. All 7086 entries are 1-hop symlinks, each with chain and realpath under run_adapter ROOT_FILTER and a
  regular-file target, in 16 distinct target directories.
- d30s: 3543 files, 2,850,853,625 B, max 3,375,086. d60s: 3543 files, 2,886,120,495 B, max 5,256,485.
- The rescore's original reader `bgbench.forecast_train.load_partition` "hashes and deserializes exactly the same
  bytes, including through shard symlinks" (src/bgbench/forecast_train.py:120), against the gate shas. The links are
  the designed storage layout. Only d2's `not_regular == []` gate and its link-size sizing were unaware of that.

Change (`build_d2_r3.py` from approved d2_r2 b71e0410; d2_r3.diff): captured_inputs() is the only changed function,
and it calls the new resolved_links().
- resolved_links() requires D1 not_regular == exactly the sorted link-census entries, with bad == {}.
- Each entry must be: a symlink, 1..HOP_CAP hops, chain_in_root, in_root, target file, size > 0, and D1 type other.
- It replaces those entries' sizes with the resolved target bytes, in memory only.
- The link census is sha-bound (2890fcee).
- DEST, code shas, inputs, outs and the approval gate are unchanged.

Resulting D2 job script (d2-script.json):
- job_script_sha256 733a6676, tool 4b8ccda6;
- a 2-task array (d30, d60), 1 CPU / 14 GiB / 2 h each, cpu partition, no requeue;
- plan 6e18854b, report 049c7a9c.

Tests: 9 pass.
- The reviewed d2_r2 refuses the actual capture, and r3 accepts it.
- 7086 entries are resolved, and resources use the resolved bytes.
- Drift refuses: bad entries, an extra link, a hop outside the root, too many hops, a non-file target, a changed
  census.
