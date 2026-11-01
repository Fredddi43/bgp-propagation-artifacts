# H3 packet #2b: H3 audit-only v4 successor (bound_base) + per-group release dispatcher

Author 4ba6111c (h3_author). Reviewer review2 7f4c18c0. Local only; nothing executed. The H3 port of the H1 v4 fix
(55ef accepted). F1 cause: the H3 base_manifest 74ff724e/1dad255b graph refs are leaf links, and h3_audit.read():17 and
source_io.raw():14 require resolve()==path.

- `build_audit_v4.py`: closed edits of the frozen H3 package (plan e32b00eb). The edits are the same as H1 build_v4:
  * W1 audits/h3/audit.py: in audit_shard, selected=[(bound_row(a),b) ...]. bound_row rebinds only an AVAILABLE base
    row's graph_path through bound_base (the H1 function verbatim). The sha stays the manifest's, so h3_audit.read()
    and source_io.raw() keep their canonical + exact-bytes checks. Panel rows are untouched. h3_audit.py,
    source_io.py and both verify_h3_* files stay byte-identical (asserted).
  * J1 job.py: the audit plan is the preserved H3 assembly's audit-plan.json, bound to group['predecessor'].
  * C1-C5 controller: namespace sensitivity-parallel-h3-audit-v4, PHASES audit + audit-finalize, audit-only storage.
  * jobs/: the audit + audit-finalize scripts are regenerated. plan.json gains per-group predecessor refs, with
    reservation 4 + 4 x 35 GiB.
  * The code shas are final now (controller 32b6d1ca, audit 86c0c315, job f41fb68d). Only plan.json changes at freeze,
    from chain_h3's predecessors.json after their independent acceptance.
- `build_release_h3_v4.py` -> `release_h3_v4.py`: closed edits R1-R7 of waves_v2. Per-group release of
  [audit, audit-finalize] once; the first group writes the v4 binding through BIND_REMOTE and later groups require
  that exact binding digest; reservation 35 GiB per group. held() accepts the afterok:<array>_* forms
  (H1 v4 lesson F2).
- Tests (`test_audit_v4.py`, 25 passed):
  * declared-only file and plan deltas;
  * the predecessor checks in groups();
  * bound_base/bound_row units, with 6 refusal cases;
  * the dispatcher: derivation, first group / later group, and refusals.
  `mutation-proof.txt` 4/4.
- Stage/submit-held of the v4 package uses the controller's reviewed stage/submit, like H1 v4 G3, after the freeze.
  A chained v4 runner (stage -> submit-held -> read-held -> per-group release -> chain_wait/capture) follows the same
  pattern once the predecessors exist.
