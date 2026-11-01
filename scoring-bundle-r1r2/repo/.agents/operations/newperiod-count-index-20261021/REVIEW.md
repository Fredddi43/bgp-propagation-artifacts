# Pure development count-source index candidate binder

Author /root/reference_reuse_recovery. Code-only review, no production metadata read,
cluster action, protected access, index admission or execution requested.

Existing independently reviewed count_coverage.development consumes
newperiod_count_source_index_v1 but has no actual ownership-index producer.
bind_index.candidate now joins caller-supplied, hash-bound JSON captures: two exact
manifest populations/panels, source-audit-to-staging identity, canonical staged
summary/membership references, explicit event ownership/merge refs and acquisition
receipt refs. No globs, basename heuristics or inferred provenance. It reads no path,
opens no network and never gets membership/archive payload buffers. Missing metadata
becomes exact path+digest gap evidence; absent event mapping remains a named gap.

Candidate ALWAYS passed=false, execution/protected flagsfalse and independent actual
admission pending. It cannot satisfy the existing coverage consumer. It does not claim
archive continuity, ownership completeness, actual canonical path/symlink stability,
source correctness, R1 release or current development sealing; existing full coverage
validator and separately reviewed actual index admission must establish those later.
Capture hash checks prove only supplied metadata identity. Actual prerequisites remain
all14pending in upstream spec; readiness-gap.json copies that unchanged status and pins
it. No actual development metadata was fetched/decoded and no actual index was created.

21 synthetic tests/RuffPASS: full exact join without admission; no path/payload reads;
six exact missing-reference cases; no invented event mapping; eleven identity/cohort/
source/ownership mutations rejected. Request separate CODEPASS or concrete findings.
This review authorizes no actual capture, staging, protected read or execution.

Staging receipt JSON has a separate 64 MiB bound because the existing schema capture
records 32,137,259 bytes; all other metadata remains bounded at 16 MiB. A synthetic
17 MiB receipt regression verifies that the real metadata size is supportable.
