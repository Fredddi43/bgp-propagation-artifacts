# q52 REVIEW-QUEUE
1) ALERT-CAPTURE-GATE.md — capture rehearsal invalid-d30 (job 52650156) shows q37 gate cannot pass: no
   $EQ/RESULTS.json, gate not in controls, plan-pin!=deployed by root policy. Unblock options A/B/C inside.
2) gate_check_q52.py sha d8a237c9334d424d64d3e063e56fd06982f0df4b34cfd0530fd2ecb6d47b46b8 — REAL-DATA capture gate
   (option B): binds q51 COMPARE reports (re-hash, pins deployed==9d94de1d==runner-literal, plan sha) + per-group
   done.json/audit receipts. Tests: test_gate_local.py 14/14 PASS. Deploy if approved: cp on <BATCH_HOST>
   <RESULTS_ROOT>/nobackup/<PROJECT>/origin-direct-20261027/q52/gate_check_q52.py -> either
   controls/gate_check.py (both) or overwrite kit/q52/gate_check.py; then tell me via ROOT-REPLY, jobs re-run per group.
3) g1/promotions/g1-origin-fragment-promotion-40.json sha a2e980d3f39565fb7d108135c55070a3f805dd8abb7d322d9448d35837db5cf8 — PENDING_ROOT promotion for all 40 origin arms (draft origin; check=0 problems;
   fragments filled from the 4 gated captures signed by you 18:29:18Z; pre-fill bytes in .prefill/).
   Flip: bash signoff.sh g1/promotions/g1-origin-fragment-promotion-40.json  then promote_all.py. See ROOT-SIGN-REQUEST.md.
