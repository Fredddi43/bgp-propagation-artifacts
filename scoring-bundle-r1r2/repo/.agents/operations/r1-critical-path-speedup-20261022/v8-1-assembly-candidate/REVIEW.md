# Review packet: LOCAL O1-bound v8 assembly candidate (driver v8.1 33011eed)

- Author: claude-opus-5-5, session <SESSION_ID>. Root routing: adopt O1 **only if** the independent CODEPASS of O1 pins
  7e1a7d1f exists. Otherwise the D-1 candidate `v8-assembly-candidate/` (pins 2420b593) stays the assembly.
- **Nothing staged, approved or run, and no reviewer record is written.** The O1 review is not bound (null). The adoption
  step binds it once it exists.
- Frozen packets are untouched: `v8-assembly-candidate`, `v8-assembly-r2`, `driver-v8-1-o1`.

## How it is built (`build_v8_1.py`)

- It is a copy of the frozen `build_v8.py` with one input changed: the driver comes from `driver-v8-1-o1/`.
- The builder refuses unless the O1 pins name 33011eed as both package file and `driver_sha256`, over the D-1 base
  bb7f7e00.
- Same planned root `r1-release-assembly-v8-20261022`, same allowed draft leaves, same value guards. The fixture work
  from earlier packets is not redone.

| Item | sha256 |
|---|---|
| source candidate | fded6806 |
| manifest | 6a9a325f |
| base draft | f02fd82a |
| runtime | ee745901 |
| label-bound | 091c3fc1 |
| contract | d5798bee |
| resource candidate | 32bbd21d |
| input identity | **397e6e28, unchanged** (the driver is not an identity key) |

## Exact delta against the D-1 candidate (`delta.py` → `delta-vs-d1.json`)

| Document | Leaves that differ |
|---|---|
| source files (373, same set) | only `scripts/forecast_retrospective_release.py` (= the O1 frozen bytes) |
| source-manifest | `/files/scripts/forecast_retrospective_release.py` |
| base draft | `/release_driver_sha256`, `/release_resources/contract/sha256` |
| runtime | the v8 driver path's sha, `/release_driver_sha256` |
| label-bound | `/runtime_admission_sha256` |
| resource contract | `/release_driver_sha256`, `/runtime_admission/sha256`, `/label_bound/sha256` |

The candidate records change only in their file shas, kind and driver/review/fallback fields. No scientific leaf, no
number, no scorer path or sha, and no identity changes. The draft's diff against v7 is the same 11 leaves as D-1.
`v8-assembly-r2/check_u2.py` (A1) applies unchanged, because the root and calibration path are the same.

## Inventory (`repin_inventory_o1.py` → `repin-inventory-o1.json`)

- It reuses the frozen r2 inventory code unchanged, bound to this packet.
- The driver re-pins to **33011eed**; D-1 bb7f7e00 is recorded as the fallback.
- The manifest, runtime, label and contract known-now values come from here.
- Coverage: 101 tool files, 0 unaccounted, 0 stale.
- **Tree drift, expected:** this packet adds 3 `.py` files that carry v7 identities (`build_v8_1.py`,
  `repin_inventory_o1.py`, `test_v8_1.py`). All are classed `v8_work`. As a result the r2 snapshot
  `v8-assembly-r2/repin-inventory.json` (98 files) no longer regenerates byte-identically. The only differences are
  those 3 `v8_work` entries and the count; nothing else changes.

## Tests (`test_v8_1.py`: 8 passed; ruff clean)

- Deterministic rebuild.
- The delta equals exactly the table above, the source set is equal and only the driver changed (byte-equal to O1).
- Identity and draft-vs-v7 diff are equal to D-1; reviewer fields stay null; the fallback is recorded.
- Builder refusals: O1 pins, driver, v7 draft, D-1 base.
- The inventory regenerates; driver and manifest entries hold the O1 values; coverage is complete.

## Use

- Only after the O1 CODEPASS exists.
- Then the reviewer issues the four records (resource review, calibration re-issue binding 33011eed, retention,
  preparation) against these bytes, not the D-1 ones.
- If the CODEPASS does not pass, discard this packet and use `v8-assembly-candidate`.
