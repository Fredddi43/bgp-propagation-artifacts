# Separate protected H3 custody budget proposal

Author astra-storage2; independent review requested sol-h3t2. ROOT0845 requested
this proposal. All drafts remain false and historical values remain historical.

Reserve separate development160MiB and protected64MiB envelopes, combined224MiB,
with unchanged original dev baseline1499170426/device80/inode5636854, unchanged
absolute2GiB ceiling and64MiB headroom. No prior future slot or failed byte is
credited. Existing nine writer rows copied verbatim for root reconciliation;
protected stage appends zero. The existing protected category4MiB is not treated
as capacity for the new64MiB category.

Baseline+224MiB=1734051450, below2080374784 absolute headroom threshold.
Using the pinned historical530523 observed growth and84529704 existing future,
adding a full67108864 protected future yields152169091 total growth. This is
15603069 below the existing development160MiB aggregate guard. This arithmetic
is not fresh state, a whole-campaign admission, or proof of generic logger caps.

The initial manifest has two bounded65536B scope appends plus two generic logger
calls. Existing generic logger has no encoded-record bound; complete generic
callchain and capture overlaps remain unproven. Own64MiB is a planning reserve,
not an established per-campaign hard quota. Future reviewed source must preserve
explicit owner accounting and reconcile all actual actors/current observations.

Required source follow-up before coexistence: stage/preflight/wave/Guard old64MiB
shared checks must consume the new common contract; active development160MiB
checks remain binding until separately superseded (or complete concurrent
projection remains below160MiB). No independent caps are simply added without
checking existing shared consumers. No template can waive these stops.

Separate root all-host current roster/interval/adoption and same-log metadata are
required. Runtime native allocation, daemon evidence, retained inputs/read scope,
actual24held identity and per-boundary once review remain required. This packet
contains no remote query, protected input, real root adoption or execution.
