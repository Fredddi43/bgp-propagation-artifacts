# N-stable stage32 transport v2 (opus-science)

v1 (newperiod-stable-stage32-transport-opus-science-v1-20261026, drafted by an opus-science helper session,
never executed) documented the layout, every diff vs the T040 pattern, resources and custody volume; that text
is kept here as REVIEW-V1-DRAFT.md and still applies, except:

- B1 fixed: runner v3 (newperiod-stable-inputs-v3-opus-science-20261026) changes ONE constant,
  source_runner.py:65 `read(aref,2<<20)` -> `read(aref,32<<20)`. The approval must carry the full 57,154-path
  read_scope (7,624,285 B), so v2 refused its own approval before shape(). v3: 36 original + 3 scope-logging
  tests pass; package-source-v3 (98 files, receipt 373538a6) satisfies all runner PINS.
- B2 fixed: kernel plan plan-v40 (floor-only diff vs plan-v39, opus-review PASS on v39 plan) and phase v40
  (stable_source_stage row 21,474,836,480 B). draft-v40/ is build_transport.py output for v40; FALSE templates.
- build_transport.py: only INPUTS/PACKAGE/PINS constants changed to v3. test_transport.py: v40 plan/phase/draft;
  the B1 blocker test became a v3 admission test (>3 MiB approval read OK); the floor test checks that the v39 plan is
  refused under v40 and that a v40 rebuild is byte-identical to draft-v40. 10/10 pass.
- B3 (32-array once operator): being written next as a separate packet (adapted from the accepted singleton
  operator newperiod-timing-cohort-operator-r3-20261025).
- B4 custody route: see the board post.
