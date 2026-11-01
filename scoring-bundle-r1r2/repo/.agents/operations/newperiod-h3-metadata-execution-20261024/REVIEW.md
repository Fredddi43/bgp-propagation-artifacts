# H3 metadata execution: specialization of the reviewed timing/H1 metadata execution (author Opus f4d75bb1)

**Code.** The diff against timing (reviewed) is:
- runner.py: 40 lines;
- finite_io.py: 4 lines;
- build.py: 16 lines;
- file_limits.py, reviewed_budget.py and construction/{common,job,runtime_verifier}.py: byte-identical.

Changes:
- Namespace `data-custodian/h3-metadata-publication-v1`, the H3 kernel and plan kinds, and H3 guard snapshot 3a2b1ec7.
- The author identities (`/root/opus_implementation` and session <SESSION_ID>) are excluded as reviewers.
- **The stage is per operation** (`control-draft` / `control-finalize`). H3 needs two host operations: draft reads
  staged sources, then finalize publishes. Each control tree stays immutable.
- Kernel callbacks gain `log_read`, so every staged source read is logged before open; the kernel does this via
  the Sources seam.
- The plan's `source_scope` (staging receipt + limits) must equal the kernel plan, and the approval must name it.
- The finite inventory replaces the timing cohort/commitment with `legacy_coverage`.
Tests: 20 passed. They cover authority/resources, the per-op stage, the finite reader, packaging (h3-guard, kernel
modules), worker dispatch with the large shared log, and the guard loading before the kernel.

**Actual draft binding** (`actual-binding-v1`):
- `assemble_draft.py` builds `draft-package-v1` with 182 files and a 19-entry finite inventory. The sizes come from
  accepted local captures, and the timing-only entries are filtered out. The kernel plan is the real one from the
  publication packet's actual-local-v1.
- Resource request `resource-request.json`:
  * binding 8abcf02a;
  * 8 CPU, 128 GiB RAM, 4 h;
  * output 512 MiB per file / 2 GiB total, 250 GiB floor;
  * staged source scope: data 1.46 GB / history 86.7 MB closures; 14,787 summaries; 4 x h3.prepare.
- `transport_packet.py` is the timing stage/held packet (30 changed lines), with draft op, control-draft and
  explicit min free bytes >= 456 GiB. 5 tests passed.

**Still required, in order:**
1. Kernel/coverage code PASS.
2. Exact draft operation approval, naming source_scope.
3. Root fresh joint storage admission.
4. Stage/held review and release.
5. Actual draft capture and independent draft review.
6. The finalize packet (publication review).
