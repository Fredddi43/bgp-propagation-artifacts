# Exact bundled collector inventory transport correction

Preserves the approved r4 scientific package byte for byte. Only client.py changes: include collector-inventory.json in the exact code/control bundle; verify its exact STAGE path and declared SHA; before fresh stage creation use those verified bytes rather than opening a file which cannot yet exist. Subsequent preflight reads the actual staged inventory normally, and the original fit adapter still performs the complete source/pooled-selector/recipe lineage validation. No scientific input/read/fit authority is introduced.

The original stage refusal on existing directories, all five external prerequisite reads, full closure, independent operation/execution/transport/release approval checks and original scheduler/resource rules remain unchanged. No new publication operation, retry, source or numeric edit.

Validation: `.venv/bin/python -m pytest -q .agents/operations/newperiod-gbdt-client-r5-20261024/test_client.py` — 66 passed (9.94s). Includes genuine remote_action fresh filesystem stage→full original bundle validation→preflight→changed inventory refusal, with only five external metadata reads and host user identity replaced by synthetic equivalents. Three focused path/hash/bytes refusal cases.

Actual approvals and held-job release remain separate. The actual collector inventory is metadata composed from independently captured sealed manifests and original source/staging receipts.
