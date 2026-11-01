# Typed40 local once projection

Author: astra-final, session <SESSION_ID>.
Designated reviewer: sol-final. This packet is preparation only.

The source verdict acc64689 accepts projector98711db8 and the original local
ledger-copy provenance. This operator supplies the missing execution boundary:
one exact local87261-byte copy9b4388e5, one fixed argument object0641c564, and one
fresh sibling records directory. It does not reopen remote ledger or children.
The unchanged pure projector is compiled from the exact reviewed source bytes.

`prepare.py` emits request and false independent-review/root/snapshot templates
using the real `once.encoded`. Their flags do not approve any action. Root must
obtain a genuine exact machine execution review, then write a fresh actual root
authority and complete current snapshot. All eight control directories are bound:
the required board plus five legacy directories, and the two additional legacy
directories used by earlier capture operators. ROOT-/REVIEWER-/AUTHOR- and older
OPUS-REVIEWER-/OWNER- posts are acknowledged. Only an exact four-key route post
pointing to this authority is omitted to avoid a circular hash; extra fields or
another authority cannot be omitted. No filled snapshot is pre-approved here.

Use the real encoder for all actual documents. Root can call `once.snapshot()`
to assemble its acknowledged map immediately before issuing the once authority;
this reads only local control posts. The exact minimal route kind is
ROOT_GO_CORE_TYPED_LOCAL_PROJECTION_ONCE, addressed to astra-final. A current
snapshot and immutable actual review are required even for the control-only check:

```
.venv/bin/python -B .agents/operations/newperiod-core-typed-local-once-astra-v1-20261026/once.py --authority <absolute-genuine-root-authority.json> --check
.venv/bin/python -B .agents/operations/newperiod-core-typed-local-once-astra-v1-20261026/once.py --authority <absolute-genuine-root-authority.json>
```

`--check` never reads or hashes the ledger. Execution requires the fixed records
path to be absent, creates it exclusively, fsyncs it and the CONSUMED marker,
then rechecks authority, source, independent review, provenance and all current
posts. A durable read-intent precedes the only actual ledger read. O_NOFOLLOW,
canonical path, regular/single-link status, exact87261-byte limit, same descriptor
identity and final pathname identity prevent alias substitution. Exact SHA is
verified before JSON parsing. Failure consumes the attempt permanently; there is
no retry, refetch, fallback path, shell, network, subprocess or child expansion.

Outputs are CONSUMED.json, read-intent.json, typed40.json, result.json and, on
failure, failed.json. Each is at most1MiB; at most5 files gives a5MiB logical local
records ceiling. Exact project JSON bytes use sorted keys, allow_nan=False and a
single newline, matching the projector's output size calculation. The completion
record marks actual_projection_accepted=false. Independent actual acceptance is
still required before any owner consumes the mapping. Actual records do not yet
exist and no authority has been consumed by this author.

Checkpoint/fit-receipt/completion hashes remain null. Rule/library/query mappings
remain incomplete. No raw ledger export, argv/settings/manifests/gate bodies,
labels, prediction, scores, remote operation, custody append, INET allocation row
or scope reduction is added. G1/all400 and all downstream gates remain separate.

Nine isolated synthetic tests cover exact bytes and output whitelist; actual
check without ledger read; consumption and intent before read; failed-hash
consumption/no repeat; changed board before and after consumption; narrow route
exception; false/bool/changed authority and author-as-reviewer refusal; symlink,
hardlink and noncanonical authority refusal. Synthetic authorities exist only in
temporary test directories, never as real ROOT-/REVIEWER- posts.
