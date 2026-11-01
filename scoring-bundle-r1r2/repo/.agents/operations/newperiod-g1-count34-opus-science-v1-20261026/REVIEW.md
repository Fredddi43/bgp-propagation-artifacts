# count34 evidence staging successor (opus-science, author)

Successor of `newperiod-g1b-count-stage-v1-20261026` (preparation PASSed by sol-g1, never run),
only because its operator hard-codes `reviewer_worker == 'sol-g1'` (Codex reviewers out of credits).
Exact diff (operator.py only): reviewer_worker 'opus-review'; reviewer_session must not be
None/''/'astra-g1b'/'opus-science'/'/root'; self-announcement `to` 'opus-science'. worker.py
byte-identical. Templates: refs rebound to this dir, reviewer opus-review. test_stage.py:
reviewer rename only; 4/4 OK.

Scope unchanged: copy the accepted 13,884 B R-b disposition JSON (0e537a99) to the destination
all 34 count failure chains already name. No outputs, no custody appends, one ssh.

bind_v39.py: `--draft` writes the root capacity draft for v39 row
['earmarks','count34_evidence_staging'] (its destination equals the fixed one); `--request
<issued capacity>` writes request.v39.json; `--dry-run` drives the real operator.validate on v39
(OK; a sol-g1 review is refused). Run Python with -I (operator.py shadows stdlib otherwise).
