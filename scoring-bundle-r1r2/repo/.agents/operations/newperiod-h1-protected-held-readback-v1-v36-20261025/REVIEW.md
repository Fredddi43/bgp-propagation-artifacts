# Consumed stage-held disposition and read-only held-readback successor

Author astra-h1; independent reviewer sol-h1. No self-approval, new remote action,
job submission, stage, release, scientific payload read or retry occurred here.
Original execution package and actual records remain unchanged.

The v36v2 once authority94ec97de is consumed and STOPPED. Its29 transports returned
rc0 with empty stderr: stage matched the exact source closure; all12 original
held sbatch commands succeeded, each preceded by its required fresh metadata
preflight; every actual ID was retained. The archived scheduler readback has all12
PENDING/JobHeldUser/Priority0, no-requeue/restart0, original resources and full32
build arrays. This is archived evidence, not a fresh scheduler-state assertion.

The old controller.held_job refuses exactly assemble52529641 and52529658 with
"Held dependency differs". Their respective predecessors52529640 and52529654 are
the same horizon's full32 held build arrays. Slurm reports their dependency as
`afterok:<array-id>_*(unfulfilled)`; scalar predecessors retain the original form.

held_check.py changes only compatibility checking locally. check_all establishes
the original complete12 unique jobs, ordered phases and exact predecessor chain,
then validates each with the unchanged original held_job. Only for assemble,
the exact dependency token `afterok:<expected-parent>_*(unfulfilled)` is converted
for that old checker; returned fields restore the original spelling. All original
scheduler evidence remains byte-identical. No general suffix stripping, wildcard
regex, per-task dependency, wrong parent, fulfilled/afterany/multi-dependency or
non-assemble array dependency is accepted by this exception. Original scalar
forms remain accepted. The staged controller/plan/source hashes do not change.

operate.py requests one fresh scheduler metadata operation: one SSH to
<SUBMIT_HOST> containing exactly12 `scontrol show job -o <exact-id>` commands.
There is no remote filesystem/Python work, stage, submit, cancel or release. The
command is byte-identical to the archived readback command. This is a separately
reviewed read-only successor under a fresh authority, not resuming/retrying the
consumed stage operation. ROOT must issue canonical bytes matching
operate.encoded and run the real --check, then launch detached as usual.

The new once requires independent operation review with scope
`h1-protected-held-readback-v1`, passed/independent reviewer identity, exact
request reference, operator_sha256 and checker reference. It binds original
consumed authority, consumed/STOPPED markers, all archived actual metadata,
original source/plan/approval/profile and new disposition/checker. Current issued
v36 and all board+old6 ROOT/REVIEWER/AUTHOR controls are rechecked before the sole
call; a newer phase requires a reviewed rebind. The only snapshot exception is
an exact minimal ROOT_GO_H1_PROTECTED_HELD_READBACK_ONCE notice to astra-h1 for
this same authority. Request/operator/source/control changes fail closed.

New records are a fresh sibling. Consume before the remote call; stdout<=2MiB,
stderr<=64KiB, deadline120s; failed/uncertain transport or parsing records STOPPED
and never retries. No log tail or protected body is read. A custody stat is not
needed for this read-only scontrol operation: there is no submit or custody write.
The authority template remains false/unissued. Synthetic full-check fixtures are
in memory only, never signed or written as real approvals.

17 focused tests cover original two failures, all12 successful archived checks,
wrong task/parent/type/extra dependency and duplicate fields, non-assemble form,
resource/held/restart/array safeguards, missing or wrong chain, canonical false
ROOT rejection, full independent check with in-memory fixtures, and exactly one
mocked read-only call on success/failure with consumption and no retry.

After execution, independent held-actual acceptance remains mandatory. The first
d30 manifest release is a distinct actual-ID boundary operation with separate
review and ROOT once. All64 builds, both horizons and14 boundaries remain intact;
v36's20GiB first-manifest envelope admits no later build/export or whole campaign.
