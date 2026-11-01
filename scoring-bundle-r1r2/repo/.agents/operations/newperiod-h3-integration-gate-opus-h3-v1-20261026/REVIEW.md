# H3 integration gates v1 (opus-h3) — review packet

**What:** one `core_fit` development integration gate per H3 group (mixed7/ris7 x d30/d60). These fill the
four `core_gate<panel>_<h>` slots of the reviewed H3 forty-fit client (`newperiod-h3-client-r2-20261023`,
PASS_CODE_ONLY). Nothing in the client produces them; the client README says they must be "separately reviewed
panel-audit-bound integration gates".

**Shape (what the client checks):** `run_package.preflight` needs `approved_operations==['core_fit']`,
`manifest_kind=='development'`, `panel_audit==` the accepted audit summary; `forecast_release.authorize(core_fit)`
needs the manifest entry, task/population/release, a passed source audit that binds construction, history root,
history digest and **signature digests**, and the boundary audit; `forecast_development.fit` reads
`source_inventory_path/sha256` (the H3 construction status inventory, whose `audit` is that summary;
`h3_adapter.checked_inventory`).

**How:** `h3_issue_gate.py` starts from the published construction gate of the group (the one the audit already
authorized for `supervised_graph_build`), keeps its task/population/release/boundary/data/history/source-audit
fields (same set as `h3.py:61-63` gate template + source audit), and sets the `core_fit` fields. It fails closed
unless: the construction gate is this manifest's construction (`source_manifest_sha256`/`construction_manifest_path`),
the source audit's signature/history digests and collectors equal the manifest's, the audit binds this manifest with
every check true and exact counts, and the inventory binds this manifest + audit. Then the real
`forecast_release.authorize(core_fit)` from the staged audit-v5 guard copy (snapshot 3a2b1ec7, every imported
bgbench module hash-checked, stdlib only) runs on the gate under a temporary name; only on success is it
hard-linked to its final name (no replace). Exports path/sha/counts only. **No custody append** (same as the
reviewed audit jobs that read these files).

**Risk to know:** if the published construction source audit's `signature_source_digests` differ from the built
development manifest's, the issuer refuses (one consumed once, no output). Then a separate integration source audit
would be needed.

**Run (root, per group, after review + ROOT once):** `run_issue.py <request> <request-sha256> <fresh records dir>`.
Program travels base64 in argv; request on stdin; host <BATCH_HOST>, gate-private venv python `-I -B`.

**Tests:** `test_h3_issue_gate.py` 14/14 (real local guard copy in a fresh `-I -B` process: positive + no-replace,
request/content/signature/inventory refusals, changed guard snapshot, stdlib-only). Synthetic data only.

**Not covered here:** storage row (gates ~2 MB each; needs a phase row), the refit execution package itself.
