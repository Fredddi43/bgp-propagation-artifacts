# Budget revision r3 (O1 driver; inputs only, no limit proposed)

- Author: claude-opus-5-5, session <SESSION_ID>.
- `budget_r3.py` → `budget-r3.json`. Every input is sha-pinned and label-free.

| Stage | Hours | Basis |
|---|---|---|
| eval re-verify | 3.76-4.13 | MEASURED on host (v7 eval verify) |
| pre-label validation | **15.60-20.94** | MEASURED: S0b host `check_forecast_rows` traced 5.82-7.82 MB/s × 438.9 GB already-retained payloads (v7 loop read ~0.5 MB in 4.4 h). Consistent with K1: v7 never reached the gate. |
| post-label decode (O1) | **2.41-2.59** | MEASURED: S0b host `json.loads` 47.1-50.7 MB/s |
| partition reads, all uncached | **1.41-4.01** | Header metadata: STORED torch-zip bytes 336.4 GB over the 42 proof groups + 16 unmapped × 38.65 GB = 954.8 GB, at the measured logical 66.2 MB/s (not a guaranteed floor). Sensitivity at an assumed 25 MB/s: 3.74-10.61 h. |
| partition decode CPU | 1.53-3.80 | sha256 MEASURED (0.765); `torch.load` + object building PROXY (0.473) |
| scoring | 1.52-24.52 | PROXY 0.473-0.617 on r2 local rates; `score_membership` and H3/stable scorers UNMEASURED |
| analysis bootstrap | 0.01-0.21 | `evaluate_retrospective` MEASURED; `retrospective_14` same factor |
| **eval process** | **26.23-60.20** | D-1 alternative 30.74-66.35 (post-label re-parse 6.92-8.74) |

**Changes vs r2 (assumed 24.2-83.8 h + a 16.2 h "uncached tail"):**
1. Host rates come from S0b for the same operations.
2. Partition I/O is computed from STORED file bytes, with every read treated as uncached. r2 divided the decoded
   backing (3.1-4.8 TB) by the NFS rate, overstating the read volume about 10×. The "tail" is gone because the reads are
   now counted in full.
3. O1's saving is applied.

**Honest limits:**
- 47% of the high end comes from PROXY rows (scoring, decode CPU).
- B1 (cold-storage rate) uses a measured logical average, not a floor; a sensitivity row is given.
- Nothing here guarantees a runtime.
- Preparation (single pass) is measured at 3.88 h.

**Optional sharpening:** `PROPOSAL-S0c.md`, a synthetic-only host run of the reviewed S0 program with the reviewer's R1
import ordering. Proposal only.

**Tests:** `test_budget_r3.py`, 2 passed. The output regenerates exactly, and the measured and proxy labels are
asserted. ruff clean.
