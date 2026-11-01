# History-r2 launch binding draft (launch condition L1 of review 13298dcf CODEPASS)

Local only; no host command, no admission, no approval. `build_binding.py` derives three files from r1's
actual-binding-v1, which is not reused:
- `plan-draft.json` bc07a3ab: r1's draft with newperiod-origin-history-v1 -> v2, and the source map from the r2
  manifest 4f93fa6c. Only history_stage 0d042e23 and run.py ee71b25a differ. resource_admission is None.
- `task-0.json` a6a6e02a: byte-identical to r1 (L2: the same 8 table/validity identities and feature staging). It names
  no namespace.
- `resource-request.json`: binding_sha256 23e968b0 equals the reviewed run.py binding() of this draft. The resources
  are unchanged from r1 (L4: 16 CPU, 768 GiB, 4 h, 1 GiB output, concurrency 1).
  - r1's other-reservation numbers are removed: R1 v11 has ended, so the independent admission must take fresh df and
    the current reservations itself.
  - The N2 note is recorded: memory was not measured.
- `controls-draft.json`: the two phase controls. The admission is a placeholder for the independent record.

The test proves the reviewed r2 `prepare.package` accepts this draft once an admission sha is filled in, and that the
binding is unchanged by that fill. 4 tests pass.

Still needed, in order: an independent resource admission (fresh df), then plan.json with its sha, then the packet via
prepare.py, then an independent execution approval, then root-routed stage/held/release, run once, no retry (L3-L6).
The receipt grants no fitting authority.
