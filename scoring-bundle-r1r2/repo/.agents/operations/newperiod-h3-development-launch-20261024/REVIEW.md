# H3 four-group development construction/audit package (prospective; author Opus f4d75bb1)

Sibling of native's timing launch assembler (newperiod-timing-development-launch-20261024).

What `assemble(files, kernel, output)` does:
- Uses the owner's build_package and the shared controller/job/runtime/budget unchanged (b5cfcc5a). Groups
  ris7/mixed7 map to the frozen H3 client 47f5f407, which equals the H3 audit's CLIENT pin, and to the frozen H3
  audit callable (newperiod-h3-development 332c621f).
- Inputs:
  * the 17 actual H3 publication refs (from the finalize capture): construction manifest, gate and
    `h3_panel_coverage_extract` per group, plus the full coverage receipt;
  * the H3 kernel plan: sealed core base manifests/gates, release, recipe, staging and the N-h3 collector inventory.
- Each audit template carries every key that the H3 audit `metadata()` reads, plus the produced manifest and
  construction_receipt slots.
- The complete 10-group ledger is retained; only the 4 H3 groups are ready.

Resources (proposals; the timing values for build):
- 2 CPU / 128 GiB / 24 h per task;
- 32 shards per year x 2 years, so 64 build tasks per group;
- 32 audit shards per group;
- audit scratch 256 MiB, at most three source files of 59.8 MB each.

Storage: the retained reservation is explicit, computed with the controller's formula (about 660 GiB for all four).
It is NOT admitted. As for timing, a reviewed wave dispatcher plus joint root admission is required.

Tests: 2 passed. Placeholder publication refs go through the original builder and controller.groups(); an incomplete
publication is refused. Placeholder refs are only test scaffolding: the actual package must be assembled from the
real finalize capture.
