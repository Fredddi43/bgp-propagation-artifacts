# d300 operator v8 (successor v7, fresh astra-v7 namespace)

No execution authority; v3-v7 and the consumed v6 namespace untouched. Delta from v7: only `prepare.py` (SOURCE and PINNED successor/plan/template shas for successor v7, job name `n-timing-d300-v8`; `--export=NIL` and absolute-path job.sh kept) and `remote.py` (FRESH -> astra-v7). `operate.py` is byte-identical to v7. `recovery/` exists, so stage takes the existing-parent branch.
Pins: prepare.py 87aaf746..., remote.py 138f864e..., operate.py 56be41c2..., transport.py/ssh_contract.py unchanged. Successor v7 pins: see PINNED in prepare.py.
Tests (python3 -I -B from /tmp): test_operate 13, test_prepare 10, test_reason_codes 3 pass; FALSE templates (phase V48) refuse `--check-only`. Templates/candidate regenerated for the v7 plan.
Re-review: the successor v7 hook delta (scientific-source reviewers, both concurrences timing_science and allocation_premise must be re-issued against v8 prepare.py/plan v7); stage_hold and install_release operation reviews and root authorities rebind to v8 pins; the operating adoption pins the plan path/sha, so it must be refilled for the v7 plan.
