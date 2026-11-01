# v2 corrections for H1-ALLOC-PROSPECTIVE-1 and H1-ALLOC-WAIT-1

Fresh immutable successor; v1 remains unchanged and unexecutable. Config exact
bytes, stat-only scope, source/model/phase/held/restriction refs, all12-held barrier,
310s schedule and two observations remain unchanged. No probe or remote action.

Every observed own object, including directories, and shared custody object must
satisfy allocated<=2*logical+1MiB. Stable over-model allocation fails closed.
Current physical charge is actual own allocated bytes plus conservative2GiB shared
basis. Still-required physical writes are added without any resident credit:
manifest=2*1GiB+129MiB; boundary controls=2*256MiB+128MiB;
task/logs=2*32MiB+8MiB; shared growth=2*64MiB+1MiB; existing-directory
metadata growth=1MiB per existing directory. All are explicit separate charges.
Current+all prospective charges must fit the same20GiB row. Controls1GiB,
operational4GiB, manifest1GiB,6GiB logical and8192-object limits remain enforced.
This does not enlarge a row or assert a backend theorem. Fixed small-name directory
updates under the finite first-boundary object caps are conservatively charged
again; no reuse of existing metadata slack is assumed.

Wait uses one remaining-time calculation per iteration, breaks if nonpositive,
otherwise sleeps min(30,remaining). Deterministic deadline-crossing and expired
clock tests perform no real sleep. Exactly two samples,310s requested interval,
and >=300s actual interval/last-own-write checks remain.

20 tests pass including the exact stable17GiB/329-byte counterexample: old v1
returns passed, v2 refuses. A separate insufficient-residual-budget case refuses;
all future components are asserted present. Shared-log over-model is refused.
All earlier14 scope/zero-append/identity/alias/age/barrier checks still pass.

# H1 own-allocation and delayed stability, v36, zero appends

Exact accepted held12 snapshot57269c2e is the starting evidence, not an allocation
measurement. This packet has no new remote actual and no independent approval.
ROOT may run only after sol-h1 operation review and fresh once; detached launch.

Two operations: (1) exact12 scontrol-show metadata validates all original held
identities/resources/chain/full32 arrays with accepted array-parent compatibility;
(2) one <BATCH_HOST> Python -I -S -B process takes exactly two finite metadata
censuses,310s apart, outputs one bounded JSON pair and exits. ROOT explicitly keeps
all12 H1 jobs held and forbids other H1-namespace writes throughout. Both calls
rescan phase/control/source hashes beforehand. No automatic retry or repeat sample.

stat_capture.py contains no open/write/mkdir/logging/import of a custody logger.
Its only inputs are bounded stdin config, lstat/scandir/path-resolution metadata,
statvfs, clock and bounded findmnt metadata. It never reads source/payload/job-log
contents. It writes no remote file. Zero shared custody appends, including during
the310s wait. This is compatible with root-h3-v36-operating-adoption-v1 restrictions;
H1 first-manifest release remains forbidden until H3 capture acceptance and a new
explicit root operating clearance are bound in the separate release packet.

Closed namespace:124 exact required regular files (122 staged source/control +
2 claim intents),14 directories and at most24 exact own scheduler log names. All
expected source/control sizes come from the immutable local source or actual
approval/review/claim encoding. <=256 total objects; no extra outputs or directories,
symlinks, special files or regular hardlinks. Existing source hashes remain those
accepted at stage; this stat-only census does not claim a new content hash read.
Optional own logs are <=4MiB per stream; all jobs held, no task payload allowed.

Both snapshots must match exact same export/options and current models/results
floors. Every own object's dev/ino/mode/link-count/owner/size/mtime/ctime/st_blocks
must be identical. At least300s between first completion and last start (both wall
and monotonic clocks), and >=300s since newest observed own mtime or ctime. Directory
metadata is checked again after enumeration. This proves observed own stability
under ROOT's cooperative barrier, not absence of unobserved writes or a backend
theorem. Remote480s alarm,256MiB AS,2MiB stdout/64KiB stderr transport,500s deadline.

Shared log is stat-only, exact dev80/ino5636854, single-link/canonical, never reset,
shrunk, rotated or deleted. Other authorized H3 appenders may change its size and
allocation; global shared-log stability is NOT asserted. Each sample requires
logical size+64MiB <2GiB and observed allocation<=2GiB. Charge2GiB irrespective of
observed bytes, never credit resident allocation to df or borrow another row.

Reconciliation: retained own controls plus prospective256MiB boundary controls
must fit controls1GiB. Shared basis2GiB + existing own logs +32MiB future task/log
allowance fit operational4GiB. First-manifest output retains1GiB. Full logical
ceiling6GiB, object ceiling8192, accepted empirical2L+N*1MiB=20GiB. Count current
objects +128 prospective controls +129 output/dirs +8 task/log objects below8192.
Observed own allocation + shared2GiB basis + every prospective physical allowance must fit20GiB. All prospective
writes stay inside these components; no existing-allocation subtraction credits.
Build/native tensor/compression/export transfer is not admitted. All64 builds,
both horizons and14 boundaries remain planned.

20 tests use synthetic temporary metadata and in-memory approval fixtures only:
real census/accounting, authorized shared growth, unexpected outputs, symlink,
hardlink, missing/wrong-size source, short delay/recent write, inode/size/time/block
changes, custody rotation/shrink/overflow, export/floor changes, no-open/no-write
source proof, real preparation/false canonical once refusal, real full check and
missing root barrier refusal. No fake signed review or authority is persisted.

Required reviewer scope: h1-allocation-stability-zero-append-v1; passed independent
identity, exact request and operator_sha256. ROOT uses real operate.encoded and
--check. New actual requires independent allocation/delayed-stability acceptance
before the separate exact52529638 first-boundary release request can be finalized.
