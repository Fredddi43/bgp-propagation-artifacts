# Count34 evidence staging v2 (Sonnet author; source only; nothing executed)

Differs from v1 (unchanged on disk) only by `prepare.py` and its tests; program, runner, checker, template identical bytes.

## ROOT needs to supply only the issued phase (and flip `issued` on the capacity document)
No row has to be ADDED. Every issued phase v40..v44 already carries the row (checked in v40 and v44):
- name/keys: `earmarks.count34_evidence_staging` (`phase_row_keys: ["earmarks","count34_evidence_staging"]`),
- exact value: `{"additional_shared_custody_appends":0,"borrowing_allowed":false,"bytes":1048576,"destination":{path ...complete-retention-bindings-astra-v1/count-rb-disposition.json, sha256 0e537a99...},...}`,
- plus `models_reservations_bytes.count34_evidence_staging == 1048576`.
The next phase (v45/v46...) must carry both entries UNCHANGED (1048576 B, same destination); if a phase drops or edits them, `prepare.py` refuses (`E_ROW_ABSENT`/`E_ROW_VALUE`/`E_RESERVATION_ROW`).

## Use
`cd /tmp && python3 -I -B prepare.py --phase <abs current issued root-joint-storage-phase-vNN.json> --out-dir <fresh>` writes `request.json` (floors = that phase's models/results minimums) and `capacity.UNISSUED.json` (issued=false, row keys+value copied, phase ref pinned). ROOT sets `issued:true` (its act), then fills `root-once.FALSE-TEMPLATE.json` (program, runner, request, review, phase, capacity, fresh df/custody evidence). `example-v44/` is the output for the real v44 phase (illustration; regenerate for the current phase because the request pins that phase's minimums). Tests run the real v44 file through `run_once.check_capacity`: unissued refused (`R_CAPACITY_NOT_ISSUED`), issued accepted, edited row refused.

Remaining gates unchanged: sol-g1 exact execution review of the filled request, fresh df, board rescan, one ROOT once, independent actual acceptance of `receipt.json`. Tests: 32 (v1's 29 + 3).
