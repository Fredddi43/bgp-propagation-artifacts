# Bounded native-parser source/control metadata capture

Purpose: inspect the already exported parser implementation whose exact historical SHA is absent from local git, and the already named route-views.linx task map. Task14550 is already captured (30148763); its archive URLs identify that collector. Do not recapture task or scientific payloads.

Exact scope is four existing source files under corrections-20261016/code, externally bound by docs/paper/corrections-2026-10-16/exported-code-verification.json, plus corrections-20261016/crossday-remaining-order/route-views.linx.txt explicitly named by crossday-final-submissions.json (job51970979,1590task map). The task map's current hash is recorded, not invented as a historical hash. No directory scan, inferred payload path, package import, parser execution, job launch, raw archive read or reference traversal.

Read-only regular canonical files with O_NOFOLLOW; stable descriptor identity/mtime/ctime/size,2MiB per file/8MiB total,120s remote deadline/150s client timeout. Source hashes must equal the exported manifest. Task map must consist solely of decimal task indices. Output is one exclusive local gzip capture; failure preserves the claimed output and grants no automatic retry. Captured source is never executed.

This can run while R1 evaluates: no scientific input, labels, shared runtime mutation or evaluation output is touched. Metadata capture cannot prove historical use of the current source/tree or parser binary. After capture, assess exact parser failure semantics and whether map/known job evidence links14550; if it does not, report the remaining linkage rather than manufacturing provenance. No archive reacquisition or scientific admission is authorized here.

Root command, only after separate review of this exact packet:
`.venv/bin/python -B .agents/operations/newperiod-parser-linkage-metadata-20261023/capture.py --output .agents/operations/newperiod-parser-linkage-metadata-20261023/capture.json.gz`

Synthetic tests: `.venv/bin/python -B -m pytest -q .agents/operations/newperiod-parser-linkage-metadata-20261023/test_capture.py` —8passed. Includes actual local isolated interpreter reading synthetic source without executing it, digest/malformed-map/symlink/directory/budget/scope failures, and all production paths/hash bindings reproduced from existing local records.

Author codex `/root/remaining_work_audit`. Independent code/scope review pending. No host read has occurred.
