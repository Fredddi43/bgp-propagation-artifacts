# Final whole-chain inventory (N1, at bind time). Edits nothing.

- Author: claude-opus-5-5, session <SESSION_ID>.
- It runs the CODEPASS r3 inventory code (`v8-assembly-r3/repin_inventory.py`, pins f9ee5fd0) unchanged on the
  current tree, through the thin wrapper `final_inventory.py`. The wrapper adds two things:
  1. **New packets as explicit v8-work subdirectories:** `k1-outcome`, `a3-result`, `v8-preparation-candidate`,
     `budget-r3`, `budget-r4`, `h3-stable-timing`, `final-inventory`.
     - Before this, N1 correctly reported the five new v8-preparation tool files as unaccounted.
  2. **`repinned`:** the 10 preparation-stage chain tools mapped to their v8 re-pin in
     `v8-preparation-candidate/tools` (or its replacement tests). Each target exists.
- **Result:**
  - 110 tool files carry a v7 identity: 0 unaccounted, 0 stale.
  - 78 constant entries; driver → 33011eed; manifest/runtime/label/contract from the O1 assembly.
  - **21 chain tools remain to re-pin** (`remaining_to_repin`):
    - transition;
    - final-build / B8 stage / status;
    - post-eval capture;
    - verifier-r2, adapter-r2, classd/vrun/d2.
  - Those are post-preparation stages, re-pinned when their phase is prepared. The placeholders (spec/seal/ledger
    after preparation, etc.) are listed in the r3 entries.
- **Test:** `test_final_inventory.py`, 1 passed. It regenerates exactly, accounts for everything, and every re-pin
  exists. ruff clean.
- The output depends on the tree. Any new tool file elsewhere fails the regeneration test until it is classified; that
  is intended.
