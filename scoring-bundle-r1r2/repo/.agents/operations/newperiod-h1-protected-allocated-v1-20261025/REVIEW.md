# Protected H1: actual inputs and phased allocated storage candidate

This is a resource/source review packet, not an execution packet. No source has
been staged, no protected job submitted, no protected output captured, and no
protected table contents read. The root capacity directive supersedes the old
whole-campaign 265 GiB admission route. The old builder/package remain immutable.

The new `package/plan.json` binds the independently accepted d30/d60 issue-time
table hashes. Its 113 members retain the reviewed original controller, runner,
producer budget, five H1 kernel files, complete primary source/runtime closure
and twelve job scripts. Both horizons, all 64 build tasks, all six phases and
the full scientific population remain. The plan's 265 GiB remains a declaration
of the original total maximum outputs; it is NOT the proposed concurrent
reservation and is NOT admitted. The future phased dispatcher must carry a
truthful partial-storage admission, as the development dispatcher already does.
Do not invoke the original controller's whole-campaign `admit` or `release`.

## Concrete rows for root's next phase

Run one horizon's phases at a time. Within its 32-element held build array,
release indices 0..15 and then 16..31; do not resubmit or change the shard count,
script, input data, seeds, memory, wall time or numerical kernel. Complete its
assemble/master/export/audit before starting the other horizon. This is a
resource scheduling change, not a reduction of planned scope.

* Stage/held-only controls + operational row: 5 GiB.
* Manifest, assemble, master or audit: 1 GiB producer maximum + 5 GiB = 6 GiB.
* First d30 build wave: 16 x 2 GiB original writer envelope + 5 GiB = 37 GiB
  (39,728,447,488 bytes). This is a bootstrap cap, NOT a measured output estimate.
* Subsequent build wave: own measured row M, dedicated H1 reserve
  `max(0, 32 GiB - M)`, plus 5 GiB. M must be at least
  `max(24 * max_seen_shard_allocated, ceil(1.5 * max_seen_wave_allocated))`.
* Export: original 64 GiB producer maximum + 5 GiB = 69 GiB
  (74,088,185,856 bytes). Export is a singleton with a different output form;
  a compressed build census is not evidence for a smaller export reservation.

The 5 GiB consists of 1 GiB controls and a separately reserved 4 GiB operational
allowance. The 1 GiB exceeds the original two-group control requirement
`2 * 37 * 8 MiB + 32 MiB = 624 MiB`. The 4 GiB is a proposed additional margin,
not an observed allocation or proof that logical and allocated byte caps agree.
Final transport/resource review must establish that the original writer and
producer caps plus this margin cover physical allocation, metadata and logs.
If that proof fails, increase the row or add a separately reviewed operational
bound. The policy's `nominal_phase_hard_cap_bytes` deliberately labels this
assumption; this packet does not certify an allocated hard ceiling.

There is no claimed protected H1 size measurement yet. Do not use development
H1, H3 or timing averages as a substitute. Even a tiny protected measurement
cannot release the dedicated reserve without a new whole-host proof: the
existing shared-floor allowance is already used by the development-wave
incompressible bound. Under the inherited nominal writer cap, the additional
uncovered H1 deficit is zero, because M + dedicated >= 32 GiB. No other-family
reserve, resident-output deletion credit or shared-floor reduction is used.

Rows are incremental to ALL currently issued other-writer rows. Retained
completed H1 files remain resident in fresh df; no byte is credited as freed.
At a phase boundary, root may replace only H1's inactive prospective row after
accepted terminal accounting and complete stat evidence. A new fixed phase and
once authority are required; no runner silently lowers or rebases a row.

## Mechanical evidence and stops

`allocation_policy.py` directly imports the hash-pinned, independently reviewed
`resume_support.allocated_stop`. It replays cumulative censuses of 16 then 32
shards for d30, then d60. A3 compares the just-completed wave's allocated sum
with the fixed live row; A2 compares the full-history maximum-based 1.5x
requirement with that row. Neither the dedicated reserve nor the operational
margin can satisfy A2/A3. The global maxima survive horizon changes. Earlier
logical, allocated, file-count and maximum-file stats must stay identical.

First-wave measurements must be captured once after all sixteen exact tasks
are COMPLETED 0:0 and their original control receipts are successful. The
future finite capture reads only fixed intent/done controls and stats the own
fixed `records/build-NNN/output` trees, emitting counts/bytes, not names or
contents. Both `.pt` and metadata/compression receipts count; use st_blocks*512.
No graph/table/tensor/label/score/prediction payload is parsed. Empty graph
shards still execute and are accepted only through their original completion
receipts; the policy does not drop shards or invent population exclusions.

A2/A3 stops preserve the original capture and all completed work. A successor
replays that exact accepted history under a newly reviewed row; no recapture,
retry, release of completed indices or automatic adjustment. Failed/uncertain
work is a different recovery gate. This policy is pure math, not a validator
of unauthenticated caller-provided evidence. The eventual operator must bind
source/request/capture/assessment hashes, exact actual scheduler IDs, complete
history and independent acceptance before passing data to it.

## Remaining execution integration (explicitly not authorized here)

Reuse original source staging, held submission, full held-identity and script
checks. Build a narrow phased dispatcher in a fresh sibling using the reviewed
development wave transport pattern, with the exact protected six-phase paths
and original runtime binding. It must refuse the original all-jobs release,
bind a partial-storage initial admission rather than claiming 265 GiB admitted,
check exact predecessor controls/accounting, current joint phase, fresh df,
stat-only custody ceiling, board plus all six old directories, and exclusive
authority/step intents before every action. One active H1 wave/phase globally.
An older joint phase must stop; a new phase is never adopted automatically.

The actual package/resource policy need independent review first. Stage/held,
first manifest/build wave, finite terminal/stat capture, and later phases each
need exact reviewed operator bindings and root once authority (or one reviewed
finite chain explicitly covering them). Supply canonical templates and run the
real consuming checks on root-filled bytes. Every execution record belongs in
a fresh sibling. No launch authority/template is represented as ready in this
source/resource packet.

## Validation

Sixteen synthetic tests exercise the real shared A2/A3 implementation, A3
overflow, A2 maximum growth, rebasing from unchanged evidence, global maxima
across horizons, changed historical stats, missing/reordered histories,
nonterminal/outcome failures, malformed stats and full 64-task coverage. The
actual generated plan validates with the original controller and its complete
source/job map is checked locally. No remote or research-data test was run.
