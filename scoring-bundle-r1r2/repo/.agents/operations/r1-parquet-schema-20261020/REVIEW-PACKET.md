# Sequential review: one Parquet footer-schema follow-up

Author /root; separate reviewer /root/recovery_independent_review. Root pauses all
implementation while review runs. No delegation. Review local source and captured
metadata only; the reviewer must not open the actual target or launch the attempt.

Purpose: target-resource review B5 found that the completed header audit omitted
column paths, logical schema, nesting levels and encodings. This follow-up adds
those fields for its sole 5,429,410-byte Parquet target. No Torch/NPZ files, member
payloads, row pages, dictionary pages, decoded rows, statistics API or statistics
values are read. Footer bytes can contain encoded statistics; that specific fact
is explicitly permitted in the spec, as in the prior header execution.

`common.py` and `audit_headers.py` are exact copies of the already reviewed header
execution modules. Their old array-launch/admission functions are unused. The new
runner calls only common identity/hash, bounded header-read, independent-review,
closed-registry and durable-write helpers. `schema_headers.py` uses the same exact
trailer/footer ranges and synthetic metadata-only PyArrow file as the prior reader.
It adds schema and encoding fields without calling a row or statistics API.

Review the exact spec.json/source-pins.json. The sole target is selected unchanged
from `r1-label-header-audit-20261020/execution-v2/candidate/targets.json`, whose SHA
is 458ec9899439d99228deb41f31e1ffeed3a3ef2ab90e30d5faabbfc72dd3770c.
The existing exact producer/container admission is SHA
3c287baf7f5dec89c2430fc0939df3430a86f2d7ac7bd583d5935fcb54eb8421;
its local copy is in that candidate directory. The new spec binds 29 captured
PyArrow implementation files plus the executable digest, Python and PyArrow
versions. These come from runtime-synthetic-capture-v1.json in the target-resource
directory; that capture used only invented arrays and establishes no resource admission.

Runner: 8 GiB hard+soft AS, 600-second CPU/wall ceilings, Arrow CPU/IO thread counts
one, target at most 8 MiB, cumulative footer ranges at most64 MiB, metadata output
at most1 MiB, at least1 GiB output free space. It refuses an existing attempt root;
the exclusive directory/started receipt survives failures. It verifies authority,
runtime/source bindings and closed R1 before target access, then hashes the same
open inode before footer reading and verifies stable identity afterwards. Source
and closed-R1 checks repeat before completion. Failures contain only exception type.
SIGKILL/AS/alarm failures may leave only the started receipt; never automatically retry.

Prospective execution, only after the review grants the exact footer authority:

1. Root creates the fresh transport directory named in spec.json exclusively and
   transfers only the four source files, spec.json and the reviewer's approval.json;
   verify remote SHA256s before execution. Refuse either fresh root already existing.
2. Invoke the existing cluster Python on <BATCH_HOST>, with `-I -B`, the exact
   transported run.py and `--spec`, `--spec-sha256`, `--approval`,
   `--approval-sha256` external bindings. Set OMP/MKL/OPENBLAS/POLARS thread variables
   to1. No Slurm array or repeat of the completed header audit.
3. Capture only started/complete/failed/schema receipts and verify their hashes.

Synthetic validation:13 tests PASS; source/test Ruff PASS. Tests guard actual file
read ranges, nested list/struct names and encodings with dictionary both on and off,
no statistics/value emission, budget-before-read, bad footer, successful exact target
identity, repeat refusal, pending/self-review/statistics/source/runtime/label/closed
admission refusal before target access, and failed hash preservation before footer access.

Please save reviews/astra-parquet-schema-review.txt plus a hash-bound verdict.
If satisfied, create approval.json with passed=true, actual reviewer/model identity,
scope=`r1-single-parquet-footer-schema-v1`, exact spec SHA, all common.DENY flags false,
statistics_api_authorized=false, and exactly these narrow permissions true:
opaque_target_hashing_authorized, footer_structure_authorized,
encoded_footer_statistics_bytes_authorized. Explicitly deny resource admission.
This never approves R1 scoring, labels, forecast decoding, freeze/seal, N/protected2026,
fits, prediction, or any retry. Do not author fixes.
