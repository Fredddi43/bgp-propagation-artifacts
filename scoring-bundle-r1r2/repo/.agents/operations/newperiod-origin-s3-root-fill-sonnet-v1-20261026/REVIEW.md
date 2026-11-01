# Origin S3 exact once: root fill kit (author: Sonnet, local only, not authority)

Files: `measure_allocation.py` (read-only ssh metadata), `allocation-evidence/same-export-allocation-20261026.json`
(pin this; 5209 B), `fill_root.py`, `test_fill_root.py`, `tests.txt`.

Same export = `<MODELS_ROOT>` (NFS, data-custodian dir where the once writes). Comparators measured
(st_blocks*512): projection-v1 172,310,960 B logical -> 21,530,112 allocated (0.125); h3-metadata-publication-v1 330,340,911 -> 43,298,304;
h1-metadata-publication-v2 25,448,356 -> 6,687,232; timing-metadata-publication-v1 76,023,899 -> 19,885,056. All are under the
1.25*logical+256KiB/file+64KiB/dir formula. Model: 954,793,984 B (science 873,529,344 + controls 81,264,640) is an upper bound well above
the ~0.13-0.26x measured ratio. NOT measured: incompressible payload, delayed-allocation (post-fsync/60s/300s) of an in-flight writer.

## Root commands (all attestations are explicit flags; omit a flag and its field stays False)
1. Optional re-measure: `python3 -I -B measure_allocation.py --out allocation-evidence/<new-name>.json`
2. Adoption only:
```
cd /tmp && python3 -I -B <kit>/fill_root.py --out <kit>/filled-1 \
 --allocation-evidence <kit>/allocation-evidence/same-export-allocation-20261026.json \
 --default-running-growth-bytes <conservative per running n-* job> [--job-growth n-name=BYTES] \
 --category <name>=<bytes>[:status] ...  (non-job writers: root diagnostics, captures, stage; mirror the S2 v4 category list) \
 --issue-adoption --runtime-identity-reuse --runtime-immutable --all-writers-enumerated --task-adopted \
 --same-export-transfer --no-custody-appends
```
Refuses (exit 2, no adoption written) if EOF+growth >= 2,080,374,784, output namespace present, output parent or custody not on the models device, or
avail < v44 floor (+1GiB models). Running `n-*` jobs become writers; pending `n-*` and non-`n-*` jobs are listed as non-writers (extra keys, ignored by the consumer).
3. After sol-g1 writes its execution review (binding the exact adoption sha from step 2, v44, allocation_model_accepted=True):
`python3 -I -B <kit>/fill_root.py --out <kit>/assemble-1 --reuse-adoption <kit>/filled-1/root-adoption.json --review <review.json> --authority-out <ROOT-...json> --issue-authority`
(no re-probe; writes acks of all current ROOT-/REVIEWER- files except the authority path, then the authority, then runs the real
`once_operator.py --authority ... --check` and prints rc). Re-running step 2 changes the adoption sha and voids the review.

## sol-g1 must check next
- `allocation_model_accepted`: judge evidence JSON vs 954,793,984 B (compressible-JSON measurements only; limitations listed inside the file).
- Execution review binding all 11 operator pins, the actual adoption sha, v44 `e5fab44a`, task `dfb95942`, no review authored by astra-final/root/this author.
- Custody growth sum, writer list completeness, fresh floors, ack coverage; then root runs the real `--check`.
