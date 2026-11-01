# Independent review: parallel_phases.py hunk 4 (audit eventset path)

Read-only; only this file written. No protected data read, no cluster access.
Local sha256 of q32-origin-parallel/parallel_phases.py = 9d94de1dd7becb843d83b1471ee60ee2744129e6a59afdd416b9f28807d2d2f4
(matches PP_SHA literal at q27-origin-export/chain/run_step_origin_par.py:70). Deployed copy not re-hashed (cluster not touched).

## Verdict: PASS for hunk 4 and the seam wiring; one verification gap (item 3) is a RISK, not a code fault.

## (1) Hunk 4 vs the pinned audit
- Pinned audit: scripts/custodian_newperiod_inputs.py:785 reads `data / "eventset/2026_leak/events.parquet"`.
- Kernel replacement: newperiod-family-protected-inputs-20261027-sharded/kernel.py:80 maps that literal to
  `"eventset/2026/events.parquet"` (same list also maps independent_library/from_eventsets/tie_exposure to family="").
- Hunk 4 (parallel_phases.py:359): `"eventset/2026_%s" % family if family else "eventset/2026"` under `data / ... / "events.parquet"`.
  With family == "" this is exactly `data/eventset/2026/events.parquet`, the same path and the same `data` root
  (stage_receipt["data_root"], L341 = pinned L771) as serial.
- Cannot silently select another year/family: the year 2026 is a literal in both; family is forced to "" by
  `require(... family == "" ...)` at L338, so the `2026_%s` branch is dead for origin wiring (it would only fire for a
  non-empty family, which L338 refuses first). No wrong-data-but-found path.
- Downstream check that would catch a wrong table anyway: history is bound by library.digest == master_doc["history_source_digest"] (L353);
  the 2026 table only supplies expected_by_id (L360), consumed per event in _audit_event.
- NIT 359: the `% family` branch is unreachable dead code; simpler to hardcode the literal like the kernel does. Not required.

## (2) Other seam-derived uses in parallel_phases.py
- L142 / L342: `_replay_dir(getattr(adapter, "_pp_seam_master"/"_pp_seam_audit", adapter.master/.audit))`; the attrs are set at
  L439-440 before the lambdas shadow (L441-442). Pinned replacement is `"events_replay"` (kernel.py:78-80); _replay_dir (L54-66)
  needs exactly one `events_replay*` constant: master ran in production, audit passed L342 (failure was later, at L359).
- L290: `ad.tie_exposure(..., family=S["family"])`; S["family"] = "" (L370) = kernel.py:80 `family=""`. Matches.
- L351: `adapter.independent_library(history_root, years, delay, family=family)` and L352 `from_eventsets(history_root, years, family, ...)`
  with family "" = kernel.py:80 replacements. Matches.
- L337-338: family taken from the stage receipt and required to be "" (kernel.py:50 also requires history_family == "").
- No other f-string or getattr(adapter...) seam use found (grep of family/_replay_dir/getattr/2026/year). Years come from the
  construction manifest (L347), as pinned L777.
- RISK (low): _replay_dir over the audit body counts nested code constants; if a future adapter change adds a second distinct
  `events_replay*` literal it raises ValueError (fails closed). Fine as is.

## (3) Diff vs hunks 1-3 / REVIEW-VERDICT.md (q38)
- Hunks 1-3 are present and unchanged in form: L142, L342, L439-440 (matches REVIEW-VERDICT.md B list). Hunk 4 at L359.
- RISK: "only hunk 4 changed" is NOT mechanically proven. No archived copy of 6fddec14 exists locally (git has no history for
  the file; __pycache__/parallel_phases.cpython-312.pyc is an older 02:36 build and structurally different, e.g. no _log_pending).
  Evidence for it: STATUS line 07:12Z describes a single-line fix; the 359 expression is the only line that differs in shape from
  the seam-fix description. Cheap closure for root: run `diff` of `<controls>/parallel_phases.py.pre-seamfix`-lineage backups or the
  pre-hunk-4 controls copy against the local file; expect one changed line at ~359.

## Bottom line
Hunk 4 equals the kernel's pinned audit path; audit cannot pass on a different event set than serial. No BLOCKER.
