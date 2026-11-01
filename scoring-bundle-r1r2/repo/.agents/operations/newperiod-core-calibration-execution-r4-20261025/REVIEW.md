# N-core calibration wrapper r4

Author astra-h3t; independent reviewer sol-h3t. Producer b8265789 and numeric code unchanged. No remote action or actual data read.

The r2 wrapper rejects every real sealed validation tensor because its leaf is a symlink. r4 copies H1 v4 bound_base verbatim and uses it only for .pt/.pth reads inside admitted_reads; raw then bounds and reads the canonical target. A separate precheck rejects relative links: H1 helper itself normalizes them, despite its docstring. The producer retains byte hash verification against the gate. Metadata, predictions and source files still require canonical paths. Current author identities astra-h3t and prior wrapper-packet author55ef are explicitly refused as reviewers, in addition to root.

35 local tests passed (test-run-fixed.txt). Genuine forty-fit fixture preserves sealed graph paths/hashes but moves validation graph bytes to a LINK_ROOT-shaped directory and replaces originals with absolute leaf links. Old r2 refuses the same fixture; r4 completes all40 and matches all independently calculated decision rules. Refusal cases cover relative, chained, ancestor, dangling, out-of-root and directory links, target size caps, and non-tensor aliases. Helper byte identity to H1 is tested. Packet tests stage the source closure, exercise real producer approval and wrapper authority checks, and reject upload/authority tampering.

The first test invocation had an extra imported test collected without its fixture (35 passed,1 collection/setup error); aliasing the helper import fixed it. The complete corrected run passed35. This was synthetic-only; no scientific retry.

The deterministic stage still has97 files. Only execute.py differs from r3; producer, policy, source snapshot and release guard are unchanged. build_stage/packet pins now bind the r4 wrapper. Stage manifest is in sibling newperiod-core-calibration-r4-local-proof-20261025/stage-manifest.json.

Resource and alias evidence limits: existing H1 metadata proves base graph leaf links. I have no established existing stat-only proof for core completion/receipt/prediction/checkpoint aliases. Non-tensor aliases therefore REFUSE; .pt/.pth checkpoint links use exactly the same bounded leaf-target discipline. No wider alias allowance is inferred.

8 CPU/64 GiB/12h and 512MiB tensor/prediction,128MiB metadata,64MiB output caps are unchanged. The 40x4000 validation target byte total and NFS throughput remain UNKNOWN; these caps are not a measured completion guarantee. Full execution/resource admission remains with independent reviewer/root; no stage, submit or actual calibration is authorized by this packet. No calibration inputs were opened to justify resource sizing.
