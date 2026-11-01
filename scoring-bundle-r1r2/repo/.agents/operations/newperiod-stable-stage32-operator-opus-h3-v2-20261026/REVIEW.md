# N-stable stage32 once-operator v2 (opus-h3; successor of opus-science v1 56f6d9a3)

Source only, never executed. Changes vs v1 (see operate_stage32.v1-v2.diff), nothing else:
- **E1** custody gate: the authority adds `h3_operating_adoption` (pinned). The constructor requires a root-issued
  `root_h3_v37_shared_writer_operating_adoption_v1` (issuer /root, passed, the 6 top + 4 scheduler flags true, campaign baseline ==
  final-stat-accepted e516a3d8, operating budget bytes == budget v3 07c637e7, writer arithmetic exact, total <= 160 MiB) whose
  `stable_source_stage` writer is `bounded_active_or_authorized` and lists the identity `stable-stage32-request:<authority.request.sha256>`.
  Every gate (stage, submit, release) requires log dev/inode == baseline, baseline.bytes <= size <= 2 GiB - 64 MiB and
  size - baseline.bytes + adoption.maximum_future_append_bytes <= 160 MiB (same arithmetic as H3 release_once/capture_once).
  The old 64+128 MiB headroom constant is gone; `custody_log_preflight` must equal the transport v3 template text.
- **E2** authors: opus-h3 and /root/opus-h3 added (cannot review).
- phase_compat v1 -> v2 b84be518 (ROOT-DECISION-PHASECOMPAT-V2-0258); own lane unchanged (`stable_source*`). v42 is accepted for bound v40.
- Same records dir name as v1 (`newperiod-stable-stage32-actual-v1-20261026`; v1 never ran), so v1/v2 are mutually exclusive.
- Tests: 19 OK (17 v1 + E1 adoption refusals + E1 gate cases incl. a release-gate failure that leaves the array held and an exactly-at-cap pass).
  Real-request probe now uses transport v3 draft-v40 (unsigned: refused at the signed check, as before).

Root authority: fill `root-once-authority.FALSE-TEMPLATE.json` (transport v3 template minus template_only, plus root_issued_utc and
h3_operating_adoption; operator_sha256 and records prefilled). The adoption must name the SIGNED request sha (the reviewer's build of
admission/review/approval changes request.json), so root issues a fresh adoption (DRAFT from opus-h3) after the signed request exists.
