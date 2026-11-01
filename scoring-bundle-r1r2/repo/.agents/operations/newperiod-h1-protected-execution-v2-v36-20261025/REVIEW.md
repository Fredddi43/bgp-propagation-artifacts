# v2 correction: H1-STAGE-CUSTODY-PER-SUBMIT-1

Fresh successor to frozen v1; accepted empirical-inputs.json and empirical-model.json
are byte-identical. No re-probe, remote call, protected read or authority consumption.
The only staged source change from v1 is controller.py. All scientific inputs,
resources, job scripts, guard, runner and boundary logic are unchanged.

After the exclusive subgroup claim, controller.submit requires a callback before
EACH of twelve individual sbatch calls. The callback performs a fresh stat-only
custody check, exact export/options check, both current v36 floors, source hashes,
and exact own claim verification on <BATCH_HOST>. Each following <SUBMIT_HOST>
SSH invokes one original controller.command directly. No filesystem or Python
work runs on <SUBMIT_HOST>. Batched submit mode is disabled; batched metadata
readback remains. Both transport calls recheck phase, all acknowledged board/old
posts, operator, request, package source closure, independent controls and hashes.

Each actual ID is written with exclusive creation, flush and fsync before the
next preflight. A failed gate, malformed ID, failed or uncertain transport stops
without retry; previous receipts and raw bounded metadata survive. The outer
once is consumed before the first remote action and records STOPPED on failure.
All jobs remain held with unchanged original resources, full32 arrays, no-requeue
and actual afterok predecessors. There are29 remote calls: initial preflight,
stage, staged preflight, claim, twelve(preflight + single submit), held readback.
Remote object accounting is unchanged; additional receipts are local controls.

Regression uses the real controller.submit and real preflight.main against only
synthetic temporary metadata. It proves12 stat/submit pairs and checks immediate
receipts before every following call. At each of12 positions a custody-size
change refuses that and every remaining submit; prior IDs remain. Changed claim
and uncertain scheduler output stop too. No genuine review/authority is fabricated.
All35 tests pass, including the previously accepted29 tests. False ROOT template
remains unissued; final genuine source/profile/operator approvals and ROOT bytes
must pass real --check before ROOT detached execution. Route sol-h1.

# H1 protected guarded package and held-only once packet v2, v36

Author astra-h1; route sol-h1. No approval is authored here. No remote actions,
new probe, protected input body reads, stage, job submission or release occurred.
All templates remain false/unissued. Independent empirical/model/source/operator
review and fresh ROOT once are prerequisites. ROOT launches detached only.

## Exact requested next action

Review the empirical fixed-writer transfer, coherent guarded source and one
stage/submit-held/readback operation under issued v36 (64b304bc). It reserves
20 GiB exclusively for bounded controls and the FIRST d30 manifest boundary.
Current models/results minima are 535184697344 / 45231374336 bytes. Operator
checks fresh free space and refuses any newer issued phase, changed controls,
consumed namespace or absent independent model acceptance. All twelve jobs are
submitted held; this operator contains no task-release call. Stage approval is
scientific source/scope approval, while the runtime boundary gate requires a
separate exact ROOT release binding before protected input reads.

After independent held-actual acceptance, bind real IDs into the first manifest
request in a fresh successor, obtain separate operation review and ROOT once,
then release only d30 manifest. Its release transport/actual packet is a separate
next item requiring the held IDs; this stage packet does not claim to provide it.
All64 K500 builds, both horizons and14 serial boundaries remain planned. The old
265GiB whole-campaign admission/release functions and direct controller CLI are
disabled. Build82GiB/export146GiB capacities remain unadmitted, unchanged.

## Empirical model evidence and transfer argument

empirical.py checks the exact independently accepted synthetic probe output
metadata. Partial traces retain their failed-execution provenance. The accepted
later stat completion supplies the missing >=300s sample; it does not retroactively
mark the original failed probe successful or authorize cleanup/row retirement.
No sample was repeated for this packet.

All3748 individual file observations (including3653 active write samples) fit
A<=2L+1MiB. Maximum observed A-2L was510 bytes; largest observed directory
allocation8704 bytes. The 0/60s censuses occurred6.686/66.474 seconds after last
fsync. The accepted delayed sample spans3053.2238..3053.2261 seconds and retains
all exact file identities/sizes/mtimes. Total observed allocated maximum was
3829937664 bytes. Sparse/preallocated attributes are not treated as backend
physical preallocation or as a future compression guarantee.

The multiplicative2 and additive1MiB are deliberately conservative operational
margins, not separately fitted coefficients. They are applied once to the WHOLE
prospective logical envelope and every prospective object, including controls,
logs, directories and temporary creations. The 1-byte ratio is not used to
estimate a multiplicative factor. At L=6GiB and N=8192, 2L+N*1MiB=20GiB.

Transfer proposed here is narrow: exact same NFSv4 export and mount options,
cooperative single-writer fresh namespace, fixed bounded source/control writes
and the first manifest's ordinary immutable JSON write. The probe used random
incompressible regular writes across sizes through2GiB and showed delayed
allocation; first manifest files are capped512MiB and aggregate1GiB. Stage source
and JSON controls use regular file creation/fsync. No untested native tensor,
compression workload, build16, export or future boundary is admitted by this
model request. Native Torch/old compressed writer compatibility is source-test
coverage only, not empirical model transfer to those future workloads.

This remains an empirical model, with unobserved active peaks and later backend
behavior uncertainty. A filesystem theorem is not claimed. Exact mount identity
must match the observed target/source/fstype/options before each stage/submit
operation; if it differs, stop. Shared df variation is not interpreted as own
allocation. The current free-space floor and independent model review are
substantive preconditions; model.observation_checks_passed is not admission.

Before any later boundary, require independently accepted finite terminal
allocation census, including first-write/control/log accounting and delayed
stability observation as specified by the independent profile. Do not credit
resident bytes back to df; stop on overflow/alias/change and seek a reviewed
successor. The exclusive shard27 18GiB row and all other families' rows remain
untouched. Cleanup belongs to astra-v28's separately reviewed authority.

## Guarded source and exact accounting

Generated package has119 source files,122 staged files after adding plan,
scientific approval and review text, plus7 source directories and8 additional
namespace/record objects budget:137 stage objects. Actual source bytes1435669;
plan size is recorded in accounting.json. Stage enforces32MiB decoded aggregate,
64MiB wire, <=256 objects,512MiB process AS,150s alarm and32MiB per-file limit.
Only declared immutable source/control files are staged. The outer bounded
transport caps each stdout2MiB/stderr64KiB while receiving; any uncertainty
consumes the once authority. Full stdout is source/scheduler metadata only.
No protected stderr tails are collected.

Claim has exactly five objects: claims directory, two group directories and two
finite intent JSON files. Each intent serializes only exact plan ref and two
literal group names, below4096 aggregate bytes. All12 sbatch commands preserve
original CPU/memory/time/no-requeue/afterok/full32-array specifications; every
job remains held. Actual readback validates identity/resource/dependency fields
using the real existing held_job checker. No original storage_admission call
is used to pretend the whole265GiB campaign fits.

First task has at most8 record/log objects: parent intent, worker intent,
stdout/stderr, done, failure and two Slurm logs. Parent/supervisor logs cap4MiB
each, done8MiB; intents/failure contain fixed finite control fields (<4096 each).
32MiB logical allowance covers their sum. Slurm-daemon output uses the fixed
bootstrap/transport assumption explicitly; Python RLIMIT is not asserted to
limit an arbitrary Slurm daemon. A failed task never authorizes another boundary.

Source controls have1GiB logical budget; operational4GiB includes conservative
2GiB shared-custody allocation basis, task/control exchanges and remaining margin.
Prospective boundary controls <=128 objects/256MiB; first manifest output guard
<=1GiB, one output file and<=128 created directories. The first-boundary object
count is far below8192; the declared ceiling is conservative, not an unbounded
source assumption. Remaining per-boundary counts for later phases are not
production-admitted under v36. Their eventual composer must re-prove them.

Runner integrates exact reviewed guard0ccf41d6 AFTER original Budget/FileLimits
hooks and wraps the existing torch.save wrapper. It calls guard.finish before
original reconciliation. The per-boundary binding is required BEFORE original
protected job.input_checks. Scientific construction/kernel sources, group inputs,
resources and all12 generated job scripts are byte-identical to FSIZEv2; only
operational runner/controller plus boundary/guard/checker source changes.
Controller can still stage and submit held through the reviewed once wrapper.

## Canonical bindings and remaining gates

Plan/request/boundary inline review/profile/ROOT documents use the runtime
module's compact sorted JSON plus newline. The issued phase is verified using
its REAL indent2 sorted JSON plus newline (64b304bc), while partial_dispatch's
joint_phase_sha256 separately checks its canonical semantic encoding. Do not
replace one hash with the other. Stage ROOT authority uses stage_once.encoded
(indent2 sorted newline). Root must call its real --check on final exact bytes.

The runtime binding authenticates all plan/request/profile/review/ROOT hashes,
requires independent reviewer identity, exact phase rows/history/targets, and
checks actual SLURM task membership/restart before opening protected inputs.
It is a loader/checker, not the missing future release transport. A path with no
exact immutable records/boundaries/<ordinal>/binding.json cannot execute. Future
boundaries need their exact independently reviewed history/A2A3 and capacity,
never reuse the first-manifest binding or release a parent array ID.

stage_once.py --prepare performs real local request/current-phase/source and
empirical replay checks without authority. Full check path is covered using
in-memory synthetic review/root fixtures; no fake signed approval/authority
files are persisted. False template must fail --check. Production --check
cannot pass until genuine independent reviews and ROOT authority exist.
